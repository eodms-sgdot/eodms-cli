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

import sys
import os
import requests
import re
import textwrap
from colorama import Fore, Back, Style
from tqdm.auto import tqdm
from datetime import datetime, timezone
import dateutil.parser as util_parser
import json
import glob
import logging
import time
import threading
import copy
import traceback
from typing import Any, Dict

import eodms_rapi as rapi
from eodms_rapi import EODMSRAPI
from eodms_rapi import QueryError

from eodms import dds, aaa
from eodms.search import Search_API

try:
    import dateparser
except Exception:
    message = "Dateparser package is not installed. Please install and run " \
          "script again."
    print(message)
    sys.exit(1)

from . import csv_util
from . import image
from . import spatial
from . import field


def _stac_feature_to_bbox(features):
    """Convert an INTERSECTS feature list to a flat bbox list."""
    if not features:
        return None

    try:
        from shapely import wkt as shapely_wkt
        from shapely.geometry import shape

        logger = logging.getLogger('eodms')

        geom_str = None
        if isinstance(features, (list, tuple)):
            if len(features) > 0:
                first_item = features[0]
                if isinstance(first_item, (list, tuple)) and len(first_item) >= 2:
                    geom_str = first_item[1]
                elif isinstance(first_item, dict):
                    geom_str = first_item
                elif isinstance(first_item, str):
                    geom_str = first_item
        else:
            geom_str = features

        if geom_str is None:
            logger.warning("Could not extract geometry from features")
            return None

        if isinstance(geom_str, str) and os.path.isfile(geom_str):
            try:
                with open(geom_str, 'r', encoding='utf-8') as fh:
                    geom_str = json.load(fh)
            except Exception as file_err:
                logger.error(f"Failed to load geometry file '{geom_str}': {file_err}")
                return None

        geom = None
        try:
            if isinstance(geom_str, str):
                geom = shapely_wkt.loads(geom_str)
            else:
                raise ValueError("Not a string, skip WKT")
        except Exception:
            try:
                if isinstance(geom_str, str):
                    geom_obj = json.loads(geom_str)
                else:
                    geom_obj = geom_str

                if isinstance(geom_obj, dict) and geom_obj.get('type') == 'FeatureCollection':
                    from shapely.ops import unary_union
                    geometries = []
                    for feature in geom_obj.get('features', []):
                        if feature.get('geometry'):
                            geometries.append(shape(feature['geometry']))
                    if geometries:
                        geom = unary_union(geometries)
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
            except Exception:
                logger.error("Failed to parse feature as WKT or GeoJSON")
                return None

        return list(geom.bounds)
    except Exception as err:
        logger = logging.getLogger('eodms')
        logger.error(f"Unexpected error in _stac_feature_to_bbox: {err}", exc_info=True)
        return None


def _parse_dates_to_stac(dates):
    """Convert CLI dates list to ISO 8601 datetime range string."""
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
    """Convert legacy CLI date string to ISO 8601 format."""
    if not date_str or date_str == '..':
        return date_str

    s = date_str.replace('_', 'T')
    if '-' in s:
        return s if s.endswith('Z') else s + 'Z'

    if len(s) >= 15 and s[8] == 'T':
        dp = s[:8]
        tp = s[9:15]
        return (f"{dp[:4]}-{dp[4:6]}-{dp[6:8]}"
                f"T{tp[:2]}:{tp[2:4]}:{tp[4:6]}Z")

    return s


