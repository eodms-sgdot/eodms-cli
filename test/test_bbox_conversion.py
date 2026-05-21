#!/usr/bin/env python
"""Test the STAC feature to bbox conversion function."""

import sys
import os
import json
import fiona
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.utils import _stac_feature_to_bbox

# Test 1: Features as tuple format [('INTERSECTS', geojson)]
print("Test 1: Features as tuple with GeoJSON dict")
geojson_dict = {
    "type": "Polygon",
    "coordinates": [[
        [-75.9, 45.2],
        [-75.5, 45.2],
        [-75.5, 45.5],
        [-75.9, 45.5],
        [-75.9, 45.2]
    ]]
}
features = [('INTERSECTS', geojson_dict)]
result = _stac_feature_to_bbox(features)
print(f"  Input: {features}")
print(f"  Output: {result}")
print()

# Test 2: Features as tuple with GeoJSON string
print("Test 2: Features as tuple with GeoJSON string")
geojson_str = json.dumps(geojson_dict)
features = [('INTERSECTS', geojson_str)]
result = _stac_feature_to_bbox(features)
print(f"  Input: [('INTERSECTS', '<json_string>')]")
print(f"  Output: {result}")
print()

# Test 3: Features as list with GeoJSON dict (direct)
print("Test 3: Features as list with GeoJSON dict (direct)")
features = [geojson_dict]
result = _stac_feature_to_bbox(features)
print(f"  Input: [{geojson_dict}]")
print(f"  Output: {result}")
print()

# Test 4: Load from actual file
print("Test 4: Load from actual ottawa.geojson file")
geojson_file = os.path.join(os.path.dirname(__file__), 'ottawa.geojson')
file_geoms = []
if os.path.exists(geojson_file):
    with fiona.open(geojson_file, 'r') as src:
        for feat in src:
            geom = feat.get('geometry') if isinstance(feat, dict) \
                else getattr(feat, 'geometry', None)
            if geom:
                file_geoms.append(shape(geom))

    if file_geoms:
        # Try with first feature's geometry converted back to GeoJSON-like dict
        first_geom = file_geoms[0]
        features = [('INTERSECTS', mapping(first_geom))]
        result = _stac_feature_to_bbox(features)
        print(f"  Geometry type: {first_geom.geom_type}")
        print(f"  Output bbox: {result}")
    else:
        print("  No valid geometries found in file")
else:
    print(f"  File not found: {geojson_file}")
print()

# Test 5: Try with unioned shapely geometry from Fiona read
print("Test 5: Features with Fiona+Shapely union geometry")
if file_geoms:
    merged = unary_union(file_geoms)
    features = [('INTERSECTS', merged)]
    result = _stac_feature_to_bbox(features)
    print(f"  Output: {result}")
else:
    print("  Skipped (no file geometries loaded)")
