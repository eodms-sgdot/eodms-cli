import json
import os
import sys
from typing import Any, Dict, Optional

import click

# Allow running this script directly from the tests directory.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from eodms import AAA_API, Processes_API


def _load_json_input(raw: Optional[str], label: str) -> Optional[Dict[str, Any]]:
    """Load JSON from inline string or file path."""
    if raw is None:
        return None

    candidate = raw.strip()
    if not candidate:
        return None

    if os.path.exists(candidate):
        with open(candidate, 'r', encoding='utf-8') as f:
            return json.load(f)

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid {label} JSON. Provide either a valid JSON string or a file path."
        ) from exc


def _print_process_summary(processes_json: Dict[str, Any]) -> None:
    all_processes = processes_json.get('processes', [])
    print(f"Found {len(all_processes)} processes")
    for process in all_processes:
        process_id = process.get('id', 'N/A')
        title = process.get('title', 'N/A')
        version = process.get('version', 'N/A')
        description = process.get('description') or process.get('abstract') or 'N/A'
        print(
            f"  - id={process_id} | title={title} | version={version}\n"
            f"    description={description}"
        )


def _build_aaa_api(username: Optional[str], password: Optional[str], env: str) -> Optional[AAA_API]:
    if username and password:
        return AAA_API(username, password, env)
    return None


def _example_scalar_from_schema(schema: Dict[str, Any], input_name: str) -> Any:
    """Build a representative scalar value from a JSON schema-like object."""
    if not isinstance(schema, dict):
        return "example"

    if 'default' in schema:
        return schema['default']

    enum_vals = schema.get('enum')
    if isinstance(enum_vals, list) and enum_vals:
        return enum_vals[0]

    schema_type = schema.get('type')
    schema_format = schema.get('format')

    if schema_type == 'boolean':
        return True
    if schema_type in ('integer', 'number'):
        return 1
    if schema_type == 'array':
        item_schema = schema.get('items')
        if isinstance(item_schema, dict):
            return [_example_scalar_from_schema(item_schema, input_name)]
        return ["example"]
    if schema_type == 'object':
        return {}

    if schema_format == 'date-time':
        return "2000-01-01T00:00:00Z"

    # Heuristic defaults for common processing argument names.
    lower_name = input_name.lower()
    if lower_name in ('uuid', 'id', 'segment_id'):
        return "00000000-0000-0000-0000-000000000000"
    if lower_name in ('start_time', 'stop_time'):
        return "2000-01-01T00:00:00Z"

    return "example"


def _example_value_from_input_def(input_name: str, input_def: Dict[str, Any]) -> Any:
    """Build a representative value from an OGC process input definition."""
    if not isinstance(input_def, dict):
        return "example"

    if 'default' in input_def:
        return input_def['default']

    # OGC process descriptions may express value schema in different keys.
    for schema_key in ('schema', 'valueSchema'):
        schema_obj = input_def.get(schema_key)
        if isinstance(schema_obj, dict):
            return _example_scalar_from_schema(schema_obj, input_name)

    return _example_scalar_from_schema(input_def, input_name)


def _build_sample_payload(process_id: str, process_json: Dict[str, Any]) -> Dict[str, Any]:
    """Build a sample execution payload from /processing/processes/{processID}."""
    input_defs = process_json.get('inputs', {})
    sample_inputs: Dict[str, Any] = {}

    if isinstance(input_defs, dict):
        for input_name, input_def in input_defs.items():
            sample_inputs[input_name] = _example_value_from_input_def(str(input_name), input_def)

    sample_outputs = {
        f"{process_id}-response": {
            'format': {'mediaType': 'application/json'}
        }
    }

    return {
        'inputs': sample_inputs,
        'outputs': sample_outputs,
        'mode': 'async',
    }


