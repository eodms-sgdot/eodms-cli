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
import configparser
import base64
import binascii
import logging
import logging.handlers as handlers
import time
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from urllib.error import URLError
from urllib.parse import quote, urlencode, unquote, urlsplit
from urllib.request import urlopen
from typing import Any, Dict, List, Optional, Tuple

import click
import fiona
from shapely.geometry import shape

from eodms import Processes_API, aaa, dds, search
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
DEFAULT_DDS_RETRY_FILE = ".\\downloads\\dds_retry_items.jsonl"
MAX_DDS_QUEUED_WAITS = 10
CLI_DEFAULT_LOG_NAME = "eodms_cli.log"
CLI_DEFAULT_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

_CLI_LOG_INITIALIZED = False
_CLI_LOG_PATH: Optional[str] = None
_CLI_LOG_DATEFMT = CLI_DEFAULT_LOG_DATEFMT


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


def _load_config_parser(config_path: Optional[str] = None) -> Optional[configparser.ConfigParser]:
    cfg_path = config_path or _default_config_path()
    if not os.path.exists(cfg_path):
        return None

    parser = configparser.ConfigParser(comment_prefixes='/', allow_no_value=True)
    parser.read(cfg_path)
    return parser


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
    parser = _load_config_parser(config_path)
    raw_log_path: Optional[str] = None

    if parser is not None and parser.has_section("Paths") and parser.has_option("Paths", "log"):
        raw_log_path = parser.get("Paths", "log")

    return _resolve_cli_log_path(raw_log_path)


def _load_cli_log_datefmt(config_path: Optional[str] = None) -> str:
    parser = _load_config_parser(config_path)
    if parser is None or not parser.has_section("Logging"):
        return CLI_DEFAULT_LOG_DATEFMT

    if parser.has_option("Logging", "datefmt"):
        value = parser.get("Logging", "datefmt").strip()
        if value:
            return value

    return CLI_DEFAULT_LOG_DATEFMT


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
    global _CLI_LOG_INITIALIZED, _CLI_LOG_PATH, _CLI_LOG_DATEFMT
    if _CLI_LOG_INITIALIZED:
        return

    _CLI_LOG_PATH = _load_cli_log_path()
    _CLI_LOG_DATEFMT = _load_cli_log_datefmt()
    _setup_file_logger("eodms_cli", _CLI_LOG_PATH, datefmt=_CLI_LOG_DATEFMT)
    _setup_package_logger(_CLI_LOG_PATH, datefmt=_CLI_LOG_DATEFMT)

    logging.getLogger("eodms_cli").info("CLI start time: %s", datetime.now().strftime(_CLI_LOG_DATEFMT))
    _CLI_LOG_INITIALIZED = True


def _decode_config_password(raw_password: str) -> str:
    try:
        return base64.b64decode(raw_password).decode("utf-8")
    except binascii.Error:
        return base64.b64decode(raw_password + "========").decode("utf-8")


