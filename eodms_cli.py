"""eodms_cli (non-interactive) focused on eodms-py STAC/DDS workflows.

This module provides the current command-driven CLI entrypoint with three
core flows:
- `search`: STAC catalog discovery, queryables, and GeoJSON export.
- `process`: OGC Processes list/inspect/submit/job workflows.
- `download`: STAC asset, DDS UUID, and legacy RAPI order-item downloads.

Legacy prompt-driven workflows are implemented separately in eodms_prompt.py.
"""

import json
import os
import csv
import base64
import binascii
import logging
import logging.handlers as handlers
import time
import threading
import re
import posixpath
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, unquote, urljoin, urlsplit
from urllib.request import (
    HTTPBasicAuthHandler,
    HTTPPasswordMgrWithDefaultRealm,
    Request,
    build_opener,
    urlopen,
)
from typing import Any, Dict, List, Optional, Tuple

import click
import fiona
from shapely.geometry import mapping, shape

from eodms import Processes_API, aaa, dds, search
from scripts import config_util
from scripts.__version__ import EODMS_CLI_VERSION
try:
    from eodms.errors import EODMSError
    EODMS_SERVICE_ERRORS = (EODMSError,)
except Exception:
    # Backward-compatible fallback for eodms versions that do not expose EODMSError.
    from eodms.errors import CatalogError, DDSError, ProcessingError, SearchError
    EODMS_SERVICE_ERRORS = (CatalogError, DDSError, ProcessingError, SearchError)
from eodms_rapi import EODMSRAPI, QueryError


DEFAULT_DDS_BACKOFF_SECONDS = 60
DEFAULT_DDS_CONCURRENT_DOWNLOADS = 10
DEFAULT_DOWNLOADS_MANIFEST_NAME = "downloads.jsonl"
DEFAULT_DDS_RETRY_FILE = os.path.join(".\\downloads", DEFAULT_DOWNLOADS_MANIFEST_NAME)
MAX_DDS_QUEUED_WAITS = 10
CLI_DEFAULT_LOG_NAME = "eodms_cli.log"
CLI_DEFAULT_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"
CLI_DEFAULT_LOG_LEVEL = logging.INFO

_CLI_LOG_INITIALIZED = False
_CLI_LOG_PATH: Optional[str] = None
_CLI_LOG_DATEFMT = CLI_DEFAULT_LOG_DATEFMT
_CLI_LOG_LEVEL = CLI_DEFAULT_LOG_LEVEL
_SEARCH_UA_PATCHED = False
_CLI_UA_VERSION_ENV_VAR = "EODMS_CLI_UA_VERSION"
_CLI_UA_VERSION = EODMS_CLI_VERSION
_SPINNER_WRITE_LOCK = threading.Lock()
SAR_TOOLBOX_SCHEMA_URL = "https://eodms-sgdot.nrcan-rncan.gc.ca/schemas/st/sar-toolbox-schema.json"

# Let tqdm recalculate bar width when terminal dimensions change.
os.environ.setdefault("TQDM_DYNAMIC_NCOLS", "1")


def _resolve_downloads_manifest_path(download_dir: str) -> str:
    destination = os.path.abspath(download_dir)
    return os.path.join(destination, DEFAULT_DOWNLOADS_MANIFEST_NAME)


class OrderedHelpGroup(click.Group):
    """Group that prints commands in a custom help order."""

    def list_commands(self, ctx):
        preferred = ["search", "process", "download"]
        remaining = sorted(name for name in self.commands if name not in preferred)
        return [name for name in preferred if name in self.commands] + remaining


class ServiceError(click.ClickException):
    exit_code = 2


def handle_service_errors(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except EODMS_SERVICE_ERRORS as exc:
            logging.getLogger("eodms_cli").error("Service error: %s", exc)
            raise ServiceError(f"Service error: {exc}") from exc

    return wrapper


def _default_config_path() -> str:
    user_home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return os.path.join(user_home, ".eodms", "config.ini")


def _load_config_utils(config_path: Optional[str] = None) -> config_util.ConfigUtils:
    cfg = config_util.ConfigUtils(config_path=config_path)
    cfg.import_config()
    return cfg


def _resolve_cli_user_agent_version() -> str:
    env_version = os.environ.get(_CLI_UA_VERSION_ENV_VAR, "").strip()
    if env_version:
        return env_version

    return _CLI_UA_VERSION


def _patch_search_user_agent() -> None:
    global _SEARCH_UA_PATCHED
    if _SEARCH_UA_PATCHED:
        return

    base_method = getattr(search.Search_API, "_default_user_agent", None)
    if not callable(base_method):
        _SEARCH_UA_PATCHED = True
        return

    cli_token = f"eodms-cli/{_resolve_cli_user_agent_version()}"

    def _default_user_agent_with_cli() -> str:
        try:
            base_ua = str(base_method() or "").strip()
        except TypeError:
            # Compatibility fallback for older implementations that are bound instance methods.
            base_ua = str(base_method(search.Search_API) or "").strip()
        if cli_token in base_ua:
            return base_ua
        if base_ua:
            return f"{base_ua} {cli_token}"
        return cli_token

    setattr(search.Search_API, "_default_user_agent", staticmethod(_default_user_agent_with_cli))
    _SEARCH_UA_PATCHED = True


def _resolve_cli_log_path(raw_log_path: Optional[str]) -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = (raw_log_path or "").strip()

    if not log_path:
        return os.path.join(base_dir, "log", CLI_DEFAULT_LOG_NAME)

    if not os.path.isabs(log_path):
        log_path = os.path.join(base_dir, log_path)

    if os.path.isdir(log_path):
        return os.path.join(log_path, CLI_DEFAULT_LOG_NAME)

    # Keep prompt and CLI logs separated when an old shared filename is used.
    if os.path.basename(log_path).lower() in {
        "logger.log",
        "prompt.log",
        "cli.log",
        "eodms_prompt.log",
    }:
        return os.path.join(os.path.dirname(log_path), CLI_DEFAULT_LOG_NAME)

    return log_path


def _load_cli_log_path(config_path: Optional[str] = None) -> str:
    cfg = _load_config_utils(config_path)
    raw_log_path = cfg.get("Paths", "log")

    return _resolve_cli_log_path(raw_log_path)


def _load_cli_log_datefmt(config_path: Optional[str] = None) -> str:
    cfg = _load_config_utils(config_path)
    return cfg.get_logging_datefmt(CLI_DEFAULT_LOG_DATEFMT)


def _load_cli_log_level(config_path: Optional[str] = None) -> int:
    cfg = _load_config_utils(config_path)
    return cfg.get_logging_level(CLI_DEFAULT_LOG_LEVEL)


def _setup_file_logger(log_name: str, log_path: str, level: int = logging.DEBUG,
                       datefmt: str = CLI_DEFAULT_LOG_DATEFMT) -> logging.Logger:
    logger = logging.getLogger(log_name)
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt=datefmt,
    )

    target_path = os.path.abspath(log_path)
    log_dir = os.path.dirname(target_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    existing_handler = None
    for handler in list(logger.handlers):
        if isinstance(handler, handlers.RotatingFileHandler):
            existing_path = getattr(handler, "baseFilename", None)
            if existing_path and os.path.abspath(existing_path) == target_path:
                existing_handler = handler
            else:
                logger.removeHandler(handler)
                handler.close()

    if existing_handler is None:
        existing_handler = handlers.RotatingFileHandler(
            target_path,
            maxBytes=500000,
            backupCount=2,
            encoding="utf-8",
        )
        logger.addHandler(existing_handler)

    existing_handler.setLevel(level)
    existing_handler.setFormatter(formatter)
    return logger


def _setup_package_logger(log_path: str, level: int = logging.INFO,
                          datefmt: str = CLI_DEFAULT_LOG_DATEFMT) -> None:
    package_logger = logging.getLogger("eodms")
    package_logger.setLevel(level)
    package_logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt=datefmt,
    )

    target_path = os.path.abspath(log_path)
    log_dir = os.path.dirname(target_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    file_handler = None
    stream_handler = None
    for handler in list(package_logger.handlers):
        if isinstance(handler, handlers.RotatingFileHandler):
            existing_path = getattr(handler, "baseFilename", None)
            if existing_path and os.path.abspath(existing_path) == target_path:
                file_handler = handler
            else:
                package_logger.removeHandler(handler)
                handler.close()
        elif isinstance(handler, logging.StreamHandler) and not isinstance(handler, handlers.RotatingFileHandler):
            stream_handler = handler
        elif isinstance(handler, logging.NullHandler):
            package_logger.removeHandler(handler)

    if file_handler is None:
        file_handler = handlers.RotatingFileHandler(
            target_path,
            maxBytes=500000,
            backupCount=2,
            encoding="utf-8",
        )
        package_logger.addHandler(file_handler)

    if stream_handler is None:
        stream_handler = logging.StreamHandler()
        package_logger.addHandler(stream_handler)

    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)


def _initialize_cli_logging() -> None:
    global _CLI_LOG_INITIALIZED, _CLI_LOG_PATH, _CLI_LOG_DATEFMT, _CLI_LOG_LEVEL
    if _CLI_LOG_INITIALIZED:
        return

    _CLI_LOG_PATH = _load_cli_log_path()
    _CLI_LOG_DATEFMT = _load_cli_log_datefmt()
    _CLI_LOG_LEVEL = _load_cli_log_level()
    _setup_file_logger("eodms_cli", _CLI_LOG_PATH, level=_CLI_LOG_LEVEL, datefmt=_CLI_LOG_DATEFMT)
    _setup_package_logger(_CLI_LOG_PATH, level=_CLI_LOG_LEVEL, datefmt=_CLI_LOG_DATEFMT)

    logging.getLogger("eodms_cli").info("CLI start time: %s", datetime.now().strftime(_CLI_LOG_DATEFMT))
    _CLI_LOG_INITIALIZED = True


def _decode_config_password(raw_password: str) -> str:
    try:
        return base64.b64decode(raw_password).decode("utf-8")
    except binascii.Error:
        return base64.b64decode(raw_password + "========").decode("utf-8")


