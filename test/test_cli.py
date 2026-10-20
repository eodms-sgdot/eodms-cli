import unittest
import os
import sys
import csv
import json
import tempfile
import logging
from contextlib import redirect_stdout
from io import BytesIO, StringIO
from urllib.error import HTTPError
from unittest.mock import patch

from click import ClickException
from click.testing import CliRunner

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import config_util

from eodms_cli import (
    cli,
    download_dds_item,
    eodms_config,
    _napl_api_request,
    _search_items_by_filter,
    _print_search_progress,
    _split_datetime_range_by_window,
    _StacRateLimitInfoFilter,
    _user_api_request,
)


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
                "napl",
                "user",
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
                "--window-days",
            ],
        )

    def test_napl_help_lists_options_and_order(self):
        self._assert_help(["napl", "--help"], ["options", "order"])

    def test_user_help_lists_commands(self):
        self._assert_help(["user", "--help"], ["get", "update", "change-password"])

    def test_search_datetime_year_range_splits_into_daily_windows(self):
        day_ranges = _split_datetime_range_by_window("2026/2026")

        self.assertEqual(365, len(day_ranges))
        self.assertEqual(
            "2026-01-01T00:00:00.000000Z/2026-01-01T23:59:59.999999Z",
            day_ranges[0],
        )
        self.assertEqual(
            "2026-12-31T00:00:00.000000Z/2026-12-31T23:59:59.999999Z",
            day_ranges[-1],
        )

    def test_search_datetime_range_splits_into_configured_windows(self):
        date_ranges = _split_datetime_range_by_window("2026-01-01/2026-01-05", window_days=2)

        self.assertEqual(
            [
                "2026-01-01T00:00:00.000000Z/2026-01-02T23:59:59.999999Z",
                "2026-01-03T00:00:00.000000Z/2026-01-04T23:59:59.999999Z",
                "2026-01-05T00:00:00.000000Z/2026-01-05T23:59:59.999999Z",
            ],
            date_ranges,
        )

    def test_search_datetime_window_cannot_exceed_date_range(self):
        with self.assertRaisesRegex(ValueError, "--window-days cannot exceed the date range \\(2 day\\(s\\)\\)"):
            _split_datetime_range_by_window("2026-01-01/2026-01-02", window_days=3)

    def test_search_progress_uses_reports_bar_format(self):
        output = StringIO()
        with redirect_stdout(output):
            _print_search_progress(1, 2, "Searching")

        self.assertEqual(
            "\rSearching 1/2 [" + "▒" * 20 + "-" * 20 + "] 50%",
            output.getvalue(),
        )

    def test_search_without_limit_queries_each_day_with_api_cap_and_deduplicates(self):
        class FakeSearchApi:
            class FakeItemSearch:
                def __init__(self, items):
                    self.items = items

                def items_as_dicts(self):
                    return iter(self.items)

            def __init__(self):
                self.calls = []
                self.client = self

            def compose_filter(self, filter_text, geometry_wkt):
                return filter_text

            def search(self, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 1:
                    return self.FakeItemSearch([{"id": "shared"}])
                return self.FakeItemSearch([{"id": "shared"}, {"id": "second"}])

        fake_search = FakeSearchApi()
        progress_updates = []
        with patch("eodms_cli.make_search", return_value=fake_search), patch(
            "eodms_cli._print_search_progress",
            side_effect=lambda current, total, label, suffix="": progress_updates.append(
                (current, total, label, suffix)
            ),
        ):
            result = self.runner.invoke(cli, [
                "search", "--anonymous", "--collection", "rcm-ard",
                "--datetime", "2026-01-01/2026-01-02",
            ])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("Warning: no --limit specified", result.output)
        self.assertIn("Found 2 item(s).", result.output)
        self.assertEqual([0, 1, 1, 2, 2], [update[0] for update in progress_updates])
        self.assertTrue(all(update[1] == 2 for update in progress_updates))
        self.assertEqual(
            [
                "",
                "(2026-01-01) 0 items",
                "(2026-01-01) 1 items",
                "(2026-01-02) 1 items",
                "(2026-01-02) 2 items",
            ],
            [update[3] for update in progress_updates],
        )
        self.assertEqual(2, len(fake_search.calls))
        self.assertEqual([None, None], [call["limit"] for call in fake_search.calls])
        self.assertEqual([None, None], [call["max_items"] for call in fake_search.calls])
        self.assertEqual(
            [
                "2026-01-01T00:00:00.000000Z/2026-01-01T23:59:59.999999Z",
                "2026-01-02T00:00:00.000000Z/2026-01-02T23:59:59.999999Z",
            ],
            [call["datetime"] for call in fake_search.calls],
        )

    def test_search_window_days_option_groups_date_range(self):
        class FakeSearchApi:
            class FakeItemSearch:
                def items_as_dicts(self):
                    return iter([])

            def __init__(self):
                self.calls = []
                self.client = self

            def compose_filter(self, filter_text, geometry_wkt):
                return filter_text

            def search(self, **kwargs):
                self.calls.append(kwargs)
                return self.FakeItemSearch()

        fake_search = FakeSearchApi()
        with patch("eodms_cli.make_search", return_value=fake_search):
            result = self.runner.invoke(cli, [
                "search", "--anonymous", "--collection", "rcm-ard",
                "--datetime", "2026-01-01/2026-01-03", "--window-days", "2",
            ])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertEqual(
            [
                "2026-01-01T00:00:00.000000Z/2026-01-02T23:59:59.999999Z",
                "2026-01-03T00:00:00.000000Z/2026-01-03T23:59:59.999999Z",
            ],
            [call["datetime"] for call in fake_search.calls],
        )

    def test_search_rejects_window_days_larger_than_date_range(self):
        result = self.runner.invoke(cli, [
            "search", "--anonymous", "--collection", "rcm-ard",
            "--datetime", "2026-01-01/2026-01-02", "--window-days", "3",
        ])

        self.assertEqual(1, result.exit_code)
        self.assertIn("--window-days cannot exceed the date range (2 day(s)).", result.output)

    def test_stac_rate_limit_retry_log_is_downgraded_to_info(self):
        messages = [
            "STAC request rate limited (429); retry 1/3",
            "First 429 response evidence for server team: url=https://example.test",
        ]
        for message in messages:
            with self.subTest(message=message):
                record = logging.LogRecord(
                    "eodms.search",
                    logging.WARNING,
                    "search.py",
                    1,
                    message,
                    (),
                    None,
                )

                self.assertTrue(_StacRateLimitInfoFilter().filter(record))
                self.assertEqual(logging.INFO, record.levelno)
                self.assertEqual("INFO", record.levelname)

    def test_package_console_logger_uses_configured_info_level(self):
        from eodms_cli import _setup_package_logger

        package_logger = logging.getLogger("eodms")
        original_handlers = list(package_logger.handlers)
        original_level = package_logger.level
        original_propagate = package_logger.propagate
        try:
            for handler in original_handlers:
                package_logger.removeHandler(handler)

            with tempfile.TemporaryDirectory() as temp_dir:
                _setup_package_logger(os.path.join(temp_dir, "cli.log"), level=logging.INFO)
                console_handler = next(
                    handler
                    for handler in package_logger.handlers
                    if isinstance(handler, logging.StreamHandler)
                    and not isinstance(handler, logging.FileHandler)
                )
                file_handler = next(
                    handler
                    for handler in package_logger.handlers
                    if isinstance(handler, logging.FileHandler)
                )
                self.assertEqual(logging.INFO, console_handler.level)
                self.assertEqual(logging.INFO, file_handler.level)
                for handler in list(package_logger.handlers):
                    package_logger.removeHandler(handler)
                    handler.close()
        finally:
            for handler in list(package_logger.handlers):
                package_logger.removeHandler(handler)
                handler.close()
            for handler in original_handlers:
                package_logger.addHandler(handler)
            package_logger.setLevel(original_level)
            package_logger.propagate = original_propagate

    def test_user_change_password_patches_profile_and_updates_matching_config(self):
        class FakeAAA:
            def get_access_token(self):
                return "test-access-token"

        with patch("eodms_cli.resolve_credentials", return_value=("user", "old-password")), \
             patch("eodms_cli.make_aaa", return_value=FakeAAA()), \
             patch("eodms_cli.eodms_config.get_domain_config", return_value={"domain": "https://profile.example"}), \
             patch("eodms_cli._load_credentials_from_config", return_value=("user", "old-password")), \
             patch("eodms_cli._save_credentials_to_config", return_value="config.ini") as save_credentials, \
             patch("eodms_cli._user_api_request", return_value={"updated": True}) as request:
            result = self.runner.invoke(
                cli,
                ["user", "change-password", "--env", "prod"],
                input="new-password-2026\nnew-password-2026\n",
            )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("Password requirements: at least 15 characters.", result.output)
        self.assertIn("Password changed successfully.", result.output)
        request.assert_called_once_with(
            "https://profile.example",
            "user",
            method="PATCH",
            payload={"password": "new-password-2026"},
            headers={"Authorization": "Bearer test-access-token"},
        )
        save_credentials.assert_called_once_with("user", "new-password-2026")

    def test_user_change_password_rejects_password_shorter_than_api_minimum(self):
        class FakeAAA:
            def get_access_token(self):
                return "test-access-token"

        with patch("eodms_cli.resolve_credentials", return_value=("user", "old-password")), \
             patch("eodms_cli.make_aaa", return_value=FakeAAA()), \
             patch("eodms_cli._user_api_request") as request:
            result = self.runner.invoke(
                cli,
                ["user", "change-password"],
                input="short-pass\nshort-pass\n",
            )

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("at least 15 characters", result.output)
        request.assert_not_called()

    def test_user_update_rejects_password_payload(self):
        with self.runner.isolated_filesystem():
            with open("profile.json", "w", encoding="utf-8") as payload_file:
                json.dump({"password": "new-secret"}, payload_file)

            result = self.runner.invoke(cli, ["user", "update", "--payload-file", "profile.json"])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Change passwords with `user change-password`", result.output)

    def test_user_api_request_escapes_username_and_sends_patch_json(self):
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return b'{"updated": true}'

        payload = {"email": "new@example.com"}
        with patch("eodms_cli.urlopen", return_value=FakeResponse()) as urlopen:
            response = _user_api_request(
                "https://profile.example/",
                "first.last@example.com",
                method="PATCH",
                payload=payload,
                headers={"Authorization": "Bearer token"},
            )

        self.assertEqual(response, {"updated": True})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://profile.example/aaa/v1/users/first.last%40example.com")
        self.assertEqual(request.get_method(), "PATCH")
        self.assertEqual(json.loads(request.data.decode("utf-8")), payload)
        self.assertEqual(request.get_header("Authorization"), "Bearer token")

    def test_user_api_request_reports_retry_after_for_429(self):
        retry_values = [
            ("120", "Retry after "),
            ("Tue, 13 Oct 2026 12:02:00 GMT", "Retry after 2026-10-13 12:02:00 UTC"),
        ]
        for retry_after, expected_hint in retry_values:
            with self.subTest(retry_after=retry_after):
                http_error = HTTPError(
                    "https://profile.example/aaa/v1/users/user",
                    429,
                    "Too Many Requests",
                    {"Retry-After": retry_after},
                    BytesIO(b'{"message":"429 Too Many Requests"}'),
                )
                with patch("eodms_cli.urlopen", side_effect=http_error):
                    with self.assertRaises(ClickException) as error:
                        _user_api_request("https://profile.example", "user")

                self.assertIn(expected_hint, str(error.exception))
                self.assertIn("UTC", str(error.exception))

    def test_user_api_request_notes_missing_retry_after_for_429(self):
        http_error = HTTPError(
            "https://profile.example/aaa/v1/users/user",
            429,
            "Too Many Requests",
            {},
            BytesIO(b'{"message":"429 Too Many Requests"}'),
        )
        with patch("eodms_cli.urlopen", side_effect=http_error):
            with self.assertRaises(ClickException) as error:
                _user_api_request("https://profile.example", "user")

        self.assertIn("The server did not provide a Retry-After value.", str(error.exception))

    def test_user_get_defaults_to_prod_environment(self):
        class FakeAAA:
            def get_access_token(self):
                return "test-access-token"

        with patch("eodms_cli.resolve_credentials", return_value=("user", "password")), \
             patch("eodms_cli.make_aaa", return_value=FakeAAA()) as make_aaa, \
             patch("eodms_cli.eodms_config.get_domain_config", return_value={"domain": "https://profile.example"}) as domain_config, \
             patch("eodms_cli._user_api_request", return_value={"email": "user@example.com"}) as request:
            result = self.runner.invoke(cli, ["user", "get"])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn('"email": "user@example.com"', result.output)
        make_aaa.assert_called_once_with("user", "password", "prod")
        domain_config.assert_called_once_with("prod")
        request.assert_called_once_with(
            "https://profile.example",
            "user",
            headers={"Authorization": "Bearer test-access-token"},
        )

    def test_user_get_routes_staging_independently_of_staging_domain_env_var(self):
        from eodms_cli import USER_STAGING_DOMAIN

        class FakeAAA:
            def get_access_token(self):
                return "test-access-token"

        configured_domains = []

        def make_staging_aaa(username, password, environment):
            configured_domains.append(eodms_config.get_domain_config(environment)["domain"])
            return FakeAAA()

        original_staging_domain = os.environ.get("EODMS_STAGING_DOMAIN")
        with patch.dict(os.environ, {"EODMS_STAGING_DOMAIN": "https://wrong.example"}), \
             patch("eodms_cli.resolve_credentials", return_value=("user", "password")), \
             patch("eodms_cli.make_aaa", side_effect=make_staging_aaa) as make_aaa, \
             patch("eodms_cli.eodms_config.get_domain_config", side_effect=KeyError("EODMS_STAGING_DOMAIN")), \
             patch("eodms_cli._user_api_request", return_value={"email": "user@example.com"}) as request:
            result = self.runner.invoke(cli, ["user", "get", "--env", "staging"])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertEqual([USER_STAGING_DOMAIN], configured_domains)
        self.assertEqual([unittest.mock.call("user", "password", "staging")], make_aaa.call_args_list)
        request.assert_called_once_with(
            USER_STAGING_DOMAIN,
            "user",
            headers={"Authorization": "Bearer test-access-token"},
        )
        self.assertEqual(original_staging_domain, os.environ.get("EODMS_STAGING_DOMAIN"))

    def test_user_get_writes_json_to_output_file(self):
        class FakeAAA:
            def get_access_token(self):
                return "test-access-token"

        profile = {"email": "user@example.com", "language": "English"}
        with self.runner.isolated_filesystem():
            with patch("eodms_cli.resolve_credentials", return_value=("user", "password")), \
                 patch("eodms_cli.make_aaa", return_value=FakeAAA()), \
                 patch("eodms_cli.eodms_config.get_domain_config", return_value={"domain": "https://profile.example"}), \
                 patch("eodms_cli._user_api_request", return_value=profile):
                result = self.runner.invoke(cli, ["user", "get", "--output", "wm.json", "--env", "prod"])

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("Saved user profile to", result.output)
            with open("wm.json", "r", encoding="utf-8") as profile_file:
                self.assertEqual(json.load(profile_file), profile)

    def test_user_update_patches_json_payload(self):
        class FakeAAA:
            def get_access_token(self):
                return "test-access-token"

        payload = {"language": "English", "surname": "Example"}
        with self.runner.isolated_filesystem():
            with open("profile.json", "w", encoding="utf-8") as payload_file:
                json.dump(payload, payload_file)

            with patch("eodms_cli.resolve_credentials", return_value=("user", "password")), \
                 patch("eodms_cli.make_aaa", return_value=FakeAAA()), \
                 patch("eodms_cli.eodms_config.get_domain_config", return_value={"domain": "https://profile.example"}), \
                 patch("eodms_cli._user_api_request", return_value={"updated": True}) as request:
                result = self.runner.invoke(
                    cli,
                    ["user", "update", "--payload-file", "profile.json", "--env", "prod"],
                )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        request.assert_called_once_with(
            "https://profile.example",
            "user",
            method="PATCH",
            payload=payload,
            headers={"Authorization": "Bearer test-access-token"},
        )

    def test_user_update_patches_only_requested_field_option(self):
        class FakeAAA:
            def get_access_token(self):
                return "test-access-token"

        with patch("eodms_cli.resolve_credentials", return_value=("user", "password")), \
             patch("eodms_cli.make_aaa", return_value=FakeAAA()), \
             patch("eodms_cli.eodms_config.get_domain_config", return_value={"domain": "https://profile.example"}), \
             patch("eodms_cli._user_api_request", return_value={"updated": True}) as request:
            result = self.runner.invoke(
                cli,
                ["user", "update", "--email", "new@example.com", "--env", "staging"],
            )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        request.assert_called_once_with(
            "https://www-staging-eodms.aws.nrcan-rncan.cloud",
            "user",
            method="PATCH",
            payload={"email": "new@example.com"},
            headers={"Authorization": "Bearer test-access-token"},
        )

    def test_user_update_parses_address_option_as_json_object(self):
        class FakeAAA:
            def get_access_token(self):
                return "test-access-token"

        address = {
            "@type": "main",
            "country": "Canada",
            "province": "quebec",
            "postal-code": "k1A 0y7",
        }
        with patch("eodms_cli.resolve_credentials", return_value=("user", "password")), \
             patch("eodms_cli.make_aaa", return_value=FakeAAA()), \
             patch("eodms_cli.eodms_config.get_domain_config", return_value={"domain": "https://profile.example"}), \
             patch("eodms_cli._user_api_request", return_value={"updated": True}) as request:
            result = self.runner.invoke(
                cli,
                ["user", "update", "--address", json.dumps(address), "--env", "staging"],
            )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        request.assert_called_once_with(
            "https://www-staging-eodms.aws.nrcan-rncan.cloud",
            "user",
            method="PATCH",
            payload={"address": address},
            headers={"Authorization": "Bearer test-access-token"},
        )

    def test_user_update_rejects_plain_text_address_before_api_call(self):
        with patch("eodms_cli._user_api_request") as request:
            result = self.runner.invoke(
                cli,
                ["user", "update", "--address", "580 booth", "--env", "staging"],
            )

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("--address must be a JSON object or a non-empty array of objects", result.output)
        request.assert_not_called()

    def test_user_update_accepts_multiple_typed_addresses(self):
        class FakeAAA:
            def get_access_token(self):
                return "test-access-token"

        addresses = [
            {"@type": "shipping", "street-address": "584 Booth"},
            {"@type": "main", "street-address": "580 Booth"},
            {"@type": "billing", "street-address": "582 Booth"},
        ]
        with patch("eodms_cli.resolve_credentials", return_value=("user", "password")), \
             patch("eodms_cli.make_aaa", return_value=FakeAAA()), \
             patch("eodms_cli.eodms_config.get_domain_config", return_value={"domain": "https://profile.example"}), \
             patch("eodms_cli._user_api_request", return_value={"updated": True}) as request:
            result = self.runner.invoke(
                cli,
                ["user", "update", "--address", json.dumps(addresses), "--env", "staging"],
            )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        request.assert_called_once_with(
            "https://www-staging-eodms.aws.nrcan-rncan.cloud",
            "user",
            method="PATCH",
            payload={"address": addresses},
            headers={"Authorization": "Bearer test-access-token"},
        )

    def test_user_update_rejects_mixing_payload_file_and_field_options(self):
        with self.runner.isolated_filesystem():
            with open("profile.json", "w", encoding="utf-8") as payload_file:
                json.dump({"language": "English"}, payload_file)

            result = self.runner.invoke(
                cli,
                ["user", "update", "--payload-file", "profile.json", "--email", "new@example.com"],
            )

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Use either --payload-file or profile field options, not both.", result.output)

    def test_user_update_requires_a_file_or_at_least_one_field_option(self):
        result = self.runner.invoke(cli, ["user", "update"])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Provide --payload-file or at least one profile field option", result.output)

    def test_user_update_rejects_unsupported_payload_fields(self):
        with self.runner.isolated_filesystem():
            with open("profile.json", "w", encoding="utf-8") as payload_file:
                json.dump({"phone": "555-0100"}, payload_file)

            result = self.runner.invoke(cli, ["user", "update", "--payload-file", "profile.json"])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Unsupported profile field(s): phone", result.output)

    def test_user_update_accepts_get_profile_output_file(self):
        class FakeAAA:
            def get_access_token(self):
                return "test-access-token"

        profile = {
            "personal-information": {
                "account-type": None,
                "identification": {"name": {"given-name": "Will", "surname": "Updated"}},
                "contact-information": {"address": None, "email": "will@example.com"},
            },
            "environment": None,
            "organization": {"identification": {"organization-name": None}},
        }
        expected_patch = {
            "email": "will@example.com",
            "given_name": "Will",
            "surname": "Updated",
        }
        with self.runner.isolated_filesystem():
            with open("wm.json", "w", encoding="utf-8") as payload_file:
                json.dump(profile, payload_file)

            with patch("eodms_cli.resolve_credentials", return_value=("user", "password")), \
                 patch("eodms_cli.make_aaa", return_value=FakeAAA()), \
                 patch("eodms_cli.eodms_config.get_domain_config", return_value={"domain": "https://profile.example"}), \
                 patch("eodms_cli._user_api_request", return_value={"updated": True}) as request:
                result = self.runner.invoke(cli, ["user", "update", "--payload-file", "wm.json", "--env", "prod"])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        request.assert_called_once_with(
            "https://profile.example",
            "user",
            method="PATCH",
            payload=expected_patch,
            headers={"Authorization": "Bearer test-access-token"},
        )

    def test_napl_options_fetches_public_options(self):
        options = {
            "media_types": ["Digital", "ContactPrint"],
            "file_formats": ["Jpeg", "Tiff"],
            "image_resolutions": [300, 600, 800],
        }
        with patch(
            "eodms_cli.eodms_config.get_domain_config",
            return_value={"domain": "https://napl.example"},
        ) as domain_config, patch("eodms_cli._napl_api_request", return_value=options) as request:
            result = self.runner.invoke(
                cli,
                ["napl", "options", "--env", "prod"],
            )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn('"media_types"', result.output)
        request.assert_called_once_with("https://napl.example", "order-options")
        domain_config.assert_called_once_with("prod")

    def test_napl_api_request_appends_relative_route_to_domain(self):
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return b'{"ready": true}'

        with patch("eodms_cli.urlopen", return_value=FakeResponse()) as urlopen:
            result = _napl_api_request("https://napl.example/", "order-options")

        self.assertEqual(result, {"ready": True})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://napl.example/napl/v1/order-options")

    def test_napl_api_request_reports_invalid_item_uuids(self):
        rejected_uuid = "00000000-0000-0000-0000-000000000001"
        response_body = json.dumps({
            "error": "One or more items are not eligible NAPL catalog records.",
            "invalid_items": [rejected_uuid],
        }).encode("utf-8")
        http_error = HTTPError(
            "https://napl.example/napl/v1/orders",
            422,
            "Unprocessable Entity",
            None,
            BytesIO(response_body),
        )

        with patch("eodms_cli.urlopen", side_effect=http_error):
            with self.assertRaises(ClickException) as error:
                _napl_api_request("https://napl.example", "orders", method="POST", payload={})

        self.assertIn(rejected_uuid, str(error.exception))

    def test_napl_order_uses_aaa_token_and_posts_order(self):
        class FakeAAA:
            def get_access_token(self):
                return "test-access-token"

        with patch("eodms_cli.resolve_credentials", return_value=("user", "password")), \
             patch("eodms_cli.make_aaa", return_value=FakeAAA()) as make_aaa, \
               patch("eodms_cli.eodms_config.get_domain_config", return_value={"domain": "https://napl.example"}) as domain_config, \
             patch("eodms_cli._napl_api_request", return_value={"order_id": "order-1", "status": "SUCCESS"}) as request:
            result = self.runner.invoke(
                cli,
                [
                    "napl", "order", "--uuid", "item-uuid-1,item-uuid-2",
                    "--media-type", "Digital", "--file-format", "Tiff",
                    "--image-resolution", "800", "--idempotency-key", "request-1",
                    "--yes",
                ],
            )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("Idempotency-Key: request-1", result.output)
        make_aaa.assert_called_once_with("user", "password", "staging")
        domain_config.assert_called_once_with("staging")
        request.assert_called_once_with(
            "https://napl.example",
            "orders",
            method="POST",
            payload={
                "items": [
                    {
                        "unique_identifier": "item-uuid-1",
                        "quantity": 1,
                            "options": {"media_type": "Digital", "file_format": "Tiff", "image_resolution": 800},
                    },
                    {
                        "unique_identifier": "item-uuid-2",
                        "quantity": 1,
                            "options": {"media_type": "Digital", "file_format": "Tiff", "image_resolution": 800},
                    },
                ]
            },
            headers={
                "Authorization": "Bearer test-access-token",
                "Idempotency-Key": "request-1",
            },
        )

    def test_napl_order_preserves_repeated_uuids_and_shared_quantity(self):
        with patch("eodms_cli.resolve_credentials", return_value=("user", "password")), \
             patch("eodms_cli.make_aaa") as make_aaa, \
             patch("eodms_cli.eodms_config.get_domain_config", return_value={"domain": "https://napl.example"}), \
             patch("eodms_cli._napl_api_request", return_value={"order_id": "order-1", "order_number": 123, "status": "SUCCESS"}) as request:
            make_aaa.return_value.get_access_token.return_value = "test-access-token"
            result = self.runner.invoke(cli, [
                "napl", "order", "--uuid", "item-1,item-1", "--media-type", "Digital",
                "--file-format", "Jpeg", "--image-resolution", "300", "--quantity", "2", "--yes",
                "--flight-line-index-map", "PDF",
            ])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn('"order_number": 123', result.output)
        self.assertIn("Order ID: 123", result.output)
        items = request.call_args.kwargs["payload"]["items"]
        self.assertEqual([item["unique_identifier"] for item in items], ["item-1", "item-1"])
        self.assertEqual([item["quantity"] for item in items], [2, 2])
        self.assertEqual([item["options"]["flight_line_index_map"] for item in items], ["PDF", "PDF"])

    def test_napl_items_file_preserves_per_line_options_and_quantities(self):
        body = {"items": [
            {"unique_identifier": "item-1", "quantity": 2, "options": {"media_type": "Digital", "file_format": "Tiff", "image_resolution": 800, "flight_line_index_map": "PDF"}},
            {"unique_identifier": "item-1", "options": {"media_type": "PaperPrint", "file_format": "Enlargement", "flight_line_index_map": "Paper"}},
            {"unique_identifier": "item-1", "options": {"media_type": "Diapositive", "flight_line_index_map": "PDF"}},
        ]}
        with self.runner.isolated_filesystem():
            with open("items.json", "w", encoding="utf-8") as stream:
                json.dump(body, stream)
            with patch("eodms_cli.resolve_credentials", return_value=("user", "password")), \
                 patch("eodms_cli.make_aaa") as make_aaa, \
                 patch("eodms_cli.eodms_config.get_domain_config", return_value={"domain": "https://napl.example"}), \
                 patch("eodms_cli._napl_api_request", return_value={"order_number": 123, "status": "SUCCESS"}) as request:
                make_aaa.return_value.get_access_token.return_value = "test-access-token"
                result = self.runner.invoke(cli, ["napl", "order", "--items-file", "items.json", "--yes"])

        self.assertEqual(result.exit_code, 0, result.output)
        body["items"][1]["quantity"] = 1
        body["items"][2]["quantity"] = 1
        self.assertEqual(request.call_args.kwargs["payload"], body)

    def test_napl_order_rejects_invalid_quantity_before_authentication(self):
        with patch("eodms_cli.make_aaa") as make_aaa:
            result = self.runner.invoke(cli, [
                "napl", "order", "--uuid", "item-1", "--media-type", "Digital",
                "--file-format", "Jpeg", "--image-resolution", "300", "--quantity", "0", "--yes",
            ])
        self.assertNotEqual(result.exit_code, 0)
        make_aaa.assert_not_called()

    def test_napl_items_file_rejects_invalid_lines_without_submitting(self):
        options = {"media_type": "Digital", "file_format": "Tiff", "image_resolution": 800}
        cases = [
            {"items": []}, {"items": [None]},
            {"items": [{"unique_identifier": "item-1", "options": options, "quantity": True}]},
            {"items": [{"unique_identifier": "item-1", "options": options, "quantity": 0}]},
            {"items": [{"unique_identifier": "item-1", "options": options, "quantity": "2"}]},
            {"items": [{"unique_identifier": "item-1", "options": options, "quantity": 2147483648}]},
            {"items": [{"unique_identifier": "item-1", "options": {}}]},
        ]
        cases.extend(
            {"items": [{"unique_identifier": "item-1", "options": {**options, "flight_line_index_map": choice}}]}
            for choice in ("pdf", "TIFF", "", None, True, [], {})
        )
        for body in cases:
            with self.subTest(body=body), self.runner.isolated_filesystem():
                with open("items.json", "w", encoding="utf-8") as stream:
                    json.dump(body, stream)
                with patch("eodms_cli.make_aaa") as make_aaa, patch("eodms_cli._napl_api_request") as request:
                    result = self.runner.invoke(cli, ["napl", "order", "--items-file", "items.json", "--yes"])
                self.assertNotEqual(result.exit_code, 0, result.output)
                make_aaa.assert_not_called()
                request.assert_not_called()

    def test_napl_map_flag_cannot_override_items_file(self):
        with self.runner.isolated_filesystem():
            with open("items.json", "w", encoding="utf-8") as stream:
                json.dump({"items": []}, stream)
            with patch("eodms_cli._napl_api_request") as request:
                result = self.runner.invoke(cli, [
                    "napl", "order", "--items-file", "items.json", "--flight-line-index-map", "PDF", "--yes",
                ])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("without --uuid or shared item-option flags", result.output)
        request.assert_not_called()

    def test_napl_media_type_controls_applicable_options(self):
        cases = [
            ("Digital", ["--file-format", "Tiff", "--image-resolution", "800"], True),
            ("PaperPrint", ["--file-format", "ContactPrint"], True),
            ("PaperPrint", ["--file-format", "Enlargement"], True),
            ("Diapositive", [], True),
            ("Digital", ["--file-format", "ContactPrint", "--image-resolution", "800"], False),
            ("PaperPrint", ["--file-format", "Tiff", "--image-resolution", "800"], False),
            ("PaperPrint", ["--file-format", "ContactPrint", "--image-resolution", "800"], False),
            ("Diapositive", ["--file-format", "Tiff"], False),
            ("Diapositive", ["--image-resolution", "800"], False),
        ]
        cases.extend(
            (media_type, flags, accepted)
            for media_type in ("Mosaic", "ContactTransparency", "Uncorrected", "TransparencyEnlargement")
            for flags, accepted in (([], True), (["--file-format", "Tiff"], False), (["--image-resolution", "800"], False))
        )
        for media_type, flags, accepted in cases:
            with self.subTest(media_type=media_type, flags=flags), \
                 patch("eodms_cli.resolve_credentials", return_value=("user", "password")), \
                 patch("eodms_cli.make_aaa") as make_aaa, \
                 patch("eodms_cli.eodms_config.get_domain_config", return_value={"domain": "https://napl.example"}), \
                 patch("eodms_cli._napl_api_request", return_value={"order_number": 123}) as request:
                make_aaa.return_value.get_access_token.return_value = "fake-token"
                result = self.runner.invoke(cli, ["napl", "order", "--uuid", "item-1", "--media-type", media_type, *flags, "--yes"])
                self.assertEqual(result.exit_code == 0, accepted, result.output)
                if accepted:
                    options = request.call_args.kwargs["payload"]["items"][0]["options"]
                    if media_type not in ("Digital", "PaperPrint"):
                        self.assertEqual(options, {"media_type": media_type})
                    if media_type == "PaperPrint":
                        self.assertNotIn("image_resolution", options)
                else:
                    make_aaa.assert_not_called()
                    request.assert_not_called()

    def test_search_list_with_collection_shows_queryables(self):
        collection = object()

        class FakeSearchApi:
            def __init__(self):
                self.client = self
                self.queryables_collections = []
                self.collections_listed = False

            def get_collection(self, collection_id):
                self.requested_collection = collection_id
                return collection

            def print_queryables(self, collection_arg):
                self.queryables_collections.append(collection_arg)

            def print_collections(self):
                self.collections_listed = True

        fake_search = FakeSearchApi()
        with patch("eodms_cli.resolve_credentials", return_value=(None, None)), \
             patch("eodms_cli.make_aaa", return_value=None), \
             patch("eodms_cli.make_search", return_value=fake_search):
            result = self.runner.invoke(
                cli,
                ["search", "--list", "--collection", "RCMImageProducts"],
            )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertEqual(fake_search.requested_collection, "RCMImageProducts")
        self.assertEqual(fake_search.queryables_collections, [collection])
        self.assertFalse(fake_search.collections_listed)

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
            self.assertIn("matched 1 order_key(s)", result.output)

            with open(output_path, "r", encoding="utf-8", newline="") as out_f:
                rows = list(csv.DictReader(out_f, delimiter="\t"))

            self.assertEqual(["order_keys", "note", "uuids", "geometry", "spatial_resolution", "timestamp"], list(rows[0].keys()))
            self.assertEqual("30", rows[0]["spatial_resolution"])
            self.assertEqual("2026-06-09T12:00:00Z", rows[0]["timestamp"])
            self.assertEqual("uuid-123", rows[0]["uuids"])
            self.assertEqual("", rows[1]["spatial_resolution"])
            self.assertEqual("", rows[1]["timestamp"])
            self.assertEqual("", rows[1]["uuids"])
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

    def test_search_input_consolidates_multiple_hits_into_one_row(self):
        class FakeSearchApi:
            def stac_search(self, collections, limit, filter, filter_lang):
                if "CA74_069" in filter:
                    return [
                        {
                            "id": "8c30662a-ffbb-5e25-8654-9d7d078eea75",
                            "geometry": {"type": "Polygon", "coordinates": [[[0, 0]]]},
                            "properties": {
                                "order_key": "CA74_069",
                                "spatial_resolution": "800",
                                "datetime": "1924-07-01T00:00:00+00:00",
                            },
                        },
                        {
                            "id": "8c30662a-ffbb-5e25-8654-9d7d078eea76",
                            "geometry": {"type": "Polygon", "coordinates": [[[1, 1]]]},
                            "properties": {
                                "order_key": "CA74_069",
                                "spatial_resolution": "2032",
                                "datetime": "1924-07-01T00:00:00+00:00",
                            },
                        },
                    ]
                return []

        with self.runner.isolated_filesystem():
            with open("input.csv", "w", encoding="utf-8", newline="") as in_f:
                writer = csv.DictWriter(in_f, fieldnames=["order_key"])
                writer.writeheader()
                writer.writerow({"order_key": "CA74_069"})

            with patch("eodms_cli.resolve_credentials", return_value=(None, None)), \
                 patch("eodms_cli.make_aaa", return_value=None), \
                 patch("eodms_cli.make_search", return_value=FakeSearchApi()):
                result = self.runner.invoke(cli, [
                    "search", "--input", "input.csv", "--collection", "NAPL", "--output", "output.csv",
                ])

            self.assertEqual(result.exit_code, 0, msg=result.output)
            with open("output.csv", "r", encoding="utf-8", newline="") as out_f:
                rows = list(csv.DictReader(out_f))
            self.assertEqual(1, len(rows))
            self.assertEqual(
                "8c30662a-ffbb-5e25-8654-9d7d078eea75;8c30662a-ffbb-5e25-8654-9d7d078eea76",
                rows[0]["uuids"],
            )
            self.assertEqual("800;2032", rows[0]["spatial_resolution"])
            self.assertEqual("1924-07-01T00:00:00+00:00", rows[0]["timestamp"])
            self.assertEqual(json.dumps({"type": "Polygon", "coordinates": [[[0, 0]]]}, separators=(",", ":")), rows[0]["geometry"])

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

    def test_uuid2record_clears_accumulated_rapi_results(self):
        class FakeSearchApi:
            def get_item(self, collection, item_uuid):
                return {"id": item_uuid, "properties": {"order_key": f"ORDER_{item_uuid}"}}

        class FakeRapi:
            def __init__(self, username, password):
                self.results = []

            def clear_results(self):
                self.results = []

            def search(self, collection, filters, max_results, dates=None):
                order_key = filters["ARCHIVE_IMAGE.ORDER_KEY"][1][0]
                self.results += [{"recordId": f"RECORD_{order_key}"}]

            def get_results(self, result_type, show_progress=False):
                return self.results

        with patch("eodms_cli.resolve_credentials", return_value=("user", "password")), \
             patch("eodms_cli.make_aaa", return_value=None), \
             patch("eodms_cli.make_search", return_value=FakeSearchApi()), \
             patch("eodms_cli.EODMSRAPI", FakeRapi):
            result = self.runner.invoke(cli, [
                "search", "--uuid2record", "--collection", "RCMImageProducts",
                "--uuid", "UUID_ONE,UUID_TWO",
            ])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("UUID_ONE: order_key=ORDER_UUID_ONE; record_id=RECORD_ORDER_UUID_ONE", result.output)
        self.assertIn("UUID_TWO: order_key=ORDER_UUID_TWO; record_id=RECORD_ORDER_UUID_TWO", result.output)


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

    def test_download_dir_default_is_platform_appropriate(self):
        from eodms_cli import _normalize_download_dir

        self.assertEqual("downloads", _normalize_download_dir(".\\downloads"))
        self.assertEqual("downloads", _normalize_download_dir("downloads"))
        self.assertNotIn("\\", _normalize_download_dir(".\\downloads"))

    def test_download_input_supports_wes_csv_archive_id(self):
        from eodms_cli import _load_download_items

        with self.runner.isolated_filesystem():
            with open("results.csv", "w", encoding="utf-8", newline="") as out_f:
                out_f.write(
                    "Result Number,Satellite,Archive ID,Footprint\n"
                    "1,RCM,93f7f839-b561-52e1-8659-6ab14f9bc19e,-93 64\n"
                )

            self.assertEqual(
                [{"id": "93f7f839-b561-52e1-8659-6ab14f9bc19e"}],
                _load_download_items("results.csv"),
            )

    def test_config_write_does_not_use_comment_strings_as_option_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg_path = os.path.join(temp_dir, "config.ini")
            cfg = config_util.ConfigUtils(config_path=cfg_path)
            cfg.write()

            with open(cfg_path, "r", encoding="utf-8") as fh:
                contents = fh.read()

            self.assertIn("[Paths]", contents)
            self.assertIn("downloads =", contents)
            self.assertIn("[Credentials]", contents)

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