def _load_credentials_from_config(config_path: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    parser = _load_config_parser(config_path)
    if parser is None:
        return None, None

    username = None
    password = None

    for section in ("Credentials", "RAPI"):
        if username is None and parser.has_option(section, "username"):
            candidate = parser.get(section, "username").strip()
            if candidate:
                username = candidate

        if password is None and parser.has_option(section, "password"):
            encoded = parser.get(section, "password").strip()
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
    parser = _load_config_parser(config_path)
    if parser is None or not parser.has_section("DDS"):
        return DEFAULT_DDS_BACKOFF_SECONDS

    for option_name in ("backoff_interval", "back_interval"):
        if parser.has_option("DDS", option_name):
            value = parser.get("DDS", option_name).strip()
            try:
                parsed = int(value)
                if parsed > 0:
                    return parsed
            except ValueError:
                continue

    return DEFAULT_DDS_BACKOFF_SECONDS


def _load_dds_concurrent_downloads(config_path: Optional[str] = None) -> int:
    parser = _load_config_parser(config_path)
    if parser is None or not parser.has_section("DDS"):
        return DEFAULT_DDS_CONCURRENT_DOWNLOADS

    if parser.has_option("DDS", "concurrent_downloads"):
        value = parser.get("DDS", "concurrent_downloads").strip()
        try:
            parsed = int(value)
            if parsed > 0:
                return parsed
        except ValueError:
            pass

    return DEFAULT_DDS_CONCURRENT_DOWNLOADS


def _save_credentials_to_config(username: str, password: str,
                                config_path: Optional[str] = None) -> str:
    cfg_path = config_path or _default_config_path()
    cfg_dir = os.path.dirname(cfg_path)
    if cfg_dir:
        os.makedirs(cfg_dir, exist_ok=True)

    parser = configparser.ConfigParser(comment_prefixes='/', allow_no_value=True)
    if os.path.exists(cfg_path):
        parser.read(cfg_path)

    if not parser.has_section("Credentials"):
        parser.add_section("Credentials")

    parser.set("Credentials", "username", username)
    encoded_password = base64.b64encode(password.encode("utf-8")).decode("utf-8")
    parser.set("Credentials", "password", encoded_password)

    with open(cfg_path, "w", encoding="utf-8") as cfg_file:
        parser.write(cfg_file, space_around_delimiters=True)

    return cfg_path


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


def _append_dds_retry_item(retry_file: str, collection: str, item_uuid: str, status: str,
                           timestamp: Optional[str] = None) -> None:
    retry_path = os.path.abspath(retry_file)
    normalized_collection = str(collection or "").strip().lower()
    normalized_uuid = str(item_uuid or "").strip().lower()
    normalized_status = _normalize_status(status)
    resolved_timestamp = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    rows: List[Tuple[str, Any]] = []
    duplicate_found = False

    # Refresh timestamp for existing retry rows with same collection/uuid/status.
    if os.path.exists(retry_path):
        try:
            with open(retry_path, "r", encoding="utf-8") as in_f:
                for line in in_f:
                    candidate = line.strip()
                    if not candidate:
                        rows.append(("raw", ""))
                        continue
                    try:
                        row = json.loads(candidate)
                    except json.JSONDecodeError:
                        rows.append(("raw", candidate))
                        continue

                    if not isinstance(row, dict):
                        rows.append(("raw", candidate))
                        continue

                    row_collection = str(row.get("collection", "")).strip().lower()
                    row_uuid = str(
                        row.get("uuid")
                        or row.get("id")
                        or row.get("item_id")
                        or row.get("itemId")
                        or ""
                    ).strip().lower()
                    row_status = _normalize_status(str(row.get("status", "")))

                    if (
                        row_collection == normalized_collection
                        and row_uuid == normalized_uuid
                        and row_status == normalized_status
                    ):
                        row["timestamp"] = resolved_timestamp
                        row["status"] = status
                        duplicate_found = True

                    rows.append(("json", row))

            if duplicate_found:
                retry_dir = os.path.dirname(retry_path)
                if retry_dir:
                    os.makedirs(retry_dir, exist_ok=True)

                with open(retry_path, "w", encoding="utf-8") as out_f:
                    for row_type, row_value in rows:
                        if row_type == "json":
                            out_f.write(json.dumps(row_value, ensure_ascii=True) + "\n")
                        elif row_value == "":
                            out_f.write("\n")
                        else:
                            out_f.write(str(row_value) + "\n")

                return
        except Exception:
            # If dedupe scan/update fails for any reason, continue and append.
            pass

    record = {
        "collection": collection,
        "uuid": item_uuid,
        "status": status,
        "timestamp": resolved_timestamp,
    }

    retry_dir = os.path.dirname(retry_path)
    if retry_dir:
        os.makedirs(retry_dir, exist_ok=True)

    with open(retry_path, "a", encoding="utf-8") as out_f:
        out_f.write(json.dumps(record, ensure_ascii=True) + "\n")


def download_dds_item(dds_api, collection: str, item_uuid: str, download_dir: str,
                      queued_backoff_seconds: int = DEFAULT_DDS_BACKOFF_SECONDS,
                      retry_file: str = DEFAULT_DDS_RETRY_FILE) -> Optional[Dict[str, Any]]:
    waits = 0

    while True:
        item_info = dds_api.get_item(collection, item_uuid)
        if item_info is None:
            click.echo(f"Item not found: collection={collection}, uuid={item_uuid}")
            return None

        status_value = _extract_dds_status(item_info)
        normalized_status = _normalize_status(status_value)

        if normalized_status == "QUEUED":
            if waits >= MAX_DDS_QUEUED_WAITS:
                click.echo(
                    f"Item remained Queued after {MAX_DDS_QUEUED_WAITS} wait(s): "
                    f"collection={collection}, uuid={item_uuid}"
                )
                return None

            waits += 1
            click.echo(
                f"DDS item Queued: collection={collection}, uuid={item_uuid}. "
                f"Waiting {queued_backoff_seconds}s before retry ({waits}/{MAX_DDS_QUEUED_WAITS})..."
            )
            time.sleep(queued_backoff_seconds)
            continue

        if normalized_status in {"ITEMRESTORING", "ITEMSRESTORING"}:
            restoring_timestamp = _extract_dds_timestamp(item_info)
            retry_abs_path = os.path.abspath(retry_file)
            retry_rel_path = os.path.relpath(retry_abs_path, os.getcwd())
            retry_rel_path = os.path.normpath(retry_rel_path)
            if not (retry_rel_path.startswith(".") or os.path.isabs(retry_rel_path)):
                retry_rel_path = f".{os.sep}{retry_rel_path}"
            _append_dds_retry_item(
                retry_file=retry_file,
                collection=collection,
                item_uuid=item_uuid,
                status=status_value or "ItemRestoring",
                timestamp=restoring_timestamp,
            )
            click.echo(
                f"DDS item is {status_value or 'ItemRestoring'}; recorded for retry: "
                f"collection={collection}, uuid={item_uuid}, file={retry_rel_path}"
            )
            click.echo(
                "Retry with: "
                f"py eodms_cli.py download --dds-retry-file \"{retry_rel_path}\""
            )
            return {
                "_dds_retry_logged": True,
                "collection": collection,
                "uuid": item_uuid,
                "status": status_value or "ItemRestoring",
                "timestamp": restoring_timestamp,
            }

        if "download_url" not in item_info:
            click.echo(
                f"Item has no download URL: collection={collection}, uuid={item_uuid}, "
                f"status={status_value or 'unknown'}"
            )
            return None

        dds_api.download_item(os.path.abspath(download_dir))
        return item_info


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


def download_public_stac_assets(search_api, collection: str, item_uuid: str, download_dir: str) -> int:
    item_info = search_api.get_item(collection, item_uuid)
    if item_info is None:
        click.echo(f"Item not found: collection={collection}, uuid={item_uuid}")
        return 0

    assets = item_info.get("assets") if isinstance(item_info, dict) else None
    if not isinstance(assets, dict) or not assets:
        click.echo(f"Item has no assets: collection={collection}, uuid={item_uuid}")
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
            continue

        downloaded_count += 1
        click.echo(f"Saved asset to {out_path}")

    if downloaded_count == 0:
        click.echo(f"No downloadable asset links found for collection={collection}, uuid={item_uuid}")

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

            retry_items = payload.get("items")
            if isinstance(retry_items, list):
                return [item for item in retry_items if isinstance(item, dict)]

            # Accept a single retry object (for example one JSONL line copied to .json)
            # when it has an identifiable item UUID/id field.
            if _extract_item_uuid(payload):
                return [payload]

            raise click.ClickException(
                "Input JSON must be GeoJSON FeatureCollection ('features') "
                "or retry JSON with an 'items' list (or a single item object with uuid/id)."
            )

        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        raise click.ClickException("Input JSON must be an object or list.")

    # Fallback: JSON lines support for retry files (one object per line).
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
        "Input file must be GeoJSON, JSON retry records, or JSONL retry records."
    )


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


