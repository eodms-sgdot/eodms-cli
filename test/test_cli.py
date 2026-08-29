import unittest
import os
import sys
import csv
import json
from unittest.mock import patch

from click.testing import CliRunner

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eodms_cli import cli, download_dds_item, _search_items_by_filter


class TestEodmsCli(unittest.TestCase):

    def setUp(self):
        self.runner = CliRunner()

    def _assert_help(self, args, expected_tokens):
        result = self.runner.invoke(cli, args)
        self.assertEqual(result.exit_code, 0, msg=result.output)
        for token in expected_tokens:
            self.assertIn(token, result.output)

    def test_root_help_lists_all_commands(self):
        self._assert_help(
            ["--help"],
            [
                "configure",
                "search",
                "process",
                "download",
            ],
        )

    def test_configure_command_help(self):
        self._assert_help(
            ["configure", "--help"],
            [
                "--username",
                "--password",
                "--show",
            ],
        )

    def test_search_command_help(self):
        self._assert_help(
            ["search", "--help"],
            [
                "--collection",
                "--input",
                "--list",
                "--queryables",
                "--output",
            ],
        )

    def test_search_input_tsv_appends_search_fields(self):
        class FakeSearchApi:
            def __init__(self):
                self.calls = []

            def stac_search(self, collections, limit, filter, filter_lang):
                self.calls.append(
                    {
                        "collections": collections,
                        "limit": limit,
                        "filter": filter,
                        "filter_lang": filter_lang,
                    }
                )
                results = []
                if "MATCH_ONE" in filter:
                    results.append({
                        "id": "uuid-123",
                        "properties": {
                            "order_key": "MATCH_ONE",
                            "spatial_resolution": "30",
                            "datetime": "2026-06-09T12:00:00Z",
                        },
                    })
                if "MISS_ONE" in filter:
                    return results
                return results

        fake_search = FakeSearchApi()

        with self.runner.isolated_filesystem():
            input_path = "orders.tsv"
            output_path = "results.tsv"

            with open(input_path, "w", encoding="utf-8", newline="") as in_f:
                writer = csv.DictWriter(in_f, fieldnames=["order_keys", "note"], delimiter="\t")
                writer.writeheader()
                writer.writerow({"order_keys": "MATCH_ONE", "note": "first"})
                writer.writerow({"order_keys": "MISS_ONE", "note": "second"})

            with patch("eodms_cli.resolve_credentials", return_value=(None, None)), \
                 patch("eodms_cli.make_aaa", return_value=None), \
                 patch("eodms_cli.make_search", return_value=fake_search):
                result = self.runner.invoke(
                    cli,
                    [
                        "search",
                        "--input",
                        input_path,
                        "--collection",
                        "RCMImageProducts",
                        "--output",
                        output_path,
                    ],
                )

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("matched 1 item(s)", result.output)

            with open(output_path, "r", encoding="utf-8", newline="") as out_f:
                rows = list(csv.DictReader(out_f, delimiter="\t"))

            self.assertEqual(["order_keys", "note", "uuid", "geometry", "spatial_resolution", "timestamp"], list(rows[0].keys()))
            self.assertEqual("30", rows[0]["spatial_resolution"])
            self.assertEqual("2026-06-09T12:00:00Z", rows[0]["timestamp"])
            self.assertEqual("uuid-123", rows[0]["uuid"])
            self.assertEqual("", rows[1]["spatial_resolution"])
            self.assertEqual("", rows[1]["timestamp"])
            self.assertEqual("", rows[1]["uuid"])
            self.assertEqual(2, len(fake_search.calls))
            self.assertIn("MATCH_ONE", fake_search.calls[0]["filter"])
            self.assertIn("MISS_ONE", fake_search.calls[0]["filter"])

    def test_search_input_writes_spatial_resolution_from_result(self):
        class FakeSearchApi:
            def stac_search(self, collections, limit, filter, filter_lang):
                return [{
                    "id": "uuid-800",
                    "properties": {
                        "order_key": "A2133_036",
                        "spatialResolution": 800,
                    },
                }]

        with self.runner.isolated_filesystem():
            with open("input.csv", "w", encoding="utf-8", newline="") as in_f:
                writer = csv.DictWriter(in_f, fieldnames=["order_key"])
                writer.writeheader()
                writer.writerow({"order_key": "A2133_036"})

            with patch("eodms_cli.resolve_credentials", return_value=(None, None)), \
                 patch("eodms_cli.make_aaa", return_value=None), \
                 patch("eodms_cli.make_search", return_value=FakeSearchApi()):
                result = self.runner.invoke(cli, [
                    "search", "--input", "input.csv", "--collection", "NAPL", "--output", "output.csv",
                ])

            self.assertEqual(result.exit_code, 0, msg=result.output)
            with open("output.csv", "r", encoding="utf-8", newline="") as out_f:
                rows = list(csv.DictReader(out_f))
            self.assertEqual("800", rows[0]["spatial_resolution"])

    def test_search_input_requires_order_key_column(self):
        with self.runner.isolated_filesystem():
            with open("input.csv", "w", encoding="utf-8", newline="") as in_f:
                writer = csv.DictWriter(in_f, fieldnames=["ROLL", "PHOTO"])
                writer.writeheader()
                writer.writerow({"ROLL": "A2133", "PHOTO": "36"})

            with patch("eodms_cli.resolve_credentials", return_value=(None, None)), \
                 patch("eodms_cli.make_aaa", return_value=None):
                result = self.runner.invoke(cli, [
                    "search", "--input", "input.csv", "--collection", "NAPL",
                    "--output", "output.csv",
                ])

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("Input file must contain an order_key/order_keys column.", result.output)


    def test_process_command_help(self):
        self._assert_help(
            ["process", "--help"],
            [
                "--process_id",
                "--describe",
                "--submit",
                "--download_dir",
            ],
        )

    def test_download_command_help(self):
        self._assert_help(
            ["download", "--help"],
            [
                "--uuid",
                "--input",
                "--download-available",
                "--dl_dir",
            ],
        )

    def test_dds_manifest_includes_download_url_expires(self):
        class FakeDdsApi:
            def get_item(self, collection, item_uuid):
                return {
                    "status": "Available",
                    "download_url": "https://example.test/files/item.zip?Signature=abc&Expires=1787241600",
                    "download_expires": 1787241600,
                    "download_expires_at": "2026-08-20T16:00:00Z",
                    "http_response_code": 200,
                }

            def download_item(self, download_dir):
                return os.path.join(download_dir, "item.zip")

        with self.runner.isolated_filesystem():
            os.makedirs("downloads", exist_ok=True)

            result = download_dds_item(
                FakeDdsApi(),
                "RCMImageProducts",
                "item-uuid",
                "downloads",
                retry_file=os.path.join("downloads", "downloads.jsonl"),
                update_retry_existing_only=False,
            )

            self.assertEqual("Downloaded", result["status"])

            with open(os.path.join("downloads", "downloads.jsonl"), "r", encoding="utf-8") as in_f:
                rows = [json.loads(line) for line in in_f if line.strip()]

            self.assertEqual(1, len(rows))
            self.assertEqual(1787241600, rows[0]["download_expires"])
            self.assertEqual("2026-08-20T16:00:00Z", rows[0]["download_expires_at"])


if __name__ == "__main__":
    unittest.main()
