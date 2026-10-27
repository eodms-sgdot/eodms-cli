import os
import sys
import unittest
import json
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eodms_prompt import Prompter, cli
from eodms_rapi import QueryError
from scripts.utils import EodmsUtils, EodmsProcess
from scripts.sar import SARToolbox


class TestPromptOrderKeys(unittest.TestCase):
    def setUp(self):
        self.eod = Mock()
        self.eod.silent = False
        self.eod.eodms_domain = None
        self.eod.exit_cli.side_effect = SystemExit
        self.eod.get_collections.return_value = [
            {"id": "RCMImageProducts", "title": "RCM Image Products"},
        ]
        self.eod.get_record_ids.return_value = ["12345"]
        self.params = {
            "username": "test-user",
            "password": "test-password",
            "process": "order_st",
            "silent": False,
        }
        self.stac_item = {
            "id": "test-item",
            "collection": "RCMImageProducts",
            "properties": {"datetime": "2021-10-10T22:52:02Z"},
        }
        self.rapi_dates = [{"start": "20211010_225202", "end": "20211011_225202"}]

    def run_prompt(self, inputs, **params):
        self.params.update(params, input_val=inputs)
        prompter = Prompter(self.eod, Mock(), self.params)
        with patch.object(prompter, "ask_st", return_value="toolbox"), \
             patch.object(prompter, "print_syntax"), \
             patch("eodms_prompt.print"):
            prompter.prompt()
        return prompter

    def assert_submitted(self, prompter, record_ids):
        self.assertEqual(
            prompter.params["input_val"],
            {"collection_id": "RCMImageProducts", "record_ids": record_ids},
        )
        self.eod.order_st.assert_called_once_with("toolbox", prompter.params)

    def test_single_order_key_with_collection_option(self):
        prompter = self.run_prompt("RCM2_OK123", collection="RCMImageProducts")

        self.eod.get_record_ids.assert_called_once_with(
            "RCMImageProducts", ["RCM2_OK123"])
        self.assert_submitted(prompter, ["12345"])

    def test_single_order_key_prompts_for_collection(self):
        with patch.object(Prompter, "get_input", return_value="1") as get_input:
            prompter = self.run_prompt("RCM2_OK123")

        get_input.assert_called_once()
        self.assert_submitted(prompter, ["12345"])

    def test_interactive_single_order_key(self):
        with patch.object(Prompter, "get_input", side_effect=["RCM2_OK123", "1"]):
            prompter = self.run_prompt(None)

        self.eod.validate_st_images.assert_called_once_with("RCM2_OK123")
        self.assert_submitted(prompter, ["12345"])

    def test_prefixed_single_and_multiple_order_keys(self):
        for ids in ["RCM2_OK123", "RCM2_OK123|RCM2_OK456"]:
            with self.subTest(ids=ids):
                self.eod.reset_mock()
                prompter = self.run_prompt(
                    f" RCMImageProducts : {ids} ", collection="OtherCollection")
                self.eod.get_record_ids.assert_called_once_with(
                    "RCMImageProducts", ids.split("|"))
                self.assert_submitted(prompter, ["12345"])

    def test_bare_multiple_order_keys(self):
        prompter = self.run_prompt(
            " RCM2_OK123 | RCM2_OK456 ", collection="RCMImageProducts")

        self.eod.get_record_ids.assert_called_once_with(
            "RCMImageProducts", ["RCM2_OK123", "RCM2_OK456"])
        self.assert_submitted(prompter, ["12345"])

    def test_record_ids_still_supported(self):
        for inputs in ["12345", "RCMImageProducts:12345|67890"]:
            with self.subTest(inputs=inputs):
                self.eod.reset_mock()
                prompter = self.run_prompt(inputs, collection="RCMImageProducts")
                self.eod.get_record_ids.assert_not_called()
                self.assert_submitted(prompter, inputs.split(":")[-1].split("|"))

    def test_json_input_still_supported(self):
        prompter = self.run_prompt(
            '{"collection_id": "RCMImageProducts", "record_ids": ["12345"]}')

        self.eod.get_record_ids.assert_not_called()
        self.assert_submitted(prompter, ["12345"])

    def test_silent_without_collection_reports_error(self):
        self.eod.silent = True
        with self.assertLogs("eodms", level="ERROR"), \
             self.assertRaises(SystemExit):
            self.run_prompt("RCM2_OK123", silent=True)

        self.eod.print_msg.assert_called_with(
            "No collection specified. Exiting process.", heading="error")
        self.eod.order_st.assert_not_called()

    def test_silent_with_collection_accepts_bare_key(self):
        self.eod.silent = True
        prompter = self.run_prompt(
            "RCM2_OK123", collection="RCMImageProducts", silent=True)

        self.assert_submitted(prompter, ["12345"])

    def test_invalid_inputs_report_error_before_lookup(self):
        cases = [
            ("RCMImageProducts:", None),
            (":RCM2_OK123", None),
            ("RCMImageProducts:RCM2_OK123|", None),
            ("RCMImageProducts:123:456", None),
            ("RCM2_OK123", "RCMImageProducts,Radarsat2"),
        ]
        for inputs, collection in cases:
            with self.subTest(inputs=inputs, collection=collection):
                self.eod.reset_mock()
                with self.assertLogs("eodms", level="ERROR"), \
                     self.assertRaises(SystemExit):
                    self.run_prompt(inputs, collection=collection)
                self.eod.print_msg.assert_called_once()
                self.eod.get_record_ids.assert_not_called()
                self.eod.order_st.assert_not_called()

    def test_missing_order_key_reports_error(self):
        self.eod.get_record_ids.return_value = []
        with self.assertRaises(SystemExit):
            self.run_prompt("RCM2_OK123", collection="RCMImageProducts")

        self.eod.print_msg.assert_called_once_with(
            "No images could be found with Order Keys: RCM2_OK123.",
            heading="error",
        )
        self.eod.order_st.assert_not_called()

    def test_request_file_still_supported(self):
        with patch("eodms_prompt.sar.SARToolbox") as toolbox_factory:
            self.run_prompt(None, st_request="request.json")

        toolbox_factory.assert_called_once_with(self.eod, out_fn="request.json")
        toolbox_factory.return_value.ingest_request.assert_called_once_with()
        self.eod.get_record_ids.assert_not_called()
        self.eod.order_st.assert_called_once()

    def test_no_submit_flag_reaches_order_process(self):
        prompter = self.run_prompt(
            "RCMImageProducts:12345", no_order=True)
        self.assertTrue(prompter.params["no_order"])
        self.assert_submitted(prompter, ["12345"])

    def test_record_lookup_preserves_matches_for_all_keys(self):
        eod = Mock()
        eod._search_stac.return_value = [self.stac_item]
        eod.eodms_rapi.get_results.side_effect = [
            [{"recordId": "12345"}],
            [],
            [{"recordId": "67890"}, {"recordId": "67891"}],
        ]

        result = EodmsUtils.get_record_ids(
            eod, "RCMImageProducts", ["RCM2_OK123", "MISSING_KEY", "RCM2_OK456"])

        self.assertEqual(result, ["12345", "67890", "67891"])
        self.assertEqual(eod.eodms_rapi.clear_results.call_count, 3)
        self.assertEqual(
            [call.kwargs["filters"] for call in eod.eodms_rapi.search.call_args_list],
            [{"ARCHIVE_IMAGE.ORDER_KEY": ("=", [key])}
             for key in ["RCM2_OK123", "MISSING_KEY", "RCM2_OK456"]],
        )

    def test_record_lookup_accepts_single_key(self):
        eod = Mock()
        eod._search_stac.return_value = [self.stac_item]
        eod.max_results = 1000
        eod.eodms_rapi.get_results.return_value = [{"recordId": "12345"}]

        self.assertEqual(
            EodmsUtils.get_record_ids(eod, "RCMImageProducts", "RCM2_OK123"),
            ["12345"],
        )
        eod.eodms_rapi.search.assert_called_once_with(
            "RCMImageProducts",
            filters={"ARCHIVE_IMAGE.ORDER_KEY": ("=", ["RCM2_OK123"])},
            dates=self.rapi_dates,
            max_results=1000,
        )

    def test_stac_wrapper_uses_configured_limit(self):
        eod = EodmsUtils.__new__(EodmsUtils)
        eod.max_results = 1000
        eod.search_api = Mock()
        eod.search_api.stac_search.return_value = []

        for maximum, expected in [(None, 1000), (0, 1000), (5, 5), ("7", 7)]:
            with self.subTest(maximum=maximum):
                eod._search_stac("RCMImageProducts", max_results=maximum)
                self.assertEqual(
                    eod.search_api.stac_search.call_args.kwargs["limit"],
                    expected,
                )

    def test_order_key_lookup_uses_stac_timestamps_to_bound_rapi(self):
        eod = EodmsUtils.__new__(EodmsUtils)
        eod.max_results = 1000
        eod.eodms_rapi = Mock()
        eod.eodms_rapi.get_results.return_value = [{"recordId": 12345}]
        eod.search_api = Mock()
        eod.search_api.stac_search.return_value = [self.stac_item]

        result = eod.get_record_ids("RCMImageProducts", "RCM2_OK123")

        self.assertEqual(result, ["12345"])
        eod.search_api.stac_search.assert_called_once_with(
            collections=["RCMImageProducts"], bbox=None, datetime=None,
            limit=1000, filter="order_key = 'RCM2_OK123'",
            filter_lang="cql2-text",
        )
        self.assertEqual(
            eod.eodms_rapi.search.call_args.kwargs["dates"], self.rapi_dates)
        eod.eodms_rapi.get_results.assert_called_once_with(
            "brief", show_progress=False)

    def test_record_lookup_rejects_failed_or_missing_record_responses(self):
        for response in [None, [{"errors": ["API failure"]}], [{"archiveId": "uuid-only"}]]:
            with self.subTest(response=response):
                eod = Mock()
                eod._search_stac.return_value = [self.stac_item]
                eod.eodms_rapi.get_results.return_value = response
                with self.assertRaisesRegex(RuntimeError, "lookup"):
                    EodmsUtils.get_record_ids(eod, "RCMImageProducts", "RCM2_OK123")

    def test_record_lookup_surfaces_query_errors(self):
        eod = Mock()
        eod._search_stac.return_value = [self.stac_item]
        query_error = Mock(spec=QueryError)
        query_error.get_msgs.return_value = "API failure"
        eod.eodms_rapi.search.return_value = query_error
        with self.assertRaisesRegex(RuntimeError, "API failure"):
            EodmsUtils.get_record_ids(eod, "RCMImageProducts", "RCM2_OK123")
        eod.eodms_rapi.get_results.assert_not_called()

    def test_missing_stac_match_never_queries_rapi(self):
        eod = Mock()
        eod._search_stac.return_value = []
        self.assertEqual(
            EodmsUtils.get_record_ids(eod, "RCMImageProducts", "MISSING_KEY"), [])
        eod.eodms_rapi.search.assert_not_called()

    def test_missing_or_invalid_stac_timestamps_never_query_rapi(self):
        for properties in [{}, {"datetime": "invalid"}, {"datetime": None}]:
            with self.subTest(properties=properties):
                eod = Mock()
                eod._search_stac.return_value = [{"properties": properties}]
                with self.assertRaisesRegex(RuntimeError, "acquisition timestamp"):
                    EodmsUtils.get_record_ids(eod, "RCMImageProducts", "RCM2_OK123")
                eod.eodms_rapi.search.assert_not_called()

    def test_stac_failure_never_queries_rapi(self):
        eod = Mock()
        eod._search_stac.side_effect = RuntimeError("STAC unavailable")
        with self.assertRaisesRegex(RuntimeError, "STAC unavailable"):
            EodmsUtils.get_record_ids(eod, "RCMImageProducts", "RCM2_OK123")
        eod.eodms_rapi.search.assert_not_called()

    def test_order_key_filter_escapes_quotes(self):
        eod = Mock()
        eod._search_stac.return_value = []
        EodmsUtils.get_record_ids(eod, "RCMImageProducts", "KEY_WITH_'QUOTE")
        eod._search_stac.assert_called_once_with(
            "RCMImageProducts", filters="order_key = 'KEY_WITH_''QUOTE'")

    def test_each_order_key_has_its_own_time_bound(self):
        eod = Mock()
        eod._search_stac.side_effect = [
            [self.stac_item],
            [{"properties": {"datetime": "2022-01-01T10:00:00Z"}}],
        ]
        eod.eodms_rapi.get_results.return_value = [{"recordId": "12345"}]
        EodmsUtils.get_record_ids(eod, "RCMImageProducts", ["KEY_ONE", "KEY_TWO"])
        self.assertEqual(
            [call.kwargs["dates"] for call in eod.eodms_rapi.search.call_args_list],
            [self.rapi_dates, [{"start": "20220101_100000", "end": "20220102_100000"}]],
        )

    def test_stac_intervals_are_combined_and_normalized_to_utc(self):
        eod = Mock()
        eod._search_stac.return_value = [
            {"properties": {
                "start_datetime": "2021-10-10T22:52:02-04:00",
                "end_datetime": "2021-10-10T22:53:02-04:00",
            }},
            {"properties": {
                "start_datetime": "2021-10-11T03:00:00Z",
                "end_datetime": "2021-10-11T03:01:00Z",
            }},
        ]
        eod.eodms_rapi.get_results.return_value = [{"recordId": "12345"}]
        EodmsUtils.get_record_ids(eod, "RCMImageProducts", "RCM2_OK123")
        self.assertEqual(
            eod.eodms_rapi.search.call_args.kwargs["dates"],
            [{"start": "20211011_025202", "end": "20211011_030100"}],
        )