def _download_rapi_items(rapi_api: EODMSRAPI, items: List[Dict[str, Any]], download_dir: str) -> None:
    if not items:
        click.echo("No downloadable items found.")
        return

    destination = os.path.abspath(download_dir)
    os.makedirs(destination, exist_ok=True)

    click.echo(f"Downloading {len(items)} item(s) to {destination}")
    result = _safe_rapi_call(rapi_api.download, items, destination)

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


def _print_process_summary(processes_json: Dict[str, Any]) -> None:
    all_processes = processes_json.get("processes", [])
    click.echo("\nProcessing Service:\n")
    for process_obj in all_processes:
        process_id = process_obj.get("id", "N/A")
        version = process_obj.get("version", "N/A")
        description = process_obj.get("description") or process_obj.get("abstract") or "N/A"
        click.echo(f"* {process_id} (v{version}): {description}")

    click.echo("\nSAR Toolbox:\n")
    click.echo(
        "* SAR_Toolbox (vX.X): Filters, Ortho-rectification and mosaic "
        "Radiometry, Polarimetry, Interferometry, Analysis Ready Data. Support for RADARSAT-2, RCMImageProducts"
    )


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
@click.option("--uuid", required=False, default=None,
              help="UUID (or comma-separated UUIDs) used with --uuid2record.")
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
@click.option("--output", "-o", required=False, default=None,
              help="Output GeoJSON file for search results.")
@click.option("--env", "-e", required=False, default="prod",
              help='Environment (default: "prod").')
