import unittest
import os
import sys
import csv
from unittest.mock import patch

from click.testing import CliRunner

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eodms_cli import cli


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
            self.assertIn("matched 1 order_key value(s)", result.output)

            with open(output_path, "r", encoding="utf-8", newline="") as out_f:
                rows = list(csv.DictReader(out_f, delimiter="\t"))

            self.assertEqual(["order_keys", "note", "spatial_resolution", "timestamp", "uuid"], list(rows[0].keys()))
            self.assertEqual("30", rows[0]["spatial_resolution"])
            self.assertEqual("2026-06-09T12:00:00Z", rows[0]["timestamp"])
            self.assertEqual("uuid-123", rows[0]["uuid"])
            self.assertEqual("", rows[1]["spatial_resolution"])
            self.assertEqual("", rows[1]["timestamp"])
            self.assertEqual("", rows[1]["uuid"])
            self.assertEqual(1, len(fake_search.calls))
            self.assertIn("MATCH_ONE", fake_search.calls[0]["filter"])
            self.assertIn("MISS_ONE", fake_search.calls[0]["filter"])

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


if __name__ == "__main__":
    unittest.main()