def run(
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
) -> None:
    aaa_api = _build_aaa_api(username, password, env)
    proc_api = Processes_API(aaa_api=aaa_api, environment=env)

    # 1) List processes (default behavior)
    if list_processes and not submit and not input_structure and not job_id:
        processes_json = proc_api.list_processes()
        _print_process_summary(processes_json)
        return

    # 2) Show process input structure
    if input_structure:
        if not process_id:
            raise click.UsageError("--process_id is required with --input-structure")
        process_json = proc_api.get_process(process_id)
        print(json.dumps(process_json.get('inputs', {}), indent=4))

        sample_payload = _build_sample_payload(process_id, process_json)
        print("\nSample execution payload:")
        print(json.dumps(sample_payload, indent=4))

        if output:
            with open(output, 'w', encoding='utf-8') as f:
                json.dump(process_json, f, indent=2)
            print(f"Saved process description to {output}")
        return

    # 3) Submit processing job
    submitted_job_id = None
    if submit:
        if not process_id:
            raise click.UsageError("--process_id is required with --submit")
        if aaa_api is None:
            raise click.UsageError("--username and --password are required with --submit")

        loaded_inputs = _load_json_input(inputs_json, 'inputs')
        outputs = _load_json_input(outputs_json, 'outputs')
        if loaded_inputs is None:
            raise click.UsageError("--inputs_json is required with --submit")

        # Support both formats for --inputs_json:
        # 1) Inputs-only object: {"uuid": "...", ...}
        # 2) Full execution payload: {"inputs": {...}, "outputs": {...}, "mode": "async"}
        request_mode = mode
        if isinstance(loaded_inputs, dict) and 'inputs' in loaded_inputs:
            inputs = loaded_inputs.get('inputs')
            if outputs is None and isinstance(loaded_inputs.get('outputs'), dict):
                outputs = loaded_inputs.get('outputs')
            if isinstance(loaded_inputs.get('mode'), str) and loaded_inputs.get('mode').strip():
                request_mode = loaded_inputs.get('mode').strip()
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

        print(json.dumps(submit_json, indent=2))
        submitted_job_id = submit_json.get('jobID')
        print(f"Submitted jobID: {submitted_job_id}")

        if output:
            with open(output, 'w', encoding='utf-8') as f:
                json.dump(submit_json, f, indent=2)
            print(f"Saved submission response to {output}")

    # Prefer explicit --job_id, otherwise use submitted jobID.
    target_job_id = job_id or submitted_job_id

    # 4) Status check / polling
    if wait:
        if not target_job_id:
            raise click.UsageError("A job ID is required for --wait (provide --job_id or --submit)")
        status_json = proc_api.poll_job_status(target_job_id, interval=interval, timeout=timeout)
        print(json.dumps(status_json, indent=2))
    elif target_job_id and not show_results and not download_dir:
        status_json = proc_api.get_job_status(target_job_id)
        print(json.dumps(status_json, indent=2))

    # 5) Fetch results
    if show_results:
        if not target_job_id:
            raise click.UsageError("A job ID is required for --show_results")
        results_json = proc_api.get_job_results(target_job_id)
        print(json.dumps(results_json, indent=2))

    # 6) Download result files
    if download_dir:
        if not target_job_id:
            raise click.UsageError("A job ID is required for --download_dir")
        downloaded = proc_api.download_job_results(
            job_id=target_job_id,
            out_dir=os.path.abspath(download_dir),
            skip_existing=skip_existing,
        )
        print(json.dumps({'jobID': target_job_id, 'downloaded_files': downloaded}, indent=2))


@click.command(context_settings={'help_option_names': ['-h', '--help']})
@click.option('--username', '-u', required=False, help='The EODMS username.')
@click.option('--password', '-p', required=False, help='The EODMS password.')
@click.option('--env', '-e', required=False, default='prod',
              help='Defaults to "prod". If "staging", define EODMS_STAGING_DOMAIN env variable.')
@click.option('--process_id', '-pi', required=False, default=None,
              help='Processing service ID (e.g., Radarsat1GAMMAL1SLC).')
@click.option('--list_processes/--no-list_processes', default=True,
              help='List available processes (default behavior).')
@click.option('--input-structure', 'input_structure', is_flag=True,
              help='Print process input structure and sample payload from /processing/processes/{processID}.')
@click.option('--submit', is_flag=True,
              help='Submit a processing job (requires auth).')
@click.option('--inputs_json', required=False, default=None,
              help='JSON string or path to JSON file for submit inputs.')
@click.option('--outputs_json', required=False, default=None,
              help='JSON string or path to JSON file for generic submit outputs.')
@click.option('--mode', required=False, default='async',
              help='Execution mode for generic submit (default: async).')
@click.option('--job_id', '-j', required=False, default=None,
              help='Existing job ID to check/poll/results/download.')
@click.option('--wait', is_flag=True,
              help='Poll job status until terminal state.')
@click.option('--interval', required=False, default=30, type=int,
              help='Polling interval seconds for --wait (default: 30).')
@click.option('--timeout', required=False, default=600, type=int,
              help='Polling timeout seconds for --wait (default: 600).')
@click.option('--show_results', is_flag=True,
              help='Print /jobs/{jobID}/results JSON.')
@click.option('--download_dir', '-dl', required=False, default=None,
              help='Download all job result files to this folder.')
@click.option('--skip_existing/--no-skip_existing', default=True,
              help='Skip existing local files when downloading results (default: enabled).')
@click.option('--output', '-o', required=False, default=None,
              help='Write JSON response (process details or submit response) to file.')
def cli(
    username,
    password,
    env,
    process_id,
    list_processes,
    input_structure,
    submit,
    inputs_json,
    outputs_json,
    mode,
    job_id,
    wait,
    interval,
    timeout,
    show_results,
    download_dir,
    skip_existing,
    output,
):
    """
    OGC Processes CLI for EODMS processing workflows.

    Examples:

    \b
    # List available processes
    python processes_test.py

    \b
    # Print input structure for a process
    python processes_test.py --input-structure --process_id Radarsat1GAMMAL1SLC

    \b
    # Submit generic process payload from file
    python processes_test.py -u USER -p PASS --submit --process_id Radarsat1GAMMAL1SLC --inputs_json ./inputs.json

    \b
    # Poll an existing job to completion
    python processes_test.py -u USER -p PASS --job_id JOB_ID --wait --interval 60 --timeout 3600

    \b
    # Download all result files
    python processes_test.py -u USER -p PASS --job_id JOB_ID --download_dir ./data/JOB_ID
    """
    try:
        run(
            username=username,
            password=password,
            env=env,
            process_id=process_id,
            list_processes=list_processes,
            input_structure=input_structure,
            submit=submit,
            inputs_json=inputs_json,
            outputs_json=outputs_json,
            mode=mode,
            job_id=job_id,
            wait=wait,
            interval=interval,
            timeout=timeout,
            show_results=show_results,
            download_dir=download_dir,
            skip_existing=skip_existing,
            output=output,
        )
    except click.UsageError:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


if __name__ == '__main__':
    cli()
