##############################################################################
#
# Copyright (c) His Majesty the King in Right of Canada, as
# represented by the Minister of Natural Resources, 2024
# 
# Licensed under the MIT license
# (see LICENSE or <http://opensource.org/licenses/MIT>) All files in the 
# project carrying such notice may not be copied, modified, or distributed 
# except according to those terms.
# 
##############################################################################

__title__ = 'EODMS-CLI'
__author__ = 'Kevin Ballantyne'
__copyright__ = 'Copyright (c) His Majesty the King in Right of Canada, ' \
                'as represented by the Minister of Natural Resources, 2024'
__license__ = 'MIT License'
__description__ = 'Script used to search, order and download imagery from ' \
                  'the EODMS using the REST API (RAPI) service.'
__version__ = '3.6.2'
__maintainer__ = 'Kevin Ballantyne'
__email__ = 'eodms-sgdot@nrcan-rncan.gc.ca'

import sys
import os
import re
import requests
# import argparse
import click
import traceback
import getpass
import datetime
import textwrap
# from geomet import wkt
# import json
# import configparser
import base64
import binascii
import logging
import logging.handlers as handlers
import pathlib
from colorama import Fore, Back, Style
# from distutils.version import LooseVersion
# from distutils.version import StrictVersion
from packaging import version as pack_v
# import unicodedata
import eodms_rapi

# from eodms_rapi import EODMSRAPI

from scripts import utils as eod_util
from scripts import field
from scripts import config_util
from scripts import sar

# from utils import csv_util
# from utils import image
# from utils import geo

proc_choices = {'full': {
                    'name': 'Search, order and/or download',
                    'desc': 'Search, order and/or download images using an AOI '
                            'and/or filters'
                },
                'order_csv': {
                    'name': 'EODMS UI Ordering',
                    'desc': 'Order & download images using EODMS UI search '
                            'results (CSV file)'
                },
                'record_id': {
                    'name': 'Record IDs',
                    'desc': 'Order and download a single or set of images '
                            'using Record IDs'
                },
                'download_available': {
                    'name': 'Download Available Order Items',
                    'desc': 'Downloads order items with status '
                            'AVAILABLE_FOR_DOWNLOAD'
                },
                'download_results': {
                    'name': 'Download EODMS-CLI Results',
                    'desc': 'Download existing orders using a CSV file from '
                            'a previous order/download process (files found '
                            'under "results" folder)'
                },
                'order_st': {
                    'name': 'Submit Order to SAR Toolbox',
                    'desc': 'Submit order to the SAR Toolbox'
                }
            }

min_rapi_version = '1.9.0'

