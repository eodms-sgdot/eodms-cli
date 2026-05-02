##############################################################################
#
# Copyright (c) His Majesty the King in Right of Canada, as
# represented by the Minister of Natural Resources, 2026
#
# Licensed under the MIT license
# (see LICENSE or <http://opensource.org/licenses/MIT>) All files in the
# project carrying such notice may not be copied, modified, or distributed
# except according to those terms.
#
##############################################################################

"""Contract tests for search backends.

Backends have different capabilities (for example STAC exposes fewer
queryables than RAPI), so tests focus on a minimal shared contract rather
than strict feature parity.

The tests use mocks for all network I/O so they run offline.
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Ensure the repo root is on the path when running directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.search_backend import (
    RapiSearchBackend,
    StacSearchBackend,
    _normalize_stac_item,
    _stac_feature_to_bbox,
    _parse_dates_to_stac,
    _rapi_date_to_iso,
)
from scripts.utils import EodmsUtils

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {'recordId', 'collectionId', 'archiveId'}

# A minimal RAPI-style result dict (what py-eodms-rapi returns)
RAPI_RESULT = {
    'recordId': '123456',
    'collectionId': 'RCMImageProducts',
    'archiveId': 'abc-def-uuid',
    'title': 'Test Image',
    'collectionTitle': 'RCM Image Products',
    'thisRecordUrl': 'https://example.com/record/123456',
    'geometry': {
        'type': 'Polygon',
        'coordinates': [[[-75, 45], [-74, 45], [-74, 46], [-75, 46], [-75, 45]]]
    },
    'metadata': [
        ['Acquisition Start Date', '2024-01-01T00:00:00Z'],
        ['Beam Mode', 'SC50MA'],
    ]
}

# A minimal STAC item dict (what pystac_client returns as .to_dict())
STAC_ITEM = {
    'type': 'Feature',
    'id': '123456',
    'collection': 'RCMImageProducts',
    'geometry': {
        'type': 'Polygon',
        'coordinates': [[[-75, 45], [-74, 45], [-74, 46], [-75, 46], [-75, 45]]]
    },
    'properties': {
        'datetime': '2024-01-01T00:00:00Z',
        'title': 'Test Image',
        'archiveId': 'abc-def-uuid',
        'beamMode': 'SC50MA',
    },
    'links': [
        {'rel': 'self', 'href': 'https://example.com/record/123456'}
    ],
    'assets': {},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rapi_backend(results):
    """Build a RapiSearchBackend backed by a mock RAPI client."""
    mock_rapi = MagicMock()
    mock_rapi.get_results.return_value = results
    mock_rapi.get_available_fields.return_value = {
        'results': {'beamMode': 'Beam Mode'},
        'query': {'beamMode': 'Beam Mode'},
    }
    return RapiSearchBackend(mock_rapi)


def _make_stac_backend(stac_items):
    """Build a StacSearchBackend with a mocked Search_API."""
    with patch('scripts.search_backend.StacSearchBackend.__init__',
               return_value=None):
        backend = StacSearchBackend.__new__(StacSearchBackend)

    mock_search_api = MagicMock()
    mock_search_api.stac_search.return_value = stac_items

    mock_collection = MagicMock()
    mock_collection.get_queryables.return_value = {
        'properties': {'beamMode': {'type': 'string'}}
    }
    mock_search_api.client.get_collection.return_value = mock_collection

    backend._search_api = mock_search_api
    backend._results = []
    return backend


# ---------------------------------------------------------------------------
# Contract: normalized result shape
# ---------------------------------------------------------------------------

class TestResultShape(unittest.TestCase):
    """Verify both backends produce records with the required internal fields."""

    def _assert_required_fields(self, result):
        for field in REQUIRED_FIELDS:
            self.assertIn(field, result,
                          f"Missing required field '{field}' in result")
            self.assertIsNotNone(result[field],
                                 f"Required field '{field}' must not be None")

    def test_rapi_result_has_required_fields(self):
        backend = _make_rapi_backend([RAPI_RESULT])
        backend.search('RCMImageProducts')
        results = backend.get_results()
        self.assertEqual(len(results), 1)
        self._assert_required_fields(results[0])

    def test_stac_result_has_required_fields(self):
        backend = _make_stac_backend([STAC_ITEM])
        backend.search('RCMImageProducts')
        results = backend.get_results()
        self.assertEqual(len(results), 1)
        self._assert_required_fields(results[0])

    def test_stac_result_has_geometry(self):
        backend = _make_stac_backend([STAC_ITEM])
        backend.search('RCMImageProducts')
        result = backend.get_results()[0]
        self.assertIn('geometry', result)
        self.assertIsNotNone(result['geometry'])


class TestSessionSetup(unittest.TestCase):

    @patch('scripts.utils.field.EodFieldMapper')
    @patch('scripts.utils.dds.DDS_API')
    @patch('scripts.utils.aaa.AAA_API')
    @patch('scripts.utils.EODMSRAPI')
    def test_stac_session_does_not_initialize_field_mapper(self,
                                                           mock_rapi_cls,
                                                           _mock_aaa_cls,
                                                           _mock_dds_cls,
                                                           mock_field_mapper):
        mock_rapi = MagicMock()
        mock_rapi_cls.return_value = mock_rapi

        eod = EodmsUtils(search_backend='stac')
        eod.create_session('user', 'pass')

        mock_field_mapper.assert_not_called()
        self.assertIsNone(eod.field_mapper)

    @patch('scripts.utils.field.EodFieldMapper')
    @patch('scripts.utils.dds.DDS_API')
    @patch('scripts.utils.aaa.AAA_API')
    @patch('scripts.utils.EODMSRAPI')
    def test_rapi_session_initializes_field_mapper(self,
                                                   mock_rapi_cls,
                                                   _mock_aaa_cls,
                                                   _mock_dds_cls,
                                                   mock_field_mapper):
        mock_rapi = MagicMock()
        mock_rapi_cls.return_value = mock_rapi
        mock_field_mapper.return_value = MagicMock()

        eod = EodmsUtils(search_backend='rapi')
        eod.create_session('user', 'pass')

        mock_field_mapper.assert_called_once()
        self.assertIsNotNone(eod.field_mapper)


class TestStacFilterHelpers(unittest.TestCase):

    def _make_eod(self):
        eod = EodmsUtils(search_backend='stac')
        eod.logger = MagicMock()
        eod.print_msg = MagicMock()
        eod.get_available_fields = MagicMock(return_value={
            'results': {
                'beamMode': {'type': 'string'},
                'incidenceAngle': {'type': 'number'},
            }
        })
        return eod

    def test_parse_stac_filters_preserves_queryable_names(self):
        eod = self._make_eod()
        result = eod._parse_stac_filters([
            'beamMode=SC50MA|SC100',
            'incidenceAngle>=20'
        ], 'RCMImageProducts')

        self.assertEqual(result['beamMode'], ('=', ['SC50MA', 'SC100']))
        self.assertEqual(result['incidenceAngle'], ('>=', ['20']))

    def test_validate_stac_filters_accepts_known_queryables(self):
        eod = self._make_eod()
        result = eod._validate_stac_filters('beamMode=SC50MA',
                                            'RCMImageProducts')
        self.assertEqual(result, 'beamMode=SC50MA')

    def test_validate_stac_filters_rejects_unknown_queryables(self):
        eod = self._make_eod()
        result = eod._validate_stac_filters('unknownField=abc',
                                            'RCMImageProducts')
        self.assertFalse(result)

    def test_parse_filters_dispatches_to_stac_helper(self):
        eod = self._make_eod()
        eod.coll_id = 'RCMImageProducts'

        with patch.object(eod, '_parse_stac_filters',
                          return_value={'beamMode': ('=', ['SC50MA'])}) as mock_helper:
            result = eod._parse_filters(['beamMode=SC50MA'])

        mock_helper.assert_called_once_with(['beamMode=SC50MA'],
                                            'RCMImageProducts')
        self.assertEqual(result, {'beamMode': ('=', ['SC50MA'])})

    def test_validate_filters_dispatches_to_stac_helper(self):
        eod = self._make_eod()

        with patch.object(eod, '_validate_stac_filters',
                          return_value='beamMode=SC50MA') as mock_helper:
            result = eod.validate_filters('beamMode=SC50MA',
                                          'RCMImageProducts')

        mock_helper.assert_called_once_with('beamMode=SC50MA',
                                            'RCMImageProducts')
        self.assertEqual(result, 'beamMode=SC50MA')


# ---------------------------------------------------------------------------
# Contract: get_available_fields response shape
# ---------------------------------------------------------------------------

class TestAvailableFields(unittest.TestCase):

    def test_rapi_available_fields_has_results_key(self):
        backend = _make_rapi_backend([])
        fields = backend.get_available_fields('RCMImageProducts')
        self.assertIn('results', fields)

    def test_stac_available_fields_has_results_key(self):
        backend = _make_stac_backend([])
        fields = backend.get_available_fields('RCMImageProducts')
        self.assertIsNotNone(fields)
        assert fields is not None
        self.assertIn('results', fields)

    def test_stac_available_fields_returns_none_for_missing_collection(self):
        backend = _make_stac_backend([])
        backend._search_api.client.get_collection.return_value = None
        fields = backend.get_available_fields('NonExistent')
        self.assertIsNone(fields)


# ---------------------------------------------------------------------------
# Unit tests: normalizer helpers
# ---------------------------------------------------------------------------

class TestNormalizeStacItem(unittest.TestCase):

    def test_id_becomes_record_id(self):
        result = _normalize_stac_item(STAC_ITEM)
        self.assertEqual(result['recordId'], '123456')

    def test_collection_becomes_collection_id(self):
        result = _normalize_stac_item(STAC_ITEM)
        self.assertEqual(result['collectionId'], 'RCMImageProducts')

    def test_self_link_becomes_record_url(self):
        result = _normalize_stac_item(STAC_ITEM)
        self.assertEqual(result['thisRecordUrl'],
                         'https://example.com/record/123456')

    def test_geometry_preserved(self):
        result = _normalize_stac_item(STAC_ITEM)
        self.assertEqual(result['geometry'], STAC_ITEM['geometry'])

    def test_extra_properties_merged(self):
        result = _normalize_stac_item(STAC_ITEM)
        self.assertIn('beamMode', result)
        self.assertEqual(result['beamMode'], 'SC50MA')

    def test_explicit_record_id_property_takes_precedence(self):
        item = {**STAC_ITEM,
                'properties': {**STAC_ITEM['properties'],
                                'eodms:recordId': '999999'}}
        result = _normalize_stac_item(item)
        self.assertEqual(result['recordId'], '999999')


class TestStacFeatureToBbox(unittest.TestCase):

    def test_none_features_returns_none(self):
        self.assertIsNone(_stac_feature_to_bbox(None))

    def test_wkt_polygon_returns_bbox(self):
        wkt = 'POLYGON ((-75 45, -74 45, -74 46, -75 46, -75 45))'
        bbox = _stac_feature_to_bbox([('INTERSECTS', wkt)])
        self.assertIsNotNone(bbox)
        assert bbox is not None
        self.assertEqual(len(bbox), 4)
        self.assertAlmostEqual(bbox[0], -75.0)
        self.assertAlmostEqual(bbox[1], 45.0)
        self.assertAlmostEqual(bbox[2], -74.0)
        self.assertAlmostEqual(bbox[3], 46.0)


class TestParseDatesToStac(unittest.TestCase):

    def test_none_returns_none(self):
        self.assertIsNone(_parse_dates_to_stac(None))

    def test_start_and_end_formatted_correctly(self):
        dates = [{'start': '20240101_000000', 'end': '20240601_000000'}]
        result = _parse_dates_to_stac(dates)
        self.assertEqual(result, '2024-01-01T00:00:00Z/2024-06-01T00:00:00Z')

    def test_missing_end_uses_open_range(self):
        dates = [{'start': '20240101_000000', 'end': None}]
        result = _parse_dates_to_stac(dates)
        self.assertEqual(result, '2024-01-01T00:00:00Z/..')

    def test_missing_start_uses_open_range(self):
        dates = [{'start': None, 'end': '20240601_000000'}]
        result = _parse_dates_to_stac(dates)
        self.assertEqual(result, '../2024-06-01T00:00:00Z')


class TestLegacyCliDateToIso(unittest.TestCase):

    def test_legacy_cli_format_converts_correctly(self):
        self.assertEqual(_rapi_date_to_iso('20260502_000000'),
                         '2026-05-02T00:00:00Z')

    def test_legacy_cli_format_with_time(self):
        self.assertEqual(_rapi_date_to_iso('20240115_143025'),
                         '2024-01-15T14:30:25Z')

    def test_open_range_passthrough(self):
        self.assertEqual(_rapi_date_to_iso('..'), '..')

    def test_none_passthrough(self):
        self.assertIsNone(_rapi_date_to_iso(None))

    def test_already_iso_passthrough(self):
        self.assertEqual(_rapi_date_to_iso('2024-01-01T00:00:00Z'),
                         '2024-01-01T00:00:00Z')

    def test_already_iso_without_z_gets_z(self):
        self.assertEqual(_rapi_date_to_iso('2024-01-01T00:00:00'),
                         '2024-01-01T00:00:00Z')


if __name__ == '__main__':
    unittest.main()
