import unittest
import os
import sys

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
                "--list",
                "--queryables",
                "--output",
            ],
        )

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