def _normalize_stac_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Map a raw STAC item dict to the internal EODMS-CLI record schema."""
    props = item.get('properties', {})

    record_id = props.get('eodms:recordId') or props.get('recordId') \
        or item.get('id')
    collection_id = item.get('collection') or props.get('collectionId') or ''
    archive_id = props.get('eodms:archiveId') or props.get('archiveId') \
        or props.get('uuid') or item.get('id')

    normalized = {
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

    for k, v in props.items():
        if k not in normalized:
            normalized[k] = v

    return normalized

class EodmsUtils:

    def __init__(self, **kwargs):
        """
        Initializer for the EodmsOrderDownload.
        
        :param kwargs: Options include:<br>
                username (str): The username of the EODMS account.<br>
                password (str): The password of the EODMS account.<br>
                downloads (str): The path where the image files will be
                    downloaded.<br>
                results (str): The path where the results CSV files will
                    be stored.<br>
                log (str): The path where the log file is stored.<br>
                timeout_query (float): The timeout for querying the RAPI.<br>
                timeout_order (float): The timeout for ordering in the
                    RAPI.<br>
                max_res (int): The maximum number of results to order.<br>
                silent (boolean): False to prompt the user and print info,
                    True to suppress it.<br>
        :type  kwargs: dict
        """

        self.eodms_domain = None
        self.indent = 3

        self.operators = ['=', '<', '>', '<>', '<=', '>=', ' LIKE ',
                          ' STARTS WITH ', ' ENDS WITH ', ' CONTAINS ',
                          ' CONTAINED BY ', ' CROSSES ', ' DISJOINT WITH ',
                          ' INTERSECTS ', ' OVERLAPS ', ' TOUCHES ', ' WITHIN ']

        self.username = kwargs.get('username')
        self.password = kwargs.get('password')

        self.dds_api = None
        self.search_api = None
        self.search_backend_type = 'stac'
        if kwargs.get('search_backend') is not None:
            backend_type = str(kwargs.get('search_backend')).strip().lower()
            if backend_type in ['rapi', 'stac']:
                self.search_backend_type = backend_type

        self.logger = logging.getLogger('eodms')

        self.prompter = None
        if kwargs.get('prompter') is not None:
            self.prompter = kwargs.get('prompter')

        self.version = ''
        if kwargs.get('version') is not None:
            self.version = str(kwargs.get('version'))

        self.download_path = "downloads"
        if kwargs.get('download') is not None:
            self.download_path = str(kwargs.get('download'))

        self.results_path = "results"
        if kwargs.get('results') is not None:
            self.results_path = str(kwargs.get('results'))

        self.log_path = "log"
        if kwargs.get('log') is not None:
            self.log_path = str(kwargs.get('log'))

        self.timeout_query = 60.0
        if kwargs.get('timeout_query') is not None:
            self.timeout_query = float(kwargs.get('timeout_query'))

        self.timeout_order = 180.0
        if kwargs.get('timeout_order') is not None:
            self.timeout_order = float(kwargs.get('timeout_order'))

        self.max_results = 1000
        if kwargs.get('max_res') is not None:
            self.max_results = int(kwargs.get('max_res'))

        self.keep_results = ""
        if kwargs.get('keep_results') is not None:
            self.keep_results = str(kwargs.get('keep_results'))

        self.keep_downloads = ""
        if kwargs.get('keep_downloads') is not None:
            self.keep_downloads = str(kwargs.get('keep_downloads'))

        self.colourize = True
        if kwargs.get('colourize') is not None:
            self.colourize = bool(kwargs.get('colourize'))

        self.silent = False
        if kwargs.get('silent') is not None:
            self.silent = bool(kwargs.get('silent'))

        if self.username is not None and self.password is not None:
            self.create_session(self.username, self.password)

        self.order_check_date = "3 days"
        if kwargs.get('order_check_date') is not None:
            self.order_check_date = kwargs.get('order_check_date')

        self.download_attempts = ''
        if kwargs.get('download_attempts') is not None:
            self.download_attempts = kwargs.get('download_attempts')

        if kwargs.get('eodms_domain') is not None:
            self.eodms_domain = str(kwargs.get('eodms_domain'))

        self.concurrent_downloads = '10'
        if kwargs.get('concurrent_downloads') is not None:
            self.concurrent_downloads = str(kwargs.get('concurrent_downloads'))

        if self.download_attempts is not None:
            if self.download_attempts == '':
                self.download_attempts = None
            else:
                try:
                    self.download_attempts = int(self.download_attempts)
                except:
                    msg = "'download_attempts' parameter in the configuration" \
                          " file is not a valid number. 'download_attempts' " \
                          "will be set to None."
                    self.print_msg(msg, heading='warning')
                    self.logger.warning(msg)
                    self.download_attempts = None

        self.aoi_extensions = ['.gml', '.kml', '.json', '.geojson', '.shp']

        self.cur_res = None

        self.email = 'eodms-sgdot@nrcan-rncan.gc.ca'

        self.eodms_geo = spatial.Geo(self)

        self.field_mapper = None

        self.csv_unique = ['recordid', 'record id', 'sequence id']

        self.time_words = ['hour', 'day', 'week', 'month', 'year']

        self.sat_coll_mapping = {'COSMOS-Skymed': ['COSMO-SkyMed1'],
                                 'NAPL': ['NAPL'],
                                 'sgap': ['SGBAirPhotos'],
                                 'RCM': ['RCMImageProducts', 'RCMScienceData'],
                                 'RADARSAT-1': ['Radarsat1',
                                                'Radarsat1RawProducts'],
                                 'RADARSAT-2': ['Radarsat2',
                                                'Radarsat2RawProducts'],
                                 'TerraSarX': ['TerraSarX'],
                                 'DMC': ['DMC'],
                                 'Gaofen-1': ['Gaofen-1'],
                                 'GeoEye-1': ['GeoEye-1'],
                                 'IKONOS': ['IKONOS'],
                                 'IRSP6-AWiFS': ['IRS'],
                                 'PlanetScope': ['PlanetScope'],
                                 'Pleiades': ['Pleiades'],
                                 'QuickBird-2': ['QuickBird-2'],
                                 'RapidEye': ['RapidEye'],
                                 'SPOT-6': ['SPOT'],
                                 'WorldView-1': ['WorldView-1'],
                                 'WorldView-2': ['WorldView-2'],
                                 'WorldView-3': ['WorldView-3'],
                                 'WorldView-4': ['WorldView-4']}

        self.coll_id = None
        self.attempts = None
        self.output = None
        self.fn_str = None
        self.items_restoring = []

        # Set colours
        self.reset_colour = self.get_colour(reset=True)
        self.warn_colour = self.get_colour(fore='YELLOW', style='BRIGHT')
        self.err_colour = self.get_colour(fore='RED', style='BRIGHT')
        self.note_colour = self.get_colour(fore='CYAN', style='BRIGHT')
        self.path_colour = self.get_colour(fore='GREEN', style='BRIGHT') \
                            if self.colourize else ''
        self.var_colour = self.get_colour(fore='CYAN', style='BRIGHT') \
                            if self.colourize else ''
        self.head_colour = self.get_colour(fore='YELLOW') \
                            if self.colourize else ''
        self.title_colour = self.get_colour(fore='YELLOW', style='BRIGHT') \
                            if self.colourize else ''
        self.arrow_colour = self.get_colour(fore='YELLOW', style='BRIGHT', 
                                            back='BLUE') \
                            if self.colourize else ''
        self.def_colour = self.get_colour(fore='CYAN')

        self.color_map = {
            'error': self.err_colour, 
            'warning': self.warn_colour, 
            'note': self.note_colour,
            'single_note': self.note_colour
        }
    
    def _check_dds_collection(self, coll_id):

        # LAST UPDATED: 2026-01-27
        # Hard-coded for now

        dmc_map = ["RCMImageProducts", "SGBAirPhotos", "RapidEye", "ALOS-2",
	                "WorldView-3", "Radarsat2",
                    "Radarsat-2_Tropical_Forest_Products", "WorldView-1",
                    "WorldView-2", "WorldView-4", "Radarsat1", "QuickBird-2",
	                "TerraSarX", "Pleiades", "GeoEye-1", "IRS", "Gaofen-1",
	                "DMC", "SPOT", "COSMO-SkyMed1", "PlanetScope", "IKONOS",
                    "OpenNAPL"]
        
        if coll_id in dmc_map:
            return True

        return False

    def _get_collection(self, sat):

        if sat.lower() == 'cosmos-skymed':
            return ['COSMO-SkyMed1']
        elif sat.lower() == 'napl':
            return ['NAPL']
        elif sat.lower() == 'sgap':
            return ['SGBAirPhotos']
        elif sat.lower() == 'rcm':
            return ['RCMImageProducts', 'RCMScienceData']
        elif sat.lower() == 'radarsat-1':
            return ['Radarsat1', 'Radarsat1RawProducts']
        elif sat.lower() == 'radarsat-2':
            return ['Radarsat2', 'Radarsat2RawProducts']
        elif sat.lower().find('terrasar') > -1:
            return ['TerraSarX']
        elif sat.lower() == 'dmc':
            return ['DMC']
        elif sat.lower() == 'gaofen-1':
            return ['Gaofen-1']
        elif sat.lower() == 'geoeye-1':
            return ['GeoEye-1']
        elif sat.lower() == 'ikonos':
            return ['IKONOS']
        elif sat.lower() == 'irsp6-awifs':
            return ['IRS']
        elif sat.lower() == 'planetscope':
            return ['PlanetScope']
        elif sat.lower() == 'pleiades':
            return ['Pleiades']
        elif sat.lower() == 'quickbird-2':
            return ['QuickBird-2']
        elif sat.lower() == 'rapideye':
            return ['RapidEye']
        elif sat.lower().find('spot') > -1:
            return ['SPOT']
        elif sat.lower() == 'worldview-1':
            return ['WorldView-1']
        elif sat.lower() == 'worldview-2':
            return ['WorldView-2']
        elif sat.lower() == 'worldview-3':
            return ['WorldView-3']
        elif sat.lower() == 'worldview-4':
            return ['WorldView-4']
        elif sat.lower().find('alos-2') > -1:
            return ['ALOS-2']
        elif sat.lower().find('iceye') > -1:
            return ['ICEYE']

    def _parse_dates(self, in_dates):
        """
        Parses dates from the user into a format for the EODMSRAPI
        
        :param in_dates: A string containing either a time interval 
                (24 hours, 3 months, etc.) or a range of dates 
                (20200501-20210105T054540,...)
        :type  in_dates: str
                
        :return: A list of dictionaries containing keys 'start' and 'end' 
                with the specific date ranges 
                (ex: [{'start': '20200105_045034', 'end': '20210105_000000'}])
        :rtype: list[dict]
        """

        if in_dates is None or in_dates == '':
            return ''

        # time_words = ['hour', 'day', 'week', 'month', 'year']

        if any(word in in_dates for word in self.time_words):
            dates = [in_dates]
        else:

            # Modify date for the EODMSRAPI object
            date_ranges = in_dates.split(',')

            dates = []
            start = ''
            end = ''
            for rng in date_ranges:
                start, end = rng.split('-')
                if start.lower().find('t') > -1:
                    start = start.lower().replace('t', '_')
                else:
                    start = f'{start}_000000'

                if end.lower().find('t') > -1:
                    end = end.lower().replace('t', '_')
                else:
                    end = f'{end}_000000'

                dates.append({'start': start, 'end': end})

        return dates

    def _parse_filters(self, filters, coll_id=None):
        """
        Parses filters into a format for the EODMSRAPI
        
        :param filters: A list of filters from a user for a specific 
                collection.
        :type  filters: list[str]
        :param coll_id: The Collection ID for the filters.
        :type  coll_id: str
                
        :return: A dictionary containing filters in a format for the 
                EODMSRAPI (ex: {"Beam Mnemonic": {'=': ['16M11', '16M13']}, 
                                "Incidence Angle": {'>': ['45.0']}).
        :rtype: dict
        """

        if coll_id is None:
            coll_id = self.coll_id

        if self.search_backend_type == 'stac':
            return self._parse_stac_filters(filters, coll_id)

        return self._parse_rapi_filters(filters, coll_id)

    def _parse_stac_filters(self, filters, coll_id):
        out_filters = {}
        av_fields = self.get_available_fields(coll_id, 'title')
        if av_fields is None:
            return out_filters

        stac_fields = av_fields.get('results', {})
        field_map = {k.lower(): k for k in stac_fields.keys()}

        for filt in filters:
            if all(x not in filt for x in self.operators):
                print(f"Filter '{filt}' entered incorrectly.")
                continue

            ops = [x for x in self.operators if x in filt]
            filt_split = ''
            op = ''
            for cur_op in ops:
                filt_split = filt.split(cur_op)
                op = cur_op

            key = filt_split[0].strip()
            if key.lower() not in field_map:
                err = f"Filter '{key}' is not available for Collection " \
                      f"'{coll_id}'."
                self.print_msg(err, heading='warning')
                self.logger.warning(err)
                continue

            fld_id = field_map[key.lower()]
            val = filt_split[1].strip().replace('"', '').replace("'", '')

            if val is None or val == '':
                err = f"No value specified for Filter ID '{key}'."
                self.print_msg(err, heading='warning')
                self.logger.warning(err)
                continue

            vals = [v.strip() for v in val.split('|') if v.strip() != '']
            if len(vals) == 0:
                continue

            out_filters[fld_id] = (op, vals)

        return out_filters

    def _parse_rapi_filters(self, filters, coll_id):
        out_filters = {}

        for filt in filters:
            if all(x not in filt for x in self.operators):
                print(f"Filter '{filt}' entered incorrectly.")
                continue

            ops = [x for x in self.operators if x in filt]

            filt_split = ''
            op = ''
            for cur_op in ops:
                filt_split = filt.split(cur_op)
                op = cur_op

            key = filt_split[0].strip()
            coll_fields = self.field_mapper.get_fields(coll_id)

            if key.lower() not in coll_fields.get_eod_fieldnames(lowered=True):
                err = f"Filter '{key}' is not available for Collection " \
                      f"'{coll_id}'."
                self.print_msg(err, heading='warning')
                self.logger.warning(err)
                continue

            fld = coll_fields.get_field(key)
            fld_id = fld.get_rapi_id()

            if key.lower().find('maximum') > -1 and \
                fld_id.lower().find('maximum') == -1:
                op = "<="
            elif key.lower().find('minimum') > -1 and \
                fld_id.lower().find('minimum') == -1:
                op = ">="

            val = filt_split[1].strip()
            val = val.replace('"', '').replace("'", '')

            if val is None or val == '':
                err = f"No value specified for Filter ID '{key}'."
                self.print_msg(err, heading='warning')
                self.logger.warning(err)
                continue

            vals = val.split('|')
            choices = fld.get_choices(True)

            if choices is not None:
                rep_vals = []
                for v_str in vals:
                    new_val = fld.verify_choices(v_str)
                    if new_val is None:
                        choices_str = ', '.join(list(filter(None, choices)))
                        err = f"{v_str} is not a valid choice for filter " \
                              f"'{key}'. Valid choices are: {choices_str}"
                        self.print_msg(err, heading='warning')
                        self.logger.warning(err)
                        continue
                    rep_vals.append(new_val)
                vals = rep_vals

            if len(vals) == 0:
                continue

            out_filters[fld_id] = (op, vals)

        return out_filters

    def _check_duplicate_orders(self, imgs):

        sub_statuses = ['SUBMITTED', 'AVAILABLE_FOR_DOWNLOAD', 'PROCESSING']

        # Get all orders for date range
        max_orders = imgs.count() + 25
        orders = self.eodms_rapi.get_orders(max_orders=max_orders)

        orders = self.eodms_rapi.remove_duplicate_orders(orders)

        # Remove duplicate images from the list

        # Copy input ImageList to a new ImageList so existing orders can be
        #   removed
        imgs_to_order = image.ImageList(self)
        imgs_to_order.combine(imgs)

        exist_orders = image.OrderList(self)

        img_ids = imgs.get_ids()

        for ord_item in orders:
            # Get the record ID of the order item
            ord_rec_id = ord_item.get('recordId')

            for i in img_ids:
                # If the record ID of the image matches the one of the
                #   order item
                img = imgs.get_image(i)
                if i == ord_rec_id:
                    if ord_item['status'].upper() in sub_statuses:
                        exist_orders.add_order_item(ord_item, img)
                        imgs_to_order.remove_image(i)

        return imgs_to_order, exist_orders

    def _get_eodms_res(self, csv_fn, max_images=None):
        """
        Gets the results based on a CSV file from the EODMS UI.
        
        :param csv_fn: The filename of the EODMS CSV file.
        :type  csv_fn: str
            
        :return: An ImageList object containing the images returned 
                from the EODMSRAPI.
        :rtype: image.ImageList
        """

        eodms_csv = csv_util.EODMS_CSV(self, csv_fn)
        csv_res = eodms_csv.import_eodms_csv()

        ##################################################
        self.print_heading("Retrieving Record IDs for the list of "
                           "entries in the CSV file")
        ##################################################

        # Group all records into different collections
        sat_recs = {}

        if max_images is not None and max_images != '':
            csv_res = csv_res[:max_images]

        # Group by satellite
        for rec in csv_res:

            # Get the collection ID for the image
            satellite = rec.get('satellite')

            if satellite is None:
                satellite = rec.get('title')

            rec_lst = []
            if satellite in sat_recs:
                rec_lst = sat_recs[satellite]

            rec_lst.append(rec)

            sat_recs[satellite] = rec_lst

        all_res = []

        counter = 0
        total = len(csv_res)
        for sat, recs in sat_recs.items():

            self.print_msg(f"Getting images for {sat}:", indent=False)

            for idx, rec in enumerate(recs):
                self.print_msg(f"Getting image {counter + 1} of {total}", False)

                counter += 1

                # If no satellite given, the record is an aerial image
                if sat is None or sat == '':
                    if 'photo number' in rec.keys():
                        sat = 'NAPL'
                    elif 'photo name' in rec.keys():
                        sat = 'sgap'

                res = []
                if 'sequence id' in rec.keys():
                    # If Sequence Id is in the CSV file
                    rec_id = rec.get('sequence id')
                    if rec_id is None:
                        rec_id = rec.get('sequence id')
                    colls = self._get_collection(sat)

                    if rec_id == '':
                        continue

                    # Get the results
                    for coll in colls:
                        res = self.eodms_rapi.get_record(coll, rec_id)
                        
                        if 'errors' in res and \
                                res.get('errors').find('404') > -1:
                            continue

                        if len(res) > 0:
                            break

                else:
                    msg = "Could not determine a unique field from the " \
                                      "CSV results."
                    self.print_msg(msg, heading='warning')
                    self.logger.warning(msg)
                    self.results = image.ImageList(self)
                    return self.results

                if isinstance(res, list):
                    all_res += res
                else:
                    all_res.append(res)

        # Convert results to ImageList
        self.results = image.ImageList(self)
        self.results.ingest_results(all_res)

        return self.results

    def _get_prev_res(self, csv_fn):
        """
        Imports image info from a CSV file
        
        :param csv_fn: The filename of the previous results CSV file.
        :type  csv_fn: str
        
        :return: A list of rows from the CSV file.
        :rtype: image.ImageList
        """

        eodms_csv = csv_util.EODMS_CSV(self, csv_fn)
        csv_res = eodms_csv.import_csv()

        # Convert results to ImageList
        query_imgs = image.ImageList(self)
        query_imgs.ingest_results(csv_res, True)

        return query_imgs

    def _print_results(self, imgs):

        if isinstance(imgs, image.OrderList):
            imgs = imgs.get_images()
        
        download_res = {}
        for img in imgs.get_images():
            request_status = img.get_metadata('requestStatus')

            img_lst = download_res.get(request_status, [])
            img_lst.append(img)
            download_res[request_status] = img_lst

        if len(download_res.get('Available', [])) > 0:
            msg = "The following images have been downloaded:\n"

            for avail_img in download_res.get('Available', []):
                img_uuid = avail_img.get_image_uuid()
                coll_id = avail_img.get_coll_id()
                loc_dest = avail_img.get_metadata('downloadDestination')
                src_url = avail_img.get_metadata('ddsResults').get('download_url')

                msg += f"\nImage UUID {img_uuid}\n"
                msg += f"    Collection ID: {coll_id}\n"
                msg += f"    Downloaded File: {loc_dest}\n"
                msg += f"    Source URL: {src_url}\n"

            self.print_footer('Successful Downloads', msg)

        if len(download_res.get('ItemsRestoring', [])) > 0:
            msg = "The following images are currently being restored " \
                "(status: ItemsRestoring):\n"

            for itrest_img in download_res.get('ItemsRestoring', []):
                img_uuid = itrest_img.get_image_uuid()
                coll_id = itrest_img.get_coll_id()

                msg += f"\nImage UUID {img_uuid}\n"
                msg += f"    Collection ID: {coll_id}\n"

            msg += "\nNOTE: Images with status ItemsRestoring take " \
                    "approximately 12 hours to become Available. A JSON file " \
                    "with a list of images has been saved to the 'results' " \
                    "folder. Please run Process 4 using this file at a later " \
                    "time."

            self.print_footer('ItemsRestoring Images', msg)

        if len(download_res.get('Failed', [])) > 0:
            msg = "The following images did not download:\n"

            for itrest_img in download_res.get('Failed', []):
                img_uuid = itrest_img.get_image_uuid()
                coll_id = itrest_img.get_coll_id()

                msg += f"\nImage UUID {img_uuid}\n"
                msg += f"    Collection ID: {coll_id}\n"

            self.print_footer('Failed Images', msg)

        return None

    def _parse_aws(self, query_imgs):
        """
        Separates AWS Radarsat1 images from EODMS images.

        :param query_imgs: A list of images.
        :type  query_imgs: image.ImageList

        :return: Two ImageLists with the separated images.
        :rtype:  tuple (image.ImageList)
        """

        aws_lst = []
        eodms_lst = []
        for res in query_imgs.get_raw():
            download_link = res.get('downloadLink')
            if download_link is not None and download_link.find('aws') > -1:
                aws_lst.append(res)
            else:
                eodms_lst.append(res)

        aws_imgs = image.ImageList(self)
        aws_imgs.ingest_results(aws_lst)

        eodms_imgs = image.ImageList(self)
        eodms_imgs.ingest_results(eodms_lst)

        print(f"\nNumber of AWS images: {aws_imgs.count()}")
        print(f"Number of EODMS images: {eodms_imgs.count()}\n")

        return eodms_imgs, aws_imgs

    def _filter_for_order(self, imgs):

        order_disabled = ['Radarsat1RawProducts', 'Radarsat2RawProducts',
                          'RCMScienceData']
        cli_order_disabled = ['NAPL']

        # Create a duplicate of the images for ordering
        filt_imgs = image.ImageList(self)
        filt_imgs.combine(imgs)

        # Add collection to this list so the message will appear only once
        already_mentioned = []

        # Get the raw metadata of the images
        raw_data = filt_imgs.get_raw()

        for img in raw_data:
            rec_id = img.get('recordId')
            coll_id = img.get('collectionId')
            if coll_id in order_disabled:
                # If the collection for this image is Raw, remove it
                filt_imgs.remove_image(rec_id)
                if coll_id not in already_mentioned:
                    # If not already, inform the user
                    self.print_msg(f"\nCollection {coll_id} cannot be ordered. "
                                   f"Images from this collection will be "
                                   f"removed for ordering.", heading='note')
                    already_mentioned.append(coll_id)
            if coll_id in cli_order_disabled:
                # If the collection for this image is NAPL, remove it
                filt_imgs.remove_image(rec_id)
                if coll_id not in already_mentioned:
                    # If not already, inform the user
                    self.print_msg(f"\nCollection {coll_id} cannot be order "
                                   f"using the EODMS-CLI or RAPI at this time. "
                                   f"Images from this collection will be "
                                   f"removed for ordering.", heading='note')
                    already_mentioned.append(coll_id)

        return filt_imgs

    def download_dds_item(self, img, thread_idx):

        try:

            image_uuid = img.get_image_uuid()
            coll_id = img.get_coll_id()

            status_code = 0
            suggested_retry_interval = 0

            while not status_code == 200:

                time.sleep(suggested_retry_interval)

                if coll_id == "NAPL":
                    coll_id = "OpenNAPL"

                if not self._check_dds_collection(coll_id):
                    print(f"\nCollection {coll_id} is not available in the" 
                          f" DDS API.")
                    return None
                
                item_info = self.dds_api.get_item(coll_id, image_uuid)

                err_msg = f"\nThread {thread_idx} - An error has occurred " \
                        f"with the DDS when getting image {image_uuid} in " \
                        f"Collection {coll_id}."

                if item_info is None:
                    self.print_msg(err_msg, indent=False, heading='warning', 
                                    wrap_text=False)
                    return None

                status = item_info.get('status')
                
                img.set_metadata(item_info, 'ddsResults')
                img.set_metadata(status, 'requestStatus')

                if status == 'Failed':
                    self.print_msg(f"\nThread {thread_idx} - Your request " 
                                   f"for item {image_uuid} has failed.",
                                   heading='warning', 
                                   wrap_text=False)
                    return None

                status_code = item_info.get('code')
                suggested_retry_interval = item_info.get('suggested_retry_interval')

                if status_code >= 400:
                    self.print_msg(err_msg, indent=False, heading='warning', 
                                    wrap_text=False)
                    return None

                if status_code == 200:
                    break
                else:
                    if status and status == 'ItemsRestoring':
                        item_info['image_uuid'] = image_uuid
                        item_info['collection_id'] = coll_id
                        self.items_restoring.append(item_info)
                        return None
                    else:
                        print(f"\nThread {thread_idx} - Waiting for " 
                              f"{suggested_retry_interval} seconds to check "
                              f"again for download link...")
            
            print(f"\nThread {thread_idx} - Downloading item")

            if not os.path.exists(self.download_path):
                os.makedirs(self.download_path)

            download_dest = self.dds_api.download_item(self.download_path)
            img.set_metadata(download_dest, 'downloadDestination')

        except Exception as e:
            trc_back = f"\n{traceback.format_exc()}"
            print(traceback.format_exc())
            
    def _get_dds_images(self, imgs):

        img_lst = copy.deepcopy(imgs.get_images())
        updated_imgs = []
        while len(img_lst) > 0:
            threads = []
            for idx in range(int(self.concurrent_downloads)):
                if len(img_lst) == 0:
                    break

                img = img_lst.pop()

                t1 = threading.Thread(target=self.download_dds_item, 
                                      args=(img, idx+1))
                threads.append(t1)

                updated_imgs.append(img)

            for idx, th in enumerate(threads):
                msg = f"\n{self.note_colour}**** Running thread {idx+1} of " \
                        f"{len(threads)} ****{self.reset_colour}\n"
                print(msg)
                th.start()

            for th in threads:
                th.join()

        imgs.update_images(updated_imgs)
        
        self.export_items_restoring()

    def _submit_orders(self, imgs, priority=None, max_items=None):
        """
        Submits orders to the RAPI.

        :param imgs: An ImageList object with a list of images
        :type  imgs: image.ImageList
        :param priority: The priority level for the orders.
        :type  priority: str
        :param max_items: The maximum number of images to order.
        :type  max_items: int

        :return: The order results.
        :rtype: image.OrderList
        """

        #############################################
        # Order Images
        #############################################

        # Separate orders that already exist
        imgs_to_order, exist_orders = self._check_duplicate_orders(imgs)

        self.print_msg(f"{exist_orders.count_items()} existing order items " \
                       f"found.\nSubmitting {imgs_to_order.count()} orders.")
        
        exist_orders.print_orders("Existing orders")
        imgs_to_order.print_images("Ordering images")

        orders = image.OrderList(self)
        if imgs_to_order.count() > 0:

            # Separated AWS images from order list
            # Convert results to an OrderList
            submit_orders = image.ImageList(self, imgs.get_images())
            for img in imgs.get_images():
                rec_id = img.get_record_id()
                item = exist_orders.get_item_by_rec_id(rec_id)

                if item is None:
                    continue

                if not item.is_st():
                    submit_orders.remove_image(rec_id)

            # Convert results to JSON
            json_res = submit_orders.get_raw()

            # Send orders to the RAPI
            if max_items is None or max_items == 0:
                # Order all images in a single order
                order_res = self.eodms_rapi.order(json_res, priority)
                orders.ingest_results(order_res, imgs)
            else:
                # Divide the images into the specified number of images per
                #   order
                for idx in range(0, len(json_res), max_items):
                    # Get the next 100 images
                    if len(json_res) < idx + max_items:
                        sub_recs = json_res[idx:]
                    else:
                        sub_recs = json_res[idx:max_items + idx]

                    order_res = self.eodms_rapi.order(sub_recs, priority)
                    orders.ingest_results(order_res, imgs)

            # Update the self.cur_res for output results
            self.cur_res = imgs

            if orders.count_items() == 0:
                # If no orders could be found
                err_msg = "No orders were submitted successfully."
                self.print_msg(err_msg, heading='error')
                self.logger.error(err_msg)
                self.exit_cli(1)

        else:
            self.print_msg("No new images to order. Using existing order "
                           "items.")

        # Merge all order items
        final_orders = image.OrderList(self)
        if orders:
            final_orders.merge_ordlist(orders)
        if exist_orders:
            final_orders.merge_ordlist(exist_orders)

        return final_orders
    
    def set_prompter(self, prompter):
        self.prompter = prompter

    def check_error(self, item):

        backend_label = 'RAPI' if self.search_backend_type == 'rapi' else 'STAC'

        if item is None:
            if self.eodms_rapi.auth_err:
                msg = "\nAn authentication error has occurred while " \
                    f"trying to access the EODMS {backend_label}. Please ensure " \
                    "your account login is in good standing on the actual " \
                    "website, https://www.eodms-sgdot.nrcan-rncan.gc.ca/" \
                    "index-en.html. Once your account is ready, you can " \
                    "run 'python eodms_cli.py --configure credentials' to " \
                    "add your new credentials to the configuration file."
            else:
                msg = "Failed to retrieve a list of available collections."
            self.logger.error(msg)
            self.exit_cli(1)

        if isinstance(item, QueryError):
            err_msg = item.get_msgs(True)
            if err_msg.find('401 Client Error') > -1:
                msg = "An authentication error has occurred while " \
                    f"trying to access the EODMS {backend_label}.\n\nPlease ensure " \
                    "your account login is in good standing on the actual " \
                    "website, https://www.eodms-sgdot.nrcan-rncan.gc.ca/" \
                    "index-en.html."
            else:
                msg = f"Failed to retrieve a list of available collections. " \
                          f"{item.get_msgs(True)}"
            self.logger.error(msg)
            self.print_msg(msg, heading='error')
            self.exit_cli(1)

    def check_hit_count(self):
        """
        Checks the hit count for a specified search
        """
        return None

    def cleanup_folders(self):
        """
        Clean-ups the results and downloads folder.
        """

        # Cleanup results folder
        results_start = dateparser.parse(self.keep_results)

        if results_start is not None:
            msg = f"Cleaning up files older than {self.keep_results} in " \
                  f"'results' folder..."
            print(f"\n{msg}")
            self.logger.info(msg)

            res_files = glob.glob(os.path.join(os.sep, self.results_path,
                                               '*.*'))

            for f in res_files:
                file_date = util_parser.parse(f, fuzzy=True)

                if file_date < results_start:
                    os.remove(f)

        # Cleanup downloads folder
        downloads_start = dateparser.parse(self.keep_downloads)

        if downloads_start is not None:
            msg = f"Cleaning up files older than {self.keep_downloads} in " \
                  f"'downloads' folder..."
            print(msg)
            self.logger.info(msg)

            downloads_files = glob.glob(os.path.join(os.sep,
                                                     self.download_path, '*.*'))

            for f in downloads_files:
                file_date = datetime.fromtimestamp(os.path.getmtime(f))

                if file_date < downloads_start:
                    os.remove(f)

    def convert_date(self, in_date):
        """
        Converts a date to ISO standard format.
        
        :param in_date: A string containing a date in format YYYYMMDD.
        :type  in_date: str
        
        :return: The date converted to ISO format.
        :rtype: str
        """

        if in_date.lower().find('t') > -1:
            date, tme = in_date.lower().split('t')
            year = date[:4]
            mth = date[4:6]
            day = date[6:]
            hour = tme[:2]
            minute = tme[2:4]
            sec = tme[4:]
            out_date = f'{year}-{mth}-{day}T{hour}:{minute}:{sec}Z'
        else:
            year = in_date[:4]
            mth = in_date[4:6]
            day = in_date[6:]
            out_date = f'{year}-{mth}-{day}T00:00:00Z'

        return out_date

    def create_session(self, username, password):
        """
        Creates a EODMSRAPI instance.
        
        :param username: The EODMS username of the user account.
        :type  username: str
        :param password: The EODMS password of the user account.
        :type  password: str
        """

        self.username = username
        self.password = password
        self.eodms_rapi = EODMSRAPI(username, password)

        environment = 'prod'
        if self.eodms_domain is not None:
            rapi_root = self.eodms_domain + "/wes/rapi"
            print(f"Changing root url to {rapi_root}\n")
            self.eodms_rapi.set_root_url(rapi_root)
            environment = 'staging'

        aaa_api = aaa.AAA_API(username, password, environment=environment)
        self.dds_api = dds.DDS_API(aaa_api, environment=environment)
        self.search_api = Search_API(aaa_api=aaa_api, environment=environment)

        # Add CLI version info to User-Agent in header
        if 'rapi_session' in dir(self.eodms_rapi):
            self.eodms_rapi.rapi_session.add_header('User-Agent', 
                                                f"EODMSCLI/{self.version}", 
                                                True)

        if self.search_backend_type == 'rapi':
            self.field_mapper = field.EodFieldMapper(self, self.eodms_rapi)
        else:
            self.field_mapper = None

    def _get_search_api(self):
        if self.search_api is None:
            environment = 'staging' if self.eodms_domain else 'prod'
            aaa_api = getattr(self.dds_api, 'aaa', None)
            self.search_api = Search_API(aaa_api=aaa_api,
                                         environment=environment)
        return self.search_api

    def _search_stac(self, coll_id, filters=None, features=None, dates=None,
                     max_results=None):
        """Runs a STAC search and returns normalized records."""
        search_api = self._get_search_api()

        bbox = _stac_feature_to_bbox(features)
        datetime_str = _parse_dates_to_stac(dates)
        limit = int(max_results) if max_results else 1000

        cql2_filter = filters.strip() if isinstance(filters, str) \
            and filters.strip() else None

        search_kwargs = {}
        if cql2_filter:
            search_kwargs['filter'] = cql2_filter
            search_kwargs['filter_lang'] = 'cql2-text'

        items = search_api.stac_search(
            collections=[coll_id],
            bbox=bbox,
            datetime=datetime_str,
            limit=limit,
            **search_kwargs,
        )

        return [_normalize_stac_item(it) for it in items]

    def download_aws(self, aws_imgs):
        """
        Downloads a set of AWS images.
        
        :param aws_imgs: An ImageList object with a set of Image objects.
        :type  aws_imgs: image.ImageList
        """

        self.print_msg("Downloading AWS images first...")

        requests.packages.urllib3.disable_warnings(requests.packages.
                                                   urllib3.exceptions.
                                                   InsecureRequestWarning)

        res = []
        for img in aws_imgs.get_images():
            dl_link = img.get_metadata('downloadLink')

            if dl_link.count('https') > 1:
                dl_link_splt = re.split(f'(https)', dl_link)
                dl_link_splt = list(filter(None, dl_link_splt))
                combined = [dl_link_splt[i] + dl_link_splt[i+1] 
                            for i in range(0, len(dl_link_splt), 2)]
                if len(combined) > 0:
                    dl_link = combined[0]

            aws_f = os.path.basename(dl_link)
            dest_fn = os.path.join(self.download_path, aws_f)

            # Get the file size of the link
            resp = requests.head(dl_link, verify=False)
            fsize = resp.headers.get('content-length')

            if fsize is None:
                if resp.status_code == 404:
                    msg = f"Image does not exist at link {dl_link}"
                else:
                    msg = f"Cannot download image from AWS"
                self.print_msg(msg)
                continue

            if os.path.exists(dest_fn):
                # if all-good, continue to next file
                if os.stat(dest_fn).st_size == int(fsize):
                    msg = f"No download necessary. Local file already " \
                          f"exists: {dest_fn}"
                    self.print_msg(msg)
                    continue
                # Otherwise, delete the incomplete/malformed local file and
                #   re-download
                else:
                    msg = f'Filesize mismatch with ' \
                          f'{os.path.basename(dest_fn)}. Re-downloading...'
                    self.print_msg(msg)
                    os.remove(dest_fn)

            # Use streamed download so we can wrap nicely with tqdm
            with requests.get(dl_link, stream=True, verify=False) as stream:
                with open(dest_fn, 'wb') as pipe:
                    with tqdm.wrapattr(
                            pipe,
                            method='write',
                            miniters=1,
                            total=float(fsize),
                            desc=os.path.basename(dest_fn)
                    ) as file_out:
                        for chunk in stream.iter_content(chunk_size=1024):
                            file_out.write(chunk)

            download_paths = [{'url': dl_link, 'local_destination': dest_fn}]

            img.set_metadata('SUCCESS', 'status')
            img.set_metadata(True, 'downloaded')
            img.set_metadata(download_paths, 'downloadPaths')
            img.set_metadata('N/A', 'itemId')
            img.set_metadata('N/A', 'orderId')

            res.append(img)

        return res
    
    def exit_cli(self, exit_code=0):
        """
        Properly exits the EODMS-CLI

        :param exit_code: The exit code, either 0 for OK or 1 for error.
        :type  exit_code: int
        """

        if self.cur_res:
            self.eodms_geo.export_results(self.cur_res, self.output)

        if 'eodms_rapi' in dir(self):
            if 'close_session' in dir(self.eodms_rapi):
                # If statement for backward compatibility
                self.eodms_rapi.close_session()

        if exit_code == 0:
            print("\nProcess complete.")
            self.print_support()
        else:
            print("\nExiting process.")
            self.print_support(True)
        
        sys.exit(exit_code)

    def export_items_restoring(self):
        """
        Exports results to a CSV file.
        """

        if len(self.items_restoring) == 0:
            return None
        
        if self.fn_str is None:
            return None

        # Create EODMS_CSV object to export results
        res_fn = os.path.join(self.results_path, 
                              f"{self.fn_str}_ItemsRestoring.json")
        if not os.path.exists(self.results_path):
            os.mkdir(self.results_path)
        
        with open(res_fn, 'w') as json_file:
            json.dump(self.items_restoring, json_file, indent=4)

        msg = f"Results exported to '{self.path_colour}{res_fn}" \
                f"{self.reset_colour}'."
        self.print_msg(msg, indent=False)

    def export_records(self, csv_f, header, records):
        """
        Exports a set of records to a CSV.
        
        :param csv_f: The CSV file to write to.
        :type  csv_f: (file object)
        :param header: A list containing the header for the file.
        :type  header: list[str]
        :param records: A list of images.
        :type  records: list[dict]
        """

        # Write the values to the output CSV file
        for rec in records:
            out_vals = []
            for h in header:
                if h in rec.keys():
                    val = str(rec[h])
                    if ',' in val:
                        val = f'"{val}"'
                    out_vals.append(val)
                else:
                    out_vals.append('')

            out_vals = [str(i) for i in out_vals]
            csv_f.write('%s\n' % ','.join(out_vals))

    def get_collid_by_name(self, in_title):
        """
        Gets the Collection ID based on the tile/name of the collection.
        
        :param in_title: The title/name of the collection. (ex: 'RCM Image
                        Products' for ID 'RCMImageProducts')
        :type  in_title: str
        
        :return: The full Collection ID.
        :rtype: str
        """

        if isinstance(in_title, list):
            in_title = in_title[0]

        collections = self.get_collections()
        if isinstance(collections, list):
            collections = {c['id']: {'title': c.get('title', c['id']),
                                     'aliases': c.get('aliases', [])}
                           for c in collections}

        for k, v in collections.items():
            if v['title'].find(in_title) > -1:
                return k

        return self.get_full_collid(in_title)

    def get_rapi(self):
        """
        Returns the eodms_rapi object.
        """

        return self.eodms_rapi

    def get_collections(self, as_list=False):
        """Returns collections from Search_API/STAC."""
        search_api = self._get_search_api()

        collections = []
        for coll in search_api.client.get_collections():
            collections.append({
                'id': coll.id,
                'title': getattr(coll, 'title', None) or coll.id,
                'aliases': []
            })

        if as_list:
            return collections

        return {c['id']: {'title': c['title'], 'aliases': c['aliases']}
                for c in collections}

    def get_available_fields(self, coll_id, field_type='title'):
        """Returns available queryables for a collection."""
        search_api = self._get_search_api()

        try:
            collection = search_api.client.get_collection(coll_id)
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
        """Prints queryables for a collection using Search_API."""
        search_api = self._get_search_api()
        try:
            coll = search_api.client.get_collection(coll_id)
            if coll is None:
                return False
            search_api.print_queryables(coll)
            return True
        except Exception:
            return False

    def get_colour(self, **kwargs): 
        """
        Gets a colour value for colorama
        """

        reset = kwargs.get('reset')
        if reset is None:
            reset = False
        
        fore_str = ''
        fore_col = kwargs.get('fore')
        if fore_col is not None:
            fore_str = eval(f'Fore.{fore_col}')

        back_str = ''
        back_col = kwargs.get('back')
        if back_col is not None:
            back_str = eval(f'Back.{back_col}')

        style_str = ''
        style_col = kwargs.get('style')
        if style_col is not None:
            style_str = eval(f'Style.{style_col}')
        
        if reset:
            fore_str = Fore.RESET
            back_str = Back.RESET
            style_str = Style.RESET_ALL

        colour = ''
        if self.colourize:
            colour = fore_str + back_str + style_str

        return colour

    def get_full_collid(self, coll_id):
        """
        Gets the full collection ID using the input collection ID which can be a 
            substring of the collection ID.
        
        :param coll_id: The collection ID to check.
        :type  coll_id: str
            
        :return: The full Collection ID.
        :rtype: str
        """

        collections = self.get_collections()
        if isinstance(collections, list):
            collections = {c['id']: {'title': c.get('title', c['id']),
                                     'aliases': c.get('aliases', [])}
                           for c in collections}

        for k, v in collections.items():
            if k.find(coll_id) > -1 or v['title'].find(coll_id) > -1:
                return k

    def get_input_fields(self, in_csv):
        """
        Gets a list of fields from the input CSV

        :param in_csv: The input CSV filename.
        :type  in_csv: str

        :return: A list of fields from the CSV.
        :rtype: list[str]
        """

        if in_csv.find('.csv') == -1:
            err_msg = "The provided input file is not a CSV file. " \
                          "Exiting process."
            self.print_msg(err_msg, heading='error')
            self.logger.error(err_msg)
            self.exit_cli(1)

        eod_csv = csv_util.EODMS_CSV(self, in_csv)
        
        return eod_csv.import_csv(True)

    def get_record_ids(self, coll_id, order_keys):

        if not isinstance(order_keys, list):
            order_keys = [order_keys]
        
        record_ids = []
        for ok in order_keys:
            filters = f"\"Order Key\" = '{ok}'"
            res = self._search_stac(coll_id, filters=filters)
            if len(res) > 0:
                record_ids = [r.get('recordId') for r in res]

        return record_ids

    def get_image_from_order(self, order):
        """
        Gets an image from the RAPI based on an order into an image.Image object.

        :param order: The results from the RAPI.
        :type  order: list[dict]

        :return: A list of Images based on the order.
        :rtype:  image.ImageList
        """

        if isinstance(order, list):
            images = image.ImageList(self)
            for o in order:
                rec_id = o.get('recordId')
                coll = o.get('collectionId')
                res = self.eodms_rapi.get_record(coll, rec_id)

                img = image.Image()
                img.parse_record(res)

                images.add_image(img)

            return images

    def ingest_downloads(self, orders, download_items, imgs=None):
        """
        Adds download items to the OrderList object.

        :param orders: The OrderList object.
        :type  orders: OrderList
        :param download_items: A list of items from the EODMS_RAPI download.
        :type  download_items: list[dict]
        :param imgs: An ImageList object,
        :type  imgs: ImageList
        """

        # Update the images with the download info
        orders.update_downloads(download_items)

        for order_items in orders.get_order_items():
            rec_id = order_items.get_record_id()
            coll_id = order_items.get_metadata('collectionId')

            if imgs:
                img = imgs.get_image(rec_id)
            else:
                res = self.eodms_rapi.get_record(coll_id, rec_id)

                img = image.Image()
                img.parse_record(res)

            order_items.add_image(img)

    def retrieve_orders(self, query_imgs):
        """
        Retrieves existing orders based on a list of images.
        
        :param query_imgs: An ImageList containing the images.
        :type  query_imgs: image.ImageList
        
        :return: An OrderList containing the orders
        :rtype: image.OrderList
        """

        json_res = query_imgs.get_raw()

        # Get existing orders of the images
        order_res = self.eodms_rapi.get_orders_by_records(json_res)

        # Convert results to an OrderList
        orders = image.OrderList(self, query_imgs)
        orders.ingest_results(order_res)

        if orders.count_items() == 0:
            # If no order are found...

            if self.silent:
                print("\nNo existing orders could be determined or found. "
                      "Submitting orders now...")
            else:
                # Ask user if they'd like to order the images
                msg = "\nNo existing orders could be found. Would you like " \
                      "to order the images? (y/n): "
                answer = input(msg)
                if answer.lower().find('y') == -1:
                    # Export polygons of images
                    self.eodms_geo.export_results(query_imgs, self.output)

                    self.logger.info("Process ended by user.")
                    self.exit_cli()

            order_res = self.eodms_rapi.order(json_res)
            orders.ingest_results(order_res)

        # Update the self.cur_res for output results
        self.cur_res = query_imgs

        return orders

    def is_json(self, my_json):
        """
        Checks if the input item is in JSON format.
        
        :param my_json: A string value from the requests results.
        :type  my_json: str
        
        :return: True if the input string is in valid JSON format, False if not.
        :rtype: boolean
        """
        try:
            json.loads(my_json)
        except (ValueError, TypeError):
            return False
        return True

    def sort_fields(self, fields):
        """
        Sorts a list of fields to include recordId, collectionId
        
        :param fields: A list of fields from an Image.
        :type  fields: list[str]
        
        :return: The sorted list of fields.
        :rtype: list[str]
        """

        field_order = ['recordId', 'collectionId']

        if 'orderId' in fields:
            field_order.append('orderId')
        if 'itemId' in fields:
            field_order.append('itemId')

        out_fields = field_order

        for f in fields:
            if f not in field_order:
                out_fields.append(f)

        return out_fields

    def parse_max(self, maximum):
        """
        Parses the maximum values entered by the user
        
        :param maximum: The maximum value(s) entered by the user.
        :type  maximum: str
        
        :return: The maximum number of images to order and the total number
                of images per order.
        :rtype: tuple
        """

        # Parse the maximum number of orders and items per order
        max_items = None
        max_images = None
        if maximum is not None:
            if maximum.find(':') > -1:
                max_images, max_items = maximum.split(':')
            else:
                max_items = None
                max_images = maximum

        if max_images:
            max_images = int(max_images)

        if max_items:
            max_items = int(max_items)

        return max_images, max_items

    def print_msg(self, msg, nl=True, indent=False, heading=None,
                  wrap_text=True):
        """
        Prints a message to the command prompt.
        
        :param msg: The message to print to the screen.
        :type  msg: str
        :param nl: If True, a newline will be added to the start of the message.
        :type  nl: boolean
        :param indent: A string with the indentation.
        :type  indent: boolean
        :param heading: The heading type of the message (can be 'error', 
                        'warning', 'note' or 'single_note').
        :type  heading: str
        """

        initial_indent = ''
        subsequent_indent = ''
        if indent:
            initial_indent = ' ' * self.indent
            subsequent_indent = ' ' * self.indent

        if wrap_text:
            msg = textwrap.fill(msg, width=80, break_long_words=False, 
                                replace_whitespace=False, 
                                initial_indent=initial_indent, 
                                subsequent_indent=subsequent_indent, 
                                break_on_hyphens=False)
        
        color = ''
        if heading:
            color = self.color_map.get(heading)
            if heading == 'single_note':
                msg = f"{initial_indent}**** NOTE **** {msg} ****\n"
            else:
                msg = f"{initial_indent}**** {heading.upper()} ****\n" \
                    f"{msg}\n{initial_indent}*****************\n"

        if nl:
            msg = color + f"\n{msg}"
        else:
            msg = color + f"{msg}"

        print(msg)
        print(Fore.RESET)

        if heading == 'error':
            print("\nExiting process.")
            self.print_support(True)

    def print_footer(self, title, msg):
        """
        Prints a footer to the command prompt.
        
        :param title: The title of the footer.
        :type  title: str
        :param msg: The message for the footer.
        :type  msg: str
        """

        indent_str = ' ' * self.indent
        dash_str = (59 - len(title)) * '-'
        print(f"\n{self.note_colour}{indent_str}-----{title}{dash_str}")
        msg = msg.strip('\n')
        for m in msg.split('\n'):
            print(f"{indent_str}| {m}")
        print(f"{indent_str}------------------------------------------------"
              f"----------------{self.reset_colour}")

    def print_heading(self, msg):
        """
        Prints a heading to the command prompt.
        
        :param msg: The msg for the heading.
        :type  msg: str
        """

        print("\n**********************************************************"
              "****************")
        print(f" {msg}")
        print("************************************************************"
              "**************")

    def print_support(self, err=False):
        """
        Prints the 2 different support message depending if an error occurred.

        :param err: Determines if the output should be for an error.
        :type  err: bool
        """

        if err:
            print(f"\nFor help, please contact the EODMS Support Team at "
                  f"{self.email}")
        else:
            print(f"\nIf you have any questions or require support, "
                  f"please contact the EODMS Support Team at "
                  f"{self.email}")


    def query_entries(self, collections, **kwargs):
        """
        Sends various image entries to the EODMSRAPI.
        
        :param collections: A list of collections.
        :type  collections: list[str]
        :param kwargs: A dictionary of arguments:
        
                - filters (dict): A dictionary of filters separated by 
                    collection.
                - aoi (str): The filename of the AOI.
                - dates (list): A list of date ranges 
                    ([{'start': <date>, 'end': <date>}]).
                - max_images (int): The maximum number of images to query.
        :type  kwargs: dict
        
        :return: The ImageList object containing the results of the query.
        :rtype: image.ImageList
        """

        filters = kwargs.get('filters')
        aoi = kwargs.get('aoi')
        dates = kwargs.get('dates')
        max_images = kwargs.get('max_images')

        feats = None
        if aoi is not None:
            feats = [('INTERSECTS', aoi)]

        all_res = []
        for coll in collections:

            # Get the full Collection ID
            self.coll_id = self.get_full_collid(coll)

            # Parse filters
            if filters:

                if self.coll_id in filters.keys():
                    coll_filts = filters[self.coll_id]
                    # For STAC, a raw CQL2 string is passed straight through.
                    if self.search_backend_type == 'stac' \
                            and isinstance(coll_filts, str):
                        filt_parse = coll_filts
                    else:
                        filt_parse = self._parse_filters(coll_filts)
                        if isinstance(filt_parse, str):
                            filt_parse = {}
                else:
                    filt_parse = {}
            else:
                filt_parse = {}

            # Create search method arguments dictionary:
            self.rapi_search_args = {
                "filters": filt_parse, 
                "features": feats, 
                "dates": dates, 
                "maxResults": max_images
            }

            backend_label = 'EODMSRAPI' if self.search_backend_type == 'rapi' \
                else 'STAC'
            print(f"\nSending query to {backend_label} with the following "
                  f"parameters:")
            for k, v in self.rapi_search_args.items():
                print(f"  {k}: {v}")

            res = self._search_stac(self.coll_id, filt_parse, feats, dates,
                                    max_images)

            # Add this collection's results to all results
            all_res += res

        # Convert results to ImageList
        query_imgs = image.ImageList(self)
        query_imgs.ingest_results(all_res)

        return query_imgs

    def set_attempts(self, attempts):
        """
        Sets the number of attempts for query the EODMSRAPI.
        
        :param attempts: The number of attempts.
        :type  attempts: str or int
        """

        try:
            self.attempts = int(attempts)
        except ValueError:
            self.attempts = 4

    def log_parameters(self, params, title=None):
        """
        Logs the script parameters in the log file.
        
        :param params: A dictionary of the script parameters.
        :type  params: dict
        :param title: The title of the message.
        :type  title: str
        """

        if title is None:
            title = "Script Parameters"

        msg = f"{title}:\n"
        for k, v in params.items():
            msg += f"  {k}: {v}\n"
        self.logger.info(msg)

    def set_silence(self, silent):
        """
        Sets the silence of the script.
        
        :param silent: Determines whether the script will be silent. If True,
                    the user is not prompted for info.
        :type  silent: boolean
        """

        self.silent = silent

    def validate_collection(self, coll):
        """
        Checks if the Collection entered by the user is valid.
        
        :param coll: The Collection value to check.
        :type  coll: str
        
        :return: Returns the Collection if valid, False if not.
        :rtype: str or boolean
        """

        colls = self.get_collections()
        if isinstance(colls, list):
            colls = {c['id']: {'title': c.get('title', c['id']),
                               'aliases': c.get('aliases', [])}
                     for c in colls}

        aliases = [v['aliases'] for v in colls.values()]

        coll_vals = list(colls.keys()) + [v['title'] for v in colls.values()]

        for a in aliases:
            coll_vals += a

        if coll.lower() in [c.lower() for c in coll_vals]:
            return True

        return False

    def validate_dates(self, dates):
        """
        Checks if the date entered by the user is valid.
        
        :param dates: A range of dates or time interval.
        :type  dates: str
        
        :return: Returns the dates if valid, False if not.
        :rtype: str or boolean
        """

        try:
            self._parse_dates(dates)
            return dates
        except Exception:
            return False
        
    def validate_st_images(self, in_vals):
        """
        Validates the user input for the Record Id search

        :param in_vals: The input values from the user
        :type  in_vals: str
        """

        try:
            if in_vals.find(":") > -1:
                coll, rec_ids = in_vals.split(':')
            return in_vals
        except Exception as e:
            return False

        
    def validate_record_ids(self, ids, single_coll=False):
        """
        Validates the user input for the Record Id search

        :param ids: The Id(s) entry from the user
        :type  ids: str
        """

        try:
            ids_lst = ids.split(',')
            if single_coll:
                coll, rec_ids = ids_lst[0].split(':')
            else:
                for i in ids_lst:
                    coll, rec_ids = i.split(':')
            return ids
        except Exception as e:
            return False

    def validate_int(self, val, limit=None):
        """
        Checks if the number entered by the user is valid.
        
        :param val: A string (or integer) of an integer.
        :type  val: str or int
        :param limit: A number to check whether the val is less than a certain
                    limit.
        :type  limit: int
        
        :return: Returns the val if valid, False if not.
        :rtype: str or boolean
        """

        try:
            if isinstance(val, str):
                if val == '':
                    return None
                val = int(val)

            if isinstance(val, list):
                if limit is not None:
                    if any(int(v) > limit for v in val):
                        err_msg = "One of the values entered is invalid."
                        self.print_msg(err_msg, indent=False, heading='warning')
                        self.logger.warning(err_msg)
                        return False
                return [int(v) for v in val]
            else:
                if limit is not None:
                    if int(val) > limit:
                        err_msg = "The values entered are invalid."
                        self.print_msg(err_msg, indent=False, heading='warning')
                        self.logger.warning(err_msg)
                        return False

                return int(val)

        except ValueError:
            err_msg = "Not a valid entry."
            self.print_msg(err_msg, indent=False, heading='warning')
            self.logger.warning(err_msg)
            return False

    def validate_file(self, in_fn, aoi=False):
        """
        Checks if a file name entered by the user is valid.
        
        :param in_fn: The filename of the input file.
        :type  in_fn: str
        :param aoi: Determines whether the file is an AOI.
        :type  aoi: boolean
        
        :return: If the file is invalid (wrong format or does not exist),
                False is returned. Otherwise the original filename is returned.
        :rtype: str or boolean
        """

        abs_path = os.path.abspath(in_fn)

        if aoi:
            if all(s in in_fn for s in self.aoi_extensions):
                err_msg = "The AOI file is not a valid file. Please make " \
                          "sure the file is either a GML, KML, GeoJSON " \
                          "or Shapefile."
                self.print_msg(err_msg, heading='error')
                self.logger.error(err_msg)
                return False

            if not os.path.exists(abs_path):
                err_msg = "The AOI file does not exist."
                self.print_msg(err_msg, heading='error')
                self.logger.error(err_msg)
                return False

        if not os.path.exists(abs_path):
            return False

        return abs_path

    def validate_filters(self, filt_items, coll_id):
        """
        Checks if a list of filters entered by the user is valid.
        
        :param filt_items: A list of filters entered by the user for a
                            given collection.
        :type  filt_items: str
        :param coll_id: The Collection ID of the filter.
        :type  coll_id: str
        
        :return: If one of the filters is invalid, False is returned.
                Otherwise the original filters are returned.
        :rtype: boolean or str
        """

        # Check if filter has proper operators
        if all(x in filt_items.upper() for x in self.operators):
            err_msg = "Filter(s) entered incorrectly. Make sure each " \
                      "filter is in the format of <filter_id><operator>" \
                      "<value>[|<value>] and each filter is separated by " \
                      "a comma."
            self.print_msg(err_msg, heading='error')
            self.logger.error(err_msg)
            return False

        if self.search_backend_type == 'stac':
            return self._validate_stac_filters(filt_items, coll_id)

        return self._validate_rapi_filters(filt_items, coll_id)

    def _validate_stac_filters(self, filt_items, coll_id):
        av_fields = self.get_available_fields(coll_id, 'title')
        if av_fields is None:
            err_msg = f"Could not retrieve available fields for " \
                      f"collection '{coll_id}'."
            self.print_msg(err_msg, heading='error')
            self.logger.error(err_msg)
            return False

        field_map = {k.lower(): k for k in av_fields.get('results', {})}
        filts = filt_items.split(',')

        for f in filts:
            ops = [x for x in self.operators if x in f]
            if len(ops) == 0:
                err_msg = f"Filter '{f}' entered incorrectly."
                self.print_msg(err_msg, heading='error')
                self.logger.error(err_msg)
                return False

            key = f.split(ops[0])[0].strip()
            if key.lower() not in field_map:
                err_msg = f"Filter '{f}' is not available for collection " \
                          f"'{coll_id}'."
                self.print_msg(err_msg, heading='error')
                self.logger.error(err_msg)
                return False

        return filt_items

    def _validate_rapi_filters(self, filt_items, coll_id):
        coll_fields = self.field_mapper.get_fields(coll_id)
        filts = filt_items.split(',')

        for f in filts:
            if not any(x in f.upper()
                       for x in coll_fields.get_eod_fieldnames()):
                err_msg = f"Filter '{f}' is not available for collection " \
                          f"'{coll_id}'."
                self.print_msg(err_msg, heading='error')
                self.logger.error(err_msg)
                return False

        return filt_items


class EodmsProcess(EodmsUtils):

    def __init__(self, **kwargs):
        # self.eod_utils = EodmsUtils()

        super().__init__(**kwargs)

    def _download_items(self, orders, eodms_imgs=None):
        """
        Sets up and downloads order items.
        
        :param orders: An OrderList object of the orders and order items.
        :type  orders: image.OrderList
        :param eodms_imgs: An ImageList object with a list of images.
        :type  eodms_imgs: image.ImageList
        """

        # Make the download folder if it doesn't exist
        if not os.path.exists(self.download_path):
            os.mkdir(self.download_path)

        items = orders.get_raw()

        # Download images using the EODMSRAPI
        download_items = self.eodms_rapi.download(items, self.download_path,
                                        max_attempts=self.download_attempts)

        self.ingest_downloads(orders, download_items, eodms_imgs)

    def _finish_process(self, in_imgs=None):
        """
        Exports and prints available information at the end of a process.
        """

        if not in_imgs:
            in_imgs = self.cur_res

        self._print_results(in_imgs)

        # Export polygons of images
        self.eodms_geo.export_results(in_imgs, self.output)

        end_time = datetime.now()
        end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

        self.logger.info(f"End time: {end_str}")

    def _set_result_fn(self):
        """
        Sets the filename for the output results CSV.

        :return: The start time of the process.
        :rtype:  str
        """

        start_time = datetime.now()
        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        self.fn_str = start_time.strftime("%Y%m%d_%H%M%S")

        return start_str

    def search_order_download(self, params):
        """
        Runs all steps: querying, ordering and downloading

        :param params: A dictionary containing the arguments and values.
        :type  params: dict
        """

        # Log the parameters
        self.log_parameters(params)

        # Get all the values from the parameters
        collections = params.get('collections')
        dates = params.get('dates')
        aoi = params.get('input_val')
        filters = params.get('filters')
        maximum = params.get('maximum')
        self.output = params.get('output')
        overlap = params.get("overlap")
        # priority = params.get('priority')
        aws_download = params.get('aws')
        no_order = params.get('no_order')

        # Validate AOI
        if aoi is not None:
            if os.path.exists(aoi):
                aoi_check = self.validate_file(aoi, True)
                if not aoi_check:
                    msg = "The provided input file is not a valid AOI file."
                    self.print_msg(msg, heading="warning")
                    self.logger.warning(msg)
                    aoi = None
            else:
                if not self.eodms_geo.is_wkt(aoi):
                    msg = "The provided WKT feature is not valid."
                    self.print_msg(msg, heading="warning")
                    self.logger.warning(msg)
                    aoi = None

        # Create info folder, if it doesn't exist, to store CSV files
        start_str = self._set_result_fn()

        self.logger.info(f"Process start time: {start_str}")

        #############################################
        # Search for Images
        #############################################

        # Parse maximum items
        max_images, _ = self.parse_max(maximum)

        # Convert collections to list if not already
        if not isinstance(collections, list):
            collections = [collections]

        # Parse dates if not already done
        if not isinstance(dates, list):
            dates = self._parse_dates(dates)

        # Send query to EODMSRAPI
        query_imgs = self.query_entries(collections, filters=filters,
                                        aoi=aoi, dates=dates,
                                        max_images=max_images)

        if overlap is not None \
                and not overlap == '' \
                and aoi is not None \
                and not aoi == '':
            query_imgs.filter_overlap(overlap, aoi)

        # If no results were found, inform user and end process
        if query_imgs.count() == 0:
            msg = "Sorry, no results found for given AOI or filters."
            self.print_msg(msg, heading="warning")
            self.logger.warning(msg)
            self.exit_cli()

        # Update the self.cur_res for output results
        self.cur_res = query_imgs

        # Print results info
        msg = f"{query_imgs.count()} unique images returned from search " \
              f"results\n\n"
        if query_imgs.count() <= 20:
            msg += f"Record Ids: {', '.join(query_imgs.get_ids())}"
        self.print_footer('Query Results', msg)

        if no_order:
            self.eodms_geo.export_results(query_imgs, self.output)
            self.exit_cli()

        if max_images is None or max_images == '':
            # Inform the user of the total number of found images and ask if
            #   they'd like to continue
            if not self.silent:
                answer = input(f"\n{query_imgs.count()} images found for "
                               f"your search filters. Proceed with "
                               f"ordering? (y/n): ")
                if answer.lower().find('n') > -1:
                    self.logger.info("Process stopped by user.")
                    self.exit_cli()
        else:
            # If the user specified a maximum number of orders,
            #   trim the results
            if len(collections) == 1:
                self.print_msg(f"Proceeding to order and download the first "
                               f"{max_images} images.")
                query_imgs.trim(max_images)
            else:
                self.print_msg(f"Proceeding to order and download the first "
                               f"{max_images} images from each collection.")
                query_imgs.trim(max_images, collections)

        # Parse out AWS
        if aws_download:
            eodms_imgs, aws_imgs = self._parse_aws(query_imgs)
        else:
            eodms_imgs = query_imgs
            aws_imgs = None

        # Make the download folder if it doesn't exist
        if not os.path.exists(self.download_path):
            os.mkdir(self.download_path)

        # Download all AWS images first
        aws_downloads = None
        if aws_imgs:
            aws_downloads = self.download_aws(aws_imgs)
            eodms_imgs.add_images(aws_downloads)

        ###############################################
        # Get Items and Download from DDS API
        ###############################################

        self._get_dds_images(eodms_imgs)

        self._finish_process(eodms_imgs)

    def order_csv(self, params):
        """
        Orders and downloads images using the CSV exported from the EODMS UI.

        :param params: A dictionary containing the arguments and values.
        :type  params: dict
        """

        csv_fn = params.get('input_val')
        csv_fields = params.get('csv_fields')
        maximum = params.get('maximum')
        priority = params.get('priority')
        self.output = params.get('output')
        aws_download = params.get('aws')
        no_order = params.get('no_order')

        # Log the parameters
        self.log_parameters(params)

        if csv_fn.find('.csv') == -1:
            err_msg = "The provided input file is not a CSV file. " \
                      "Exiting process."
            self.print_msg(err_msg, heading='error')
            self.logger.error(err_msg)
            self.exit_cli(1)

        # Create info folder, if it doesn't exist, to store CSV files
        start_str = self._set_result_fn()

        self.logger.info(f"Process start time: {start_str}")

        #############################################
        # Search for Images
        #############################################

        self.eodms_rapi.get_collections()

        # Parse the maximum number of orders and items per order
        max_images, _ = self.parse_max(maximum)

        # Import and query entries from the CSV
        query_imgs = self._get_eodms_res(csv_fn, max_images)

        if query_imgs.count() == 0:
            if csv_fields is None:
                msg = "Could not determine images from the CSV file."
            else:
                fields_str = ', '.join(csv_fields)
                msg = f"Sorry, no images found using these CSV fields: " \
                      f"{fields_str}"
            self.print_msg(msg, heading="warning")
            self.logger.warning(msg)
            self.exit_cli(1)

        # Update the self.cur_res for output results
        self.cur_res = query_imgs

        if no_order:
            self.eodms_geo.export_results(query_imgs, self.output)
            self.exit_cli()

        #############################################
        # Order Images
        #############################################

        # Parse out AWS
        if aws_download:
            eodms_imgs, aws_imgs = self._parse_aws(query_imgs)
        else:
            eodms_imgs = query_imgs
            aws_imgs = None

        # Download all AWS images first
        aws_downloads = None
        if aws_imgs:
            aws_downloads = self.download_aws(aws_imgs)
            eodms_imgs.add_images(aws_downloads)

        ###############################################
        # Get Items and Download from DDS API
        ###############################################

        self._get_dds_images(eodms_imgs)

        self._finish_process(eodms_imgs)

    def order_ids(self, params):
        """
        Orders and downloads a single or set of images using Record IDs.

        :param params: A dictionary containing the arguments and values.
        :type  params: dict
        """

        in_ids = params.get('input_val')
        priority = params.get('priority')
        self.output = params.get('output')
        aws_download = params.get('aws')
        no_order = params.get('no_order')

        # Log the parameters
        self.log_parameters(params)

        # Create info folder, if it doesn't exist, to store CSV files
        start_str = self._set_result_fn()

        self.logger.info(f"Process start time: {start_str}")

        #############################################
        # Search for Images
        #############################################

        self.eodms_rapi.get_collections()

        ids_lst = in_ids.split(',')

        all_res = []
        for i in ids_lst:
            
            coll, rec_ids = i.split(':')

            for rec_id in rec_ids.split('|'):
                res = self.eodms_rapi.get_record(coll, rec_id)

            if isinstance(res, dict) and 'errors' in res.keys():
                if res.get('errors').find('404 Client Error') > -1:
                    err_msg = f"Image with Record ID {rec_id} could not " \
                                f"be found in Collection {coll}."
                    self.logger.error(err_msg)
                    self.print_msg(err_msg, heading='error')
                    self.exit_cli(1)

            all_res.append(res)

        query_imgs = image.ImageList(self)
        query_imgs.ingest_results(all_res)

        if no_order:
            self.eodms_geo.export_results(query_imgs, self.output)
            self.exit_cli()

        # Update the self.cur_res for output results
        self.cur_res = query_imgs

        # Parse out AWS
        if aws_download:
            eodms_imgs, aws_imgs = self._parse_aws(query_imgs)
        else:
            eodms_imgs = query_imgs
            aws_imgs = None

        ###############################################
        # Get Items and Download from DDS API
        ###############################################

        aws_downloads = None
        if aws_imgs:
            aws_downloads = self.download_aws(aws_imgs)
            eodms_imgs.add_images(aws_downloads)

        self._get_dds_images(eodms_imgs)

        self._finish_process(eodms_imgs)

    def download_aoi(self, params):
        """
        Runs a query and downloads images from existing orders.

        :param params: A dictionary containing the arguments and values.
        :type  params: dict
        """

        # Log the parameters
        self.log_parameters(params)

        # Get all the values from the parameters
        collections = params.get('collections')
        dates = params.get('dates')
        aoi = params.get('input_val')
        overlap = params.get('overlap')
        filters = params.get('filters')
        maximum = params.get('maximum')
        self.output = params.get('output')

        # Validate AOI
        if aoi is not None:
            if os.path.exists(aoi):
                aoi_check = self.validate_file(aoi, True)
                if not aoi_check:
                    err_msg = "The provided input file is not a valid AOI " \
                              "file."
                    self.logger.error(err_msg)
                    self.exit_cli(1)
            else:
                if not self.eodms_geo.is_wkt(aoi):
                    err_msg = "The provided WKT feature is not valid."
                    self.logger.error(err_msg)
                    self.exit_cli(1)

        # Create info folder, if it doesn't exist, to store CSV files
        start_str = self._set_result_fn()

        self.logger.info(f"Process start time: {start_str}")

        #############################################
        # Search for Images
        #############################################

        # Convert collections to list if not already
        if not isinstance(collections, list):
            collections = [collections]

        # Parse dates if not already done
        if not isinstance(dates, list):
            dates = self._parse_dates(dates)

        # Send query to EODMSRAPI
        query_imgs = self.query_entries(collections, filters=filters,
                                        aoi=aoi, dates=dates)

        if overlap is not None \
                and not overlap == '' \
                and aoi is not None \
                and not aoi == '':
            query_imgs.filter_overlap(overlap, aoi)

        # If no results were found, inform user and end process
        if query_imgs.count() == 0:
            msg = "Sorry, no results found for given AOI or filters."
            self.print_msg(msg, heading="warning")
            self.logger.warning(msg)
            self.exit_cli(1)

        # Update the self.cur_res for output results
        self.cur_res = query_imgs

        # Print results info
        msg = f"{query_imgs.count()} images returned from search results.\n"
        self.print_footer('Query Results', msg)

        #############################################
        # Get Existing Order Results
        #############################################

        orders = self.retrieve_orders(query_imgs)

        #############################################
        # Download Images
        self._download_items(orders, query_imgs)

        query_imgs = orders.get_images()

        self._finish_process(query_imgs)

    def download_restored_items(self, params):
        """
        Downloads restored images using a JSON file.
        """

        # Log the parameters
        self.log_parameters(params)

        json_fn = params.get('input_val')

        with open(json_fn, 'r') as json_f:
            restored_items = json.load(json_f)
        
        query_imgs = image.ImageList(self)
        query_imgs.ingest_results(restored_items)

        self._get_dds_images(query_imgs)

        self._finish_process(query_imgs)

    def download_available(self, params):
        """
        Downloads order items that have status AVAILABLE_FOR_DOWNLOAD.

        :return:
        """

        # Log the parameters
        self.log_parameters(params)

        self.order_items = params.get('orderitems')
        self.max_downloads = params.get('maximum')
        self.output = params.get('output')

        # Create info folder, if it doesn't exist, to store CSV files
        start_str = self._set_result_fn()

        self.logger.info(f"Process start time: {start_str}")

        dtstart = None
        dtend = None
        if self.order_check_date:
            dtstart = self.order_check_date
            dtend = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')

            if any(word in dtstart for word in self.time_words):
                print(f"\nGetting orders from the last {dtstart} "
                      f"(from entry RAPI.order_check_date set in the "
                      f"configuration file).\n")
            else:
                print(f"\nGetting orders since {dtstart} "
                      f"(from entry RAPI.order_check_date set in the "
                      f"configuration file).\n")

        ################################################
        # Get Existing Orders
        ################################################
        orders = image.OrderList(self)
        if self.order_items is not None and not self.order_items == '':
            # Parse orders and order items
            oi_split = self.order_items.split('|')

            order_ids = []
            item_ids = []
            for i in oi_split:
                if i.find('order') > -1:
                    ids = [id for id in i.split(':')[1].split(',')]
                    order_ids += ids
                elif i.find('item') > -1:
                    ids =[id for id in i.split(':')[1].split(',')]
                    item_ids += ids

            # orders = []
            for id in order_ids:
                order = self.eodms_rapi.get_order(id)
                if order is not None:
                    imgs = self.get_image_from_order(order)
                    orders.ingest_results(order, imgs)
                    # orders += order

            for id in item_ids:
                item = self.eodms_rapi.get_order_item(id)
                if item is not None and not isinstance(item, QueryError):
                    # orders += item['items']
                    imgs = self.get_image_from_order(item['items'])
                    orders.ingest_results(item['items'], imgs)

        elif self.max_downloads is not None and not self.max_downloads == '':
            ord_res = self.eodms_rapi.get_orders(max_orders=self.max_downloads,
                                                dtstart=dtstart, dtend=dtend,
                                                status='AVAILABLE_FOR_DOWNLOAD')
            imgs = self.get_image_from_order(ord_res)
            orders.ingest_results(ord_res, imgs)
        else:
            max_orders = 250
            ord_res = None
            # Cycle through until orders have been returned
            while ord_res is None and max_orders > 0:
                ord_res = self.eodms_rapi.get_orders(max_orders=max_orders,
                                                dtstart=dtstart, dtend=dtend,
                                                status='AVAILABLE_FOR_DOWNLOAD')
                imgs = self.get_image_from_order(ord_res)
                orders.ingest_results(ord_res, imgs)
                max_orders -= 50

        if orders is None or orders.count() == 0:
            msg = "No orders were returned."
            self.logger.error(msg)
            # self.print_support(msg)
            self.print_msg(msg, heading='error')
            self.exit_cli(1)

        msg = f"Number of order items with status " \
              f"AVAILABLE_FOR_DOWNLOAD: {orders.count_items()}"
        print(f"\n{msg}")
        self.logger.info(msg)

        ########################################################################

        # Download images using the EODMSRAPI
        self._download_items(orders)

        # Get ImageList from orders
        query_imgs = orders.get_images()

        self.cur_res = query_imgs
        self._finish_process(query_imgs)

    def order_st(self, sar_toolbox, params):
        """
        Submit a SAR Toolbox order to the RAPI.
        """

        in_vals = params.get('input_val')
        priority = params.get('priority')

        if in_vals:
            sar_toolbox.set_coll_id(in_vals.get('collection_id'))
            sar_toolbox.set_record_ids(in_vals.get('record_ids'))
        else:
            st_request = sar_toolbox.out_fn
            if not st_request:
                err_msg = "No input JSON request file specified."
                self.logger.error(err_msg)
                self.print_msg(err_msg, heading='error')
                self.exit_cli(1)

            with open(st_request) as f:
                json_info = json.load(f)
            
            items = json_info.get('items')

            coll_id = items[0].get('collectionId')
            record_ids = [i.get('recordId') for i in items]

            sar_toolbox.set_coll_id(coll_id)
            sar_toolbox.set_record_ids(record_ids)

        start_str = self._set_result_fn()
        self.logger.info(f"Process start time: {start_str}")

        st_json = sar_toolbox.get_request()

        all_items = []
        for item in st_json.get('items'):
            coll_id = item.get('collectionId')
            rec_id = item.get('recordId')
            res = self.eodms_rapi.get_record(coll_id, rec_id)

            if isinstance(res, dict) and 'errors' in res.keys():
                if res.get('errors').find('404 Client Error') > -1:
                    err_msg = f"Image with Record ID {rec_id} could not " \
                                f"be found in Collection {coll_id}."
                    self.logger.error(err_msg)
                    self.print_msg(err_msg, heading='error')
                    self.exit_cli(1)

            all_items.append(res)

        query_imgs = image.ImageList(self)
        query_imgs.ingest_results(all_items)

        # Update the self.cur_res for output results
        self.cur_res = query_imgs

        print(f"\nSAR Toolbox JSON request POSTED to RAPI:")
        print(json.dumps(st_json, indent=4))

        orders = image.OrderList(self)
        order_res = self.eodms_rapi.order_json(st_json, priority)
        
        if isinstance(order_res, QueryError):
            err_msg = order_res.get_msgs(True)
            self.logger.error(err_msg)

            if err_msg.find('500 Server Error') > -1:
                err_msg += "\n\nSAR Toolbox validation failed." \
                    "\n\nBefore submitting a new request or contacting the " \
                    "EODMS Support Team, please check the common " \
                    "issues/errors at " \
                    "https://github.com/eodms-sgdot/eodms-cli/wiki/Process-6#validation-errorscommon-issues"

            self.print_msg(err_msg, heading='error')
            self.exit_cli(1)

        # Remove other order items in order
        order_id = order_res[0].get('orderId')
        available_order = self.eodms_rapi.get_order(order_id)

        orders.ingest_results(available_order)

        # Get a list of order items in JSON format for the EODMSRAPI
        if orders.count() > 0:
            self._download_items(orders, query_imgs)
        else:
            print("\nNo orders submitted.")

        orders.print_orders("Download results")

        # Get ImageList from orders
        query_imgs = orders.get_images()

        self._finish_process(query_imgs)
