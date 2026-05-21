"""
Lightweight EODMS CLI v2 focused on eodms-py STAC/DDS workflows.

This script ports the core STAC/DDS search flow from test/stac_dds_test.py
and includes focused ports of legacy process options:
- Option 5: Submit order to SAR Toolbox (`order-st`)
- Option 6: Download AVAILABLE_FOR_DOWNLOAD order items (`download-available`)
"""

import json
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import click
import fiona
from shapely.geometry import shape

from eodms import aaa, dds, search
from eodms_rapi import EODMSRAPI, QueryError


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


def download_dds_item(dds_api, collection: str, item_uuid: str, download_dir: str) -> Optional[Dict[str, Any]]:
    item_info = dds_api.get_item(collection, item_uuid)
    if item_info is None:
        click.echo(f"Item not found: collection={collection}, uuid={item_uuid}")
        return None

    if "download_url" not in item_info:
        click.echo(f"Item has no download URL: collection={collection}, uuid={item_uuid}")
        return None

    dds_api.download_item(os.path.abspath(download_dir))
    return item_info


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


def _collect_order_items(payload: Any) -> List[Dict[str, Any]]:
    """Extract order item dictionaries from common RAPI payload shapes."""
    items: List[Dict[str, Any]] = []

    if payload is None:
        return items

    if isinstance(payload, list):
        for entry in payload:
            items.extend(_collect_order_items(entry))
        return items

    if isinstance(payload, dict):
        if "downloadUrl" in payload or "itemId" in payload or "orderItemId" in payload:
            items.append(payload)
        if isinstance(payload.get("items"), list):
            for entry in payload["items"]:
                items.extend(_collect_order_items(entry))
        if isinstance(payload.get("results"), list):
            for entry in payload["results"]:
                items.extend(_collect_order_items(entry))

    return items


def _safe_rapi_call(callable_obj, *args, **kwargs):
    result = callable_obj(*args, **kwargs)
    if isinstance(result, QueryError):
        raise click.ClickException(result.get_msgs(as_str=True))
    return result


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


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli():
    """EODMS CLI v2: STAC/DDS-first with targeted legacy ports."""


@cli.command("search")
@click.option("--username", "-u", required=False, help="EODMS username.")
@click.option("--password", "-p", required=False, help="EODMS password.")
@click.option("--collection", "-c", required=True, help="Collection name.")
@click.option("--uuid", required=False, default=None, help="Download UUID directly and skip STAC search.")
@click.option("--datetime", "datetime_range", required=False, default=None,
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
@click.option("--download-dir", "-dl", required=False, default=".",
              help="Destination directory for downloads.")
def search_cmd(
    username: Optional[str],
    password: Optional[str],
    collection: str,
    uuid: Optional[str],
    datetime_range: Optional[str],
    bbox: Optional[str],
    limit: int,
    filter_text: Optional[str],
    s_intersect: Optional[str],
    aoi: Optional[str],
    output: Optional[str],
    env: str,
    download_dir: str,
):
    """Search STAC and optionally download first result via DDS."""

    bbox_list = parse_bbox(bbox)

    aaa_api = make_aaa(username, password, env)
    dds_api = make_dds(aaa_api, env)

    if uuid:
        click.echo(f"Downloading UUID: {uuid}")
        download_dds_item(dds_api, collection, uuid, download_dir)
        return

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

    if username and password:
        first_uuid = items[0].get("id")
        if first_uuid:
            click.echo(f"Downloading first result UUID: {first_uuid}")
            download_dds_item(dds_api, collection, first_uuid, download_dir)
    else:
        click.echo("Credentials not provided; skipping download.")


@cli.command("order-st")
@click.option("--username", "-u", required=True, help="EODMS username.")
@click.option("--password", "-p", required=True, help="EODMS password.")
@click.option("--request-json", required=True, type=click.Path(exists=True),
              help="Path to SAR Toolbox JSON order request payload.")
@click.option("--priority", required=False, default="Medium",
              type=click.Choice(["Low", "Medium", "High", "Urgent"], case_sensitive=False),
              help="Order priority.")
@click.option("--download-dir", "-dl", required=False, default=".",
              help="Destination directory for downloads.")
def order_st_cmd(
    username: str,
    password: str,
    request_json: str,
    priority: str,
    download_dir: str,
):
    """Port of legacy option 5: submit SAR Toolbox order and download available items."""

    with open(request_json, "r", encoding="utf-8") as req_file:
        payload = json.load(req_file)

    rapi_api = EODMSRAPI(username, password)

    click.echo("Submitting SAR Toolbox order JSON to RAPI.")
    order_res = _safe_rapi_call(rapi_api.order_json, payload, priority.capitalize())

    if not isinstance(order_res, list) or len(order_res) == 0:
        raise click.ClickException("Unexpected SAR Toolbox order response from RAPI.")

    order_id = order_res[0].get("orderId")
    if not order_id:
        raise click.ClickException("Order response does not contain orderId.")

    click.echo(f"Order submitted: {order_id}")

    available_order = _safe_rapi_call(rapi_api.get_order, order_id)
    items = _collect_order_items(available_order)
    _download_rapi_items(rapi_api, items, download_dir)


@cli.command("download-available")
@click.option("--username", "-u", required=True, help="EODMS username.")
@click.option("--password", "-p", required=True, help="EODMS password.")
@click.option("--order-items", required=False, default=None,
              help="Legacy selector syntax: order:id1,id2|item:id3,id4")
@click.option("--maximum", "-m", required=False, default=100, type=int,
              help="Maximum AVAILABLE_FOR_DOWNLOAD orders to retrieve.")
@click.option("--dtstart", required=False, default=None,
              help="Optional start datetime filter for order retrieval.")
@click.option("--dtend", required=False, default=None,
              help="Optional end datetime filter for order retrieval.")
@click.option("--download-dir", "-dl", required=False, default=".",
              help="Destination directory for downloads.")
def download_available_cmd(
    username: str,
    password: str,
    order_items: Optional[str],
    maximum: int,
    dtstart: Optional[str],
    dtend: Optional[str],
    download_dir: str,
):
    """Port of legacy option 6: download order items with AVAILABLE_FOR_DOWNLOAD status."""

    rapi_api = EODMSRAPI(username, password)
    downloadable_items: List[Dict[str, Any]] = []

    if order_items:
        order_ids, item_ids = parse_legacy_order_items(order_items)

        for order_id in order_ids:
            payload = _safe_rapi_call(rapi_api.get_order, order_id)
            downloadable_items.extend(_collect_order_items(payload))

        for item_id in item_ids:
            payload = _safe_rapi_call(rapi_api.get_order_item, item_id)
            downloadable_items.extend(_collect_order_items(payload))
    else:
        payload = _safe_rapi_call(
            rapi_api.get_orders,
            max_orders=maximum,
            dtstart=dtstart,
            dtend=dtend,
            status="AVAILABLE_FOR_DOWNLOAD",
        )
        downloadable_items.extend(_collect_order_items(payload))

    # Keep only items that are explicitly available for download when status exists.
    filtered_items = []
    for item in downloadable_items:
        status = str(item.get("status", "")).upper()
        if not status or status == "AVAILABLE_FOR_DOWNLOAD":
            filtered_items.append(item)

    if not filtered_items:
        click.echo("No AVAILABLE_FOR_DOWNLOAD order items found.")
        return

    click.echo(f"Found {len(filtered_items)} AVAILABLE_FOR_DOWNLOAD item(s).")
    _download_rapi_items(rapi_api, filtered_items, download_dir)


if __name__ == "__main__":
    cli()