@handle_service_errors
def search_cmd(
    username: Optional[str],
    password: Optional[str],
    collection: Optional[str],
    list_collections: bool,
    uuid2record: bool,
    uuid: Optional[str],
    show_queryables: bool,
    datetime_range: Optional[str],
    bbox: Optional[str],
    limit: int,
    filter_text: Optional[str],
    s_intersect: Optional[str],
    aoi: Optional[str],
    output: Optional[str],
    env: str,
):
    """STAC geotemporal/queryables and GeoJSON output."""

    username, password = resolve_credentials(username, password)

    bbox_list = parse_bbox(bbox)

    aaa_api = make_aaa(username, password, env)

    if list_collections:
        search_api = make_search(aaa_api, env)
        search_api.print_collections()
        return

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

    if show_queryables:
        if not collection:
            raise click.ClickException("--collection is required with --queryables.")

        search_api = make_search(aaa_api, env)
        coll = search_api.client.get_collection(collection)
        if coll is None:
            raise click.ClickException(f"Collection not found: {collection}")

        search_api.print_queryables(coll)
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
            schema_url = "https://eodms-sgdot.nrcan-rncan.gc.ca/schemas/st/sar-toolbox-schema.json"
            try:
                with urlopen(schema_url) as resp:
                    body = resp.read().decode("utf-8")
                schema_json = json.loads(body)
            except (URLError, ValueError) as exc:
                raise click.ClickException(f"Failed to fetch SAR Toolbox schema: {exc}")

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
                _download_rapi_items(rapi_api, order_items, download_dir)

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
              help="Input file for download items (GeoJSON, JSON, or JSONL retry records).")
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
@click.option("--order-status", required=False, default=None,
              help="Optional status filter for --list (example: AVAILABLE_FOR_DOWNLOAD).")
@click.option("--download-available", is_flag=True,
              help="Download AVAILABLE_FOR_DOWNLOAD order items (required for default bulk download mode).")
@click.option("--dl_dir", "download_dir", required=False, default=".\\downloads",
              help="Destination directory for downloads.")
@click.option("--download-dir", "download_dir", required=False,
              help="Destination directory for downloads.")
@click.option("--dds-retry-file", required=False, default=DEFAULT_DDS_RETRY_FILE,
              help="File used to append DDS ItemRestoring records for retry input.")
@click.pass_context
@handle_service_errors
def download_available_cmd(
    ctx: click.Context,
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
    order_status: Optional[str],
    download_available: bool,
    download_dir: str,
    dds_retry_file: str,
):
    """Download by UUID (public STAC assets or DDS) and legacy RAPI order-item downloads."""

    username, password = resolve_credentials(username, password)
    dds_backoff_seconds = _load_dds_backoff_interval()
    dds_concurrent_downloads = _load_dds_concurrent_downloads()

    # If explicitly provided, allow --dds-retry-file to act as --input for retry runs.
    dds_retry_file_provided = False
    if hasattr(ctx, "get_parameter_source"):
        try:
            src = ctx.get_parameter_source("dds_retry_file")
            param_source = getattr(click.core, "ParameterSource", None)
            if param_source is not None and src == param_source.COMMANDLINE:
                dds_retry_file_provided = True
        except Exception:
            dds_retry_file_provided = False

    if not uuid and not input_file and dds_retry_file_provided:
        retry_input_path = os.path.abspath(dds_retry_file)
        if not os.path.exists(retry_input_path):
            raise click.ClickException(
                f"DDS retry file not found: {retry_input_path}"
            )
        click.echo(f"Using DDS retry input file: {retry_input_path}")
        input_file = retry_input_path

    if uuid and input_file:
        raise click.ClickException("Use either --uuid or --input, not both.")

    if input_file:
        features = _load_download_items_from_geojson(input_file)
        if not features:
            click.echo("No items found in input file.")
            return

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
                downloaded_assets = download_public_stac_assets(search_api, str(item_collection), item_uuid, download_dir)
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
                    retry_file=dds_retry_file,
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

                    if isinstance(item_info, dict) and item_info.get("_dds_retry_logged"):
                        dds_retry_logged_count += 1
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
            downloaded_count = download_public_stac_assets(search_api, collection, uuid, download_dir)
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
            retry_file=dds_retry_file,
        )
        return

    if not username or not password:
        raise click.ClickException(
            "--username and --password are required for order listing/downloading."
        )

    if not order_items and not list_orders and not download_available:
        raise click.ClickException(
            "Use --download-available to download AVAILABLE_FOR_DOWNLOAD items, "
            "or use --list to list only."
        )

    rapi_api = EODMSRAPI(username, password)

    if list_orders:
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

    _download_rapi_items(rapi_api, filtered_items, download_dir)


if __name__ == "__main__":
    cli()
