##############################################################################
#
# Copyright (c) His Majesty the King in Right of Canada, as
# represented by the Minister of Natural Resources, 2025
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
# import dateparser
import json
import glob
import logging
# from copy import copy

import eodms_rapi as rapi
from eodms_rapi import EODMSRAPI
from eodms_rapi import QueryError

try:
    import dateparser
except Exception:
    message = "Dateparser package is not installed. Please install and run " \
          "script again."
    print(message)
    # logger.error(msg)
    sys.exit(1)

from . import csv_util
from . import image
from . import spatial
from . import field

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

        self.rapi_domain = None
        self.indent = 3

        self.operators = ['=', '<', '>', '<>', '<=', '>=', ' LIKE ',
                          ' STARTS WITH ', ' ENDS WITH ', ' CONTAINS ',
                          ' CONTAINED BY ', ' CROSSES ', ' DISJOINT WITH ',
                          ' INTERSECTS ', ' OVERLAPS ', ' TOUCHES ', ' WITHIN ']

        self.username = kwargs.get('username')
        self.password = kwargs.get('password')

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

        if kwargs.get('rapi_url') is not None:
            self.rapi_domain = str(kwargs.get('rapi_url'))
            # self.eodms_rapi.set_root_url(self.rapi_domain)

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

        # self.field_mapper = field.EodFieldMapper(self.eodms_rapi)
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
            'note': self.note_colour
        }
            

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
            # print(f"in_dates: {in_dates}")
            date_ranges = in_dates.split(',')

            # print(f"date_ranges: {date_ranges}")

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

        out_filters = {}

        for filt in filters:

            # filt = filt.upper()

            if all(x not in filt for x in self.operators):
                print(f"Filter '{filt}' entered incorrectly.")
                continue

            ops = [x for x in self.operators if x in filt]

            filt_split = ''
            op = ''
            for o in ops:
                filt_split = filt.split(o)
                op = o

            if coll_id is None:
                coll_id = self.coll_id

            # Convert the input field for EODMS_RAPI
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

            # Modified operator if maximum or minimum
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

            # Check if val is a valid entry for the filter
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

        # Translate order_check_date into date range for the RAPI
        # dtend = datetime.datetime.now()
        # dtstart = dateparser.parse(self.order_check_date)

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

    def _print_results(self, orders):
        """
        Prints the results of order downloads.
        
        :param orders: A list of orders after they've been downloaded.
        :type  orders: image.OrderList
        """

        success_orders = image.OrderList(self)
        failed_orders = image.OrderList(self)

        for item in orders.get_order_items():
            # print(f"img status: {img.get_metadata()}")

            # print(f"item: {item}")

            # order_items = item.get_metadata('orderItems')

            # for item in order_items:
            # order_item_id = item.get_item_id()
            # img = item.get_image()
            status = item.get_status()
            # print(f"status: {status}")
            if status in ['AVAILABLE_FOR_DOWNLOAD', 'SUCCESS']:
                # order_item_info = {"order_item_id": order_item_id, 
                #                     "image": img}
                success_orders.add_order_item(item)
            else:
                # order_item_info = {"order_item_id": order_item_id, 
                #                     "image": img}
                failed_orders.add_order_item(item)

        if success_orders.count_items() > 0:
            # Print information for all successful orders
            #   including the download location
            msg = "The following images have been downloaded:\n"
            for item_info in success_orders.get_order_items():

                # order_item_id = item_info.get('order_item_id')
                # img = item_info.get_image()

                # rec_id = img.get_record_id()
                # coll_id = img.get_metadata('collectionId')
                rec_id = item_info.get_record_id()
                coll_id = item_info.get_metadata('collectionId')
                order_id = item_info.get_metadata('orderId')
                orderitem_id = item_info.get_metadata('itemId')
                dests = item_info.get_metadata('downloadPaths')
                if dests is None:
                    # print(f"Skipping Image with Record Id: {rec_id}")
                    continue

                for d in dests:
                    loc_dest = d['local_destination']
                    src_url = d['url']
                    msg += f"\nRecord ID {rec_id}\n"
                    msg += f"    Collection ID: {coll_id}\n"
                    msg += f"    Order Item ID: {orderitem_id}\n"
                    msg += f"    Order ID: {order_id}\n"
                    msg += f"    Downloaded File: {loc_dest}\n"
                    msg += f"    Source URL: {src_url}\n"
            self.print_footer('Successful Downloads', msg)
            self.logger.info(f"Successful Downloads: {msg}")

        if failed_orders.count_items() > 0:
            msg = "The following images did not download:\n"
            for item_info in failed_orders.get_order_items():
                
                # order_item_id = item_info.get('order_item_id')
                # img = item_info.get_image()

                # rec_id = img.get_record_id()
                order_id = item_info.get_metadata('orderId')
                rec_id = item_info.get_record_id()
                coll_id = item_info.get_metadata('collectionId')
                orderitem_id = item_info.get_metadata('itemId')
                status = item_info.get_status()
                stat_msg = item_info.get_metadata('statusMessage')

                msg += f"\nRecord ID {rec_id}\n"
                msg += f"    Order Item ID: {orderitem_id}\n"
                msg += f"    Order ID: {order_id}\n"
                msg += f"    Status: {status}\n"
                msg += f"    Status Message: {stat_msg}\n"
            self.print_footer('Failed Downloads', msg)
            self.logger.info(f"Failed Downloads: {msg}")

            if self.download_attempts is not None:
                self.print_msg(f"The 'download_attempts' parameter in the "
                               f"configuration file is currently "
                               f"set to {self.download_attempts}.\nPlease "
                               f"consider increasing it to make sure the "
                               f"script continues to check for your orders "
                               f"until they become AVAILABLE_FOR_DOWNLOAD.\n"
                               f"(You can change the value by runnning "
                               f"'python eodms_cli.py --configure RAPI' "
                               f"and go through the parameters until you "
                               f"reach the 'download_attempts').", 
                               heading='note')

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
        # exist_orders = None
        if imgs_to_order.count() > 0:

            # Separated AWS images from order list
            # Convert results to an OrderList
            submit_orders = image.ImageList(self, imgs.get_images())
            for img in imgs.get_images():
                rec_id = img.get_record_id()
                item = exist_orders.get_item_by_rec_id(rec_id)
                # print(f"item: {item}")

                if item is None:
                    continue

                if not item.is_st():
                    submit_orders.remove_image(rec_id)

            # Convert results to JSON
            json_res = submit_orders.get_raw()

            # print(f"json_res: {json_res}")

            # orders = image.OrderList(self, imgs)

            # print(f"orders id: {id(orders)}")

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
                self.export_results()
                err_msg = "No orders were submitted successfully."
                # self.print_support(True, err_msg)
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

        if item is None:
            if self.eodms_rapi.auth_err:
                msg = "\nAn authentication error has occurred while " \
                    "trying to access the EODMS RAPI. Please ensure " \
                    "your account login is in good standing on the actual " \
                    "website, https://www.eodms-sgdot.nrcan-rncan.gc.ca/" \
                    "index-en.html. Once your account is ready, you can " \
                    "run 'python eodms_cli.py --configure credentials' to " \
                    "add your new credentials to the configuration file."
            else:
                msg = "Failed to retrieve a list of available collections."
            self.logger.error(msg)
            self.exit_cli(1)

        # if 'get_msgs' in dir(coll_lst):
        if isinstance(item, QueryError):
            err_msg = item.get_msgs(True)
            if err_msg.find('401 Client Error') > -1:
                msg = "An authentication error has occurred while " \
                    "trying to access the EODMS RAPI.\n\nPlease ensure " \
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

        filters = self.rapi_search_args.get('filters')
        features = self.rapi_search_args.get('features')
        dates = self.rapi_search_args.get('dates')
        result_fields = self.rapi_search_args.get('resultFields')
        max_res = self.rapi_search_args.get('maxResults')

        # Get hit count
        print(f"\nGetting hit count...")
        hit_count = self.eodms_rapi.search(self.coll_id, filters, features, 
                                           dates, result_fields, max_res, 
                                           hit_count=True).get('hitCount')
        
        msg = f"Hit Count for Search: {hit_count}"
        print(f"\n{msg}")
        self.logger.info(msg)
        
        return hit_count

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
                    # # print("The file %s will be deleted." % r)
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

        # Add CLI version info to User-Agent in header
        if 'rapi_session' in dir(self.eodms_rapi):
            self.eodms_rapi.rapi_session.add_header('User-Agent', 
                                                f"EODMSCLI/{self.version}", 
                                                True)

        if self.rapi_domain is not None:
            print(f"Changing root url to {self.rapi_domain}\n")
            self.eodms_rapi.set_root_url(self.rapi_domain)

        self.field_mapper = field.EodFieldMapper(self, self.eodms_rapi)

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

            aws_f = os.path.basename(dl_link)
            dest_fn = os.path.join(self.download_path, aws_f)

            # Get the file size of the link
            resp = requests.head(dl_link, verify=False)
            fsize = resp.headers['content-length']

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

    def export_results(self):
        """
        Exports results to a CSV file.
        """

        if self.cur_res is None:
            return None

        # Create EODMS_CSV object to export results
        res_fn = os.path.join(self.results_path, f"{self.fn_str}_Results.csv")
        res_csv = csv_util.EODMS_CSV(self, res_fn)

        res_csv.export_results(self.cur_res)

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

    def get_collid_by_name(self, in_title):  # , unsupported=False):
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

        for k, v in self.eodms_rapi.get_collections().items():
            if v['title'].find(in_title) > -1:
                return k

        return self.get_full_collid(in_title)

    def get_rapi(self):
        """
        Returns the eodms_rapi object.
        """

        return self.eodms_rapi

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
            
        # print(f"colour: {colour}")

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

        collections = self.eodms_rapi.get_collections()
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
            # self.print_support(True, err_msg)
            self.print_msg(err_msg, heading='error')
            self.logger.error(err_msg)
            self.exit_cli(1)

        eod_csv = csv_util.EODMS_CSV(self, in_csv)
        
        return eod_csv.import_csv(True)

    # def get_filters(self, coll_id):
    #     """

    #     """

    #     all_fields = self.eodms_rapi.get_available_fields(coll_id)['search']

    #     display_fields = {k: v for k, v in all_fields.items() 
    #                         if v.get('displayed')}

    #     return displayed_fields

    def get_record_ids(self, coll_id, order_keys):

        if not isinstance(order_keys, list):
            order_keys = [order_keys]
        
        record_ids = []
        for ok in order_keys:
            filters = {'Order Key': ('=', ok)}
            self.eodms_rapi.search(coll_id, filters)

            res = self.eodms_rapi.get_results()
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

        # print(f"order item count: {orders.count_items()}")

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

                    self.export_results()
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

    def print_msg(self, msg, nl=True, indent=False, heading=None, wrap_text=True):
        """
        Prints a message to the command prompt.
        
        :param msg: The message to print to the screen.
        :type  msg: str
        :param nl: If True, a newline will be added to the start of the message.
        :type  nl: boolean
        :param indent: A string with the indentation.
        :type  indent: boolean
        """

        # tabsize = 0
        initial_indent = ''
        subsequent_indent = ''
        if indent:
            # tabsize = 4
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

    # def print_support(self, err=False, err_str=None):
    #     """
    #     Prints the 2 different support message depending if an error occurred.

    #     :param err: Determines if the output should be for an error.
    #     :type  err: bool
    #     :param err_str: The error string to print along with support.
    #     :type  err_str: str
    #     """

    #     if err:
    #         if err_str:
    #             err_str = textwrap.fill(err_str, width=80, 
    #                                     break_long_words=False, 
    #                                     replace_whitespace=False, 
    #                                     break_on_hyphens=False)
    #             # wrapper = textwrap.TextWrapper(width=80,
    #             #                                break_long_words=False,
    #             #                                replace_whitespace=False, 
    #             #                                break_on_hyphens=False)
    #             # err_str = wrapper.fill(text=err_str)
    #             color = color_map.get('error')
    #             style = Style.BRIGHT
    #             print(style + color + f"\nERROR:\n{err_str}")

    #         print(Fore.RESET + "\nExiting process.")

    #         print(f"\nFor help, please contact the EODMS Support Team at "
    #               f"{self.email}")
    #     else:
    #         print(f"\nIf you have any questions or require support, "
    #               f"please contact the EODMS Support Team at "
    #               f"{self.email}")

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

                # print(f"self.coll_id: {self.coll_id}")
                # print(f"filters.keys(): {filters.keys()}")

                if self.coll_id in filters.keys():
                    coll_filts = filters[self.coll_id]
                    filt_parse = self._parse_filters(coll_filts)
                    if isinstance(filt_parse, str):
                        filt_parse = {}
                else:
                    filt_parse = {}
            else:
                filt_parse = {}

            # print(f"filt_parse: {filt_parse}")

            # if self.coll_id == 'NAPL':
            #     filt_parse['Price'] = ('=', True)

            # print(f"filt_parse: {filt_parse}")

            result_fields = []
            if filt_parse is not None:
                av_fields = self.eodms_rapi.get_available_fields(self.coll_id,
                                                                 'title')

                if av_fields is None:
                    return None

                result_fields.extend(k for k in filt_parse.keys() 
                    if k in av_fields['results'])

            # Create search method arguments dictionary:
            self.rapi_search_args = {
                "filters": filt_parse, 
                "features": feats, 
                "dates": dates, 
                "resultFields": result_fields, 
                "maxResults": max_images
            }

            # Send a query to the EODMSRAPI object
            print(f"\nSending query to EODMSRAPI with the following "
                  f"parameters:")
            for k, v in self.rapi_search_args.items():
                print(f"  {k}: {v}")

            # Check hit count for the search
            hit_count = self.check_hit_count()

            if hit_count == 0:
                msg = "Sorry, no results found for given AOI or filters."
                self.print_msg(msg, heading="warning")
                self.logger.warning(msg)
                self.exit_cli()

            if max_images is None or max_images == '' or max_images > hit_count:
                max_images = hit_count

            if max_images > 1500:
                msg = f"""The hit count for this search is too high. The RAPI will most likely timeout. 
Please separate your searches into separate commands, narrowing your searches with other filters (such as adding a date range(s)).
Example:
{self.prompter.cli_syntax} -d <yymmddThhmmss>-<yymmddThhmmss>"""
                self.print_msg(msg, indent=False, heading='warning', 
                               wrap_text=False)
                # print(msg)

                # answer = input("\nWould you like to continue with the first 1500 results returned from RAPI?: ")

                ask_msg = "Would you like to continue with the 1500 latest " \
                    "results returned from RAPI?"
                answer = self.prompter.get_input(ask_msg, required=False, 
                                                 default='n', 
                                                 options=['Yes', 'No'])

                if answer.lower().find('n') > -1:
                    sys.exit()
                # warn_msg = "The hit count for this search is too high. " \
                #     "The RAPI will most likely timeout."
                # self.print_msg(warn_msg, indent=False, heading='error')
                # self.logger.warning(warn_msg)
                max_images = 1500

            self.eodms_rapi.search(self.coll_id, filt_parse, feats, dates,
                                   result_fields, max_images)

            res = self.eodms_rapi.get_results()

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

        colls = self.eodms_rapi.get_collections()

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
                # self.print_support(True, err_msg)
                self.print_msg(err_msg, heading='error')
                self.logger.error(err_msg)
                return False

            if not os.path.exists(abs_path):
                err_msg = "The AOI file does not exist."
                # self.print_support(True, err_msg)
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
            # self.print_support(True, err_msg)
            self.print_msg(err_msg, heading='error')
            self.logger.error(err_msg)
            return False

        # Check if filter name is valid
        coll_fields = self.field_mapper.get_fields(coll_id)

        filts = filt_items.split(',')

        for f in filts:
            if not any(x in f.upper()
                       for x in coll_fields.get_eod_fieldnames()):
                err_msg = f"Filter '{f}' is not available for collection " \
                          f"'{coll_id}'."
                # self.print_support(True, err_msg)
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

        # print(f"items: {len(items)}")

        # Download images using the EODMSRAPI
        download_items = self.eodms_rapi.download(items, self.download_path,
                                        max_attempts=self.download_attempts)

        self.ingest_downloads(orders, download_items, eodms_imgs)

    def _finish_process(self, orders=None, in_imgs=None):
        """
        Exports and prints available information at the end of a process.
        """

        if not in_imgs:
            in_imgs = self.cur_res

        self._print_results(orders)

        # Export polygons of images
        self.eodms_geo.export_results(in_imgs, self.output)

        self.export_results()

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
        # process = params.get('process')
        maximum = params.get('maximum')
        self.output = params.get('output')
        overlap = params.get("overlap")
        priority = params.get('priority')
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
        max_images, max_items = self.parse_max(maximum)

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

        # print("#1")

        if overlap is not None \
                and not overlap == '' \
                and aoi is not None \
                and not aoi == '':
            query_imgs.filter_overlap(overlap, aoi)

        # print("#2")

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
              f"results:\n\n"
        if query_imgs.count() <= 20:
            msg += f"Record Ids: {', '.join(query_imgs.get_ids())}"
        else:
            msg += "Check the results file for Record Ids."
        self.print_footer('Query Results', msg)

        if no_order:
            self.eodms_geo.export_results(query_imgs, self.output)
            self.export_results()
            self.exit_cli()

        if max_images is None or max_images == '':
            # Inform the user of the total number of found images and ask if
            #   they'd like to continue
            if not self.silent:
                answer = input(f"\n{query_imgs.count()} images found for "
                               f"your search filters. Proceed with "
                               f"ordering? (y/n): ")
                if answer.lower().find('n') > -1:
                    self.export_results()
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

        #############################################
        # Order Images
        #############################################
        orders = image.OrderList(self)
        if eodms_imgs.count() > 0:
            orders = self._submit_orders(eodms_imgs, priority, max_items)

        #############################################
        # Download Images
        #############################################

        # Make the download folder if it doesn't exist
        if not os.path.exists(self.download_path):
            os.mkdir(self.download_path)

        # Download all AWS images first
        aws_downloads = None
        if aws_imgs:
            aws_downloads = self.download_aws(aws_imgs)

        # Get a list of order items in JSON format for the EODMSRAPI
        if orders.count() > 0:
            self._download_items(orders, eodms_imgs)

        if aws_downloads:
            eodms_imgs.add_images(aws_downloads)

        self._finish_process(orders)

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
            # self.print_support(err_msg)
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
        max_images, max_items = self.parse_max(maximum)

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

        # self.export_results()

        if no_order:
            self.eodms_geo.export_results(query_imgs, self.output)
            self.export_results()
            self.exit_cli()

        #############################################
        # Order Images
        #############################################

        # print(f"query_imgs: {query_imgs.count()}")

        # Remove collections that don't allow ordering
        # filt_imgs = self._filter_for_order(query_imgs)

        # Parse out AWS
        if aws_download:
            eodms_imgs, aws_imgs = self._parse_aws(query_imgs)
        else:
            eodms_imgs = query_imgs
            aws_imgs = None

        # print(f"filt_imgs: {filt_imgs.count()}")

        orders = image.OrderList(self)
        if eodms_imgs.count() > 0:
            orders = self._submit_orders(eodms_imgs, priority)

        #############################################
        # Download Images
        #############################################

        # Make the download folder if it doesn't exist
        if not os.path.exists(self.download_path):
            os.mkdir(self.download_path)

        # Download all AWS images first
        aws_downloads = None
        if aws_imgs:
            aws_downloads = self.download_aws(aws_imgs)

        # Get a list of order items in JSON format for the EODMSRAPI
        if orders.count() > 0:
            self._download_items(orders, eodms_imgs)

        if aws_downloads:
            eodms_imgs.add_images(aws_downloads)

        self._finish_process(orders)

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
                    # self.print_support(err_msg)
                    self.print_msg(err_msg, heading='error')
                    self.exit_cli(1)

            all_res.append(res)

        # print("all_res: %s" % all_res)

        query_imgs = image.ImageList(self)
        query_imgs.ingest_results(all_res)

        if no_order:
            self.eodms_geo.export_results(query_imgs, self.output)
            self.export_results()
            self.exit_cli()

        # # Parse the maximum number of orders and items per order
        # max_images, max_items = self.parse_max(maximum)

        # # Import and query entries from the CSV
        # query_imgs = self._get_eodmsRes(csv_fn)
        print(f"query_imgs: {query_imgs.count()}")

        # Update the self.cur_res for output results
        self.cur_res = query_imgs

        # Parse out AWS
        if aws_download:
            eodms_imgs, aws_imgs = self._parse_aws(query_imgs)
        else:
            eodms_imgs = query_imgs
            aws_imgs = None

        #############################################
        # Order Images
        #############################################

        if eodms_imgs.count() > 0:
            orders = self._submit_orders(eodms_imgs, priority)

        # print(f"2240 - orders: {id(orders)}")

        if orders is None:
            orders = image.OrderList(self)

        # print(f"orders 2 len: {orders.count_items()}")
       #  orders.print_orders("Orders 2")

        # print(f"2248 - orders: {id(orders)}")

        #############################################
        # Download Images
        #############################################

        # Download all AWS images first
        aws_downloads = None
        if aws_imgs:
            aws_downloads = self.download_aws(aws_imgs)

        # Get a list of order items in JSON format for the EODMSRAPI
        if orders.count() > 0:
            self._download_items(orders, eodms_imgs)
        
        # print(f"orders 3 len: {orders.count_items()}")
        # orders.print_orders("Orders 3")

        # print(f"2266 - orders: {id(orders)}")

        orders.print_orders("Download results")

        if aws_downloads:
            eodms_imgs.add_images(aws_downloads)

        self._finish_process(orders)

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
        # process = params.get('process')
        maximum = params.get('maximum')
        self.output = params.get('output')
        # priority = params.get('priority')

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

        # Parse maximum items
        _, max_items = self.parse_max(maximum)

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

        self._finish_process(orders)

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
        self._finish_process(orders)

    def download_results(self, params):
        """
        Downloads existing images using the CSV results file from a previous
            session.

        :param params: A dictionary containing the arguments and values.
        :type  params: dict
        """

        # Log the parameters
        self.log_parameters(params)

        csv_fn = params.get('input_val')
        self.output = params.get('output')

        if csv_fn.find('.csv') == -1:
            msg = "The provided input file is not a CSV file."
            self.logger.error(msg)
            # self.print_support(msg)
            self.print_msg(msg, heading='error')
            self.exit_cli(1)

        # Create info folder, if it doesn't exist, to store CSV files
        start_str = self._set_result_fn()
        self.logger.info(f"Process start time: {start_str}")

        ################################################
        # Get results from Results CSV
        query_imgs = self._get_prev_res(csv_fn)

        ########################################################################

        ################################################
        # Get Existing Orders
        ################################################

        orders = self.retrieve_orders(query_imgs)

        ################################################
        # Download Images
        self._download_items(orders, query_imgs)

        # Export info
        self.cur_res = query_imgs
        self._finish_process(orders)

    def order_st(self, sar_toolbox, params): # sar_toolbox, priority):
        """
        Submit a SAR Toolbox order to the RAPI.
        """

        in_vals = params.get('input_val')
        priority = params.get('priority')

        if in_vals:
            sar_toolbox.set_coll_id(in_vals.get('collection_id'))
            sar_toolbox.set_record_ids(in_vals.get('record_ids'))
        else:
            st_request = params.get('st_request')
            if not st_request:
                err_msg = "No input JSON request file specified."
                self.logger.error(err_msg)
                # self.print_support(err_msg)
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
                    # self.print_support(err_msg)
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
        # print(type(self.eodms_rapi))
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

        self._finish_process(orders)
