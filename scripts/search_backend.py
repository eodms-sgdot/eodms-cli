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

from abc import ABC, abstractmethod
import logging
from typing import Any, Dict, List, Optional


class SearchBackend(ABC):
    """Interface for search backends used by EODMS-CLI."""

    @abstractmethod
    def search(self, coll_id, filters=None, features=None, dates=None,
             max_results=None, hit_count=False) -> Any:
        """Run a search query using the backend implementation."""

        raise NotImplementedError

    @abstractmethod
    def get_results(self) -> List[Dict[str, Any]]:
        """Return cached/last search results from backend implementation."""

        raise NotImplementedError

    @abstractmethod
    def get_available_fields(self, coll_id, field_type='title') -> Optional[Dict[str, Any]]:
        """Get available fields for a collection."""

        raise NotImplementedError


class RapiSearchBackend(SearchBackend):
    """Adapter for py-eodms-rapi search behavior."""

    def __init__(self, rapi_client):
        self.rapi_client = rapi_client

    def search(self, coll_id, filters=None, features=None, dates=None,
               max_results=None, hit_count=False):
        return self.rapi_client.search(coll_id, filters, features, dates,
                                       None, max_results,
                                       hit_count=hit_count)

    def get_results(self):
        return self.rapi_client.get_results()

    def get_available_fields(self, coll_id, field_type='title'):
        return self.rapi_client.get_available_fields(coll_id, field_type)

    def get_collections(self, as_list=False):
        if as_list:
            return self.rapi_client.get_collections(True, opt='both')
        return self.rapi_client.get_collections()

    def print_queryables(self, coll_id):
        return False


def _stac_feature_to_bbox(features):
    """Convert an INTERSECTS feature list to a flat bbox list.

    Features from the CLI are expressed as [('INTERSECTS', wkt_or_geojson)].
    The STAC backend needs [west, south, east, north].  When no features are
    provided this returns None so the search is unconstrained spatially.
    """
    if not features:
        return None

    try:
        from shapely import wkt as shapely_wkt
        from shapely.geometry import shape
        import json
        import os
        
        logger = logging.getLogger('eodms')
        logger.debug(f"_stac_feature_to_bbox input type: {type(features)}, value: {features}")

        # Handle different input formats
        geom_str = None
        if isinstance(features, (list, tuple)):
            if len(features) > 0:
                first_item = features[0]
                logger.debug(f"First item type: {type(first_item)}, value: {first_item}")
                
                if isinstance(first_item, (list, tuple)) and len(first_item) >= 2:
                    # Format: [('INTERSECTS', geom)]
                    geom_str = first_item[1]
                elif isinstance(first_item, dict):
                    # Format: [geojson_dict]
                    geom_str = first_item
                elif isinstance(first_item, str):
                    # Format: [geojson_string] or [wkt_string]
                    geom_str = first_item
        else:
            # Direct geom string or object
            geom_str = features

        if geom_str is None:
            logger.warning("Could not extract geometry from features")
            return None

        logger.debug(f"Extracted geometry: {geom_str}")

        # If INTERSECTS contains a local file path, load its JSON payload.
        if isinstance(geom_str, str) and os.path.isfile(geom_str):
            try:
                geom_path = geom_str
                with open(geom_str, 'r', encoding='utf-8') as fh:
                    geom_str = json.load(fh)
                logger.debug(f"Loaded geometry from file path: {geom_path}")
            except Exception as file_err:
                logger.error(f"Failed to load geometry file '{geom_str}': {file_err}")
                return None

        # Try WKT first, then GeoJSON
        geom = None
        try:
            # If it's a string, try WKT first
            if isinstance(geom_str, str):
                geom = shapely_wkt.loads(geom_str)
                logger.debug(f"Successfully parsed as WKT")
            else:
                raise ValueError("Not a string, skip WKT")
        except Exception as wkt_err:
            logger.debug(f"WKT parsing failed: {wkt_err}, trying GeoJSON")
            try:
                # Try to parse as GeoJSON
                if isinstance(geom_str, str):
                    geom_obj = json.loads(geom_str)
                else:
                    geom_obj = geom_str
                
                # Handle FeatureCollection by extracting and merging all geometries
                if isinstance(geom_obj, dict) and geom_obj.get('type') == 'FeatureCollection':
                    logger.debug("Detected FeatureCollection, extracting geometries")
                    from shapely.ops import unary_union
                    geometries = []
                    for feature in geom_obj.get('features', []):
                        if feature.get('geometry'):
                            geometries.append(shape(feature['geometry']))
                    if geometries:
                        geom = unary_union(geometries)
                        logger.debug(f"Merged {len(geometries)} geometries from FeatureCollection")
                    else:
                        logger.error("FeatureCollection has no valid geometries")
                        return None
                elif isinstance(geom_obj, dict) and geom_obj.get('type') == 'Feature':
                    feature_geom = geom_obj.get('geometry')
                    if feature_geom is None:
                        logger.error("GeoJSON Feature has no geometry")
                        return None
                    geom = shape(feature_geom)
                else:
                    geom = shape(geom_obj)
                logger.debug(f"Successfully parsed as GeoJSON")
            except Exception as geojson_err:
                logger.error(f"Failed to parse as WKT or GeoJSON: WKT={wkt_err}, GeoJSON={geojson_err}")
                return None

        bounds = geom.bounds  # (minx, miny, maxx, maxy)
        bbox = list(bounds)
        logger.debug(f"Converted bbox: {bbox}")
        return bbox
    except Exception as e:
        logger = logging.getLogger('eodms')
        logger.error(f"Unexpected error in _stac_feature_to_bbox: {e}", exc_info=True)
        return None