class Prompter:
    """
    Class used to prompt the user for all inputs.
    """

    def __init__(self, eod, config_util, params, in_click, testing=False):
        """
        Initializer for the Prompter class.
        
        :param eod: The Eodms_OrderDownload object.
        :type  eod: self.Eodms_OrderDownload
        :param config_util: The ConfigUtils object
        :type  config_util: ConfigUtils
        :param params: An empty dictionary of parameters.
        :type  params: dict
        """

        self.eod = eod
        self.eod.set_prompter(self)
        self.reset_col = eod.get_colour(reset=True)
        self.config_util = config_util
        self.config_info = config_util.get_info()
        self.params = params
        self.click = in_click
        self.process = None
        self.testing = testing

        self.logger = logging.getLogger('eodms')

    # def remove_accents(self, s):
    #     nkfd_form = unicodedata.normalize('NFKD', s)
    #     return u''.join([c for c in nkfd_form
    #     if not unicodedata.combining(c)])

    def ask_aoi(self, input_fn):
        """
        Asks the user for the geospatial input filename.
        
        :param input_fn: The geospatial input filename if already set by the
                command-line.
        :type  input_fn: str
        
        :return: The geospatial filename entered by the user.
        :rtype: str
        """

        if input_fn is None or input_fn == '':

            # if self.eod.silent:
            #     err_msg = "No AOI file or feature specified. Exiting process."
            #     self.eod.print_support(err_msg)
            #     self.logger.error(err_msg)
            #     sys.exit(1)

            if not self.eod.silent:
                self.print_header("Enter Input Geospatial File or Feature")

                msg = f"Enter the full path name of a " \
                    f"{self.eod.var_colour}.gml{self.eod.reset_colour}, " \
                    f"{self.eod.var_colour}.kml{self.eod.reset_colour}, " \
                    f"{self.eod.var_colour}.shp{self.eod.reset_colour} or " \
                    f"{self.eod.var_colour}.geojson{self.eod.reset_colour} " \
                    f" containing an AOI or a WKT feature to " \
                    f"restrict the search to a specific location"
                err_msg = "No AOI or feature specified. Please enter a WKT " \
                          "feature or a valid GML, KML, Shapefile or GeoJSON " \
                          "file"
                def_msg = "leave blank to exclude spatial filtering"
                input_fn = self.get_input(msg, err_msg, required=False, 
                                          def_msg=def_msg)

        if input_fn is None or input_fn == '':
            return None

        if os.path.exists(input_fn):
            if input_fn.find('.shp') > -1:
                try:
                    import osgeo.ogr as ogr
                    import osgeo.osr as osr
                    # GDAL_INCLUDED = True
                except ImportError:
                    try:
                        import ogr
                        import osr
                        # GDAL_INCLUDED = True
                    except ImportError:
                        err_msg = "Cannot open a Shapefile without GDAL. " \
                                  "Please install the GDAL Python package if " \
                                  "you'd like to use a Shapefile for your AOI."
                        self.eod.print_msg(err_msg, heading='warning')
                        self.logger.warning(err_msg)
                        return None

            input_fn = input_fn.strip()
            input_fn = input_fn.strip("'")
            input_fn = input_fn.strip('"')

            # ---------------------------------
            # Check validity of the input file
            # ---------------------------------

            input_fn = self.eod.validate_file(input_fn, True)

            if not input_fn:
                return None

        elif any(s in input_fn for s in self.eod.aoi_extensions):
            err_msg = f"Input file {os.path.abspath(input_fn)} does not exist."
            # self.eod.print_support(err_msg)
            self.eod.print_msg(err_msg, heading="warning")
            self.logger.warning(err_msg)
            return None

        else:
            if not self.eod.eodms_geo.is_wkt(input_fn):
                err_msg = "Input feature is not a valid WKT."
                # self.eod.print_support(err_msg)
                self.eod.print_msg(err_msg, heading="warning")
                self.logger.warning(err_msg)
                return None

        return input_fn

    def ask_aws(self, aws):
        """
        Asks the user if they'd like to download the image using AWS,
            if applicable.
        
        :param aws: If already entered by the command-line, True if the user
                    wishes to download from AWS.
        :type  aws: boolean
        
        :return: True if the user wishes to download from AWS.
        :rtype: boolean
        """

        if not aws:

            if not self.eod.silent:
                self.print_header("Download from AWS?")

                print("\nSome Radarsat-1 images contain direct download "
                      "links to GeoTIFF files in an Open Data AWS "
                      "Repository.")

                msg = "For images that have an AWS link, would you like to " \
                      "download the GeoTIFFs from the repository instead of " \
                      "submitting an order to the EODMS?"
                aws = self.get_input(msg, required=False, default='y', 
                                     options=['Yes', 'No'])

                if aws.lower().find('y') > -1:
                    aws = True
                else:
                    aws = False

        return aws

    def ask_collection(self, coll, coll_lst=None):
        """
        Asks the user for the collection(s).
        
        :param coll: The collections if already set by the command-line.
        :type  coll: str
        :param coll_lst: A list of collections retrieved from the RAPI.
        :type  coll_lst: list[str]
        
        :return: A list of collections entered by the user.
        :rtype: list[str]
        """

        if coll is None:

            if coll_lst is None:
                coll_lst = self.eod.eodms_rapi.get_collections(True, opt='both')

            if self.eod.silent:
                err_msg = "No collection specified. Exiting process."
                # self.eod.print_support(True, err_msg)
                self.eod.print_msg(err_msg, heading='error')
                self.logger.error(err_msg)
                self.eod.exit_cli(1)

            # print(dir(coll_lst))

            # print("coll_lst: %s" % coll_lst)

            self.print_header("Enter Collection")

            # List available collections for this user
            print("\nAvailable Collections:\n")
            # print(f"coll_lst: {coll_lst}")
            coll_lst = sorted(coll_lst, key=lambda x: x['title'])
            # coll_lst.sort()
            for idx, c in enumerate(coll_lst):
                msg = f"{self.eod.var_colour}{idx + 1}{self.eod.reset_colour}" \
                    f". {c['title']} ({c['id']})"
                # if c['id'] == 'NAPL':
                #     msg += ' (open data only)'
                print(self.wrap_text(msg))

            # Prompted user for number(s) from list
            msg = "Enter the number of a collection from the list " \
                  "above (for multiple collections, enter each number " \
                  "separated with a comma)"
            err_msg = "At least one collection must be specified."
            in_coll = self.get_input(msg, err_msg)

            # Convert number(s) to collection name(s)
            coll_vals = in_coll.split(',')

            # ---------------------------------------
            # Check validity of the collection entry
            # ---------------------------------------

            check = self.eod.validate_int(coll_vals, len(coll_lst))
            if not check:
                err_msg = "A valid Collection must be specified. " \
                          "Exiting process."
                # self.eod.print_support(True, err_msg)
                self.eod.print_msg(err_msg, heading='error')
                self.logger.error(err_msg)
                self.eod.exit_cli(1)

            coll = [coll_lst[int(i) - 1]['id'] for i in coll_vals
                    if i.isdigit()]
        else:
            coll = coll.split(',')

        # ------------------------------
        # Check validity of Collections
        # ------------------------------
        for c in coll:
            check = self.eod.validate_collection(c)
            if not check:
                err_msg = f"Collection '{c}'' is not valid."
                # self.eod.print_support(True, err_msg)
                self.eod.print_msg(err_msg, heading='error')
                self.logger.error(err_msg)
                self.eod.exit_cli(1)

        return coll

    def ask_dates(self, dates):
        """
        Asks the user for dates.
        
        :param dates: The dates if already set by the command-line.
        :type  dates: str
        
        :return: The dates entered by the user.
        :rtype: str
        """

        # Get the date range
        if dates is None:

            if not self.eod.silent:
                self.print_header("Enter Date Range")

                msg = f"Enter a date range (ex: " \
                    f"{self.eod.var_colour}20200525-20200630T200950" \
                    f"{self.eod.reset_colour}) or a previous time-frame " \
                    f"({self.eod.var_colour}24 hours{self.eod.reset_colour})"
                def_msg = "leave blank to search all years"
                dates = self.get_input(msg, required=False, def_msg=def_msg)

        # -------------------------------
        # Check validity of filter input
        # -------------------------------
        if dates is not None and not dates == '':
            dates = self.eod.validate_dates(dates)

            if not dates:
                err_msg = "The dates entered are invalid. "
                # self.eod.print_support(True, err_msg)
                self.eod.print_msg(err_msg, heading='error')
                self.logger.error(err_msg)
                self.eod.exit_cli(1)

        return dates

    def ask_fields(self, csv_fields, fields):

        if csv_fields is not None:
            return csv_fields.split(',')

        srch_fields = []
        for f in fields:
            if f.lower() in self.eod.csv_unique:
                srch_fields.append(f.lower())

        if len(srch_fields) > 0:
            return srch_fields

        if not self.eod.silent:
            self.print_header("Enter CSV Unique Fields")

            print("\nAvailable fields in the CSV file:")
            for f in fields:
                print(f"  {f}")

            msg = "Enter the fields from the CSV file which can be used to " \
                  "determine the images (separate each with a comma)"
            # err_msg = "At least one collection must be specified."
            input_fields = self.get_input(msg)  # , err_msg)

            srch_fields = [f.strip() for f in input_fields.split(',')]

            return srch_fields

    def ask_filter(self, filters):
        """
        Asks the user for the search filters.
        
        :param filters: The filters if already set by the command-line.
        :type  filters: str
        
        :return: A dictionary containing the filters entered by the user.
        :rtype: dict
        """

        if filters is None:
            filt_dict = {}

            if not self.eod.silent:

                self.print_header("Enter Filters")

                # Ask for the filters for the given collection(s)
                for coll in self.params['collections']:
                    coll_id = self.eod.get_full_collid(coll)

                    coll_fields = self.eod.field_mapper.get_fields(coll_id)
                    # coll_fields = self.eod.get_filters(coll_id)

                    if coll_id in self.eod.field_mapper.get_colls():
                        # field_map = self.eod.get_fieldMap()[coll_id]

                        print(f"\nAvailable fields for '{coll}':")
                        # for f in coll_fields.get_eod_fieldnames():
                        #     print(f"  {f}")
                        avail_fields = coll_fields.get_eod_fieldnames(True)
                        fields_str = ', '.join(avail_fields)
                        print(self.wrap_text(fields_str, init_indent='  '))

                        print(self.wrap_text(f"\nFilters must be entered in " \
                              f"the format of {self.eod.var_colour}" \
                              f"[field_id]=[value]|[value]|" \
                              f"{self.eod.reset_colour}... " 
                              f"(field IDs are not case sensitive); " 
                              f"separate each filter with a comma.\nTo see " 
                              f"a list of field choices, enter '" \
                              f"{self.eod.var_colour}? [field_id]" \
                              f"{self.eod.reset_colour}'."
                              f"\n\nExample: BEAM_MNEMONIC=16M4|16M7," 
                              f"PIXEL_SPACING<=20"))

                        msg = "Enter the filters you would like to apply " \
                              "to the search"

                        filt_items = '?'

                        while filt_items.find('?') > -1:
                            # print(f"\n{msg}:\n")
                            # filt_items = input(f"{self.add_arrow()} ")
                            def_msg = "leave blank for no fields"
                            filt_items = self.get_input(msg, required=False, 
                                                        def_msg=def_msg)
                            # filt_items = input(f"\n{self.add_arrow()} " \
                            #                    f"{msg}:\n")

                            if filt_items.find('?') > -1:
                                field_val = filt_items.replace('?', '').strip()

                                field_obj = coll_fields.get_field(field_val)
                                field_title = field_obj.get_rapi_title()

                                if field_title is None:
                                    print("Not a valid field.")
                                    continue

                                field_choices = self.eod.eodms_rapi. \
                                    get_field_choices(coll_id, field_title)

                                if isinstance(field_choices, dict):
                                    field_choices = f'any %s value' % \
                                                    field_choices['data_type']
                                else:
                                    field_choices = ', '.join(field_choices)

                                print(f"\nAvailable choices for "
                                      f"'{field_val}': {field_choices}")

                        if filt_items == '':
                            filt_dict[coll_id] = []
                        else:

                            # -------------------------------
                            # Check validity of filter input
                            # -------------------------------
                            filt_items = self.eod.validate_filters(filt_items,
                                                                   coll_id)

                            if not filt_items:
                                self.eod.exit_cli(1)

                            filt_items = filt_items.split(',')
                            # In case the user put collections in filters
                            filt_items = [f.split('.')[1]
                                          if f.find('.') > -1
                                          else f for f in filt_items]
                            filt_dict[coll_id] = filt_items

        else:
            # User specified in command-line

            # Possible formats:
            #   1. Only one collection: <field_id>=<value>|<value>,
            #       <field_id>=<value>&<value>,...
            #   2. Multiple collections but only specifying one set of filters:
            #       <coll_id>.<field_id>=<value>|<value>,...
            #   3. Multiple collections with filters:
            #       <coll_id>.<field_id>=<value>,...
            #       <coll_id>.<field_id>=<value>,...

            filt_dict = {}

            for coll in self.params['collections']:
                # Split filters by comma
                filt_lst = filters.split(',')
                for f in filt_lst:
                    f = f.strip('"')
                    if f == '':
                        continue
                    if f.find('.') > -1:
                        coll, filt_items = f.split('.')
                        filt_items = self.eod.validate_filters(filt_items,
                                                               coll)
                        if not filt_items:
                            self.eod.exit_cli(1)
                        coll_id = self.eod.get_full_collid(coll)
                        if coll_id in filt_dict.keys():
                            coll_filters = filt_dict.get(coll_id)
                        else:
                            coll_filters = []
                        coll_filters.append(
                            filt_items.replace('"', '').replace("'", ''))
                        filt_dict[coll_id] = coll_filters
                    else:
                        coll_id = self.eod.get_collid_by_name(coll)
                        if coll_id in filt_dict.keys():
                            coll_filters = filt_dict[coll_id]
                        else:
                            coll_filters = []
                        coll_filters.append(f)
                        filt_dict[coll_id] = coll_filters

        # print(f"filt_dict: {filt_dict}")

        return filt_dict

    def ask_input_file(self, input_fn, msg):
        """
        Asks the user for the input filename.
        
        :param input_fn: The input filename if already set by the command-line.
        :type  input_fn: str
        :param msg: The message used to ask the user.
        :type  msg: str
        
        :return: The input filename.
        :rtype: str
        """

        if input_fn is None or input_fn == '':

            if self.eod.silent:
                err_msg = "No CSV file specified. Exiting process."
                self.eod.print_msg(err_msg, heading='error')
                # self.eod.print_support(True, err_msg)
                self.logger.error(err_msg)
                self.eod.exit_cli(1)

            self.print_header("Enter Input CSV File")

            err_msg = "No CSV specified. Please enter a valid CSV file"
            input_fn = self.get_input(msg, err_msg)

        if not os.path.exists(input_fn):
            # err_msg = "Not a valid CSV file. Please enter a valid CSV file."
            err_msg = f"The specified CSV file ({input_fn}) does not exist. " \
                      f"Please enter a valid CSV file."
            # self.eod.print_support(True, err_msg)
            self.eod.print_msg(err_msg, heading='error')
            self.logger.error(err_msg)
            self.eod.exit_cli(1)

        return input_fn

    def ask_maximum(self, maximum, max_type='order'):
        """
        Asks the user for maximum number of order items and the number of
            items per order.
        
        :param maximum: The maximum if already set by the command-line.
        :type  maximum: str
        :param max_type: The type of maximum to set ('order' or 'download').
        :type  max_type: str
        :param no_order: Determines whether the maximum is for searching or
        ordering.
        :type  no_order: boolean
        
        :return: If max_type is 'order', the maximum number of order items
        and/or number of items per order, separated by ':'. If max_type is
        'download', a single number specifying how many images to download.
        :rtype: str
        """

        # Get the no_order value
        no_order = self.params.get('no_order')

        if maximum is None or maximum == '':

            if not self.eod.silent:
                if no_order:
                    self.print_header("Enter Maximum Search Results")
                    msg = "Enter the maximum number of images you would " \
                          "like to search for"
                    def_msg = "leave blank to search for all images"

                    maximum = self.get_input(msg, required=False, 
                                             def_msg=def_msg)

                    return maximum

                if max_type == 'download':
                    self.print_header("Enter Maximum for Downloads")
                    msg = "Enter the number of images with status " \
                          "AVAILABLE_FOR_DOWNLOAD you would like to " \
                          "download"
                    def_msg = "leave blank to download all images with " \
                        "this status"

                    maximum = self.get_input(msg, required=False, 
                                             def_msg=def_msg)

                    return maximum
                else:
                    if not self.process == 'order_csv':

                        self.print_header("Enter Maximums for Ordering")

                        msg = "Enter the total number of images you'd " \
                              "like to order"
                        def_msg = "leave blank for no limit"
                        total_records = self.get_input(msg, required=False, 
                                                       def_msg=def_msg)

                        # ------------------------------------------
                        # Check validity of the total_records entry
                        # ------------------------------------------

                        if total_records == '':
                            total_records = None
                        else:
                            total_records = self.eod.validate_int(total_records)
                            if not total_records:
                                self.eod.print_msg("Total number of images "
                                                   "value not valid. "
                                                   "Excluding it.",
                                                   indent=False, 
                                                   heading='warning')
                                total_records = None
                            else:
                                total_records = str(total_records)
                    else:
                        total_records = None

                    msg = "If you'd like a limit of images per order, " \
                          "enter a value (EODMS sets a maximum limit of " \
                          "100)"
                    def_msg = "leave blank to order all images in one order " \
                        "(up to 100)"
                    order_limit = self.get_input(msg, required=False, 
                                                 def_msg=def_msg)

                    if order_limit == '':
                        order_limit = None
                    else:
                        order_limit = self.eod.validate_int(order_limit,
                                                            100)
                        if not order_limit:
                            self.eod.print_msg("Order limit "
                                               "value not valid. "
                                               "Excluding it.",
                                               indent=False, heading='warning')
                            order_limit = None
                        else:
                            order_limit = str(order_limit)

                    maximum = ':'.join(filter(None, [total_records,
                                                     order_limit]))

        else:

            if max_type == 'order':
                if self.process == 'order_csv':

                    self.print_header("Enter Images per Order")

                    if maximum.find(':') > -1:
                        total_records, order_limit = maximum.split(':')
                    else:
                        total_records = None
                        order_limit = maximum

                    maximum = ':'.join(filter(None, [total_records,
                                                     order_limit]))

        return maximum

    def ask_orderitems(self, orderitems):
        """
        Asks the user for a list Order IDs or Order Item IDs.

        :param orderitems

        """

        if orderitems is None:
            if not self.eod.silent:
                self.print_header("Order/Order Item IDs")

                msg = "\nEnter a list of Order IDs and/or Order Item IDs, " \
                      "separating each ID with a comma and separating Order " \
                      "IDs and Order Items with a vertical line " \
                      "(ex: 'orders:<order_id>,<order_id>|items:" \
                      "<order_item_id>,...')"
                def_msg = "leave blank to skip"
                orderitems = self.get_input(msg, required=False, 
                                            def_msg=def_msg)

        return orderitems

    def ask_order(self, no_order):
        """
        Asks the user if they would like to suppress ordering and downloading.

        :param no_order:
        :return:
        """

        if no_order is None:
            if not self.eod.silent:
                self.print_header("Suppress Ordering")

                msg = "Would you like to only search and not order?"
                no_order = self.get_input(msg, required=False,
                                          options=['Yes', 'No'], default='n')

                if no_order.lower().find('y') > -1:
                    no_order = True
                else:
                    no_order = False

        return no_order

    def ask_output(self, output):
        """
        Asks the user for the output geospatial file.
        
        :param output: The output if already set by the command-line.
        :type  output: str
        
        :return: The output geospatial filename.
        :rtype: str
        """

        if output is None:

            if not self.eod.silent:
                self.print_header("Enter Output Geospatial File")

                msg = f"\nEnter the full path of the output geospatial file " \
                      f"(can also be " \
                      f"{self.eod.var_colour}.geojson{self.eod.reset_colour}," \
                      f" {self.eod.var_colour}.kml{self.eod.reset_colour}, " \
                      f"{self.eod.var_colour}.gml{self.eod.reset_colour}, or" \
                      f" {self.eod.var_colour}.shp{self.eod.reset_colour})"
                def_msg = "default is no output file"
                output = self.get_input(msg, required=False, 
                                        def_msg=def_msg)

        return output

    def ask_overlap(self, overlap):

        if overlap is None:

            if not self.eod.silent:
                self.print_header("Enter Minimum Overlap Percentage")

                msg = "\nEnter the minimum percentage of overlap between " \
                      "images and the AOI"
                def_msg = "leave blank for no overlap limit"
                overlap = self.get_input(msg, required=False, def_msg=def_msg)

        return overlap

    def ask_priority(self, priority):
        """
        Asks the user for the order priority level
        
        :param priority: The priority if already set by the command-line.
        :type  priority: str
        
        :return: The priority level.
        :rtype: str
        """

        priorities = ['low', 'medium', 'high', 'urgent']

        if priority is None:
            if not self.eod.silent:
                self.print_header("Enter Priority")

                msg = "Enter the priority level for the order"

                priority = self.get_input(msg, required=False,
                                          options=priorities, default='medium')

        if priority is None or priority == '':
            priority = 'Medium'
        elif priority.lower() not in priorities:
            self.eod.print_msg("Not a valid 'priority' entry. "
                               "Setting priority to 'Medium'.", indent=False, 
                               heading='warning')
            priority = 'Medium'

        return priority

    def ask_process(self):
        """
        Asks the user what process they would like to run.
        
        :return: The value the process the user has chosen.
        :rtype: str
        """

        if self.eod.silent:
            process = 'full'
        else:
            self.print_header("Choose Process Option")
            choice_strs = []
            # print(f"proc_choices.items(): {proc_choices.items()}")
            for idx, v in enumerate(proc_choices.items()):
                desc_str = re.sub(r'\s+', ' ', v[1]['desc'].replace('\n', ''))
                choice_strs.append(self.wrap_text(f"{self.eod.var_colour}{idx + 1}" \
                                    f"{self.eod.reset_colour}: ({v[0]}) " \
                                    f"{desc_str}", sub_indent='     '))
            choices = '\n'.join(choice_strs)

            print(f"\nWhat would you like to do?\n\n{choices}")
            msg = "Please choose the type of process"
            # process = input(f"{self.add_arrow()} ")
            process = self.get_input(msg, required=False, default='1')
            # process = input(f"{self.add_arrow()} " \
            #                 f"Please choose the type of process [1]: ")

            if self.testing:
                print(f"FOR TESTING - Process entered: {process}")

            if process == '':
                process = 'full'
            else:
                # Set process value and check its validity

                process = self.eod.validate_int(process)

                if not process:
                    err_msg = "Invalid value entered for the 'process' " \
                              "parameter."
                    # self.eod.print_support(True, err_msg)
                    self.eod.print_msg(err_msg, heading='error')
                    self.logger.error(err_msg)
                    self.eod.exit_cli(1)

                if process > len(proc_choices.keys()):
                    err_msg = "Invalid value entered for the 'process' " \
                              "parameter."
                    # self.eod.print_support(True, err_msg)
                    self.eod.print_msg(err_msg, heading='error')
                    self.logger.error(err_msg)
                    self.eod.exit_cli(1)
                else:
                    process = list(proc_choices.keys())[int(process) - 1]

        return process

    def ask_record_ids(self, ids, single_coll=False):
        """
        Asks the user for a single or set of Record IDs.
        
        :param ids: A single or set of Record IDs with their collections.
        :type  ids: str
        """

        if ids is None or ids == '':

            if not self.eod.silent:
                self.print_header("Enter Record Id(s)")

                msg = "\nEnter a single or set of Record IDs. Include the " \
                      "Collection ID at the start of IDs separated by a " \
                      "pipe. Separate collection's Ids with a comma. " \
                      f"(Ex: {self.eod.var_colour}" \
                      f"RCMImageProducts:7625368|25654750" \
                      f",NAPL:3736869{self.eod.reset_colour})\n"
                if single_coll:
                    msg = f"\nEnter a single or set of Record IDs with the " \
                        f"Collection ID at the start of IDs separated by a " \
                        f"pipe (Ex: {self.eod.var_colour}" \
                        f"RCMImageProducts:7625368|25654750" \
                        f"{self.eod.reset_colour})\n"
                ids = self.get_input(msg, required=False)

                process = self.eod.validate_record_ids(ids, single_coll)

                if not process:
                    err_msg = "Invalid entry for the Record Ids."
                    # self.eod.print_support(True, err_msg)
                    self.eod.print_msg(err_msg, heading='error')
                    self.logger.error(err_msg)
                    self.eod.exit_cli(1)

        return ids

    def ask_st_images(self, ids):

        """
        Asks the user for Record IDs or Order Keys for SAR Toolbox orders.
        
        :param ids: A single or set of Record IDs with their collections.
        :type  ids: str
        """

        if ids is None or ids == '':

            if not self.eod.silent:
                self.print_header("Enter Record Id(s) or Order Key(s)")
                
                msg = f"\nEnter a single or set of Record IDs or enter a " \
                    f"single or set of Order Keys separated by a pipe. " \
                    f"Include the Collection Id at the beginning of the set." \
                    f" (Ex: {self.eod.var_colour}" \
                    f"RCMImageProducts:7625368|25654750" \
                    f"{self.eod.reset_colour} or {self.eod.var_colour}" \
                    f"RCMImageProducts:RCM2_OK1373330_PK1530425_1_16M12_" \
                    f"20210326_111202_HH_HV_GRD|RCM2_OK1373330_PK1524695_1_" \
                    f"16M17_20210321_225956_HH_HV_GRD{self.eod.reset_colour})\n"
                ids = self.get_input(msg, required=False)

                process = self.eod.validate_st_images(ids)

                if not process:
                    err_msg = "Invalid entry for the Record Ids or Order Keys."
                    # self.eod.print_support(True, err_msg)
                    self.eod.print_msg(err_msg, heading='error')
                    self.logger.error(err_msg)
                    self.eod.exit_cli(1)

        return ids

    def ask_st(self):
        """
        Ask user for all SAR Toolbox information
        """

        def ask_param(param):

            default = param.get_default(as_listidx=True, include_label=True)
            # print(f"default: {default}")
            if param.const_vals:
                default_val = param.get_default(as_listidx=True)
                default_str = param.get_default(as_listidx=True,
                                                include_label=True)
                labels = [c.get('label') for c in param.const_vals 
                          if c.get('active')]
                multiple = param.multiple
                choice = ask_item(param.label, labels, 'param', 
                                        multiple=multiple,
                                        default=default_val,
                                        def_msg=default_str)
            else:
                msg = f'Enter the "{param.get_label()}"'
                choice = self.get_input(msg, required=False,
                                        default=default)
            
            # print(f"choice: {choice}")
            
            val_check = param.set_value(choice)

            if not val_check:
                err_msg = f"An invalid value has been entered. The value has " \
                            f"to be of type '{param.get_data_type()}'"
                self.eod.print_msg(err_msg, heading='error')
                self.logger.error(err_msg)
                self.eod.exit_cli(1)

            if param.const_vals:
                # print(f"param.const_vals: {param.const_vals}")
                # print(f"labels: {labels}")
                # print(f"choice_idx: {choice}")
                choice = [labels[int(idx) - 1] for idx in choice]

            # print(f"choice: {choice}")

            # if (param.data_type == bool and choice) or ():
            if param.get_value():
                sub_params = param.get_sub_param()
                # print(f"param.get_value(): {param.get_value()}")
                if param.data_type == 'bool' and param.get_value() == 'False':
                    return None
                if sub_params:
                    for s_param in sub_params:
                        # print(f"s_param: {type(s_param)}")
                        if param.param_id == 'OutputPixSpacing':
                            param_val = param.get_value(True)
                            if param_val.lower() == 'meters' \
                                    and s_param.param_id == 'OutputPixSpacingMeters':
                                ask_param(s_param)
                            elif param_val.lower() == 'degrees' \
                                    and s_param.param_id == 'OutputPixSpacingDegrees':
                                ask_param(s_param)
                        else:
                            ask_param(s_param)

        def ask_item(item_name, item_list, item_type='runner', multiple=False,
                     required=False, default=None, def_msg=None):
            choice_strs = []
            for idx, v in enumerate(item_list):
                choice_strs.append(self.wrap_text(
                                    f"{self.eod.var_colour}{idx + 1}" \
                                    f"{self.eod.reset_colour}: {v}", 
                                    sub_indent='     '))
            choices = '\n'.join(choice_strs)

            info_str = ""
            if multiple:
                info_str = " (separate each number with a comma)"

            # default_str = ""
            # if default:
            #     default_str = f" {self.eod.def_colour}[{default}]" \
            #                     f"{self.eod.reset_colour}"

            if item_type == 'runner':
                msg = f'Which "{item_name}" would you like to run?'
            elif item_type == 'product':
                msg = f"Select the Output Layer options"
            else:
                msg = f'Available "{item_name}" options'
            print(f'\n{msg}:\n\n{choices}')

            if item_type == 'product':
                msg = f'Please choose the Output Layer options{info_str}'
            else:
                msg = f'Please choose the "{item_name}"{info_str}'
            choice = self.get_input(msg, required=required, default=default,
                                    def_msg=def_msg)

            if not multiple and required:
                if not choice.isdigit():
                    err_msg = "An invalid value has been entered."
                    # self.eod.print_support(True, err_msg)
                    self.eod.print_msg(err_msg, heading='error')
                    self.logger.error(err_msg)
                    self.eod.exit_cli(1)
            else:
                if choice:
                    choice = str(choice).split(',')

                    for c in choice:
                        if not c.isdigit() or int(c) > len(item_list) \
                                or int(c) <= 0:
                            err_msg = "An invalid value has been entered."
                            self.eod.print_msg(err_msg, heading='error')
                            self.logger.error(err_msg)
                            self.eod.exit_cli(1)

            return choice

        self.print_header("Enter SAR Toolbox Information")

        st = sar.SARToolbox(self.eod)
        
        ###############################
        # Set the category
        ###############################

        # Ask for polarization to start
        param = st.get_polarization_param()
        def_msg = param.get_default(as_listidx=True, include_label=True)
        default = param.get_default(as_listidx=True)
        labels = [c.get('label') for c in param.const_vals]
        # print(f"labels: {labels}")
        multiple = param.multiple
        choice_idx = ask_item(param.label, labels, 'param', 
                                default=default, 
                                multiple=multiple,
                                def_msg=def_msg)
        polarization = [labels[int(idx) - 1] for idx in choice_idx]
        param.set_value(polarization)

        cat_names = st.get_cat_names(True)
        cat_indices = ask_item("Categories", cat_names, multiple=True, 
                               required=True)
        categories = st.set_category_runs(cat_indices)

        for category in categories:
            self.print_sub_header(f'Enter Methods for "{category.name}"')

            ###############################
            # Set the method
            ###############################

            methods = category.get_method_names(True)
            method_indices = ask_item("Methods", methods, multiple=True, 
                                      required=True)
            methods = category.set_method_runs(method_indices)

            for method in methods:

                self.print_sub_header(f'Enter Arguments for '
                                      f'"{category.name} - {method.name}"')

                ###############################
                # Ask for arguments
                ###############################
                params = method.get_parameters()
                for param in params:
                    ask_param(param)
                    method.add_param_run(param)

                ###############################
                # Ask for products
                ###############################

                products = method.get_products()

                if products:
                    labels = [p.name for p in products]
                    choice_idx = ask_item(param.label, labels, 'product', True)
                    if choice_idx:
                        choices = [products[int(c) - 1] for c in choice_idx]
                        method.set_prod_runs(choices)

                method.print_info()

        msg = "If you'd like to save the SAR Toolbox JSON request, " \
                "enter the file path"
        save_st = self.get_input(msg, required=False)
        st.set_output_fn(save_st)

        return st

    def build_syntax(self):
        """
        Builds the command-line syntax to print to the command prompt.
        
        :return: A string containing the command-line syntax for the script.
        :rtype: str
        """

        click_ctx = click.get_current_context(silent=True)

        flags = {}
        if click_ctx is None:
            return ''

        cmd_params = click_ctx.to_info_dict()['command']['params']
        for p in cmd_params:
            flags[p['name']] = p['opts']

        syntax_params = []
        for p, pv in self.params.items():
            if pv is None or pv == '':
                continue
            if p == 'session':
                continue
            if p == 'eodms_rapi':
                continue

            flag = flags[p][1]

            if isinstance(pv, list):
                if flag == '-d':
                    pv = '-'.join(['"%s"' % i if i.find(' ') > -1 else i
                                   for i in pv])
                else:
                    pv = ','.join(['"%s"' % i if i.find(' ') > -1 else i
                                   for i in pv])

            elif isinstance(pv, dict):

                if flag == '-f':
                    filt_lst = []
                    for k, v_lst in pv.items():
                        for v in v_lst:
                            if v is None or v == '':
                                continue
                            v = v.replace('"', '').replace("'", '')
                            filt_lst.append(f"{k}.{v}")
                    if len(filt_lst) == 0:
                        continue
                    pv = '"%s"' % ','.join(filt_lst)

            elif isinstance(pv, bool):
                if not pv:
                    continue
                else:
                    pv = ''
            else:
                if isinstance(pv, str) and pv.find(' ') > -1:
                    pv = f'"{pv}"'
                elif isinstance(pv, str) and pv.find('|') > -1:
                    pv = f'"{pv}"'

            syntax_params.append(f'{flag} {pv}')

        out_syntax = "python %s %s -s" % (os.path.realpath(__file__),
                                          ' '.join(syntax_params))

        return out_syntax

    def get_input(self, msg, err_msg=None, required=True, options=None,
                  default=None, def_msg=None, password=False):
        """
        Gets an input from the user for an argument.
        
        :param msg: The message used to prompt the user.
        :type  msg: str
        :param err_msg: The message to print when the user enters an invalid
                input.
        :type  err_msg: str
        :param required: Determines if the argument is required.
        :type  required: boolean
        :param options: A list of available options for the user to choose from.
        :type  options: list[str]
        :param default: The default value if the user just hits enter.
        :type  default: str
        :param def_msg: If the default is None or an empty string, this 
                        variable will tell the user what happens with no answer.
        :type  def_msg: str
        :param password: Determines if the argument is for password entry.
        :type  password: boolean
        
        :return: The value entered by the user.
        :rtype: str
        """

        if password:
            # If the argument is for password entry, hide entry
            print(f"{msg}:")
            in_val = getpass.getpass(prompt=f'{self.add_arrow()} ')
        else:
            opt_str = ''
            if options is not None:
                opt_join = '/'.join(options)
                opt_str = f" ({self.eod.var_colour}{opt_join}" \
                        f"{self.eod.reset_colour})"

            def_str = ''
            if default is not None:
                def_str = f" {self.eod.def_colour}[{default}]" \
                    f"{self.eod.reset_colour}"
            
            if def_msg is not None:
                def_str = f" {self.eod.def_colour}[{def_msg}]" \
                    f"{self.eod.reset_colour}"

            # output = f"\n{self.add_arrow()} {msg}{opt_str}{def_str}: "
            output = f"\n{msg}{opt_str}{def_str}: "
            if msg.endswith('\n'):
                msg_strp = msg.strip('\n')
                # output = f"\n{self.add_arrow()} {msg_strp}{opt_str}{def_str}:\n"
                output = f"\n{msg_strp}{opt_str}{def_str}:\n"
            try:
                # output = self.wrap_text(output)
                print(self.wrap_text(output))
                in_val = input(f"\n{self.add_arrow()} ")
            except EOFError as error:
                # Output expected EOFErrors.
                self.logger.error(error)
                eod_util.EodmsProcess().exit_cli(1)

        if required and in_val == '':
            # eod_util.EodmsProcess().print_support(True, err_msg)
            if err_msg is None:
                err_msg = "Parameter is required."
            eod_util.EodmsProcess().print_msg(err_msg, heading='error')
            self.logger.error(err_msg)
            eod_util.EodmsProcess().exit_cli(1)

        if in_val == '' and default is not None and not default == '':
            in_val = default

        if self.testing:
            print(f"FOR TESTING - Value entered: {in_val}")

        return in_val
    
    def add_arrow(self):
        """
        Adds an arrow (->>) to the output

        :return: A string containing a coloured arrow.
        :rtype: str
        """
        arrow = f"{self.eod.arrow_colour}->>{self.eod.reset_colour}"

        return arrow
    
    def wrap_text(self, in_str, width=105, sub_indent='  ', init_indent=''):
        """
        Wraps a given text to a certain width.

        :param in_str: The input string to wrap.
        :type  in_str: str
        :param width: The width of the text.
        :type  width: int

        :return: The input string now wrapped.
        :rtype: str
        """

        out_str = textwrap.fill(in_str, width=width, 
                                replace_whitespace=False, 
                                initial_indent=init_indent,
                                subsequent_indent=sub_indent)
        return out_str
    
    def print_header(self, header):
        """
        Prints the header for input
        """

        print(f"{self.eod.head_colour}\n--------------{header}--------------" \
              f"{self.eod.reset_colour}")

    def print_sub_header(self, header):
        """
        Prints the header for input
        """

        print(f"{self.eod.head_colour}\n=== {header} ===" \
              f"{self.eod.reset_colour}")

    def print_syntax(self):
        """
        Prints the command-line syntax for the script.
        """

        print("\nUse this command-line syntax to run the same parameters:")
        self.cli_syntax = self.build_syntax()
        print(f"{self.eod.path_colour}{self.cli_syntax}{self.eod.reset_colour}")
        self.logger.info(f"Command-line Syntax: {self.cli_syntax}")

    def prompt(self):
        """
        Prompts the user for the input options.
        """

        username = self.params.get('username')
        password = self.params.get('password')
        input_val = self.params.get('input_val')
        collections = self.params.get('collections')
        process = self.params.get('process')
        filters = self.params.get('filters')
        dates = self.params.get('dates')
        maximum = self.params.get('maximum')
        priority = self.params.get('priority')
        output = self.params.get('output')
        # csv_fields = self.params.get('csv_fields')
        aws = self.params.get('aws')
        overlap = self.params.get('overlap')
        orderitems = self.params.get('orderitems')
        no_order = self.params.get('no_order')
        downloads = self.params.get('downloads')
        st_request = self.params.get('st_request')
        silent = self.params.get('silent')
        version = self.params.get('version')

        if version:
            print(f"{__title__}: Version {__version__}")
            self.eod.exit_cli()

        self.eod.set_silence(silent)

        new_user = False
        new_pass = False

        if username is None or password is None:
            self.print_header("Enter EODMS Credentials")

        if username is None or username == '':

            username = self.config_util.get('Credentials', 'username')

            # print(f"username: {username}")

            if username == '':
                msg = "Enter the username for authentication"
                err_msg = "A username is required to order images."
                username = self.get_input(msg, err_msg)
                new_user = True
            else:
                print(f"\nUsing the username set in the " 
                      f"'{self.eod.path_colour}"
                      f"{self.config_util.get_filename()}" 
                      f"{self.eod.reset_colour}' file...")

        if password is None or password == '':

            password = self.config_util.get('Credentials', 'password')

            if password == '':
                msg = 'Enter the password for authentication'
                err_msg = "A password is required to order images."
                password = self.get_input(msg, err_msg, password=True)
                new_pass = True
            else:
                try:
                    password = base64.b64decode(password).decode("utf-8")
                except binascii.Error as err:
                    password = base64.b64decode(password +
                                                "========").decode("utf-8")
                print(f"Using the password set in the " 
                      f"'{self.eod.path_colour}"
                      f"{self.config_util.get_filename()}" 
                      f"{self.eod.reset_colour}' file...\n")

        if new_user or new_pass:
            suggestion = ''
            if self.eod.silent:
                suggestion = " (it is best to store the credentials if " \
                             "you'd like to run the script in silent mode)"
            # print(f"\nWould you like to store the credentials for a future " \
            #     f"session{suggestion}? (y/n):")
            msg = f"Would you like to store the credentials for a future " \
                f"session{suggestion}? (y/n)"
            # answer = input(f"\n{self.add_arrow()} Would you like to store the credentials "
            #                f"for a future session{suggestion}? (y/n):")
            # answer = input(f"{self.add_arrow} ")
            answer = self.get_input(msg, required=False, default='n')
            if answer.lower().find('y') > -1:
                # self.config_info.set('Credentials', 'username', username)
                self.config_util.set('Credentials', 'username', username)
                pass_enc = base64.b64encode(password.encode("utf-8")).decode(
                    "utf-8")
                # self.config_info.set('Credentials', 'password', str(pass_enc))
                self.config_util.set('Credentials', 'password', str(pass_enc))

                self.config_util.write()

        # Set the RAPI URL from the config file (only for development of
        #   EODMS-CLI)
        rapi_url = self.config_util.get('Debug', 'rapi_url')
        # print(f"rapi_url: {rapi_url}")
        if rapi_url:
            if rapi_url.find('staging'):
                print("\n**** RUNNING IN STAGING ENVIRONMENT ****\n")
            self.eod.rapi_domain = rapi_url

        # Get number of attempts when querying the RAPI
        self.eod.set_attempts(self.config_util.get('RAPI', 'access_attempts'))

        self.eod.create_session(username, password)

        self.params = {'collections': collections,
                       'dates': dates,
                       'input_val': input_val,
                       'maximum': maximum,
                       'process': process,
                       'downloads': downloads}

        # colour = self.eod.get_colour(fore='GREEN')
        print()
        coll_dict = self.eod.eodms_rapi.get_collections(True, opt='both')

        # print(f"dir(coll_lst): {dir(coll_lst)}")
        # print(f"coll_lst.__class__: {coll_lst.__class__}")
        # print(f"coll_lst type: {type(coll_lst).__name__}")
        # print(f"{'get_msgs' in dir(coll_lst)}")

        self.eod.check_error(coll_dict)

        print("\n(For more information on the following prompts, please refer"
              " to the README file.)")

        #########################################
        # Get the type of process
        #########################################

        if process is None or process == '':
            self.process = self.ask_process()
        else:
            self.process = process

        if self.process == 'search_only':
            msg = "The 'search_only' process is no longer available. " \
                  "In future, please use the flags '--no_order' or '-nord' " \
                  "to suppress ordering and downloading. Script will " \
                  "perform a search without ordering or downloading."
            self.eod.print_msg(msg, heading='note')
            self.logger.warning(msg)
            self.process = 'full'
            no_order = True

        proc_num = list(proc_choices.keys()).index(self.process) + 1
        print(self.eod.title_colour)
        print("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
        print(f" Running Process "
              f"{proc_num}: "
              f"{proc_choices[self.process]['name']}")
        print("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%")
        print(self.eod.reset_colour)

        self.params['process'] = self.process

        if self.process == 'download_only':
            self.eod.print_msg("The process 'download_only' is now named "
                  "'download_results'. Please update any command-line "
                  "syntaxes.", heading='note')
            self.process = 'download_results'

        if self.process == 'full':

            self.logger.info("Searching, ordering and downloading images "
                             "using an AOI.")

            # Get the collection(s)
            coll = self.ask_collection(collections, coll_lst=coll_dict)
            self.params['collections'] = coll

            # If Radarsat-1, ask user if they want to download from AWS
            if 'Radarsat1' in coll:
                aws = self.ask_aws(aws)
                self.params['aws'] = aws

            # Get the AOI file
            inputs = self.ask_aoi(input_val)
            self.params['input_val'] = inputs

            # If an AOI is specified, ask for a minimum overlap percentage
            if inputs is not None:
                overlap = self.ask_overlap(overlap)
                self.params['overlap'] = overlap

            # Get the filter(s)
            filt_dict = self.ask_filter(filters)
            # print(f"filt_dict: {filt_dict}")
            self.params['filters'] = filt_dict

            # Get the date(s)
            dates = self.ask_dates(dates)
            self.params['dates'] = dates

            # Get the output geospatial filename
            output = self.ask_output(output)
            self.params['output'] = output

            # Ask user if they'd like to order and download
            no_order = self.ask_order(no_order)
            self.params['no_order'] = no_order

            # Get the maximum(s)
            maximum = self.ask_maximum(maximum)
            self.params['maximum'] = maximum

            if not no_order:
                # Get the priority
                priority = self.ask_priority(priority)
                self.params['priority'] = priority

            # Print command-line syntax for future processes
            self.print_syntax()

            self.eod.search_order_download(self.params)

        elif self.process == 'order_csv':

            self.logger.info("Ordering and downloading images using results "
                             "from a CSV file.")

            #########################################
            # Get the CSV file
            #########################################

            msg = "Enter the full path of the CSV file exported " \
                  "from the EODMS UI website"
            inputs = self.ask_input_file(input_val, msg)
            self.params['input_val'] = inputs

            # fields = self.eod.get_input_fields(inputs)
            # csv_fields = self.ask_fields(csv_fields, fields)
            # self.params['csv_fields'] = csv_fields

            # If Radarsat-1, ask user if they want to download from AWS
            if os.path.exists(inputs):
                lines = open(inputs, 'r').read()
                if lines.lower().find('radarsat-1') > -1:
                    aws = self.ask_aws(aws)
                    self.params['aws'] = aws

            # Get the output geospatial filename
            output = self.ask_output(output)
            self.params['output'] = output

            # Ask user if they'd like to order and download
            no_order = self.ask_order(no_order)
            self.params['no_order'] = no_order

            # Get the maximum(s)
            maximum = self.ask_maximum(maximum)
            self.params['maximum'] = maximum

            if not no_order:
                # Get the priority
                priority = self.ask_priority(priority)
                self.params['priority'] = priority

            # Print command-line syntax for future processes
            self.print_syntax()

            # Run the order_csv process
            self.eod.order_csv(self.params)

        # elif self.process == 'download_aoi' or self.process == 'search_only':
        #
        #     if self.process == 'download_aoi':
        #         self.logger.info("Downloading existing orders using an AOI.")
        #     else:
        #         self.logger.info("Searching for images using an AOI.")
        #
        #     # Get the collection(s)
        #     coll = self.ask_collection(collections)
        #     self.params['collections'] = coll
        #
        #     # Get the AOI file
        #     inputs = self.ask_aoi(input_val)
        #     self.params['input_val'] = inputs
        #
        #     # If an AOI is specified, ask for a minimum overlap percentage
        #     if inputs is not None:
        #         overlap = self.ask_overlap(overlap)
        #         self.params['overlap'] = overlap
        #
        #     # Get the filter(s)
        #     filt_dict = self.ask_filter(filters)
        #     self.params['filters'] = filt_dict
        #
        #     # Get the date(s)
        #     dates = self.ask_dates(dates)
        #     self.params['dates'] = dates
        #
        #     # Get the output geospatial filename
        #     output = self.ask_output(output)
        #     self.params['output'] = output
        #
        #     # Print command-line syntax for future processes
        #     self.print_syntax()
        #
        #     if self.process == 'download_aoi':
        #         self.eod.download_aoi(self.params)
        #     else:
        #         self.eod.search_only(self.params)

        elif self.process == 'download_results':
            # Download existing orders using CSV file from previous session

            self.logger.info("Downloading images using results from a CSV "
                             "file from a previous session.")

            # Get the CSV file
            msg = "Enter the full path of the CSV Results file from a " \
                  "previous session"
            inputs = self.ask_input_file(input_val, msg)
            self.params['input_val'] = inputs

            # Get the output geospatial filename
            output = self.ask_output(output)
            self.params['output'] = output

            # Print command-line syntax for future processes
            self.print_syntax()

            # Run the download_only process
            self.eod.download_results(self.params)

        elif self.process == 'download_available':
            self.logger.info("Downloading existing order items with status"
                             "AVAILABLE_FOR_DOWNLOAD.")

            orderitems = self.ask_orderitems(orderitems)
            self.params['orderitems'] = orderitems

            if orderitems is None or orderitems == '':
                # Get the maximum(s)
                maximum = self.ask_maximum(maximum, 'download')
                self.params['maximum'] = maximum

            # Get the output geospatial filename
            output = self.ask_output(output)
            self.params['output'] = output

            # Print command-line syntax for future processes
            self.print_syntax()

            # Run the download_available process
            self.eod.download_available(self.params)


        elif self.process == 'record_id':
            # Order and download a single or set of images using Record IDs

            self.logger.info("Ordering and downloading images using "
                             "Record IDs")

            inputs = self.ask_record_ids(input_val)
            self.params['input_val'] = inputs

            # If Radarsat-1, ask user if they want to download from AWS
            if 'Radarsat1' in inputs:
                aws = self.ask_aws(aws)
                self.params['aws'] = aws

            # Get the output geospatial filename
            output = self.ask_output(output)
            self.params['output'] = output

            # Ask user if they'd like to order and download
            no_order = self.ask_order(no_order)
            self.params['no_order'] = no_order

            if not no_order:
                # Get the priority
                priority = self.ask_priority(priority)
                self.params['priority'] = priority

            # Print command-line syntax for future processes
            self.print_syntax()

            # Run the order_csv process
            self.eod.order_ids(self.params)

        elif self.process == 'order_st':
            self.logger.info("Ordering an image from the SAR Toolbox")

            # print(f"self.params: {self.params}")

            # st_request = self.params.get('st_request')
            # print(f"st_request: {st_request}")
            if st_request:
                sar_tb = sar.SARToolbox(self.eod, out_fn=st_request)
                sar_tb.ingest_request()
            else:
                inputs = self.ask_st_images(input_val)

                coll_id, ids = inputs.split(':')
                # If Order Keys are entered, check if they exist
                if inputs.find("_") > -1:
                    ord_keys = ids.split('|')
                    rec_ids = self.eod.get_record_ids(coll_id, ord_keys)

                    if len(rec_ids) == 0:
                        err_msg = f"No images could be found with Order Keys: "\
                                f"{', '.join(ord_keys)}."
                        self.eod.logger.error(err_msg)
                        # self.print_support(err_msg)
                        self.eod.print_msg(err_msg, heading='error')
                        self.eod.exit_cli(1)
                else:
                    rec_ids = ids.split('|')

                print(f"\nSubmitting images with Record Ids: " \
                      f"{', '.join(rec_ids)}")

                self.params['input_val'] = {"collection_id": coll_id, 
                                            "record_ids": rec_ids}

                # sar_tb = self.ask_st(self.params['input_val'])
                sar_tb = self.ask_st()

            self.params['st_request'] = sar_tb.out_fn

            # Get the priority
            priority = self.ask_priority(priority)
            self.params['priority'] = priority

            # Print command-line syntax for future processes
            self.print_syntax()

            # Run the order_csv process
            self.eod.order_st(sar_tb, self.params)

        else:
            # self.eod.print_support("That is not a valid process type.")
            self.eod.print_msg("That is not a valid process type.", 
                               heading='error')
            self.logger.error("An invalid parameter was entered during "
                              "the prompt.")
            self.eod.exit_cli(1)

#------------------------------------------------------------------------------

output_help = '''The output file path containing the results in a
                             geospatial format.
 The output parameter can be:
 - None (empty): No output will be created (a results CSV file will still be
     created in the 'results' folder)
 - GeoJSON: The output will be in the GeoJSON format
     (use extension .geojson or .json)
 - KML: The output will be in KML format (use extension .kml) (requires GDAL 
        Python package)
 - GML: The output will be in GML format (use extension .gml) (requires GDAL 
        Python package)
 - Shapefile: The output will be ESRI Shapefile (requires GDAL Python package)
     (use extension .shp)'''

abs_path = os.path.abspath(__file__)

def get_configuration_values(config_util, download_path):

    config_params = {}

    # Set the various paths
    if download_path is None or download_path == '':
        # download_path = config_info.get('Script', 'downloads')
        download_path = config_util.get('Paths', 'downloads')

        if download_path == '':
            download_path = os.path.join(os.path.dirname(abs_path),
                                         'downloads')
        elif not os.path.isabs(download_path):
            download_path = os.path.join(os.path.dirname(abs_path),
                                         download_path)
    config_params['download_path'] = download_path

    res_path = config_util.get('Paths', 'results')
    if res_path == '':
        res_path = os.path.join(os.path.dirname(abs_path), 'results')
    elif not os.path.isabs(res_path):
        res_path = os.path.join(os.path.dirname(abs_path),
                                res_path)
    config_params['res_path'] = res_path

    log_path = config_util.get('Paths', 'log')
    if log_path == '':
        log_path = os.path.join(os.path.dirname(abs_path), 'log',
                               'logger.log')
    elif not os.path.isabs(log_path):
        log_path = os.path.join(os.path.dirname(abs_path),
                               log_path)
    config_params['log_path'] = log_path

    # Set the timeout values
    timeout_query = config_util.get('RAPI', 'timeout_query')
    # timeout_order = config_info.get('Script', 'timeout_order')
    timeout_order = config_util.get('RAPI', 'timeout_order')

    try:
        timeout_query = float(timeout_query)
    except ValueError:
        timeout_query = 60.0

    try:
        timeout_order = float(timeout_order)
    except ValueError:
        timeout_order = 180.0
    config_params['timeout_query'] = timeout_query
    config_params['timeout_order'] = timeout_order

    config_params['keep_results'] = config_util.get('Script', 'keep_results')
    config_params['keep_downloads'] = config_util.get('Script',
                                                      'keep_downloads')
    config_params['colourize'] = config_util.get('Script', 'colourize')

    # Get the total number of results per query
    config_params['max_results'] = config_util.get('RAPI', 'max_results')

    # Get the minimum date value to check orders
    config_params['order_check_date'] = config_util.get('RAPI',
                                                        'order_check_date')

    config_params['download_attempts'] = config_util.get('RAPI',
                                                        'download_attempts')

    # Get URL for debug purposes
    config_params['rapi_url'] = config_util.get('Debug', 'root_url')

    return config_params

def print_support(err_str=None):
    """
    Prints the 2 different support message depending if an error occurred.
    
    :param err_str: The error string to print along with support.
    :type  err_str: str
    """

    # eod_util.EodmsProcess().print_support(True, err_str)
    eod_util.EodmsProcess().print_msg(err_str, heading='error')

def get_latest_version():
    package = 'py-eodms-rapi'  # replace with the package you want to check
    response = requests.get(f'https://pypi.org/pypi/{package}/json')
    latest_version = response.json()['info']['version']

    return latest_version

eodmsrapi_recent = get_latest_version()

@click.command(context_settings={'help_option_names': ['-h', '--help']})
@click.option('--configure', default=None,
              help='Runs the configuration setup allowing the user to enter '
                   'configuration values.')
@click.option('--username', '-u', default=None,
              help='The username of the EODMS account used for '
                   'authentication.')
@click.option('--password', '-p', default=None,
              help='The password of the EODMS account used for '
                   'authentication.')
@click.option('--process', '-prc', '-r', default=None,
              help='The type of process to run from this list of '
                   'options:\n- %s'
                   % '\n- '.join(["%s: %s" % (k, v)
                                  for k, v in proc_choices.items()]))
@click.option('--input_val', '-i', default=None,
              help='An input file (can either be an AOI, a CSV file '
                   'exported from the EODMS UI), a WKT feature or a set '
                   'of Record IDs. Valid AOI formats are GeoJSON, KML or '
                   'Shapefile (Shapefile requires the GDAL Python '
                   'package).')
@click.option('--collections', '-c', default=None,
              help='The collection of the images being ordered (separate '
                   'multiple collections with a comma).')
@click.option('--filters', '-f', default=None,
              help='A list of filters for a specific collection.')
@click.option('--dates', '-d', default=None,
              help='The date ranges for the search.')
@click.option('--maximum', '-max', '-m', default=None,
              help='For Process 1 & 2, the maximum number of images to order '
                   'and download and the maximum number of images per order, '
                   'separated by a colon. If no_order is set to True, this '
                   'parameter will set the maximum images for which to search. '
                   'For Process 4, a single value to specify the maximum '
                   'number of images with status AVAILABLE_FOR_DOWNLOAD '
                   'to download.')
@click.option('--priority', '-pri', '-l', default=None,
              help='The priority level of the order.\nOne of "Low", '
                   '"Medium", "High" or "Urgent" (default "Medium").')
@click.option('--output', '-o', default=None, help=output_help)
# @click.option('--csv_fields', '-cf', default=None,
#               help='The fields in the input CSV file used to get images.')
@click.option('--aws', '-a', is_flag=True, default=None,
              help='Determines whether to download from AWS (only applies '
                   'to Radarsat-1 imagery).')
@click.option('--overlap', '-ov', default=None,
              help='The minimum percentage of overlap between AOI and images '
                   '(if no AOI specified, this parameter is ignored).')
@click.option('--orderitems', '-oid', default=None,
              help="For Process 4, a set of Order IDs and/or Order Item IDs. "
                   "This example specifies Order IDs and Order Item IDs: "
                   "'order:151873,151872|item:1706113,1706111'")
@click.option('--no_order', '-nord', is_flag=True, default=None,
              help='If set, no ordering and downloading will occur.')
@click.option('--downloads', '-dn', default=None,
              help='The path where the images will be downloaded. Overrides '
                   'the downloads parameter in the configuration file.')
@click.option('--st_request', '-st', default=None,
              help='The path of a file containing the JSON request for a ' 
              'SAR Toolbox order.')
@click.option('--silent', '-s', is_flag=True, default=None,
              help='Sets process to silent which suppresses all questions.')
@click.option('--version', '-v', is_flag=True, default=None,
              help='Prints the version of the script.')
def cli(username, password, input_val, collections, process, filters, dates,
        maximum, priority, output, aws, overlap, orderitems, no_order,
        downloads, st_request, silent, version, configure):
    """
    Search & Order EODMS products.
    """

    os.system("title " + __title__)
    sys.stdout.write("\x1b]2;%s\x07" % __title__)

    python_version_cur = ".".join([str(sys.version_info.major),
                                   str(sys.version_info.minor),
                                   str(sys.version_info.micro)])
    # if StrictVersion(python_version_cur) < StrictVersion('3.6'):
    if pack_v.Version(python_version_cur) < pack_v.Version('3.6'):
        raise Exception("Must be using Python 3.6 or higher")

    if '-v' in sys.argv or '--v' in sys.argv or '--version' in sys.argv:
        print(f"\n  {__title__}, version {__version__}\n")
        eod_util.EodmsProcess().exit_cli()

    conf_util = config_util.ConfigUtils(eod_util.EodmsProcess())

    if configure:
        conf_util.ask_user(configure)
        # print("You've entered configuration mode.")
        eod_util.EodmsProcess().exit_cli()
        
    # Set all the parameters from the config.ini file
    # config_info = get_config()
    conf_util.import_config()

    config_params = get_configuration_values(conf_util, downloads)
    download_path = os.path.abspath(config_params['download_path'])
    res_path = config_params['res_path']
    log_path = config_params['log_path']
    timeout_query = config_params['timeout_query']
    timeout_order = config_params['timeout_order']
    keep_results = config_params['keep_results']
    keep_downloads = config_params['keep_downloads']
    colourize = config_params['colourize']
    max_results = config_params['max_results']
    order_check_date = config_params['order_check_date']
    download_attempts = config_params['download_attempts']
    rapi_url = config_params['rapi_url']

    print(eod_util.EodmsProcess(colourize=colourize).title_colour)
    print("##########################################################"
          "#######################")
    print(f"#                              {__title__} v{__version__}         "
          f"                        #")
    print("############################################################"
          "#####################")
    print(eod_util.EodmsProcess(colourize=colourize).reset_colour)

    rapi_installed_ver = eodms_rapi.__version__

    path_colour = eod_util.EodmsProcess(colourize=colourize).path_colour
    warn_colour = eod_util.EodmsProcess(colourize=colourize).warn_colour
    if pack_v.Version(rapi_installed_ver) < pack_v.Version(min_rapi_version):
        err_msg = f"The py-eodms-rapi currently installed is an older " \
                    f"version (v{rapi_installed_ver}) than the minimum " \
                    f"required version (v{min_rapi_version}). Please " \
                    f"install it using: '{path_colour}pip install " \
                    f"py-eodms-rapi -U{warn_colour}'."
        # eod_util.EodmsProcess().print_support(True, err_msg)
        eod_util.EodmsProcess().print_msg(err_msg, heading='error')
        eod_util.EodmsProcess().exit_cli(1)

    elif pack_v.Version(rapi_installed_ver) < \
            pack_v.Version(eodmsrapi_recent):
        msg = ""
        msg = f"The py-eodms-rapi currently installed " \
                f"(v{rapi_installed_ver}) is not the latest "\
                f"version (v{eodmsrapi_recent}). It is recommended to use "\
                f"the latest version of the package. Please install it " \
                f"using: '{path_colour}pip install py-eodms-rapi -U" \
                f"{warn_colour}'."
        eod_util.EodmsProcess().print_msg(msg, heading="warning")
        # logger.warning(msg)


    # Create info folder, if it doesn't exist, to store CSV files
    start_time = datetime.datetime.now()
    start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")

    eod = None
    logger = None

    try:

        params = {'username': username,
                  'password': password,
                  'input_val': input_val,
                  'collections': collections,
                  'process': process,
                  'filters': filters,
                  'dates': dates,
                  'maximum': maximum,
                  'priority': priority,
                  'output': output,
                  # 'csv_fields': csv_fields,
                  'aws': aws,
                  'overlap': overlap,
                  'orderitems': orderitems,
                  'no_order': no_order,
                  'downloads': downloads,
                  'st_request': st_request,
                  'silent': silent,
                  'version': version}

        # color = eod_util.EodmsProcess().get_colour('BLACK', style_col='BRIGHT')
        fn_col = eod_util.EodmsProcess(colourize=colourize).path_colour
        reset = eod_util.EodmsProcess(colourize=colourize).reset_colour
        print(f"\nImages will be downloaded to " \
            f"'{fn_col}{download_path}{reset}'.")

        if not os.path.exists(os.path.dirname(log_path)):
            pathlib.Path(os.path.dirname(log_path)).mkdir(
                parents=True, exist_ok=True)
            
        # Setup logging
        logger = logging.getLogger('EODMSRAPI')

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - '
                                        '%(message)s',
                                        datefmt='%Y-%m-%d %I:%M:%S %p')
        log_handler = handlers.RotatingFileHandler(log_path,
                                                    maxBytes=500000,
                                                    backupCount=2)
        log_handler.setLevel(logging.DEBUG)
        log_handler.setFormatter(formatter)
        logger.addHandler(log_handler)

        logger.info(f"Script start time: {start_str}")

        eod = eod_util.EodmsProcess(version=__version__, 
                                    download=download_path,
                                    results=res_path, log=log_path,
                                    timeout_order=timeout_order,
                                    timeout_query=timeout_query,
                                    max_res=max_results,
                                    keep_results=keep_results,
                                    keep_downloads=keep_downloads,
                                    colourize=colourize, 
                                    order_check_date=order_check_date,
                                    download_attempts=download_attempts,
                                    rapi_url=rapi_url)

        print(f"\nCSV Results will be placed in '{fn_col}{eod.results_path}" \
                f"{reset}'.")

        eod.cleanup_folders()

        #########################################
        # Get authentication if not specified
        #########################################

        prmpt = Prompter(eod, conf_util, params, click)

        prmpt.prompt()

        eod.eodms_rapi.close_session()

        print("\nProcess complete.")

        eod.print_support()

        eod.exit_cli()

    except KeyboardInterrupt:
        msg = "Process ended by user."
        print(f"\n{msg}")

        logger.info(msg)

        if 'eod' in vars() or 'eod' in globals():
            eod.export_results()
            eod.exit_cli(1)
        else:
            eod_util.EodmsProcess().exit_cli(1)
    except Exception:
        trc_back = f"\n{traceback.format_exc()}"
        # print(f"trc_back: {trc_back}")
        logger.error(traceback.format_exc())
        if 'eod' in vars() or 'eod' in globals():
            # eod.print_support(True, trc_back)
            eod.print_msg(trc_back, heading='error')
            eod.export_results()
            eod.exit_cli(0)
        else:
            # eod_util.EodmsProcess().print_support(True, trc_back)
            eod_util.EodmsProcess().print_msg(trc_back, heading='error')
            eod_util.EodmsProcess().exit_cli(0)

if __name__ == '__main__':
    # sys.exit(cli())
    cli()
