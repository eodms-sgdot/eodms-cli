import os
import sys
import unittest
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eodms_cli import (
    _extract_order_key,
    _search_items_by_order_keys,
    make_aaa,
    make_search,
    resolve_credentials,
)


def _normalize_items(payload: Any) -> List[Dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, dict):
        features = payload.get("features")
        if isinstance(features, list):
            return [item for item in features if isinstance(item, dict)]
        return [payload]
    return [item for item in list(payload) if isinstance(item, dict)]


def _parse_iso8601(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _extract_creation_date(item: Dict[str, Any]) -> Optional[datetime]:
    keys = (
        "creation_date",
        "creationDate",
        "created",
        "published",
        "datetime",
    )

    for key in keys:
        parsed = _parse_iso8601(item.get(key))
        if parsed is not None:
            return parsed

    props = item.get("properties")
    if isinstance(props, dict):
        for key in keys:
            parsed = _parse_iso8601(props.get(key))
            if parsed is not None:
                return parsed

    return None


class TestRcmArdCreationDelta(unittest.TestCase):
    def test_rcm_ard_to_image_products_creation_delta(self):
        username, password = resolve_credentials(None, None)
        if not username or not password:
            self.skipTest("Missing credentials; set ~/.eodms/config.ini or pass env-backed credentials.")

        environment = os.getenv("EODMS_ENV", "prod")
        aaa_api = make_aaa(username, password, environment)
        search_api = make_search(aaa_api, environment)

        today = datetime.now(timezone.utc).date().isoformat()
        datetime_range = f"{today}T00:00:00Z/{today}T23:59:59Z"

        preferred_collection = os.getenv("EODMS_ARD_COLLECTION", "rcm-ard")
        candidates = []
        for name in (preferred_collection, "RCM-ARD"):
            if name and name not in candidates:
                candidates.append(name)

        ard_items: List[Dict[str, Any]] = []
        last_error: Optional[Exception] = None
        for collection_name in candidates:
            try:
                payload = search_api.search_multiple_geometries(
                    s_intersect_list=[{"name": None, "wkt": None}],
                    collection=collection_name,
                    datetime_range=datetime_range,
                    bbox=None,
                    limit=25,
                    filter_text=None,
                )
                ard_items = _normalize_items(payload)
                if ard_items:
                    break
            except Exception as exc:
                last_error = exc

        if not ard_items:
            if last_error is not None:
                self.skipTest(f"Unable to query today's RCM-ARD scenes: {last_error}")
            self.skipTest("No RCM-ARD scenes found for today.")

        ard_by_order_key: Dict[str, Dict[str, Any]] = {}
        for item in ard_items:
            order_key = _extract_order_key(item)
            if not order_key or order_key in ard_by_order_key:
                continue
            ard_by_order_key[order_key] = item
            if len(ard_by_order_key) == 5:
                break

        if not ard_by_order_key:
            self.skipTest("No RCM-ARD scenes with order_key found for today.")

        order_keys = list(ard_by_order_key.keys())
        image_products_collection = os.getenv("EODMS_IMAGE_PRODUCTS_COLLECTION", "RCMImageProducts")

        items_by_order_key = _search_items_by_order_keys(
            search_api,
            image_products_collection,
            order_keys,
            chunk_size=100,
        )

        comparisons = []
        for order_key in order_keys:
            ard_item = ard_by_order_key.get(order_key)
            mip_item = items_by_order_key.get(order_key)
            if ard_item is None or mip_item is None:
                continue

            ard_created = _extract_creation_date(ard_item)
            mip_created = _extract_creation_date(mip_item)
            if ard_created is None or mip_created is None:
                continue

            delta_seconds = (mip_created - ard_created).total_seconds()
            delta_hours = delta_seconds / 3600.0
            comparisons.append(
                {
                    "order_key": order_key,
                    "ard_creation_date": ard_created.isoformat(),
                    "image_product_creation_date": mip_created.isoformat(),
                    "delta_seconds": delta_seconds,
                    "delta_hours": delta_hours,
                }
            )

        if not comparisons:
            self.skipTest("No matched order_key records with parseable creation_date values.")

        # Provide a concise report in test output.
        print("\norder_key\tard_creation_date\timage_product_creation_date\tdelta_hours\tdelta_seconds")
        for row in comparisons:
            print(
                f"{row['order_key']}\t{row['ard_creation_date']}\t"
                f"{row['image_product_creation_date']}\t"
                f"{row['delta_hours']:.3f}\t{row['delta_seconds']}"
            )

        self.assertGreaterEqual(len(comparisons), 1)