class TestSarToolboxNoSubmit(unittest.TestCase):
    def make_request(self, path):
        eod = Mock()
        eod.silent = False
        eod.eodms_rapi.get_metadata.return_value = {"authenticatedUser": "test-user"}
        toolbox = SARToolbox.__new__(SARToolbox)
        toolbox.eod = eod
        toolbox.logger = Mock()
        toolbox.full_request = None
        toolbox.out_fn = path
        toolbox.category_runs = []
        toolbox.polarization = SimpleNamespace(value=[])
        toolbox.constants = {"polarizations": []}
        return eod, toolbox

    def test_no_submit_saves_real_json_without_ordering(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "request.json")
            eod, toolbox = self.make_request(path)
            with patch("scripts.utils.click.confirm") as confirm:
                EodmsProcess.order_st(eod, toolbox, {
                    "input_val": {
                        "collection_id": "RCMImageProducts",
                        "record_ids": ["12345"],
                    },
                    "no_order": True,
                })
            with open(path, encoding="utf-8") as request_file:
                saved = json.load(request_file)
            self.assertEqual(saved["items"][0]["recordId"], "12345")
            confirm.assert_not_called()
            eod.eodms_rapi.order_json.assert_not_called()
            eod.eodms_rapi.get_record.assert_not_called()
            eod._download_items.assert_not_called()

    def test_declining_after_save_keeps_json_without_submitting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "request.json")
            eod, toolbox = self.make_request(path)

            def decline(*args, **kwargs):
                self.assertTrue(os.path.isfile(path))
                self.assertFalse(kwargs["default"])
                return False

            params = {
                "process": "order_st",
                "input_val": {"collection_id": "RCMImageProducts", "record_ids": ["12345"]},
            }
            with patch("scripts.utils.click.confirm", side_effect=decline) as confirm:
                EodmsProcess.order_st(eod, toolbox, params)
            confirm.assert_called_once()
            eod.eodms_rapi.order_json.assert_not_called()
            eod._download_items.assert_not_called()
            self.assertTrue(os.path.isfile(path))
            self.assertTrue(params["no_order"])
            self.assertEqual(params["st_request"], path)
            self.assertIsNone(params["input_val"])
            prompter = Prompter(eod, Mock(), params)
            with cli.make_context("prompt", []):
                syntax = prompter.build_syntax()
            self.assertIn(f"-st {path}", syntax)
            self.assertIn("-nord", syntax)
            self.assertNotIn("-i ", syntax)

    def test_rerun_with_saved_path_spaces_and_submission_enabled(self):
        prompter = Prompter(Mock(), Mock(), {
            "process": "order_st", "st_request": r"C:\my requests\request.json",
            "input_val": {"record_ids": ["stale"]}, "no_order": False,
        })
        with cli.make_context("prompt", []):
            syntax = prompter.build_syntax()
        self.assertIn('-st "C:\\my requests\\request.json"', syntax)
        self.assertNotIn("-nord", syntax)
        self.assertNotIn("-i ", syntax)

    def test_unsaved_request_warns_instead_of_printing_incomplete_command(self):
        prompter = Prompter(Mock(), Mock(), {"process": "order_st"})
        with patch("eodms_prompt.print") as print_message:
            prompter.print_syntax()
        self.assertEqual(prompter.cli_syntax, "")
        self.assertIn("not saved", print_message.call_args.args[0])

    def test_confirming_submission_continues_to_order(self):
        eod, toolbox = self.make_request("request.json")
        toolbox.full_request = {"items": []}
        eod.eodms_rapi.order_json.side_effect = RuntimeError("submission reached")
        with patch("scripts.utils.click.confirm", return_value=True), \
             self.assertRaisesRegex(RuntimeError, "submission reached"):
            EodmsProcess.order_st(eod, toolbox, {
                "input_val": {"collection_id": "RCMImageProducts", "record_ids": ["12345"]},
            })
        eod.eodms_rapi.order_json.assert_called_once()

    def test_silent_without_flag_preserves_submission(self):
        eod, toolbox = self.make_request("request.json")
        eod.silent = True
        toolbox.full_request = {"items": []}
        eod.eodms_rapi.order_json.side_effect = RuntimeError("submission reached")
        with patch("scripts.utils.click.confirm") as confirm, \
             self.assertRaisesRegex(RuntimeError, "submission reached"):
            EodmsProcess.order_st(eod, toolbox, {
                "input_val": {"collection_id": "RCMImageProducts", "record_ids": ["12345"]},
            })
        confirm.assert_not_called()

    def test_silent_with_flag_never_submits_loaded_request(self):
        eod, toolbox = self.make_request("request.json")
        eod.silent = True
        toolbox.full_request = {"items": []}
        with tempfile.TemporaryDirectory() as directory:
            toolbox.out_fn = os.path.join(directory, "request.json")
            with open(toolbox.out_fn, "w", encoding="utf-8") as request_file:
                json.dump({"items": [{
                    "collectionId": "RCMImageProducts", "recordId": "12345",
                }]}, request_file)
            with patch("scripts.utils.click.confirm") as confirm:
                EodmsProcess.order_st(eod, toolbox, {"no_order": True})
        confirm.assert_not_called()
        eod.eodms_rapi.order_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