def _load_credentials_from_config(config_path: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    cfg = _load_config_utils(config_path)

    username = str(cfg.get("Credentials", "username") or "").strip() or None

    encoded = str(cfg.get("Credentials", "password") or "").strip()
    password = None
    if encoded:
        try:
            password = _decode_config_password(encoded)
        except Exception:
            password = encoded

    return username, password


def resolve_credentials(username: Optional[str], password: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if username and password:
        return username, password

    cfg_username, cfg_password = _load_credentials_from_config()
    return username or cfg_username, password or cfg_password


def _load_dds_backoff_interval(config_path: Optional[str] = None) -> int:
    cfg = _load_config_utils(config_path)

    for option_name in ("backoff_interval", "back_interval"):
        value = str(cfg.get("DDS", option_name) or "").strip()
        try:
            parsed = int(value)
            if parsed > 0:
                return parsed
        except ValueError:
            continue

    return DEFAULT_DDS_BACKOFF_SECONDS


def _load_dds_concurrent_downloads(config_path: Optional[str] = None) -> int:
    cfg = _load_config_utils(config_path)
    value = str(cfg.get("DDS", "concurrent_downloads") or "").strip()
    try:
        parsed = int(value)
        if parsed > 0:
            return parsed
    except ValueError:
        pass

    return DEFAULT_DDS_CONCURRENT_DOWNLOADS


def _save_credentials_to_config(username: str, password: str,
                                config_path: Optional[str] = None) -> str:
    cfg = _load_config_utils(config_path)
    cfg.set("Credentials", "username", username)
    encoded_password = base64.b64encode(password.encode("utf-8")).decode("utf-8")
    cfg.set("Credentials", "password", encoded_password)
    cfg.write()

    return cfg.get_filename()


def parse_aoi_file(aoi_file: str) -> List[Dict[str, Any]]:
    """Read polygon features from a geospatial file and return WKT geometries."""
    try:
        with fiona.open(aoi_file) as src:
            features = list(src)
    except Exception as exc:
        raise ValueError(f"Could not open AOI file '{aoi_file}': {exc}")

    polygons: List[Dict[str, Any]] = []
    for feature in features:
        geom = feature.get("geometry")
        if geom is None or geom.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        name = (feature.get("properties") or {}).get("name")
        polygons.append({"name": name, "wkt": shape(geom).wkt})

    if not polygons:
        raise ValueError("No polygon geometries found in AOI file.")
    if len(polygons) > 5:
        raise ValueError(f"AOI file contains {len(polygons)} polygons; maximum is 5.")

    return polygons


def parse_bbox(bbox: Optional[str]) -> Optional[List[float]]:
    if not bbox:
        return None

    try:
        bbox_list = [float(x.strip()) for x in bbox.split(",")]
    except ValueError as exc:
        raise click.BadParameter(f"Invalid bbox values: {exc}")

    if len(bbox_list) != 4:
        raise click.BadParameter("Bounding box must contain exactly 4 values: west,south,east,north")

    return bbox_list


def save_items_geojson(items: Optional[List[Dict[str, Any]]], output_file: str) -> None:
    feature_collection = {
        "type": "FeatureCollection",
        "features": items or [],
    }

    with open(output_file, "w", encoding="utf-8") as out_f:
        json.dump(feature_collection, out_f, indent=2)

    click.echo(f"Saved {len(feature_collection['features'])} item(s) to {output_file}")


def _read_tsv_rows(input_file: str) -> Tuple[List[str], List[Dict[str, str]]]:
    try:
        with open(input_file, "r", encoding="utf-8-sig", newline="") as src:
            reader = csv.DictReader(src, delimiter="\t")
            if not reader.fieldnames:
                raise click.ClickException("Input TSV must include a header row.")
            return list(reader.fieldnames), [dict(row) for row in reader]
    except click.ClickException:
        raise
    except Exception as exc:
        raise click.ClickException(f"Failed to read TSV input '{input_file}': {exc}")


def _write_tsv_rows(output_file: str, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    try:
        with open(output_file, "w", encoding="utf-8", newline="") as out_f:
            writer = csv.DictWriter(out_f, fieldnames=fieldnames, delimiter="\t")
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    field_name: "" if row.get(field_name) is None else str(row.get(field_name))
                    for field_name in fieldnames
                })
    except Exception as exc:
        raise click.ClickException(f"Failed to write TSV output '{output_file}': {exc}")


def _write_input_rows_geojson(output_file: str, rows: List[Dict[str, Any]], geometry_field: str = "geometry") -> int:
    """Write matched input rows as a GeoJSON FeatureCollection.

    Only rows with a valid GeoJSON object in `geometry_field` are emitted.
    """
    features: List[Dict[str, Any]] = []

    for row in rows:
        raw_geometry = row.get(geometry_field)
        geometry_obj: Optional[Dict[str, Any]] = None

        if isinstance(raw_geometry, dict):
            geometry_obj = raw_geometry
        elif isinstance(raw_geometry, str):
            raw_geometry = raw_geometry.strip()
            if raw_geometry:
                try:
                    parsed = json.loads(raw_geometry)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    geometry_obj = parsed

        if not isinstance(geometry_obj, dict):
            continue

        try:
            # Validate and normalize geometry via Shapely before writing GeoJSON.
            parsed_geom = shape(geometry_obj)
            if parsed_geom.is_empty:
                continue
            geometry_obj = mapping(parsed_geom)
        except Exception:
            continue

        properties = {
            str(key): value
            for key, value in row.items()
            if key != geometry_field
        }

        features.append({
            "type": "Feature",
            "geometry": geometry_obj,
            "properties": properties,
        })

    with open(output_file, "w", encoding="utf-8") as out_f:
        json.dump({"type": "FeatureCollection", "features": features}, out_f, indent=2)

    return len(features)


def _get_tsv_order_key_column(fieldnames: List[str]) -> Optional[str]:
    normalized = {str(name).strip().lower(): name for name in fieldnames}
    return (
        normalized.get("order_keys")
        or normalized.get("order_key")
        or normalized.get("orderkey")
    )


def _get_tsv_datetime_column(fieldnames: List[str]) -> Optional[str]:
    normalized = {str(name).strip().lower(): name for name in fieldnames}
    return (
        normalized.get("datetime")
        or normalized.get("datetime_start")
        or normalized.get("timestamp")
    )


def _extract_item_title(item: Dict[str, Any]) -> Optional[str]:
    if not isinstance(item, dict):
        return None

    value = item.get("title")
    if value is not None and str(value).strip():
        return str(value)

    props = item.get("properties")
    if isinstance(props, dict):
        value = props.get("title")
        if value is not None and str(value).strip():
            return str(value)

    return None


def _matches_title_or_order_key(item: Dict[str, Any], order_key: str) -> bool:
    if not order_key:
        return False

    expected = str(order_key).strip()
    if not expected:
        return False

    item_order_key = _extract_order_key(item)
    if item_order_key and str(item_order_key).strip() == expected:
        return True

    item_title = _extract_item_title(item)
    if item_title and expected in str(item_title):
        return True

    return False


def _extract_search_dates_for_row(datetime_value: str) -> List[str]:
    """Return calendar date(s) (YYYY-MM-DD) covered by a datetime value/range."""

    def _coerce_to_utc_datetime(raw_value: str) -> Optional[datetime]:
        parsed = _parse_iso_datetime(raw_value)
        if parsed is not None:
            return parsed

        try:
            date_only = datetime.strptime(raw_value, "%Y-%m-%d")
            return date_only.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    value = str(datetime_value or "").strip()
    if not value:
        return []

    if "/" in value:
        start_raw, end_raw = value.split("/", 1)
    else:
        start_raw, end_raw = value, value

    start_dt = _coerce_to_utc_datetime(str(start_raw).strip())
    end_dt = _coerce_to_utc_datetime(str(end_raw).strip())
    if start_dt is None or end_dt is None:
        return []

    start_date = min(start_dt, end_dt).date()
    end_date = max(start_dt, end_dt).date()

    dates: List[str] = []
    cursor = start_date
    while cursor <= end_date:
        dates.append(cursor.isoformat())
        cursor += timedelta(days=1)

    return dates


def _extract_search_spatial_resolution(item: Dict[str, Any]) -> Optional[str]:
    if not isinstance(item, dict):
        return None

    props = item.get("properties")
    containers = [item]
    if isinstance(props, dict):
        containers.append(props)

    for container in containers:
        for key in ("spatial_resolution", "spatialResolution", "SPATIAL_RESOLUTION"):
            value = container.get(key)
            if value is not None and str(value).strip():
                return str(value)

    return None


def _extract_search_timestamp(item: Dict[str, Any]) -> Optional[str]:
    if not isinstance(item, dict):
        return None

    props = item.get("properties")
    containers = [item]
    if isinstance(props, dict):
        containers.append(props)

    for container in containers:
        for key in (
            "timestamp",
            "datetime",
            "date",
            "updated",
            "updated_at",
            "start_datetime",
            "acquisition_datetime",
        ):
            value = container.get(key)
            if value is not None and str(value).strip():
                return str(value)

    return None


def _extract_thumbnail_url(item: Dict[str, Any]) -> Optional[str]:
    if not isinstance(item, dict):
        return None

    # Prefer STAC assets that typically hold browse imagery.
    assets = item.get("assets")
    if isinstance(assets, dict):
        for asset_key in ("thumbnail", "thumb", "quicklook", "browse", "overview", "preview"):
            asset = assets.get(asset_key)
            if isinstance(asset, dict):
                href = asset.get("href")
                if href is not None and str(href).strip():
                    return str(href)

        # Fall back to any asset that has a non-empty href.
        for asset in assets.values():
            if isinstance(asset, dict):
                href = asset.get("href")
                if href is not None and str(href).strip():
                    return str(href)

    # Alternate STAC shape using links with rel hints.
    links = item.get("links")
    if isinstance(links, list):
        for link in links:
            if not isinstance(link, dict):
                continue
            rel = str(link.get("rel") or "").strip().lower()
            if rel in ("thumbnail", "preview", "icon"):
                href = link.get("href")
                if href is not None and str(href).strip():
                    return str(href)

    return None


def _quote_cql2_text_string(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _chunk_values(values: List[str], chunk_size: int) -> List[List[str]]:
    resolved_chunk_size = max(1, int(chunk_size or 1))
    return [values[idx:idx + resolved_chunk_size] for idx in range(0, len(values), resolved_chunk_size)]


def _search_items_by_filter(search_api, collection: str, filter_text: str, limit: int) -> List[Dict[str, Any]]:
    resolved_limit = max(1, int(limit or 1))

    try:
        items = search_api.stac_search(
            collections=[collection],
            limit=resolved_limit,
            filter=filter_text,
            filter_lang="cql2-text",
        )
    except (AttributeError, TypeError):
        items = search_api.search_multiple_geometries(
            s_intersect_list=[{"name": None, "wkt": None}],
            collection=collection,
            datetime_range=None,
            bbox=None,
            limit=resolved_limit,
            filter_text=filter_text,
        )

    if items is None:
        return []
    if isinstance(items, dict):
        features = items.get("features")
        if isinstance(features, list):
            return [item for item in features if isinstance(item, dict)]
        return [items]
    return [item for item in list(items) if isinstance(item, dict)]


def _search_items_by_order_keys(search_api, collection: str, order_keys: List[str],
                                chunk_size: int = 100) -> Dict[str, Dict[str, Any]]:
    matched_items: Dict[str, Dict[str, Any]] = {}
    cleaned_order_keys = []
    seen_order_keys = set()

    for raw_order_key in order_keys:
        order_key = str(raw_order_key or "").strip()
        if not order_key or order_key in seen_order_keys:
            continue
        cleaned_order_keys.append(order_key)
        seen_order_keys.add(order_key)

    for order_key_chunk in _chunk_values(cleaned_order_keys, chunk_size):
        if not order_key_chunk:
            continue

        chunk_filter = " OR ".join(
            f"order_key = {_quote_cql2_text_string(order_key)}"
            for order_key in order_key_chunk
        )
        items = _search_items_by_filter(
            search_api,
            collection,
            f"({chunk_filter})",
            limit=len(order_key_chunk),
        )

        for item in items:
            found_order_key = _extract_order_key(item)
            if not found_order_key or found_order_key in matched_items:
                continue
            matched_items[found_order_key] = item

    return matched_items


def make_aaa(username: Optional[str], password: Optional[str], environment: str):
    if username and password:
        return aaa.AAA_API(username, password, environment)
    return None


def make_dds(aaa_api, environment: str):
    try:
        return dds.DDS_API(aaa_api, environment=environment)
    except TypeError:
        return dds.DDS_API(aaa_api, environment)


def make_search(aaa_api, environment: str):
    _patch_search_user_agent()
    try:
        return search.Search_API(aaa_api=aaa_api, environment=environment)
    except TypeError:
        return search.Search_API(aaa_api, environment)


def make_processes(aaa_api, environment: str):
    try:
        return Processes_API(aaa_api=aaa_api, environment=environment)
    except TypeError:
        return Processes_API(aaa_api, environment)


def _normalize_status(value: Optional[str]) -> str:
    if not value:
        return ""
    return "".join(ch for ch in str(value).upper() if ch.isalnum())


def _extract_dds_status(item_info: Any) -> Optional[str]:
    if not isinstance(item_info, dict):
        return None

    for key in ("status", "item_status", "itemStatus", "state"):
        value = item_info.get(key)
        if value is not None and str(value).strip():
            return str(value)

    props = item_info.get("properties")
    if isinstance(props, dict):
        for key in ("status", "item_status", "itemStatus", "state"):
            value = props.get(key)
            if value is not None and str(value).strip():
                return str(value)

    return None


def _extract_dds_timestamp(item_info: Any) -> Optional[str]:
    if not isinstance(item_info, dict):
        return None

    for key in (
        "last_update",
        "lastUpdate",
        "timestamp",
        "updated",
        "updated_at",
        "date",
        "datetime",
    ):
        value = item_info.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    props = item_info.get("properties")
    if isinstance(props, dict):
        for key in (
            "last_update",
            "lastUpdate",
            "timestamp",
            "updated",
            "updated_at",
            "date",
            "datetime",
        ):
            value = props.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()

    return None


def _extract_dds_download_filename(item_info: Dict[str, Any], item_uuid: str) -> Optional[str]:
    if not isinstance(item_info, dict):
        return None

    download_url = item_info.get("download_url")
    if download_url is not None and str(download_url).strip():
        parsed = urlsplit(str(download_url).strip())
        file_name = unquote(os.path.basename(parsed.path or "")).strip()
        if file_name:
            return file_name

    for key in ("filename", "file_name", "name", "title"):
        value = item_info.get(key)
        if value is None:
            continue
        file_name = str(value).strip()
        if file_name:
            return file_name

    if item_uuid:
        return f"{item_uuid}.zip"

    return None


def _coerce_http_status_code(value: Any) -> Optional[int]:
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value if 100 <= value <= 599 else None

    value_str = str(value).strip()
    if not value_str:
        return None

    if value_str.isdigit():
        code = int(value_str)
        return code if 100 <= code <= 599 else None

    match = re.search(r"\b([1-5][0-9]{2})\b", value_str)
    if not match:
        return None

    code = int(match.group(1))
    return code if 100 <= code <= 599 else None


def _extract_http_status_code(payload: Any) -> Optional[int]:
    if payload is None:
        return None

    if isinstance(payload, dict):
        for key in (
            "http_response_code",
            "http_status_code",
            "status_code",
            "response_code",
            "http_status",
            "status",
            "code",
        ):
            code = _coerce_http_status_code(payload.get(key))
            if code is not None:
                return code

        nested_response = payload.get("response")
        nested_code = _extract_http_status_code(nested_response)
        if nested_code is not None:
            return nested_code

    for attr in (
        "http_response_code",
        "http_status_code",
        "status_code",
        "response_code",
        "http_status",
        "status",
        "code",
    ):
        code = _coerce_http_status_code(getattr(payload, attr, None))
        if code is not None:
            return code

    nested_response = getattr(payload, "response", None)
    nested_code = _extract_http_status_code(nested_response)
    if nested_code is not None:
        return nested_code

    return _coerce_http_status_code(payload)


def _write_jsonl_rows_atomic(file_path: str, rows: List[Dict[str, Any]]) -> None:
    target_path = os.path.abspath(file_path)
    target_dir = os.path.dirname(target_path)
    if target_dir:
        os.makedirs(target_dir, exist_ok=True)

    temp_path = f"{target_path}.tmp.{os.getpid()}.{threading.get_ident()}"
    try:
        with open(temp_path, "w", encoding="utf-8") as out_f:
            for row in rows:
                out_f.write(json.dumps(row, ensure_ascii=True) + "\n")
            out_f.flush()
            os.fsync(out_f.fileno())

        os.replace(temp_path, target_path)

        if target_dir:
            try:
                dir_fd = os.open(target_dir, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except Exception:
                pass
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _append_dds_retry_item(
    retry_file: str,
    collection: str,
    item_uuid: str,
    status: str,
    timestamp: Optional[str] = None,
    http_response_code: Optional[int] = None,
    source: Optional[str] = None,
    file_name: Optional[str] = None,
    file_path: Optional[str] = None,
    detail: Optional[str] = None,
    update_existing_only: bool = False,
) -> bool:
    retry_path = os.path.abspath(retry_file)
    resolved_timestamp = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    normalized_uuid = str(item_uuid or "").strip().lower()
    if not normalized_uuid:
        return False

    deduped_by_uuid: Dict[str, Dict[str, Any]] = {}
    if os.path.exists(retry_path):
        with open(retry_path, "r", encoding="utf-8") as in_f:
            for line in in_f:
                candidate = line.strip()
                if not candidate:
                    continue

                try:
                    row = json.loads(candidate)
                except json.JSONDecodeError:
                    continue

                if not isinstance(row, dict):
                    continue

                row_uuid = str(
                    row.get("uuid")
                    or row.get("id")
                    or row.get("item_id")
                    or row.get("itemId")
                    or ""
                ).strip()
                if not row_uuid:
                    continue

                deduped_by_uuid[row_uuid.lower()] = {
                    "collection": str(row.get("collection") or "").strip(),
                    "uuid": row_uuid,
                    "status": str(row.get("status") or "").strip(),
                    "timestamp": str(row.get("timestamp") or "").strip()
                    or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "http_response_code": _extract_http_status_code(row),
                    "source": str(row.get("source") or "").strip(),
                    "file_name": str(row.get("file_name") or "").strip(),
                    "file_path": str(row.get("file_path") or "").strip(),
                    "detail": str(row.get("detail") or "").strip(),
                }

    current_row = deduped_by_uuid.get(normalized_uuid)
    if current_row is None and update_existing_only:
        return False

    if current_row is None:
        current_row = {
            "collection": str(collection or "").strip(),
            "uuid": str(item_uuid).strip(),
            "status": str(status or "").strip(),
            "timestamp": resolved_timestamp,
        }
    else:
        current_row["collection"] = str(collection or current_row.get("collection") or "").strip()
        current_row["status"] = str(status or current_row.get("status") or "").strip()
        current_row["timestamp"] = resolved_timestamp

    if http_response_code is None:
        current_row.pop("http_response_code", None)
    else:
        current_row["http_response_code"] = int(http_response_code)

    if source is None:
        current_row.pop("source", None)
    else:
        current_row["source"] = str(source).strip()

    if file_name is None:
        current_row.pop("file_name", None)
    else:
        current_row["file_name"] = str(file_name).strip()

    if file_path is None:
        current_row.pop("file_path", None)
    else:
        current_row["file_path"] = str(file_path).strip()

    if detail is None:
        current_row.pop("detail", None)
    else:
        current_row["detail"] = str(detail).strip()

    deduped_by_uuid[normalized_uuid] = current_row

    rows = list(deduped_by_uuid.values())
    rows.sort(key=lambda row: str(row.get("uuid") or "").lower())

    _write_jsonl_rows_atomic(retry_path, rows)

    return True


def _compact_dds_retry_file(retry_file: str) -> int:
    retry_path = os.path.abspath(retry_file)
    if not os.path.exists(retry_path):
        return 0

    deduped: Dict[str, Dict[str, Any]] = {}

    with open(retry_path, "r", encoding="utf-8") as in_f:
        for line in in_f:
            candidate = line.strip()
            if not candidate:
                continue

            try:
                row = json.loads(candidate)
            except json.JSONDecodeError:
                continue

            if not isinstance(row, dict):
                continue

            row_collection = str(row.get("collection", "")).strip()
            row_uuid = str(
                row.get("uuid")
                or row.get("id")
                or row.get("item_id")
                or row.get("itemId")
                or ""
            ).strip()
            row_status = str(row.get("status", "")).strip()

            if not row_collection or not row_uuid:
                continue

            if not row_status:
                continue

            deduped[row_uuid.lower()] = {
                "collection": row_collection,
                "uuid": row_uuid,
                "status": row_status,
                "timestamp": str(row.get("timestamp") or "").strip()
                or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "http_response_code": _extract_http_status_code(row),
                "source": str(row.get("source") or "").strip(),
                "file_name": str(row.get("file_name") or "").strip(),
                "file_path": str(row.get("file_path") or "").strip(),
                "detail": str(row.get("detail") or "").strip(),
            }

    deduped_rows = list(deduped.values())
    deduped_rows.sort(
        key=lambda row: (
            str(row.get("uuid") or "").lower(),
        )
    )

    _write_jsonl_rows_atomic(retry_path, deduped_rows)

    return len(deduped_rows)


def _record_dds_retry(
    retry_file: str,
    collection: str,
    item_uuid: str,
    status: str,
    timestamp: Optional[str] = None,
    http_response_code: Optional[int] = None,
    source: Optional[str] = None,
    file_name: Optional[str] = None,
    file_path: Optional[str] = None,
    detail: Optional[str] = None,
    update_existing_only: bool = False,
) -> Dict[str, Any]:
    retry_abs_path = os.path.abspath(retry_file)
    retry_rel_path = os.path.relpath(retry_abs_path, os.getcwd())
    retry_rel_path = os.path.normpath(retry_rel_path)
    if not (retry_rel_path.startswith(".") or os.path.isabs(retry_rel_path)):
        retry_rel_path = f".{os.sep}{retry_rel_path}"

    wrote_record = _append_dds_retry_item(
        retry_file=retry_file,
        collection=collection,
        item_uuid=item_uuid,
        status=status,
        timestamp=timestamp,
        http_response_code=http_response_code,
        source=source,
        file_name=file_name,
        file_path=file_path,
        detail=detail,
        update_existing_only=update_existing_only,
    )

    if not wrote_record and update_existing_only:
        click.echo(
            f"Download manifest update skipped (uuid not present in manifest): "
            f"collection={collection}, uuid={item_uuid}, status={status}"
        )
        return {
            "_dds_retry_logged": False,
            "_dds_retry_skipped": True,
            "_manifest_status": status,
            "collection": collection,
            "uuid": item_uuid,
            "status": status,
            "timestamp": timestamp,
            "http_response_code": http_response_code,
            "source": source,
            "file_name": file_name,
            "file_path": file_path,
            "detail": detail,
        }

    extra_detail = f", detail={detail}" if detail else ""
    extra_http = f", http_response_code={http_response_code}" if http_response_code is not None else ""
    extra_source = f", source={source}" if source else ""
    extra_file_name = f", file_name={file_name}" if file_name else ""
    extra_file_path = f", file_path={file_path}" if file_path else ""
    click.echo(
        f"Download manifest updated: collection={collection}, uuid={item_uuid}, "
        f"status={status}{extra_source}{extra_http}{extra_file_name}{extra_file_path}{extra_detail}, "
        f"manifest={retry_rel_path}"
    )
    if status.lower().find("restoring") > -1 or status.lower().find("queued") > -1:
        click.echo(
            "Replay with: "
            f"py eodms_cli.py download --input \"{retry_rel_path}\""
        )

    return {
        "_dds_retry_logged": True,
        "_manifest_status": status,
        "collection": collection,
        "uuid": item_uuid,
        "status": status,
        "timestamp": timestamp,
        "http_response_code": http_response_code,
        "source": source,
        "file_name": file_name,
        "file_path": file_path,
        "detail": detail,
    }


def _spinner_backoff_wait(wait_seconds: int, label: str) -> None:
    total = int(wait_seconds)
    if total <= 0:
        return

    with _SPINNER_WRITE_LOCK:
        click.echo(f"{label} waiting {total}s...")

    start = time.monotonic()
    last_print_elapsed = 0.0
    _PRINT_INTERVAL = 15

    while True:
        elapsed = time.monotonic() - start
        remaining = int(max(0, total - elapsed + 0.999))
        if remaining <= 0:
            break

        if elapsed - last_print_elapsed >= _PRINT_INTERVAL:
            with _SPINNER_WRITE_LOCK:
                click.echo(f"{label} {remaining}s remaining...")
            last_print_elapsed = elapsed

        time.sleep(1)

    with _SPINNER_WRITE_LOCK:
        click.echo(f"{label} done.")


def download_dds_item(dds_api, collection: str, item_uuid: str, download_dir: str,
                      queued_backoff_seconds: int = DEFAULT_DDS_BACKOFF_SECONDS,
                      retry_file: str = DEFAULT_DDS_RETRY_FILE,
                      update_retry_existing_only: bool = True) -> Optional[Dict[str, Any]]:
    waits = 0

    while True:
        try:
            item_info = dds_api.get_item(collection, item_uuid)
        except Exception as exc:
            http_response_code = _extract_http_status_code(exc)
            click.echo(
                f"DDS get_item failed: collection={collection}, uuid={item_uuid}, "
                f"http_response_code={http_response_code}, error={exc}"
            )
            return _record_dds_retry(
                retry_file=retry_file,
                collection=collection,
                item_uuid=item_uuid,
                status="GetItemError",
                http_response_code=http_response_code,
                source="dds",
                detail=str(exc),
                update_existing_only=update_retry_existing_only,
            )

        if item_info is None:
            click.echo(f"Item not found: collection={collection}, uuid={item_uuid}")
            return _record_dds_retry(
                retry_file=retry_file,
                collection=collection,
                item_uuid=item_uuid,
                status="ItemNotFound",
                source="dds",
                update_existing_only=update_retry_existing_only,
            )

        if not isinstance(item_info, dict):
            http_response_code = _extract_http_status_code(item_info)
            click.echo(
                f"Unexpected DDS item response type: collection={collection}, uuid={item_uuid}, "
                f"http_response_code={http_response_code}, type={type(item_info).__name__}"
            )
            return _record_dds_retry(
                retry_file=retry_file,
                collection=collection,
                item_uuid=item_uuid,
                status="InvalidItemResponse",
                http_response_code=http_response_code,
                source="dds",
                update_existing_only=update_retry_existing_only,
            )

        status_value = _extract_dds_status(item_info)
        normalized_status = _normalize_status(status_value)
        item_timestamp = _extract_dds_timestamp(item_info)
        item_http_response_code = _extract_http_status_code(item_info)

        if normalized_status == "QUEUED":
            _record_dds_retry(
                retry_file=retry_file,
                collection=collection,
                item_uuid=item_uuid,
                status="Queued",
                timestamp=item_timestamp,
                http_response_code=item_http_response_code,
                source="dds",
                detail=f"wait_attempt={waits + 1}/{MAX_DDS_QUEUED_WAITS}",
                update_existing_only=update_retry_existing_only,
            )

            if waits >= MAX_DDS_QUEUED_WAITS:
                click.echo(
                    f"Item remained Queued after {MAX_DDS_QUEUED_WAITS} wait(s): "
                    f"collection={collection}, uuid={item_uuid}"
                )
                return _record_dds_retry(
                    retry_file=retry_file,
                    collection=collection,
                    item_uuid=item_uuid,
                    status="QueuedTimeout",
                    timestamp=item_timestamp,
                    http_response_code=item_http_response_code,
                    source="dds",
                    update_existing_only=update_retry_existing_only,
                )

            waits += 1
            click.echo(
                f"DDS item Queued: collection={collection}, uuid={item_uuid}. "
                f"Waiting {queued_backoff_seconds}s before retry ({waits}/{MAX_DDS_QUEUED_WAITS})..."
            )
            _spinner_backoff_wait(
                queued_backoff_seconds,
                f"Backoff wait ({waits}/{MAX_DDS_QUEUED_WAITS}) for {item_uuid}:",
            )
            continue

        if normalized_status in {"ITEMRESTORING", "ITEMSRESTORING"}:
            return _record_dds_retry(
                retry_file=retry_file,
                collection=collection,
                item_uuid=item_uuid,
                status=status_value or "ItemRestoring",
                timestamp=item_timestamp,
                http_response_code=item_http_response_code,
                source="dds",
                update_existing_only=update_retry_existing_only,
            )

        if "download_url" not in item_info:
            click.echo(
                f"Item has no download URL: collection={collection}, uuid={item_uuid}, "
                f"status={status_value or 'unknown'}"
            )
            return _record_dds_retry(
                retry_file=retry_file,
                collection=collection,
                item_uuid=item_uuid,
                status=status_value or "NoDownloadURL",
                timestamp=item_timestamp,
                http_response_code=item_http_response_code,
                source="dds",
                update_existing_only=update_retry_existing_only,
            )

        resolved_download_dir = os.path.abspath(download_dir)
        os.makedirs(resolved_download_dir, exist_ok=True)

        expected_file_name = _extract_dds_download_filename(item_info, item_uuid)
        if expected_file_name:
            expected_file_path = os.path.join(resolved_download_dir, expected_file_name)
            if os.path.exists(expected_file_path):
                click.echo(
                    f"Skipping DDS download (file already exists): "
                    f"collection={collection}, uuid={item_uuid}, file={expected_file_path}"
                )
                return _record_dds_retry(
                    retry_file=retry_file,
                    collection=collection,
                    item_uuid=item_uuid,
                    status="SkippedExisting",
                    timestamp=item_timestamp,
                    http_response_code=item_http_response_code,
                    source="dds",
                    file_name=expected_file_name,
                    file_path=expected_file_path,
                    update_existing_only=update_retry_existing_only,
                )

        try:
            download_result = dds_api.download_item(resolved_download_dir)
        except Exception as exc:
            http_response_code = _extract_http_status_code(exc)
            click.echo(
                f"DDS download failed: collection={collection}, uuid={item_uuid}, "
                f"http_response_code={http_response_code}, error={exc}"
            )
            return _record_dds_retry(
                retry_file=retry_file,
                collection=collection,
                item_uuid=item_uuid,
                status="DownloadError",
                timestamp=item_timestamp,
                http_response_code=http_response_code,
                source="dds",
                file_name=expected_file_name,
                file_path=(os.path.join(resolved_download_dir, expected_file_name)
                           if expected_file_name else None),
                detail=str(exc),
                update_existing_only=update_retry_existing_only,
            )

        resolved_path: Optional[str] = None
        if isinstance(download_result, str) and str(download_result).strip():
            resolved_path = str(download_result).strip()
        elif expected_file_name:
            resolved_path = os.path.join(resolved_download_dir, expected_file_name)

        return _record_dds_retry(
            retry_file=retry_file,
            collection=collection,
            item_uuid=item_uuid,
            status="Downloaded",
            timestamp=item_timestamp,
            http_response_code=item_http_response_code,
            source="dds",
            file_name=expected_file_name,
            file_path=resolved_path,
            update_existing_only=update_retry_existing_only,
        )


def _is_public_asset_collection(collection: str) -> bool:
    normalized = str(collection or "").strip().lower()
    return normalized in {"rcm-ard", "sentinel-1", "sentinel-2"}


def _asset_filename(item_uuid: str, asset_name: str, href: str) -> str:
    parsed = urlsplit(href)
    file_name = os.path.basename(parsed.path)
    file_name = unquote(file_name)
    if file_name:
        return file_name
    return f"{item_uuid}_{asset_name}"


def _unique_destination_path(destination_dir: str, file_name: str) -> str:
    full_path = os.path.join(destination_dir, file_name)
    if not os.path.exists(full_path):
        return full_path

    stem, ext = os.path.splitext(file_name)
    idx = 1
    while True:
        candidate = os.path.join(destination_dir, f"{stem}_{idx}{ext}")
        if not os.path.exists(candidate):
            return candidate
        idx += 1


class _DirectoryHrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if str(tag).lower() != "a":
            return

        for key, value in attrs:
            if str(key).lower() == "href" and value:
                self.hrefs.append(str(value))
                break


def _build_http_opener_for_cart(base_url: str, username: Optional[str], password: Optional[str]):
    handlers = []
    if username and password:
        parsed = urlsplit(base_url)
        top_level_url = f"{parsed.scheme}://{parsed.netloc}"
        password_mgr = HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, top_level_url, username, password)
        password_mgr.add_password(None, base_url, username, password)
        handlers.append(HTTPBasicAuthHandler(password_mgr))

    return build_opener(*handlers)


def _open_cart_http_url(opener, url: str):
    req = Request(
        url,
        headers={"User-Agent": f"eodms-cli/{_resolve_cli_user_agent_version()}"},
    )
    return opener.open(req)


def _extract_cart_links(html_text: str, current_url: str) -> List[str]:
    parser = _DirectoryHrefParser()
    parser.feed(html_text)

    links: List[str] = []
    for raw_href in parser.hrefs:
        href = str(raw_href or "").strip()
        if not href:
            continue
        lowered = href.lower()
        if lowered.startswith("#") or lowered.startswith("?"):
            continue
        if lowered.startswith("javascript:") or lowered.startswith("mailto:"):
            continue
        links.append(urljoin(current_url, href))

    return links


def _to_relative_cart_file_path(file_url: str, root_url: str) -> str:
    file_parts = urlsplit(file_url)
    root_parts = urlsplit(root_url)

    file_path = unquote(file_parts.path or "")
    root_path = unquote(root_parts.path or "")
    if not root_path.endswith("/"):
        root_path = f"{root_path}/"

    if file_path.startswith(root_path):
        rel_path = file_path[len(root_path):]
    else:
        rel_path = os.path.basename(file_path)

    return rel_path.lstrip("/")


def _safe_cart_output_path(destination_dir: str, relative_path: str) -> Optional[str]:
    rel_parts = [part for part in str(relative_path).split("/") if part not in {"", ".", ".."}]
    if not rel_parts:
        return None

    candidate = os.path.abspath(os.path.join(destination_dir, *rel_parts))
    destination_abs = os.path.abspath(destination_dir)
    if candidate != destination_abs and not candidate.startswith(destination_abs + os.sep):
        return None

    return candidate


def download_http_cart_directory(
    cart_url: str,
    download_dir: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    manifest_file: Optional[str] = None,
) -> Dict[str, int]:
    parsed = urlsplit(str(cart_url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        raise click.ClickException(f"Cart URL must use http/https: {cart_url}")

    root_url = str(cart_url or "").strip()
    if not root_url.endswith("/"):
        root_url = f"{root_url}/"

    root_parts = urlsplit(root_url)
    root_prefix_path = unquote(root_parts.path or "")
    if not root_prefix_path.endswith("/"):
        root_prefix_path = f"{root_prefix_path}/"

    opener = _build_http_opener_for_cart(root_url, username, password)
    destination = os.path.abspath(download_dir)
    os.makedirs(destination, exist_ok=True)

    queue: List[str] = [root_url]
    visited_dirs: set = set()
    downloaded = 0
    skipped_existing = 0
    errors = 0

    while queue:
        current_url = queue.pop(0)
        if current_url in visited_dirs:
            continue
        visited_dirs.add(current_url)

        try:
            with _open_cart_http_url(opener, current_url) as resp:
                page = resp.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            if exc.code == 401 and not (username and password):
                raise click.ClickException(
                    f"HTTP 401 for cart URL '{cart_url}'. Provide --username and --password "
                    "(or configure credentials)."
                )

            errors += 1
            click.echo(f"Failed to list directory '{current_url}': HTTP {exc.code}")
            continue
        except URLError as exc:
            errors += 1
            click.echo(f"Failed to list directory '{current_url}': {exc}")
            continue

        child_links = _extract_cart_links(page, current_url)
        for link_url in child_links:
            link_parts = urlsplit(link_url)
            if link_parts.scheme != root_parts.scheme or link_parts.netloc != root_parts.netloc:
                continue

            path = unquote(link_parts.path or "")
            normalized_path = posixpath.normpath(path)
            if path.endswith("/") and not normalized_path.endswith("/"):
                normalized_path = f"{normalized_path}/"

            if not normalized_path.startswith(root_prefix_path):
                continue

            if (link_parts.path or "").endswith("/"):
                if link_url not in visited_dirs:
                    queue.append(link_url)
                continue

            relative_file_path = _to_relative_cart_file_path(link_url, root_url)
            local_path = _safe_cart_output_path(destination, relative_file_path)
            if not local_path:
                continue

            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            if os.path.exists(local_path):
                skipped_existing += 1
                if manifest_file:
                    _record_dds_retry(
                        retry_file=manifest_file,
                        collection="http-cart",
                        item_uuid=relative_file_path,
                        status="SkippedExisting",
                        source="http-cart",
                        file_name=os.path.basename(local_path),
                        file_path=local_path,
                        detail=f"url={link_url}",
                        update_existing_only=False,
                    )
                continue

            try:
                with _open_cart_http_url(opener, link_url) as resp, open(local_path, "wb") as out_f:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        out_f.write(chunk)
                downloaded += 1
                click.echo(f"Saved cart file to {local_path}")

                if manifest_file:
                    _record_dds_retry(
                        retry_file=manifest_file,
                        collection="http-cart",
                        item_uuid=relative_file_path,
                        status="Downloaded",
                        source="http-cart",
                        file_name=os.path.basename(local_path),
                        file_path=local_path,
                        detail=f"url={link_url}",
                        update_existing_only=False,
                    )
            except HTTPError as exc:
                errors += 1
                click.echo(f"Failed to download '{link_url}': HTTP {exc.code}")
                if manifest_file:
                    _record_dds_retry(
                        retry_file=manifest_file,
                        collection="http-cart",
                        item_uuid=relative_file_path,
                        status="DownloadError",
                        http_response_code=exc.code,
                        source="http-cart",
                        file_name=os.path.basename(local_path),
                        file_path=local_path,
                        detail=f"url={link_url}",
                        update_existing_only=False,
                    )
            except URLError as exc:
                errors += 1
                click.echo(f"Failed to download '{link_url}': {exc}")
                if manifest_file:
                    _record_dds_retry(
                        retry_file=manifest_file,
                        collection="http-cart",
                        item_uuid=relative_file_path,
                        status="DownloadError",
                        source="http-cart",
                        file_name=os.path.basename(local_path),
                        file_path=local_path,
                        detail=f"url={link_url}, error={exc}",
                        update_existing_only=False,
                    )

    return {
        "downloaded": downloaded,
        "skipped_existing": skipped_existing,
        "errors": errors,
    }


def download_public_stac_assets(search_api, collection: str, item_uuid: str, download_dir: str,
                                manifest_file: Optional[str] = None) -> int:
    item_info = search_api.get_item(collection, item_uuid)
    if item_info is None:
        click.echo(f"Item not found: collection={collection}, uuid={item_uuid}")
        if manifest_file:
            _record_dds_retry(
                retry_file=manifest_file,
                collection=collection,
                item_uuid=item_uuid,
                status="ItemNotFound",
                source="stac",
                update_existing_only=False,
            )
        return 0

    assets = item_info.get("assets") if isinstance(item_info, dict) else None
    if not isinstance(assets, dict) or not assets:
        click.echo(f"Item has no assets: collection={collection}, uuid={item_uuid}")
        if manifest_file:
            _record_dds_retry(
                retry_file=manifest_file,
                collection=collection,
                item_uuid=item_uuid,
                status="NoAssets",
                source="stac",
                update_existing_only=False,
            )
        return 0

    destination = os.path.abspath(download_dir)
    os.makedirs(destination, exist_ok=True)

    downloaded_count = 0
    for asset_name, asset_obj in assets.items():
        href = None
        if isinstance(asset_obj, dict):
            href = asset_obj.get("href")
        elif isinstance(asset_obj, str):
            href = asset_obj

        if not href:
            continue

        out_name = _asset_filename(item_uuid, str(asset_name), str(href))
        out_path = _unique_destination_path(destination, out_name)

        click.echo(f"Downloading asset '{asset_name}'...")
        try:
            with urlopen(str(href)) as resp, open(out_path, "wb") as out_f:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    out_f.write(chunk)
        except Exception as exc:
            click.echo(f"Failed to download asset '{asset_name}': {exc}")
            if manifest_file:
                _record_dds_retry(
                    retry_file=manifest_file,
                    collection=collection,
                    item_uuid=item_uuid,
                    status="AssetDownloadError",
                    source="stac",
                    file_name=out_name,
                    file_path=out_path,
                    detail=str(exc),
                    update_existing_only=False,
                )
            continue

        downloaded_count += 1
        click.echo(f"Saved asset to {out_path}")
        if manifest_file:
            _record_dds_retry(
                retry_file=manifest_file,
                collection=collection,
                item_uuid=item_uuid,
                status="Downloaded",
                source="stac",
                file_name=out_name,
                file_path=out_path,
                update_existing_only=False,
            )

    if downloaded_count == 0:
        click.echo(f"No downloadable asset links found for collection={collection}, uuid={item_uuid}")
        if manifest_file:
            _record_dds_retry(
                retry_file=manifest_file,
                collection=collection,
                item_uuid=item_uuid,
                status="NoDownloadableAssets",
                source="stac",
                update_existing_only=False,
            )

    return downloaded_count


def _load_download_items_from_geojson(input_file: str) -> List[Dict[str, Any]]:
    try:
        with open(input_file, "r", encoding="utf-8") as src:
            raw_text = src.read().strip()
    except Exception as exc:
        raise click.ClickException(f"Failed to read input file '{input_file}': {exc}")

    if not raw_text:
        return []

    payload: Any = None
    parsed_json = False
    try:
        payload = json.loads(raw_text)
        parsed_json = True
    except json.JSONDecodeError:
        parsed_json = False

    if parsed_json:
        if isinstance(payload, dict):
            features = payload.get("features")
            if isinstance(features, list):
                return [feature for feature in features if isinstance(feature, dict)]

            manifest_items = payload.get("items")
            if isinstance(manifest_items, list):
                return [item for item in manifest_items if isinstance(item, dict)]

            # Accept a single manifest object (for example one JSONL line copied to .json)
            # when it has an identifiable item UUID/id field.
            if _extract_item_uuid(payload):
                return [payload]

            raise click.ClickException(
                "Input JSON must be GeoJSON FeatureCollection ('features') "
                "or manifest JSON with an 'items' list (or a single item object with uuid/id)."
            )

        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        raise click.ClickException("Input JSON must be an object or list.")

    # Fallback: JSON lines support for manifest files (one object per line).
    items: List[Dict[str, Any]] = []
    for idx, line in enumerate(raw_text.splitlines(), start=1):
        candidate = line.strip()
        if not candidate:
            continue
        try:
            parsed_line = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise click.ClickException(
                f"Invalid JSON line at {idx} in '{input_file}': {exc}"
            )
        if isinstance(parsed_line, dict):
            items.append(parsed_line)

    if items:
        return items

    raise click.ClickException(
        "Input file must be GeoJSON, JSON manifest records, or JSONL manifest records."
    )


def _load_download_items_from_tsv(input_file: str) -> List[Dict[str, Any]]:
    fieldnames, rows = _read_tsv_rows(input_file)

    normalized = {str(name).strip().lower(): name for name in fieldnames}
    uuid_col = (
        normalized.get("uuid")
        or normalized.get("id")
        or normalized.get("item_id")
        or normalized.get("itemid")
    )
    collection_col = normalized.get("collection")

    if not uuid_col:
        raise click.ClickException(
            "Input TSV for download must contain a 'uuid' (or id/item_id) column."
        )

    features: List[Dict[str, Any]] = []
    for row in rows:
        item_uuid = str(row.get(uuid_col) or "").strip()
        if not item_uuid:
            continue

        item_collection = ""
        if collection_col:
            item_collection = str(row.get(collection_col) or "").strip()

        feature: Dict[str, Any] = {"id": item_uuid}
        if item_collection:
            feature["collection"] = item_collection
        features.append(feature)

    return features


def _load_download_items(input_file: str) -> List[Dict[str, Any]]:
    lower_name = str(input_file or "").strip().lower()
    if lower_name.endswith(".tsv"):
        return _load_download_items_from_tsv(input_file)
    return _load_download_items_from_geojson(input_file)


def parse_legacy_order_items(order_items: str) -> Tuple[List[str], List[str]]:
    """Parse legacy order-item selector syntax: order:id1,id2|item:id3,id4"""
    order_ids: List[str] = []
    item_ids: List[str] = []

    for part in order_items.split("|"):
        part = part.strip()
        if not part or ":" not in part:
            continue

        key, raw_ids = [p.strip().lower() for p in part.split(":", 1)]
        ids = [value.strip() for value in raw_ids.split(",") if value.strip()]

        if key.startswith("order"):
            order_ids.extend(ids)
        elif key.startswith("item"):
            item_ids.extend(ids)

    return order_ids, item_ids


def _to_rapi_orders_dt_string(value: Any) -> Optional[str]:
    if value is None:
        return None

    if isinstance(value, datetime):
        dt_val = value.astimezone(timezone.utc)
        return dt_val.strftime("%Y-%m-%dT%H:%M:%SZ")

    if isinstance(value, str):
        parsed = _parse_iso_datetime(value)
        if parsed is not None:
            return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
        stripped = value.strip()
        if stripped:
            return stripped

    return None


def _build_rapi_orders_url(rapi_api: EODMSRAPI, max_orders: int,
                           dtstart: Any = None, dtend: Any = None,
                           status: Optional[str] = None,
                           out_format: str = "json") -> str:
    params: Dict[str, Any] = {"maxOrders": max_orders}

    dtstart_s = _to_rapi_orders_dt_string(dtstart)
    dtend_s = _to_rapi_orders_dt_string(dtend)
    if dtstart_s:
        params["dtstart"] = dtstart_s
    if dtend_s:
        params["dtend"] = dtend_s
    if status:
        params["status"] = status.upper()

    param_str = urlencode(params)
    return f"{rapi_api.rapi_root}/order?{param_str}&format={out_format}"


def _safe_rapi_call(callable_obj, *args, **kwargs):
    result = callable_obj(*args, **kwargs)
    if isinstance(result, QueryError):
        raise click.ClickException(result.get_msgs(as_str=True))
    return result


def _first_dict(payload: Any) -> Optional[Dict[str, Any]]:
    if isinstance(payload, dict):
        if isinstance(payload.get("results"), list):
            for entry in payload["results"]:
                found = _first_dict(entry)
                if found is not None:
                    return found
        if isinstance(payload.get("items"), list):
            for entry in payload["items"]:
                found = _first_dict(entry)
                if found is not None:
                    return found
        return payload
    if isinstance(payload, list):
        for entry in payload:
            found = _first_dict(entry)
            if found is not None:
                return found
    return None


def _extract_first_order_id(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        for key in ("orderId", "order_id", "ORDER_ID"):
            value = payload.get(key)
            if value is not None:
                return str(value)
        for key in ("results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                for entry in value:
                    found = _extract_first_order_id(entry)
                    if found:
                        return found
        return None

    if isinstance(payload, list):
        for entry in payload:
            found = _extract_first_order_id(entry)
            if found:
                return found

    return None


def _extract_order_key(stac_item: Dict[str, Any]) -> Optional[str]:
    props = stac_item.get("properties") if isinstance(stac_item, dict) else None
    if not isinstance(props, dict):
        return None

    return (
        props.get("order_key")
        or props.get("orderKey")
        or props.get("Order Key")
    )


def _extract_item_uuid(stac_item: Dict[str, Any]) -> Optional[str]:
    if not isinstance(stac_item, dict):
        return None

    for key in ("id", "uuid", "item_id", "itemId"):
        value = stac_item.get(key)
        if value is not None and str(value).strip():
            return str(value)

    props = stac_item.get("properties")
    if isinstance(props, dict):
        for key in ("uuid", "UUID", "id"):
            value = props.get(key)
            if value is not None and str(value).strip():
                return str(value)

    return None


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None

    raw = value.strip()
    if not raw:
        return None

    # Handle STAC UTC suffix format.
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    try:
        dt_val = datetime.fromisoformat(raw)
    except ValueError:
        return None

    if dt_val.tzinfo is None:
        dt_val = dt_val.replace(tzinfo=timezone.utc)

    return dt_val.astimezone(timezone.utc)


def _format_rapi_datetime(dt_val: datetime) -> str:
    return dt_val.strftime("%Y%m%d_%H%M%S")


def _build_rapi_dates_from_stac_item(stac_item: Dict[str, Any], span_days: int = 1) -> Optional[List[Dict[str, str]]]:
    props = stac_item.get("properties") if isinstance(stac_item, dict) else None
    if not isinstance(props, dict):
        return None

    start_dt = _parse_iso_datetime(
        props.get("start_datetime")
        or props.get("startDateTime")
        or props.get("acquisition_start")
        or props.get("acquisitionStart")
    )
    end_dt = _parse_iso_datetime(
        props.get("end_datetime")
        or props.get("endDateTime")
        or props.get("acquisition_end")
        or props.get("acquisitionEnd")
    )

    if start_dt is None and end_dt is None:
        center_dt = _parse_iso_datetime(
            props.get("datetime")
            or props.get("acquisition_datetime")
            or props.get("acquisitionDateTime")
        )
        if center_dt is None:
            return None
        start_dt = center_dt
        end_dt = center_dt + timedelta(days=span_days)
    elif start_dt is None and end_dt is not None:
        start_dt = end_dt - timedelta(days=span_days)
    elif end_dt is None and start_dt is not None:
        end_dt = start_dt + timedelta(days=span_days)

    if start_dt is None or end_dt is None:
        return None

    if end_dt < start_dt:
        start_dt, end_dt = end_dt, start_dt

    return [{"start": _format_rapi_datetime(start_dt), "end": _format_rapi_datetime(end_dt)}]


def _download_rapi_items(rapi_api: EODMSRAPI, items: List[Dict[str, Any]], download_dir: str,
                         manifest_file: Optional[str] = None) -> None:
    if not items:
        click.echo("No downloadable items found.")
        return

    destination = os.path.abspath(download_dir)
    os.makedirs(destination, exist_ok=True)

    click.echo(f"Downloading {len(items)} item(s) to {destination}")
    result = _safe_rapi_call(rapi_api.download, items, destination)

    if manifest_file:
        for item in items:
            if not isinstance(item, dict):
                continue

            row_collection = str(item.get("collection") or item.get("collectionId") or "").strip()
            row_uuid = str(
                item.get("uuid")
                or item.get("id")
                or item.get("item_id")
                or item.get("itemId")
                or item.get("recordId")
                or item.get("orderItemId")
                or item.get("orderId")
                or ""
            ).strip()
            if not row_uuid:
                continue

            _record_dds_retry(
                retry_file=manifest_file,
                collection=row_collection,
                item_uuid=row_uuid,
                status="DownloadRequested",
                source="rapi",
                update_existing_only=False,
            )

    if isinstance(result, list):
        click.echo(f"Downloaded/attempted {len(result)} item(s).")
    else:
        click.echo("Download request submitted.")


def _load_json_input(raw: Optional[str], label: str) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None

    candidate = raw.strip()
    if not candidate:
        return None

    if os.path.exists(candidate):
        with open(candidate, "r", encoding="utf-8") as src:
            return json.load(src)

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise click.ClickException(
            f"Invalid {label} JSON. Provide either a valid JSON string or a file path."
        ) from exc


def _fetch_sar_toolbox_schema() -> Dict[str, Any]:
    try:
        with urlopen(SAR_TOOLBOX_SCHEMA_URL) as resp:
            body = resp.read().decode("utf-8")
        schema_json = json.loads(body)
    except (URLError, ValueError) as exc:
        raise click.ClickException(f"Failed to fetch SAR Toolbox schema: {exc}") from exc

    if not isinstance(schema_json, dict):
        raise click.ClickException("Failed to fetch SAR Toolbox schema: expected a JSON object.")

    return schema_json


def _extract_sar_toolbox_category_names(schema_json: Dict[str, Any]) -> List[str]:
    categories = schema_json.get("categories")
    if not isinstance(categories, list):
        return []

    extracted: List[Tuple[int, str]] = []
    for idx, category in enumerate(categories):
        if not isinstance(category, dict):
            continue

        raw_name = category.get("name")
        name = str(raw_name or "").strip()
        if not name:
            continue

        display_order = category.get("display_order")
        try:
            sort_key = int(display_order)
        except (TypeError, ValueError):
            sort_key = idx

        extracted.append((sort_key, name))

    extracted.sort(key=lambda entry: (entry[0], entry[1].lower()))
    return [name for _, name in extracted]


def _print_process_summary(processes_json: Dict[str, Any]) -> None:
    all_processes = processes_json.get("processes", [])
    click.echo("\nProcessing Service:\n")
    for process_obj in all_processes:
        process_id = process_obj.get("id", "N/A")
        version = process_obj.get("version", "N/A")
        description = process_obj.get("description") or process_obj.get("abstract") or "N/A"
        click.echo(f"* {process_id} (v{version}): {description}")

    click.echo("\nSAR Toolbox:\n")
    try:
        schema_json = _fetch_sar_toolbox_schema()
        category_names = _extract_sar_toolbox_category_names(schema_json)
    except click.ClickException as exc:
        click.echo(f"* SAR_Toolbox: categories unavailable ({exc})")
        return

    if category_names:
        click.echo(f"* SAR_Toolbox categories: {', '.join(category_names)}")
    else:
        click.echo("* SAR_Toolbox: no categories found in remote schema")


def _example_scalar_from_schema(schema: Dict[str, Any], input_name: str) -> Any:
    if not isinstance(schema, dict):
        return "example"

    if "default" in schema:
        return schema["default"]

    enum_vals = schema.get("enum")
    if isinstance(enum_vals, list) and enum_vals:
        return enum_vals[0]

    schema_type = schema.get("type")
    schema_format = schema.get("format")

    if schema_type == "boolean":
        return True
    if schema_type in ("integer", "number"):
        return 1
    if schema_type == "array":
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            return [_example_scalar_from_schema(item_schema, input_name)]
        return ["example"]
    if schema_type == "object":
        return {}

    if schema_format == "date-time":
        return "2000-01-01T00:00:00Z"

    lower_name = input_name.lower()
    if lower_name in ("uuid", "id", "segment_id"):
        return "00000000-0000-0000-0000-000000000000"
    if lower_name in ("start_time", "stop_time"):
        return "2000-01-01T00:00:00Z"

    return "example"


def _example_value_from_input_def(input_name: str, input_def: Dict[str, Any]) -> Any:
    if not isinstance(input_def, dict):
        return "example"

    if "default" in input_def:
        return input_def["default"]

    for schema_key in ("schema", "valueSchema"):
        schema_obj = input_def.get(schema_key)
        if isinstance(schema_obj, dict):
            return _example_scalar_from_schema(schema_obj, input_name)

    return _example_scalar_from_schema(input_def, input_name)


def _build_sample_payload(process_id: str, process_json: Dict[str, Any]) -> Dict[str, Any]:
    input_defs = process_json.get("inputs", {})
    sample_inputs: Dict[str, Any] = {}

    if isinstance(input_defs, dict):
        for input_name, input_def in input_defs.items():
            sample_inputs[input_name] = _example_value_from_input_def(str(input_name), input_def)

    sample_outputs = {
        f"{process_id}-response": {
            "format": {"mediaType": "application/json"}
        }
    }

    return {
        "inputs": sample_inputs,
        "outputs": sample_outputs,
        "mode": "async",
    }


@click.group(cls=OrderedHelpGroup, context_settings={"help_option_names": ["-h", "--help"]})
def cli():
    """EODMS CLI v2: STAC/DDS-first, non-interactive with minimal legacy ports."""
    try:
        _initialize_cli_logging()
    except Exception as exc:
        click.echo(f"Warning: failed to initialize CLI file logging: {exc}")
    click.echo()


@cli.command("configure")
@click.option("--username", "username", "-u", required=False,
              help="EODMS username to store in config.ini.")
@click.option("--password", "password", "-p", required=False,
              help="EODMS password to store in config.ini.")
@click.option("--show", "show_config", is_flag=True,
              help="Print the current config.ini file and exit.")
def configure_cmd(username: Optional[str], password: Optional[str], show_config: bool):
    """Save Credentials.username/password to %USERPROFILE%\\.eodms\\config.ini."""

    cfg_path = _default_config_path()

    if show_config:
        if username or password:
            raise click.ClickException("--show cannot be combined with --username or --password.")

        if not os.path.exists(cfg_path):
            raise click.ClickException(f"Config file not found: {cfg_path}")

        click.echo(f"Config file: {cfg_path}")
        click.echo()
        with open(cfg_path, "r", encoding="utf-8") as cfg_file:
            click.echo(cfg_file.read().rstrip())
        return

    if not username or not password:
        raise click.ClickException("--username and --password are required unless --show is used.")

    cfg_path = _save_credentials_to_config(username=username, password=password)
    click.echo(f"Saved credentials to {cfg_path}")


@cli.command("search")
@click.option("--username", "-u", required=False, help="EODMS username.")
@click.option("--password", "-p", required=False, help="EODMS password.")
@click.option("--collection", "-c", required=False, help="Collection name.")
@click.option("--list", "list_collections", is_flag=True,
              help="List available STAC collections and exit.")
@click.option("--uuid2record", "uuid2record", is_flag=True,
              help="Resolve UUID to order_key (search) then recordId (RAPI).")
@click.option("--orderkey2uuid", "orderkey2uuid", is_flag=True,
              help="Resolve order_key value(s) to UUID(s) using search.")
@click.option("--uuid", required=False, default=None,
              help="UUID (or comma-separated UUIDs) used with --uuid2record.")
@click.option("--order-key", "order_key", required=False, default=None,
              help="order_key value (or comma-separated values) used with --orderkey2uuid.")
@click.option("--queryables", "show_queryables", is_flag=True,
              help="Print queryables for --collection and exit.")
@click.option("--datetime", "-d", "datetime_range", required=False, default=None,
              help='Temporal filter as ISO 8601 string/range (example: "2023-01-01/2023-12-31").')
@click.option("--bbox", "-b", required=False, default=None,
              help="Bounding box as west,south,east,north")
@click.option("--limit", "-l", required=False, default=1000, type=int,
              help="Maximum number of items to fetch (default: 1000).")
@click.option("--filter", "-f", "filter_text", required=False, default=None,
              help="CQL2 text filter expression.")
@click.option("--s-intersect", "s_intersect", required=False, default=None,
              help="WKT geometry used with S_INTERSECTS.")
@click.option("--aoi", required=False, default=None, type=click.Path(exists=True),
              help="Path to geospatial AOI file with 1-5 polygons.")
@click.option("--input", "input_file", required=False, default=None, type=click.Path(exists=True),
              help="Input TSV with order_key/order_keys and datetime columns; requires --collection and --output.")
@click.option("--output", "-o", required=False, default=None,
              help="Output file path (GeoJSON or TSV).")
@click.option("--env", "-e", required=False, default="prod",
              help='Environment (default: "prod").')
@handle_service_errors
def search_cmd(
    username: Optional[str],
    password: Optional[str],
    collection: Optional[str],
    list_collections: bool,
    uuid2record: bool,
    orderkey2uuid: bool,
    uuid: Optional[str],
    order_key: Optional[str],
    show_queryables: bool,
    datetime_range: Optional[str],
    bbox: Optional[str],
    limit: int,
    filter_text: Optional[str],
    s_intersect: Optional[str],
    aoi: Optional[str],
    input_file: Optional[str],
    output: Optional[str],
    env: str,
):
    """STAC geotemporal/queryables and GeoJSON/TSV output."""

    username, password = resolve_credentials(username, password)

    bbox_list = parse_bbox(bbox)

    aaa_api = make_aaa(username, password, env)

    if list_collections:
        search_api = make_search(aaa_api, env)
        search_api.print_collections()
        return

    if uuid2record and orderkey2uuid:
        raise click.ClickException("Use either --uuid2record or --orderkey2uuid, not both.")

    if uuid2record:
        if not uuid:
            raise click.ClickException("--uuid is required with --uuid2record.")
        if not collection:
            raise click.ClickException("--collection is required with --uuid2record.")
        if not username or not password:
            raise click.ClickException("--username and --password are required with --uuid2record.")

        search_api = make_search(aaa_api, env)
        rapi_api = EODMSRAPI(username, password)
        uuid_values = [u.strip() for u in uuid.split(",") if u.strip()]
        if not uuid_values:
            raise click.ClickException("At least one UUID must be provided.")

        for uuid_value in uuid_values:
            item = search_api.get_item(collection, uuid_value)
            if item is None:
                click.echo(f"{uuid_value}: no item found in search/{collection}")
                continue

            order_key = _extract_order_key(item)
            if not order_key:
                click.echo(f"{uuid_value}: no order_key on STAC item")
                continue

            filter_dict = {"ARCHIVE_IMAGE.ORDER_KEY": ("=", [order_key])}
            rapi_dates = _build_rapi_dates_from_stac_item(item, span_days=1)
            try:
                search_kwargs: Dict[str, Any] = {
                    "filters": filter_dict,
                    "max_results": 5,
                }
                if rapi_dates:
                    search_kwargs["dates"] = rapi_dates

                _safe_rapi_call(rapi_api.search, collection, **search_kwargs)
                payload = _safe_rapi_call(rapi_api.get_results, "brief", show_progress=False)
            except Exception as exc:
                click.echo(f"{uuid_value}: order_key={order_key}; RAPI lookup error: {exc}")
                continue

            record = _first_dict(payload)
            record_id = None
            if isinstance(record, dict):
                record_id = (
                    record.get("recordId")
                    or record.get("record_id")
                    or record.get("RECORD_ID")
                )

            if record_id:
                click.echo(f"{uuid_value}: order_key={order_key}; record_id={record_id}")
            else:
                click.echo(f"{uuid_value}: order_key={order_key}; record_id not found")
        return

    if orderkey2uuid:
        if not order_key:
            raise click.ClickException("--order-key is required with --orderkey2uuid.")
        if not collection:
            raise click.ClickException("--collection is required with --orderkey2uuid.")

        search_api = make_search(aaa_api, env)
        order_key_values = [value.strip() for value in order_key.split(",") if value.strip()]
        if not order_key_values:
            raise click.ClickException("At least one order_key value must be provided.")

        items_by_order_key = _search_items_by_order_keys(
            search_api,
            collection,
            order_key_values,
            chunk_size=100,
        )

        for order_key_value in order_key_values:
            item = items_by_order_key.get(order_key_value)
            if item is None:
                click.echo(f"{order_key_value}: no item found in search/{collection}")
                continue

            item_uuid = _extract_item_uuid(item)
            if item_uuid:
                click.echo(f"{order_key_value}: uuid={item_uuid}")
            else:
                click.echo(f"{order_key_value}: uuid not found")
        return

    if show_queryables:
        if not collection:
            raise click.ClickException("--collection is required with --queryables.")

        search_api = make_search(aaa_api, env)
        coll = search_api.client.get_collection(collection)
        if coll is None:
            raise click.ClickException(f"Collection not found: {collection}")

        search_api.print_queryables(coll)
        return

    if input_file:
        if not collection:
            raise click.ClickException("--collection is required with --input.")
        if not output:
            raise click.ClickException("--output is required with --input.")

        input_fields, input_rows = _read_tsv_rows(input_file)
        order_key_column = _get_tsv_order_key_column(input_fields)
        datetime_column = _get_tsv_datetime_column(input_fields)
        if not order_key_column or not datetime_column:
            raise click.ClickException(
                "Input TSV must contain both order_key/order_keys and datetime columns."
            )

        search_api = make_search(aaa_api, env)
        output_fields = list(input_fields)
        for field_name in ("uuid", "geometry"):
            if field_name not in output_fields:
                output_fields.append(field_name)

        row_date_ranges: List[List[str]] = []
        unique_date_ranges = set()
        for row in input_rows:
            datetime_value = str(row.get(datetime_column) or "").strip()
            date_values = _extract_search_dates_for_row(datetime_value)
            date_ranges = [f"{date_value}/{date_value}" for date_value in date_values]
            row_date_ranges.append(date_ranges)
            unique_date_ranges.update(date_ranges)

        items_by_date_range: Dict[str, List[Dict[str, Any]]] = {}
        for date_range in sorted(unique_date_ranges):
            items = search_api.search_multiple_geometries(
                s_intersect_list=[{"name": None, "wkt": None}],
                collection=collection,
                datetime_range=date_range,
                bbox=bbox_list,
                limit=limit,
                filter_text=filter_text,
            )
            items_by_date_range[date_range] = items or []

        matched_count = 0
        for row, date_ranges in zip(input_rows, row_date_ranges):
            row["uuid"] = ""
            row["geometry"] = ""

            order_key = str(row.get(order_key_column) or "").strip()
            if not order_key or not date_ranges:
                continue

            matched_item = None
            for date_range in date_ranges:
                items = items_by_date_range.get(date_range) or []
                for item in items:
                    if _matches_title_or_order_key(item, order_key):
                        matched_item = item
                        break
                if matched_item:
                    break

            if not matched_item:
                continue

            item_uuid = _extract_item_uuid(matched_item)
            if item_uuid is not None:
                row["uuid"] = item_uuid

            item_geometry = matched_item.get("geometry") if isinstance(matched_item, dict) else None
            if isinstance(item_geometry, dict):
                row["geometry"] = json.dumps(item_geometry, separators=(",", ":"))

            matched_count += 1

        output_ext = os.path.splitext(str(output))[1].lower()
        if output_ext in (".geojson", ".json"):
            feature_count = _write_input_rows_geojson(output, input_rows, geometry_field="geometry")
            click.echo(
                f"Saved {feature_count} feature(s) to {output}; "
                f"searched {len(unique_date_ranges)} calendar day(s); matched {matched_count} row(s)."
            )
        else:
            _write_tsv_rows(output, output_fields, input_rows)
            click.echo(
                f"Saved {len(input_rows)} row(s) to {output}; "
                f"searched {len(unique_date_ranges)} calendar day(s); matched {matched_count} row(s)."
            )
        return

    if not collection:
        raise click.ClickException("--collection is required unless --list is used.")

    s_intersect_list: List[Dict[str, Any]] = []
    if aoi:
        try:
            s_intersect_list = parse_aoi_file(aoi)
            click.echo(f"Loaded {len(s_intersect_list)} polygon(s) from AOI file")
        except ValueError as exc:
            raise click.ClickException(str(exc))
    elif s_intersect:
        s_intersect_list = [{"name": None, "wkt": s_intersect}]

    if not s_intersect_list:
        s_intersect_list = [{"name": None, "wkt": None}]

    # Set default datetime range if not provided
    if datetime_range is None:
        cfg = _load_config_utils()
        default_days = int(cfg.get('Search', 'default_date_range_days') or '90')
        now = datetime.now()
        start_date = now - timedelta(days=default_days)
        datetime_range = f"{start_date.strftime('%Y-%m-%d')}/{now.strftime('%Y-%m-%d')}"
        click.echo(f"Using default date range ({default_days} days): {datetime_range}")

    search_api = make_search(aaa_api, env)
    items = search_api.search_multiple_geometries(
        s_intersect_list=s_intersect_list,
        collection=collection,
        datetime_range=datetime_range,
        bbox=bbox_list,
        limit=limit,
        filter_text=filter_text,
    )

    if not items:
        click.echo("No items found.")
        return

    click.echo(f"Found {len(items)} item(s).")

    if output:
        save_items_geojson(items, output)
        return

    preview_uuids: List[str] = []
    for item in items:
        item_uuid = _extract_item_uuid(item)
        if item_uuid:
            preview_uuids.append(item_uuid)
        if len(preview_uuids) == 5:
            break

    if preview_uuids:
        click.echo("First 5 UUID(s):")
        for item_uuid in preview_uuids:
            click.echo(item_uuid)
    else:
        click.echo("No UUID values found in search results.")


@cli.command("process")
@click.option("--username", "-u", required=False, help="EODMS username.")
@click.option("--password", "-p", required=False, help="EODMS password.")
@click.option("--env", "-e", required=False, default="prod",
              help='Environment (default: "prod").')
@click.option("--process_id", "-pi", required=False, default=None,
              help="Processing service ID.")
@click.option("--list/--no-list", "list_processes", default=True,
              help="List available processes (default behavior).")
@click.option("--describe", "describe", is_flag=True,
              help="Print process input structure and sample payload.")
@click.option("--submit", is_flag=True,
              help="Submit a processing job (requires auth).")
@click.option("--inputs_json", "--input_json", required=False, default=None,
              help="JSON string or path to JSON file for submit inputs.")
@click.option("--outputs_json", required=False, default=None,
              help="JSON string or path to JSON file for generic submit outputs.")
@click.option("--mode", required=False, default="async",
              help="Execution mode for generic submit (default: async).")
@click.option("--job_id", "-j", required=False, default=None,
              help="Existing job ID to check, poll, retrieve results, or download outputs.")
@click.option("--wait", is_flag=True,
              help="Poll job status until terminal state.")
@click.option("--interval", required=False, default=30, type=int,
              help="Polling interval seconds for --wait (default: 30).")
@click.option("--timeout", required=False, default=600, type=int,
              help="Polling timeout seconds for --wait (default: 600).")
@click.option("--show_results", is_flag=True,
              help="Print job results JSON.")
@click.option("--download_dir", "-dl", required=False, default=None,
              help="Download all job result files to this folder.")
@click.option("--skip_existing/--no-skip_existing", default=True,
              help="Skip existing local files when downloading results (default: enabled).")
@click.option("--output", "-o", required=False, default=None,
              help="Write JSON response (process details or submit response) to file.")
@handle_service_errors
def order_st_cmd(
    username: Optional[str],
    password: Optional[str],
    env: str,
    process_id: Optional[str],
    list_processes: bool,
    describe: bool,
    submit: bool,
    inputs_json: Optional[str],
    outputs_json: Optional[str],
    mode: str,
    job_id: Optional[str],
    wait: bool,
    interval: int,
    timeout: int,
    show_results: bool,
    download_dir: Optional[str],
    skip_existing: bool,
    output: Optional[str],
):
    """Processing Service for RADARDAT data; Level-1, SAR Toolbox, and ARD."""

    username, password = resolve_credentials(username, password)

    aaa_api = make_aaa(username, password, env)
    proc_api = make_processes(aaa_api, env)

    if list_processes and not submit and not describe and not job_id:
        processes_json = proc_api.list_processes()
        _print_process_summary(processes_json)
        return

    if describe:
        if not process_id:
            raise click.UsageError("--process_id is required with --describe")

        if str(process_id).strip() == "SAR_Toolbox":
            schema_json = _fetch_sar_toolbox_schema()

            click.echo(json.dumps(schema_json, indent=4))
            if output:
                with open(output, "w", encoding="utf-8") as out_f:
                    json.dump(schema_json, out_f, indent=2)
                click.echo(f"Saved SAR Toolbox schema to {output}")
            return

        process_json = proc_api.get_process(process_id)
        click.echo(json.dumps(process_json.get("inputs", {}), indent=4))

        sample_payload = _build_sample_payload(process_id, process_json)
        click.echo("\nSample execution payload:")
        click.echo(json.dumps(sample_payload, indent=4))

        if output:
            with open(output, "w", encoding="utf-8") as out_f:
                json.dump(process_json, out_f, indent=2)
            click.echo(f"Saved process description to {output}")
        return

    submitted_job_id = None
    if submit:
        if not process_id:
            raise click.UsageError("--process_id is required with --submit")
        if aaa_api is None:
            raise click.UsageError("--username and --password are required with --submit")

        loaded_inputs = _load_json_input(inputs_json, "inputs")
        if str(process_id).strip() == "SAR_Toolbox":
            if loaded_inputs is None:
                raise click.UsageError("--input_json (or --inputs_json) is required with --submit for SAR_Toolbox")

            sar_request = loaded_inputs
            if isinstance(loaded_inputs, dict) and "inputs" in loaded_inputs and isinstance(loaded_inputs.get("inputs"), dict):
                nested_inputs = loaded_inputs.get("inputs")
                if isinstance(nested_inputs, dict) and "items" in nested_inputs:
                    sar_request = nested_inputs

            if not isinstance(sar_request, dict) or not isinstance(sar_request.get("items"), list):
                raise click.UsageError(
                    "SAR_Toolbox submit expects a JSON request containing an 'items' list "
                    "(same structure used by legacy order_st / st_request)."
                )

            rapi_api = EODMSRAPI(username, password)
            submit_json = _safe_rapi_call(rapi_api.order_json, sar_request)
            click.echo(json.dumps(submit_json, indent=2))

            if output:
                with open(output, "w", encoding="utf-8") as out_f:
                    json.dump(submit_json, out_f, indent=2)
                click.echo(f"Saved submission response to {output}")

            if download_dir:
                order_id = _extract_first_order_id(submit_json)
                if not order_id:
                    raise click.ClickException("No orderId found in SAR_Toolbox submit response; cannot download.")
                order_payload = _safe_rapi_call(rapi_api.get_order, order_id)
                order_items = _safe_rapi_call(rapi_api.collect_order_items, order_payload)
                _download_rapi_items(
                    rapi_api,
                    order_items,
                    download_dir,
                    manifest_file=_resolve_downloads_manifest_path(download_dir),
                )

            return

        outputs = _load_json_input(outputs_json, "outputs")
        if loaded_inputs is None:
            raise click.UsageError("--inputs_json is required with --submit")

        request_mode = mode
        if isinstance(loaded_inputs, dict) and "inputs" in loaded_inputs:
            inputs = loaded_inputs.get("inputs")
            if outputs is None and isinstance(loaded_inputs.get("outputs"), dict):
                outputs = loaded_inputs.get("outputs")
            if isinstance(loaded_inputs.get("mode"), str) and loaded_inputs.get("mode").strip():
                request_mode = loaded_inputs.get("mode").strip()
        else:
            inputs = loaded_inputs

        if not isinstance(inputs, dict):
            raise click.UsageError("Resolved submit inputs must be a JSON object.")

        submit_json = proc_api.submit_process(
            process_id=process_id,
            inputs=inputs,
            outputs=outputs,
            mode=request_mode,
        )

        click.echo(json.dumps(submit_json, indent=2))
        submitted_job_id = submit_json.get("jobID")
        click.echo(f"Submitted jobID: {submitted_job_id}")

        if output:
            with open(output, "w", encoding="utf-8") as out_f:
                json.dump(submit_json, out_f, indent=2)
            click.echo(f"Saved submission response to {output}")

    target_job_id = job_id or submitted_job_id

    if wait:
        if not target_job_id:
            raise click.UsageError("A job ID is required for --wait (provide --job_id or --submit)")
        status_json = proc_api.poll_job_status(target_job_id, interval=interval, timeout=timeout)
        click.echo(json.dumps(status_json, indent=2))
    elif target_job_id and not show_results and not download_dir:
        status_json = proc_api.get_job_status(target_job_id)
        click.echo(json.dumps(status_json, indent=2))

    if show_results:
        if not target_job_id:
            raise click.UsageError("A job ID is required for --show_results")
        results_json = proc_api.get_job_results(target_job_id)
        click.echo(json.dumps(results_json, indent=2))

    if download_dir:
        if not target_job_id:
            raise click.UsageError("A job ID is required for --download_dir")
        downloaded = proc_api.download_job_results(
            job_id=target_job_id,
            out_dir=os.path.abspath(download_dir),
            skip_existing=skip_existing,
        )
        click.echo(json.dumps({"jobID": target_job_id, "downloaded_files": downloaded}, indent=2))


@cli.command("download")
@click.option("--username", "-u", required=False, help="EODMS username.")
@click.option("--password", "-p", required=False, help="EODMS password.")
@click.option("--uuid", required=False, default=None,
              help="Download UUID directly via STAC assets (public collections) or DDS.")
@click.option("--input", "input_file", required=False, default=None, type=click.Path(exists=True),
              help="Input file for download items (TSV, GeoJSON, JSON, or JSONL). Use downloads.jsonl here to replay tracked items.")
@click.option("--collection", "-c", required=False, default=None,
              help="Collection for --uuid download.")
@click.option("--env", "-e", required=False, default="prod",
              help='Environment for DDS download (default: "prod").')
@click.option("--order-items", required=False, default=None,
              help="Legacy selector syntax: order:id1,id2|item:id3,id4")
@click.option("--limit", "-l", required=False, default=100, type=int,
              help="Maximum AVAILABLE_FOR_DOWNLOAD orders to retrieve.")
@click.option("--dtstart", required=False, default=None,
              help="Optional start datetime filter for order retrieval.")
@click.option("--dtend", required=False, default=None,
              help="Optional end datetime filter for order retrieval.")
@click.option("--list", "list_orders", is_flag=True,
              help="List orders in the last 30 days and exit (no download).")
@click.option("--order-id", "order_id_filter", required=False, default=None,
              help="Fetch a specific order by ID with --list (skips date-range query).")
@click.option("--order-status", required=False, default=None,
              help="Optional status filter for --list (example: AVAILABLE_FOR_DOWNLOAD).")
@click.option("--download-available", is_flag=True,
              help="Download AVAILABLE_FOR_DOWNLOAD order items (required for default bulk download mode).")
@click.option("--dl_dir", "download_dir", required=False, default=".\\downloads",
              help="Destination directory for downloads.")
@click.option("--download-dir", "download_dir", required=False,
              help="Destination directory for downloads.")
@click.option("--cart-url", "cart_urls", required=False, multiple=True,
              help="HTTP cart directory URL to recursively download. Can be provided multiple times.")
@handle_service_errors
def download_available_cmd(
    username: Optional[str],
    password: Optional[str],
    uuid: Optional[str],
    input_file: Optional[str],
    collection: Optional[str],
    env: str,
    order_items: Optional[str],
    limit: int,
    dtstart: Optional[str],
    dtend: Optional[str],
    list_orders: bool,
    order_id_filter: Optional[str],
    order_status: Optional[str],
    download_available: bool,
    download_dir: str,
    cart_urls: Tuple[str, ...],
):
    """Download by UUID (public STAC assets or DDS) and legacy RAPI order-item downloads."""

    username, password = resolve_credentials(username, password)
    dds_backoff_seconds = _load_dds_backoff_interval()
    dds_concurrent_downloads = _load_dds_concurrent_downloads()

    if uuid and input_file:
        raise click.ClickException("Use either --uuid or --input, not both.")

    if cart_urls:
        if any([uuid, input_file, order_items, order_id_filter, list_orders, download_available]):
            raise click.ClickException(
                "--cart-url cannot be combined with UUID/input/order download options."
            )

        manifest_file_for_run = _resolve_downloads_manifest_path(download_dir)
        click.echo(f"Download manifest path: {os.path.abspath(manifest_file_for_run)}")

        total_downloaded = 0
        total_skipped_existing = 0
        total_errors = 0
        failed_carts = 0

        for cart_url in cart_urls:
            click.echo(f"Recursively downloading cart URL: {cart_url}")
            try:
                summary = download_http_cart_directory(
                    cart_url=cart_url,
                    download_dir=download_dir,
                    username=username,
                    password=password,
                    manifest_file=manifest_file_for_run,
                )
            except click.ClickException as exc:
                failed_carts += 1
                click.echo(f"Cart download failed for {cart_url}: {exc}")
                continue

            total_downloaded += int(summary.get("downloaded", 0) or 0)
            total_skipped_existing += int(summary.get("skipped_existing", 0) or 0)
            total_errors += int(summary.get("errors", 0) or 0)

        if failed_carts == len(cart_urls):
            raise click.ClickException("All cart URL downloads failed.")

        click.echo(
            "Cart download summary: "
            f"downloaded={total_downloaded}, skipped_existing={total_skipped_existing}, "
            f"errors={total_errors}, failed_cart_urls={failed_carts}"
        )
        return

    if input_file:
        features = _load_download_items(input_file)
        if not features:
            click.echo("No items found in input file.")
            return

        # Download activity is tracked in a manifest inside the active
        # download directory and updated for every status transition.
        input_abs = os.path.abspath(input_file)
        update_retry_existing_only = False
        manifest_file_for_run = _resolve_downloads_manifest_path(download_dir)

        input_suffix = str(input_file).strip().lower()
        is_manifest_input = input_suffix.endswith(".manifest") or input_suffix.endswith(".jsonl")
        if is_manifest_input:
            deduped_count = _compact_dds_retry_file(input_file)
            if deduped_count:
                click.echo(
                    f"Compacted download manifest to {deduped_count} unique item(s): {input_abs}"
                )
                features = _load_download_items(input_file)

        click.echo(
            f"Download manifest path: {os.path.abspath(manifest_file_for_run)}"
        )

        aaa_api = make_aaa(username, password, env)
        search_api = None
        dds_api = None
        dds_work_items: List[Tuple[str, str]] = []

        total_features = len(features)
        processed_count = 0
        skipped_count = 0
        asset_download_count = 0
        dds_download_count = 0
        dds_retry_logged_count = 0
        dds_no_download_count = 0

        click.echo(f"Found {total_features} item(s) in input file.")
        for feature in features:
            item_uuid = _extract_item_uuid(feature)
            item_collection = collection or feature.get("collection")

            if not item_collection and isinstance(feature.get("properties"), dict):
                item_collection = feature.get("properties", {}).get("collection")

            if not item_uuid:
                click.echo("Skipping item with no UUID/id field.")
                skipped_count += 1
                continue

            if not item_collection:
                click.echo(f"Skipping uuid={item_uuid}: no collection on feature and no --collection override.")
                skipped_count += 1
                continue

            if _is_public_asset_collection(str(item_collection)):
                if search_api is None:
                    search_api = make_search(aaa_api, env)
                click.echo(f"Downloading public assets: collection={item_collection}, uuid={item_uuid}")
                downloaded_assets = download_public_stac_assets(
                    search_api,
                    str(item_collection),
                    item_uuid,
                    download_dir,
                    manifest_file=manifest_file_for_run,
                )
                asset_download_count += downloaded_assets
                processed_count += 1
                continue

            if not username or not password:
                click.echo(
                    f"Skipping uuid={item_uuid} in collection={item_collection}: credentials required for DDS."
                )
                skipped_count += 1
                continue

            if dds_api is None:
                dds_api = make_dds(aaa_api, env)
            dds_work_items.append((str(item_collection), item_uuid))

        if dds_work_items:
            click.echo(
                f"Downloading {len(dds_work_items)} DDS item(s) with "
                f"up to {dds_concurrent_downloads} concurrent worker(s)..."
            )

            def _dds_worker(work_item: Tuple[str, str]) -> Optional[Dict[str, Any]]:
                work_collection, work_uuid = work_item
                click.echo(f"Downloading DDS item: collection={work_collection}, uuid={work_uuid}")
                return download_dds_item(
                    dds_api,
                    work_collection,
                    work_uuid,
                    download_dir,
                    queued_backoff_seconds=dds_backoff_seconds,
                    retry_file=manifest_file_for_run,
                    update_retry_existing_only=update_retry_existing_only,
                )

            with ThreadPoolExecutor(max_workers=dds_concurrent_downloads) as executor:
                future_map = {
                    executor.submit(_dds_worker, work_item): work_item
                    for work_item in dds_work_items
                }

                for future in as_completed(future_map):
                    work_collection, work_uuid = future_map[future]
                    try:
                        item_info = future.result()
                    except Exception as exc:
                        click.echo(
                            f"DDS download failed: collection={work_collection}, "
                            f"uuid={work_uuid}, error={exc}"
                        )
                        dds_no_download_count += 1
                        continue

                    if isinstance(item_info, dict):
                        manifest_status = _normalize_status(item_info.get("_manifest_status") or item_info.get("status"))
                        if manifest_status in {"DOWNLOADED", "SKIPPEDEXISTING"}:
                            dds_download_count += 1
                        elif item_info.get("_dds_retry_logged"):
                            dds_retry_logged_count += 1
                        else:
                            dds_no_download_count += 1
                    elif item_info is not None:
                        dds_download_count += 1
                    else:
                        dds_no_download_count += 1

            processed_count += len(dds_work_items)

        click.echo(
            "Input download summary: "
            f"processed_features={processed_count}, skipped_features={skipped_count}, "
            f"public_assets_downloaded={asset_download_count}, dds_items_downloaded={dds_download_count}, "
            f"dds_retry_logged={dds_retry_logged_count}, dds_not_downloaded={dds_no_download_count}"
        )
        return

    if uuid:
        if not collection:
            raise click.ClickException("--collection is required when using --uuid.")

        if _is_public_asset_collection(collection):
            aaa_api = make_aaa(username, password, env)
            search_api = make_search(aaa_api, env)
            click.echo(f"Downloading all available STAC assets for UUID: {uuid}")
            downloaded_count = download_public_stac_assets(
                search_api,
                collection,
                uuid,
                download_dir,
                manifest_file=_resolve_downloads_manifest_path(download_dir),
            )
            click.echo(f"Downloaded {downloaded_count} asset(s).")
            return

        if not username or not password:
            raise click.ClickException(
                "--username and --password are required for DDS UUID downloads "
                "(non-public collections)."
            )

        aaa_api = make_aaa(username, password, env)
        dds_api = make_dds(aaa_api, env)
        click.echo(f"Downloading UUID: {uuid}")
        download_dds_item(
            dds_api,
            collection,
            uuid,
            download_dir,
            queued_backoff_seconds=dds_backoff_seconds,
            retry_file=_resolve_downloads_manifest_path(download_dir),
            update_retry_existing_only=False,
        )
        return

    if not username or not password:
        raise click.ClickException(
            "--username and --password are required for order listing/downloading."
        )

    if not order_items and not order_id_filter and not list_orders and not download_available:
        raise click.ClickException(
            "Use --download-available to download AVAILABLE_FOR_DOWNLOAD items, "
            "or use --list to list only."
        )

    rapi_api = EODMSRAPI(username, password)

    if list_orders:
        if order_id_filter:
            click.echo(f"Getting order: {order_id_filter}...")
            payload = _safe_rapi_call(rapi_api.get_order, order_id_filter)
            items = _safe_rapi_call(rapi_api.collect_order_items, payload) if payload else []
            if not items:
                click.echo(f"No items found for order {order_id_filter}.")
                return

            click.echo(f"\nFound {len(items)} item(s) in order {order_id_filter}.")
            for item in items:
                click.echo(json.dumps(item, indent=2, ensure_ascii=True))
            return

        if dtstart and dtend:
            list_dtstart = _parse_iso_datetime(dtstart)
            list_dtend = _parse_iso_datetime(dtend)
            if list_dtstart is None or list_dtend is None:
                raise click.ClickException("--dtstart and --dtend must be ISO datetime strings (example: 2026-05-21T00:00:00Z).")
            list_dtstart_label = str(dtstart)
            list_dtend_label = str(dtend)
        else:
            now_utc = datetime.now(timezone.utc)
            list_dtend = now_utc
            list_dtstart = now_utc - timedelta(days=30)
            list_dtstart_label = _format_rapi_datetime(list_dtstart)
            list_dtend_label = _format_rapi_datetime(list_dtend)

        click.echo(f"Getting list of orders from {list_dtstart_label} to {list_dtend_label}...")
        list_params: Dict[str, Any] = {
            "maxOrders": limit,
            "dtstart": _to_rapi_orders_dt_string(list_dtstart),
            "dtend": _to_rapi_orders_dt_string(list_dtend),
            "status": order_status.upper() if order_status else None,
            "collection": collection,
            "env": env,
        }
        click.echo(f"List parameters: {json.dumps(list_params, indent=2)}")
        request_url = _build_rapi_orders_url(
            rapi_api,
            max_orders=limit,
            dtstart=list_dtstart,
            dtend=list_dtend,
            status=order_status,
        )
        click.echo(f"RAPI GET URL: {request_url}")
        payload = _safe_rapi_call(
            rapi_api.get_order_summaries,
            max_orders=limit,
            dtstart=list_dtstart,
            dtend=list_dtend,
            status=order_status,
        )
        orders = payload or []

        if not orders:
            click.echo("No orders found.")
            return

        click.echo(f"\nFound {len(orders)} order(s).")
        for order in orders:
            flat_order = {
                "order_id": order.get("order_id") or "N/A",
                "status": order.get("status") or "N/A",
                "submitted": order.get("submitted") or "N/A",
                "updated": order.get("updated") or "N/A",
                "priority": order.get("priority") or "N/A",
                "items": order.get("items") if order.get("items") is not None else 0,
                "record_ids": order.get("record_ids") or [],
                "collections": order.get("collections") or [],
                "name": order.get("names") or [],
                "destinations": order.get("destinations") or [],
            }
            click.echo(json.dumps(flat_order, indent=2, ensure_ascii=True))
        return

    downloadable_items: List[Dict[str, Any]] = []
    filtered_items: List[Dict[str, Any]] = []

    if order_items or order_id_filter:
        if order_id_filter:
            payload = _safe_rapi_call(rapi_api.get_order, order_id_filter)
            downloadable_items.extend(_safe_rapi_call(rapi_api.collect_order_items, payload))

        order_ids: List[str] = []
        item_ids: List[str] = []
        if order_items:
            order_ids, item_ids = parse_legacy_order_items(order_items)

        for order_id in order_ids:
            payload = _safe_rapi_call(rapi_api.get_order, order_id)
            downloadable_items.extend(_safe_rapi_call(rapi_api.collect_order_items, payload))

        for item_id in item_ids:
            payload = _safe_rapi_call(rapi_api.get_order_item, item_id)
            downloadable_items.extend(_safe_rapi_call(rapi_api.collect_order_items, payload))

        # Explicit order/item selectors can include non-downloadable states.
        for item in downloadable_items:
            status = str(item.get("status", "")).upper()
            if not status or status == "AVAILABLE_FOR_DOWNLOAD":
                filtered_items.append(item)
    else:
        bulk_dtstart = _parse_iso_datetime(dtstart) if dtstart else None
        bulk_dtend = _parse_iso_datetime(dtend) if dtend else None
        if (dtstart and bulk_dtstart is None) or (dtend and bulk_dtend is None):
            raise click.ClickException("--dtstart and --dtend must be ISO datetime strings (example: 2026-05-21T00:00:00Z).")

        payload = _safe_rapi_call(
            rapi_api.list_order_items,
            max_orders=limit,
            dtstart=bulk_dtstart,
            dtend=bulk_dtend,
            status="AVAILABLE_FOR_DOWNLOAD",
        )
        filtered_items = list(payload or [])

    if not filtered_items:
        click.echo("No AVAILABLE_FOR_DOWNLOAD order items found.")
        return

    click.echo(f"Found {len(filtered_items)} AVAILABLE_FOR_DOWNLOAD item(s).")

    _download_rapi_items(
        rapi_api,
        filtered_items,
        download_dir,
        manifest_file=_resolve_downloads_manifest_path(download_dir),
    )


if __name__ == "__main__":
    cli()