def _parse_dates_to_stac(dates):
    """Convert the CLI dates list to an ISO 8601 datetime range string.

    The CLI passes dates as a list of dicts with 'start' and 'end' keys
    where values use the legacy CLI format (YYYYMMDD_HHMMSS), or as None.
    STAC datetime accepts "start/end" or open-ended ranges ("../end",
    "start/..").  Only the first date range is used.
    """
    if not dates:
        return None

    try:
        first = dates[0]
        start = _rapi_date_to_iso(first.get('start')) or '..'
        end = _rapi_date_to_iso(first.get('end')) or '..'
        return f"{start}/{end}"
    except Exception:
        return None


def _rapi_date_to_iso(date_str):
    """Convert a legacy CLI date string to ISO 8601 format.

    Handles format produced by _parse_dates():
        YYYYMMDD_HHMMSS  ->  YYYY-MM-DDTHH:MM:SSZ
    Also passes through already-valid ISO strings and open-ended '..' unchanged.
    """
    if not date_str or date_str == '..':
        return date_str

    # Normalise: replace underscore separator with T
    s = date_str.replace('_', 'T')

    # Already ISO (contains dashes) — ensure it ends with Z
    if '-' in s:
        return s if s.endswith('Z') else s + 'Z'

    # Expect YYYYMMDDTHHMMSS (15 chars after normalisation)
    if len(s) >= 15 and s[8] == 'T':
        dp = s[:8]    # YYYYMMDD
        tp = s[9:15]  # HHMMSS
        return (f"{dp[:4]}-{dp[4:6]}-{dp[6:8]}"
                f"T{tp[:2]}:{tp[2:4]}:{tp[4:6]}Z")

    # Fallback: return as-is
    return s


