"""
Lightweight EODMS CLI v2 focused on eodms-py STAC/DDS workflows.

This script ports the core STAC/DDS search flow from test/stac_dds_test.py
and includes focused command flows:
- `process`: OGC Processes list/inspect/submit/job workflows
- `download`: DDS UUID download plus legacy RAPI order-item downloads
"""

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import click
import fiona
from shapely.geometry import shape

from eodms import Processes_API, aaa, dds, search
from eodms_rapi import EODMSRAPI, QueryError


class OrderedHelpGroup(click.Group):
    """Group that prints commands in a custom help order."""

    def list_commands(self, ctx):
        preferred = ["search", "process", "download"]
        remaining = sorted(name for name in self.commands if name not in preferred)
        return [name for name in preferred if name in self.commands] + remaining


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
    click.echo(f"Found {len(all_processes)} processes")
    for process_obj in all_processes:
        process_id = process_obj.get("id", "N/A")
        title = process_obj.get("title", "N/A")
        version = process_obj.get("version", "N/A")
        description = process_obj.get("description") or process_obj.get("abstract") or "N/A"
        click.echo(
            f"  - id={process_id} | title={title} | version={version}\n"
            f"    description={description}"
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
    """EODMS CLI v2: STAC/DDS-first with targeted legacy ports."""


@cli.command("search")
@click.option("--username", "-u", required=False, help="EODMS username.")
@click.option("--password", "-p", required=False, help="EODMS password.")
@click.option("--collection", "-c", required=False, help="Collection name.")
@click.option("--list", "list_collections", is_flag=True,
              help="List available STAC collections and exit.")
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
def search_cmd(
    username: Optional[str],
    password: Optional[str],
    collection: Optional[str],
    list_collections: bool,
    datetime_range: Optional[str],
    bbox: Optional[str],
    limit: int,
    filter_text: Optional[str],
    s_intersect: Optional[str],
    aoi: Optional[str],
    output: Optional[str],
    env: str,
):
    """Search STAC and optionally write results to GeoJSON."""

    bbox_list = parse_bbox(bbox)

    aaa_api = make_aaa(username, password, env)

    if list_collections:
        search_api = make_search(aaa_api, env)
        collections = []
        for coll in search_api.client.get_collections():
            coll_title = getattr(coll, "title", None) or coll.id
            collections.append((coll.id, coll_title))

        if not collections:
            click.echo("No collections found.")
            return

        click.echo(f"Found {len(collections)} collection(s):")
        for coll_id, coll_title in collections:
            if coll_title == coll_id:
                click.echo(f"- {coll_id}")
            else:
                click.echo(f"- {coll_id}: {coll_title}")
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


@cli.command("process")
@click.option("--username", "-u", required=False, help="EODMS username.")
@click.option("--password", "-p", required=False, help="EODMS password.")
@click.option("--env", "-e", required=False, default="prod",
              help='Environment (default: "prod").')
@click.option("--process_id", "-pi", required=False, default=None,
              help="Processing service ID.")
@click.option("--list_processes/--no-list_processes", default=True,
              help="List available processes (default behavior).")
@click.option("--input-structure", "input_structure", is_flag=True,
              help="Print process input structure and sample payload.")
@click.option("--submit", is_flag=True,
              help="Submit a processing job (requires auth).")
@click.option("--inputs_json", required=False, default=None,
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
def order_st_cmd(
    username: Optional[str],
    password: Optional[str],
    env: str,
    process_id: Optional[str],
    list_processes: bool,
    input_structure: bool,
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
    """OGC Processes command: list, inspect, submit, track, and download process jobs."""

    aaa_api = make_aaa(username, password, env)
    proc_api = make_processes(aaa_api, env)

    if list_processes and not submit and not input_structure and not job_id:
        processes_json = proc_api.list_processes()
        _print_process_summary(processes_json)
        return

    if input_structure:
        if not process_id:
            raise click.UsageError("--process_id is required with --input-structure")

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
@click.option("--username", "-u", required=True, help="EODMS username.")
@click.option("--password", "-p", required=True, help="EODMS password.")
@click.option("--uuid", required=False, default=None,
              help="Download UUID directly via DDS.")
@click.option("--collection", "-c", required=False, default=None,
              help="Collection for --uuid DDS download.")
@click.option("--env", "-e", required=False, default="prod",
              help='Environment for DDS download (default: "prod").')
@click.option("--order-items", required=False, default=None,
              help="Legacy selector syntax: order:id1,id2|item:id3,id4")
@click.option("--maximum", "-m", required=False, default=100, type=int,
              help="Maximum AVAILABLE_FOR_DOWNLOAD orders to retrieve.")
@click.option("--dtstart", required=False, default=None,
              help="Optional start datetime filter for order retrieval.")
@click.option("--dtend", required=False, default=None,
              help="Optional end datetime filter for order retrieval.")
@click.option("--dl_dir", "download_dir", required=False, default=".",
              help="Destination directory for downloads.")
@click.option("--download-dir", "download_dir", required=False,
              help="Destination directory for downloads.")
def download_available_cmd(
    username: str,
    password: str,
    uuid: Optional[str],
    collection: Optional[str],
    env: str,
    order_items: Optional[str],
    maximum: int,
    dtstart: Optional[str],
    dtend: Optional[str],
    download_dir: str,
):
    """Port of legacy option 6: download order items with AVAILABLE_FOR_DOWNLOAD status."""

    if uuid:
        if not collection:
            raise click.ClickException("--collection is required when using --uuid.")

        aaa_api = make_aaa(username, password, env)
        dds_api = make_dds(aaa_api, env)
        click.echo(f"Downloading UUID: {uuid}")
        download_dds_item(dds_api, collection, uuid, download_dir)
        return

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
