from eodms_dds import dds, aaa, config
import requests
from typing import List, Dict, Any, Optional
import os
import click

class OGCFeature:
    def __init__(self, feature_dict):
        self.id = feature_dict.get('id')
        self.type = feature_dict.get('type')
        self.geometry = feature_dict.get('geometry')
        self.properties = feature_dict.get('properties', {})
        self.raw = feature_dict
    def __repr__(self):
        return f"OGCFeature(id={self.id}, type={self.type})"
    def to_dict(self):
        return self.raw

class OGCFeatureCollection:
    def __init__(self, collection_dict):
        self.type = collection_dict.get('type')
        self.features = [OGCFeature(f) for f in collection_dict.get('features', [])]
        self.raw = collection_dict
    def __repr__(self):
        return f"OGCFeatureCollection(type={self.type}, features={len(self.features)})"
    def to_dict(self):
        return self.raw

class OGCFeaturesClient:
    def __init__(self, base_url, access_token=None, verify_ssl=True):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.verify = verify_ssl
        self.headers = {}
        if access_token:
            self.headers['Authorization'] = f'Bearer {access_token}'

    def get_collections(self):
        url = f"{self.base_url}/collections"
        resp = self.session.get(url, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def get_features(self, collection_id, bbox=None, datetime=None, limit=10):
        url = f"{self.base_url}/collections/{collection_id}/items"
        params = {}
        if bbox:
            params['bbox'] = ','.join(str(x) for x in bbox)
        if datetime:
            params['datetime'] = datetime
        params['limit'] = limit
        
        all_features = []
        page_token = None
        page_count = 0
        
        while len(all_features) < limit:
            if page_token:
                print(f"Fetching page {page_count + 1} (features: {len(all_features)} token: {page_token})")
                params['page_token'] = page_token
            page_count += 1
            resp = self.session.get(url, headers=self.headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            features = data.get('features', [])
            all_features.extend(features)
            
            # Check for next page token in links or directly in response
            page_token = None
            links = data.get('links', [])
            for link in links:
                if link.get('rel') == 'next':
                    # Extract page_token from next link if present
                    next_url = link.get('href', '')
                    if 'page_token=' in next_url:
                        page_token = next_url.split('page_token=')[1].split('&')[0]
                    break
            
            # Alternative: check if page_token is directly in response
            if not page_token:
                page_token = data.get('page_token')
            
            if not page_token:
                break
        
        # Construct final collection with all features
        final_data = data.copy()
        final_data['features'] = all_features
        return OGCFeatureCollection(final_data)

    def get_feature(self, collection_id, feature_id):
        url = f"{self.base_url}/collections/{collection_id}/items/{feature_id}"
        resp = self.session.get(url, headers=self.headers)
        resp.raise_for_status()
        return OGCFeature(resp.json())

# OGC Features: /collections

def get_collections(aaa_api=None, environment='prod') -> List[Dict[str, Any]]:
    domain_config = config.get_domain_config(environment)
    domain = domain_config['domain']
    search_endpoint = f"{domain}/search"
    verify_ssl = domain_config.get('verify_ssl', True)
    access_token = None
    if aaa_api:
        access_token = aaa_api.get_access_token()
    client = OGCFeaturesClient(search_endpoint, access_token, verify_ssl)
    return client.get_collections()

# OGC Features: /collections/{collectionId}/items

def get_features(
    collection_id: str,
    aaa_api=None,
    environment='prod',
    bbox: Optional[List[float]] = None,
    datetime: Optional[str] = None,
    limit: int = 10
) -> Dict[str, Any]:
    domain_config = config.get_domain_config(environment)
    domain = domain_config['domain']
    search_endpoint = f"{domain}/search"
    verify_ssl = domain_config.get('verify_ssl', True)
    access_token = None
    if aaa_api:
        access_token = aaa_api.get_access_token()
    client = OGCFeaturesClient(search_endpoint, access_token, verify_ssl)
    return client.get_features(collection_id, bbox, datetime, limit)

# OGC Features: /collections/{collectionId}/items/{featureId}

def get_feature(
    collection_id: str,
    feature_id: str,
    aaa_api=None,
    environment='prod'
) -> Dict[str, Any]:
    domain_config = config.get_domain_config(environment)
    domain = domain_config['domain']
    search_endpoint = f"{domain}/search"
    verify_ssl = domain_config.get('verify_ssl', True)
    access_token = None
    if aaa_api:
        access_token = aaa_api.get_access_token()
    client = OGCFeaturesClient(search_endpoint, access_token, verify_ssl)
    return client.get_feature(collection_id, feature_id)

def download(dds_api, collection, item_uuid, out_folder):

    item_info = dds_api.get_item(collection, item_uuid)

    if item_info is None:
        return None

    if 'download_url' not in item_info.keys():
        return None

    dds_api.download_item(os.path.abspath(out_folder))

    return item_info

def run(username, password, collection, feature_id, env, bbox, datetime, limit):
    domain_config = config.get_domain_config(env)
    base_url = f"{domain_config['domain']}/search"
    verify_ssl = domain_config.get('verify_ssl', True)
    access_token = None
    if username and password:
        aaa_api = aaa.AAA_API(username, password, env)
        access_token = aaa_api.get_access_token()
    client = OGCFeaturesClient(base_url, access_token, verify_ssl)

    if not collection and not feature_id:
        result = client.get_collections()
        collections = result.get('collections', [])
        print(f"Available collections: {len(collections)}")
        for coll in collections:
            print(f"  - {coll.get('id')}: {coll.get('title', 'N/A')}")
        return

    if feature_id:
        feature = client.get_feature(collection, feature_id)
        print(f"Feature ID: {feature.id} geom: {feature.geometry} ")

        dds_api = dds.DDS_API(aaa_api, env)

        # If UUID is provided, skip search and download directly
        print(f"Downloading image with UUID: {feature.id}")
        download(dds_api, collection, feature.id, '.')
            
        return

    if collection:
        result = client.get_features(collection, bbox, datetime, limit)
        print(f"Found {len(result.features)} features in collection '{collection}':")
        for feature in result.features:
            print(f"  - Feature ID: {feature.id}")

@click.command(context_settings={'help_option_names': ['-h', '--help']})
@click.option('--username', '-u', required=False, help='The EODMS username.')
@click.option('--password', '-p', required=False, help='The EODMS password.')
@click.option('--collection', '-c', required=False, help='The collection name.')
@click.option('--feature_id', '-f', required=False, help='The feature (item) ID.')
@click.option('--bbox', '-b', required=False, default=None,
              help='Bounding box as comma-separated values: west,south,east,north (e.g., "-100,45,-95,50").')
@click.option('--datetime', '-d', required=False, default=None,
              help='Temporal filter as ISO 8601 string or range (e.g., "2020-10-31T00:00:00Z/2020-11-04T23:59:00Z").')
@click.option('--env', '-e', required=False, default='prod', help='Defaults to "prod". If "staging", define `EODMS_STAGING_DOMAIN` env variable.')
@click.option('--limit', '-l', required=False, default=10, type=int, help='Maximum number of features to return.')
def main(username, password, collection, feature_id, bbox, datetime, env, limit):
    """
    OGC Features CLI for EODMS STAC
    
    Examples:
    
    \b
    # List all guest collections
    python features_dds_test.py
    
    \b
    # List all collections with authentication
    python features_dds_test.py -u USER -p PASS

    \b
    # List features in a collection
    python features_dds_test.py -u USER -p PASS -c RCMImageProducts -l 5
    
    \b
    # Get a single feature by ID
    python features_dds_test.py -u USER -p PASS -c RCMImageProducts -f some-feature-id
    
    \b
    # Filter by bbox and datetime
    python features_dds_test.py -u USER -p PASS -c RCMImageProducts -b "-100,45,-95,50" -d "2020-10-31T00:00:00Z/2020-11-04T23:59:00Z"
    """
    bbox_list = None
    if bbox:
        try:
            bbox_list = [float(x.strip()) for x in bbox.split(',')]
            if len(bbox_list) != 4:
                raise ValueError("Bounding box must have exactly 4 values")
        except ValueError as e:
            click.echo(f"Error parsing bbox: {e}", err=True)
            return
    run(username, password, collection, feature_id, env, bbox_list, datetime, limit)

if __name__ == '__main__':
    main()