def _normalize_stac_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Map a raw STAC item dict to the internal EODMS-CLI record schema.

    The internal schema (consumed by image.Image.parse_record) expects at
    minimum: recordId, collectionId, archiveId, geometry (GeoJSON), plus any
    property keys that downstream code reads.
    """
    props = item.get('properties', {})

    # STAC id maps to recordId; prefer an explicit property if present
    record_id = props.get('eodms:recordId') or props.get('recordId') \
        or item.get('id')

    collection_id = item.get('collection') or props.get('collectionId') or ''

    # UUID / archiveId — look for common STAC asset or property keys
    archive_id = props.get('eodms:archiveId') or props.get('archiveId') \
        or props.get('uuid') or item.get('id')

    normalized: Dict[str, Any] = {
        'recordId': record_id,
        'collectionId': collection_id,
        'archiveId': archive_id,
        'title': props.get('title') or item.get('id', ''),
        'collectionTitle': collection_id,
        'thisRecordUrl': next(
            (lnk.get('href') for lnk in item.get('links', [])
             if lnk.get('rel') == 'self'), None),
        'geometry': item.get('geometry'),
    }

    # Merge all remaining properties so field filters still work downstream
    for k, v in props.items():
        if k not in normalized:
            normalized[k] = v

    return normalized


class StacSearchBackend(SearchBackend):
    """Search backend powered by eodms-py Search_API / STAC."""

    def __init__(self, aaa_api=None, environment='prod'):
        from eodms.search import Search_API
        self._search_api = Search_API(aaa_api=aaa_api, environment=environment)
        self._results: List[Dict[str, Any]] = []

    def search(self, coll_id, filters=None, features=None, dates=None,
               max_results=None, hit_count=False):
        """Run a STAC search and store results for get_results().

        STAC does not use a separate hit-count preflight. The hit_count flag
        is ignored and callers should inspect returned results directly.
        """
        import logging
        logger = logging.getLogger('eodms')
        
        logger.debug(f"StacSearchBackend.search called: coll_id={coll_id}, "
                     f"filters={filters}, features={features}, dates={dates}")
        
        bbox = _stac_feature_to_bbox(features)
        logger.debug(f"Resulting bbox from features: {bbox}")
        
        datetime_str = _parse_dates_to_stac(dates)
        logger.debug(f"Resulting datetime from dates: {datetime_str}")
        
        limit = int(max_results) if max_results else 1000

        # Build CQL2 filter string from the filters dict if provided
        cql2_filter = None
        if filters:
            clauses = []
            for field, condition in filters.items():
                if isinstance(condition, (list, tuple)) and len(condition) == 2:
                    op, val = condition
                    if isinstance(val, list):
                        sub_clauses = []
                        for v in val:
                            if isinstance(v, str):
                                sub_clauses.append(f"{field} {op} '{v}'")
                            else:
                                sub_clauses.append(f"{field} {op} {v}")
                        if len(sub_clauses) == 1:
                            clauses.append(sub_clauses[0])
                        elif len(sub_clauses) > 1:
                            clauses.append(f"({' OR '.join(sub_clauses)})")
                    elif isinstance(val, str):
                        clauses.append(f"{field} {op} '{val}'")
                    else:
                        clauses.append(f"{field} {op} {val}")
            if clauses:
                cql2_filter = ' AND '.join(clauses)

        search_kwargs: Dict[str, Any] = {}
        if cql2_filter:
            search_kwargs['filter'] = cql2_filter
            search_kwargs['filter_lang'] = 'cql2-text'

        logger.debug(f"Calling _search_api.stac_search with: collections={[coll_id]}, "
                     f"bbox={bbox}, datetime={datetime_str}, limit={limit}, "
                     f"kwargs={search_kwargs}")
        
        items = self._search_api.stac_search(
            collections=[coll_id],
            bbox=bbox,
            datetime=datetime_str,
            limit=limit,
            **search_kwargs,
        )

        self._results = [_normalize_stac_item(it) for it in items]
        logger.debug(f"STAC search returned {len(self._results)} results")

        return None

    def get_results(self) -> List[Dict[str, Any]]:
        return self._results

    def get_available_fields(self, coll_id, field_type='title') -> Optional[Dict]:
        """Return available queryable fields for a collection.

        Returns a dict in the shared backend shape:
            {'results': {field_name: ...}, 'query': {field_name: ...}}
        so callers that check av_fields['results'] work unchanged.
        """
        try:
            collection = self._search_api.client.get_collection(coll_id)
            if collection is None:
                return None
            queryables = collection.get_queryables()
            props = queryables.get('properties', {}) \
                if isinstance(queryables, dict) else {}
            fields = {k: v for k, v in props.items()}
            return {'results': fields, 'query': fields}
        except Exception:
            return None

    def print_queryables(self, coll_id):
        """Print STAC queryables using eodms-py's Search_API helper."""
        return self._search_api.print_queryables(self._search_api.client.get_collection(coll_id))
        
    def get_collections(self, as_list=False):
        """Return STAC collections in a shape compatible with existing CLI."""
        collections = []
        for coll in self._search_api.client.get_collections():
            collections.append({
                'id': coll.id,
                'title': getattr(coll, 'title', None) or coll.id,
                'aliases': []
            })

        if as_list:
            return collections

        return {c['id']: {'title': c['title'], 'aliases': c['aliases']}
                for c in collections}
