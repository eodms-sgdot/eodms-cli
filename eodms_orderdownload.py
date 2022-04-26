##############################################################################
# MIT License
# 
# Copyright (c) 2020-2022 Her Majesty the Queen in Right of Canada, as
# represented by the President of the Treasury Board
# 
# Permission is hereby granted, free of charge, to any person obtaining a 
# copy of this software and associated documentation files (the "Software"), 
# to deal in the Software without restriction, including without limitation 
# the rights to use, copy, modify, merge, publish, distribute, sublicense, 
# and/or sell copies of the Software, and to permit persons to whom the 
# Software is furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in 
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING 
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER 
# DEALINGS IN THE SOFTWARE.
# 
##############################################################################

__title__ = 'EODMS RAPI Orderer & Downloader'
__author__ = 'Kevin Ballantyne'
__copyright__ = 'Copyright 2020-2022 Her Majesty the Queen in Right of Canada'
__license__ = 'MIT License'
__description__ = 'Script used to search, order and download imagery from ' \
                  'the EODMS using the REST API (RAPI) service.'
__version__ = '2.5.1'
__maintainer__ = 'Kevin Ballantyne'
__email__ = 'eodms-sgdot@nrcan-rncan.gc.ca'

import sys
import os
import re
# import requests
# import argparse
import click
import traceback
import getpass
import datetime
# from geomet import wkt
# import json
import configparser
import base64
import logging
import logging.handlers as handlers
import pathlib
import unicodedata
import eodms_rapi

# from eodms_rapi import EODMSRAPI

from utils import eod as eod_util
from utils import field

# from utils import csv_util
# from utils import image
# from utils import geo

proc_choices = {'full': 'Search, order & download images using an AOI and/or '
                        'filters',
                'order_csv': 'Order & download images using EODMS UI '
                             'search results (CSV file)',
                'download_only': '''Download existing orders using a CSV file 
        from a previous order/download process (files found under "results" 
        folder)''',
                'search_only': 'Run only a search based on an AOI '
                               'and/or filters',
                'record_id': 'Order and download a single or set of '
                             'images using Record IDs'}


class Prompter:
    """
    Class used to prompt the user for all inputs.
    """

    def __init__(self, eod, config_info, params, in_click):
        """
        Initializer for the Prompter class.
        
        :param eod: The Eodms_OrderDownload object.
        :type  eod: self.Eodms_OrderDownload
        :param config_info: Configuration information taken from the config
                file.
        :type  config_info: configparser.ConfigParser
        :param params: An empty dictionary of parameters.
        :type  params: dict
        """

        self.eod = eod
        self.config_info = config_info
        self.params = params
        self.click = in_click
        self.process = None

        self.logger = logging.getLogger('eodms')

    def remove_accents(self, s):
        nkfd_form = unicodedata.normalize('NFKD', s)
        return u''.join([c for c in nkfd_form if not unicodedata.combining(c)])

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
                print(
                    "\n--------------Enter Input Geospatial File or Feature----"
                    "----------")

                msg = "Enter the full path name of a GML, KML, Shapefile or " \
                      "GeoJSON containing an AOI or a WKT feature to " \
                      "restrict the search to a specific location\n"
                err_msg = "No AOI or feature specified. Please enter a WKT " \
                          "feature or a valid GML, KML, Shapefile or GeoJSON " \
                          "file"
                input_fn = self.get_input(msg, err_msg, required=False)

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
            err_msg = "Input file %s does not exist." \
                      % os.path.abspath(input_fn)
            # self.eod.print_support(err_msg)
            self.logger.warning(err_msg)
            return None

        else:
            if not self.eod.eodms_geo.is_wkt(input_fn):
                err_msg = "Input feature is not a valid WKT."
                # self.eod.print_support(err_msg)
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
                print("\n--------------Download from AWS?--------------")

                print("\nSome Radarsat-1 images contain direct download "
                      "links to GeoTIFF files in an Open Data AWS "
                      "Repository.")

                msg = "For images that have an AWS link, would you like to " \
                      "download the GeoTIFFs from the repository instead of " \
                      "submitting an order to the EODMS?\n"
                aws = self.get_input(msg, required=False, options=['Yes', 'No'])

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
        :type  coll_lst: list
        
        :return: A list of collections entered by the user.
        :rtype: list
        """

        if coll is None:

            if coll_lst is None:
                coll_lst = self.eod.eodms_rapi.get_collections(True, opt='both')

            # print(f"coll_lst: {coll_lst}")

            if self.eod.silent:
                err_msg = "No collection specified. Exiting process."
                self.eod.print_support(err_msg)
                self.logger.error(err_msg)
                sys.exit(1)

            # print("coll_lst: %s" % coll_lst)            

            print("\n--------------Enter Collection--------------")

            # List available collections for this user
            print("\nAvailable Collections:\n")
            for idx, c in enumerate(coll_lst):
                msg = "%s. %s (%s)" % (idx + 1, c['title'], c['id'])
                if c['id'] == 'NAPL':
                    msg += ' (open data only)'
                print(msg)

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
                self.eod.print_support(err_msg)
                self.logger.error(err_msg)
                sys.exit(1)

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
                err_msg = "Collection '%s' is not valid." % c
                self.eod.print_support(err_msg)
                self.logger.error(err_msg)
                sys.exit(1)

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
                print("\n--------------Enter Date Range--------------")

                msg = "Enter a date range (ex: 20200525-20200630T200950) " \
                      "or a previous time-frame (24 hours) " \
                      "(leave blank to search all years)\n"
                dates = self.get_input(msg, required=False)

        # -------------------------------
        # Check validity of filter input
        # -------------------------------
        if dates is not None and not dates == '':
            dates = self.eod.validate_dates(dates)

            if not dates:
                err_msg = "The dates entered are invalid. "
                self.eod.print_support(err_msg)
                self.logger.error(err_msg)
                sys.exit(1)

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
            print("\n--------------Enter CSV Unique Fields--------------")

            print("\nAvailable fields in the CSV file:")
            for f in fields:
                print("  %s" % f)

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

                print("\n--------------Enter Filters--------------")

                # Ask for the filters for the given collection(s)
                for coll in self.params['collections']:
                    coll_id = self.eod.get_full_collid(coll)

                    field_mapper = field.EodFieldMapper()
                    coll_fields = field_mapper.get_fields(coll_id)

                    if coll_id in field_mapper.get_colls():
                        # field_map = self.eod.get_fieldMap()[coll_id]

                        print("\nAvailable fields for '%s':" % coll)
                        for f in coll_fields.get_eod_fieldnames():
                            print("  %s" % f)

                        print("NOTE: Filters must be entered in the format "
                              "of <field_id>=<value>|<value>|... (field "
                              "IDs are not case sensitive); separate each "
                              "filter with a comma. To see a list "
                              "of field choices, enter '? <field_id>'.")

                        msg = "Enter the filters you would like to apply " \
                              "to the search"

                        filt_items = '?'

                        while filt_items.find('?') > -1:
                            filt_items = input("\n->> %s:\n" % msg)

                            if filt_items.find('?') > -1:
                                field_val = filt_items.replace('?', '').strip()

                                field_obj = coll_fields.get_field(field_val)
                                field_title = field_obj.get_rapi_field_title()

                                if field_title is None:
                                    print("Not a valid field.")
                                    continue

                                field_choices = self.eod.eodms_rapi. \
                                    get_fieldChoices(coll_id, field_title)

                                if isinstance(field_choices, dict):
                                    field_choices = 'any %s value' % \
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
                                sys.exit(1)

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
                    if f == '':
                        continue
                    if f.find('.') > -1:
                        coll, filt_items = f.split('.')
                        filt_items = self.eod.validate_filters(filt_items,
                                                               coll)
                        if not filt_items:
                            sys.exit(1)
                        coll_id = self.eod.get_full_collid(coll)
                        if coll_id in filt_dict.keys():
                            coll_filters = filt_dict[coll_id]
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
                self.eod.print_support(err_msg)
                self.logger.error(err_msg)
                sys.exit(1)

            print("\n--------------Enter Input CSV File--------------")

            err_msg = "No CSV specified. Please enter a valid CSV file"
            input_fn = self.get_input(msg, err_msg)

        if not os.path.exists(input_fn):
            err_msg = "Not a valid CSV file. Please enter a valid CSV file."
            self.eod.print_support(err_msg)
            self.logger.error(err_msg)
            sys.exit(1)

        return input_fn

    def ask_maximum(self, maximum):
        """
        Asks the user for maximum number of order items and the number of
            items per order.
        
        :param maximum: The maximum if already set by the command-line.
        :type  maximum: str
        
        :return: The maximum number of order items and/or number of items
                per order, separated by ':'.
        :rtype: str
        """

        if maximum is None or maximum == '':

            if not self.eod.silent:
                if not self.process == 'order_csv':

                    print("\n--------------Enter Maximums--------------")

                    msg = "Enter the total number of images you'd " \
                          "like to order (leave blank for no limit)"

                    total_records = self.get_input(msg, required=False)

                    # ------------------------------------------
                    # Check validity of the total_records entry
                    # ------------------------------------------

                    if total_records == '':
                        total_records = None
                    else:
                        total_records = self.eod.validate_int(total_records)
                        if not total_records:
                            self.eod.print_msg("WARNING: Total number of "
                                               "images value not valid. "
                                               "Excluding it.", indent=False)
                            total_records = None
                        else:
                            total_records = str(total_records)
                else:
                    total_records = None

                msg = "If you'd like a limit of images per order, " \
                      "enter a value (EODMS sets a maximum limit of 100)"

                order_limit = self.get_input(msg, required=False)

                if order_limit == '':
                    order_limit = None
                else:
                    order_limit = self.eod.validate_int(order_limit, 100)
                    if not order_limit:
                        self.eod.print_msg("WARNING: Order limit value not "
                                           "valid. Excluding it.", indent=False)
                        order_limit = None
                    else:
                        order_limit = str(order_limit)

                maximum = ':'.join(filter(None, [total_records,
                                                 order_limit]))

        else:

            if self.process == 'order_csv':

                print("\n--------------Enter Images per Order--------------")

                if maximum.find(':') > -1:
                    total_records, order_limit = maximum.split(':')
                else:
                    total_records = None
                    order_limit = maximum

                maximum = ':'.join(filter(None, [total_records,
                                                 order_limit]))

        return maximum

    def ask_order(self, no_order):
        """
        Asks the user if they would like to suppress ordering and downloading.

        :param no_order:
        :return:
        """

        if no_order is None:
            if not self.eod.silent:
                print("\n--------------Suppress Ordering--------------")

                msg = "\nWould you like to only search and not order?\n"
                no_order = self.get_input(msg, required=False,
                                          options=['yes', 'no'], default='n')

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
                print("\n--------------Enter Output Geospatial File-------"
                      "-------")

                msg = "\nEnter the path of the output geospatial file " \
                      "(can also be GeoJSON, KML, GML or Shapefile) " \
                      "(default is no output file)\n"
                output = self.get_input(msg, required=False)

        return output

    def ask_overlap(self, overlap):

        if overlap is None:

            if not self.eod.silent:
                print("\n--------------Enter Minimum Overlap Percentage----"
                      "----------")

                msg = "\nEnter the minimum percentage of overlap between " \
                      "images and the AOI\n"
                overlap = self.get_input(msg, required=False)

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
                print("\n--------------Enter Priority--------------")

                msg = "Enter the priority level for the order"

                priority = self.get_input(msg, required=False,
                                          options=priorities, default='medium')

        if priority is None or priority == '':
            priority = 'Medium'
        elif priority.lower() not in priorities:
            self.eod.print_msg("WARNING: Not a valid 'priority' entry. "
                               "Setting priority to 'Medium'.", indent=False)
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
            print("\n--------------Choose Process Option--------------")

            choices = '\n'.join(["  %s: (%s) %s" % (idx + 1, v[0],
                                                    re.sub(r'\s+', ' ',
                                                           v[1].replace('\n',
                                                                        '')))
                                 for idx, v in enumerate(proc_choices.items())])

            print("\nWhat would you like to do?\n\n%s\n" % choices)
            process = input("->> Please choose the type of process [1]: ")

            if process == '':
                process = 'full'
            else:
                # Set process value and check its validity

                process = self.eod.validate_int(process)

                if not process:
                    err_msg = "Invalid value entered for the 'process' " \
                              "parameter."
                    self.eod.print_support(err_msg)
                    self.logger.error(err_msg)
                    sys.exit(1)

                if process > len(proc_choices.keys()):
                    err_msg = "Invalid value entered for the 'process' " \
                              "parameter."
                    self.eod.print_support(err_msg)
                    self.logger.error(err_msg)
                    sys.exit(1)
                else:
                    process = list(proc_choices.keys())[int(process) - 1]

        return process

    def ask_record_ids(self, ids):
        """
        Asks the user for a single or set of Record IDs.
        
        :param ids: A single or set of Record IDs with their collections.
        :type  ids: str
        """

        if ids is None or ids == '':

            if not self.eod.silent:
                print("\n--------------Enter Record ID(s)--------------")

                msg = "\nEnter a single or set of Record IDs. Include the " \
                      "Collection ID next to each ID separated by a " \
                      "colon. Separate each ID with a comma. " \
                      "(Ex: RCMImageProducts:7625368,NAPL:3736869)\n"
                ids = self.get_input(msg, required=False)

        return ids

    def build_syntax(self):
        """
        Builds the command-line syntax to print to the command prompt.
        
        :return: A string containing the command-line syntax for the script.
        :rtype: str
        """

        click_ctx = click.get_current_context(silent=True)

        cmd_params = click_ctx.to_info_dict()['command']['params']
        flags = {}
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
                            filt_lst.append("%s.%s" % (k, v))
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
                    pv = '"%s"' % pv

            syntax_params.append('%s %s' % (flag, pv))

        out_syntax = "python %s %s -s" % (os.path.realpath(__file__),
                                          ' '.join(syntax_params))

        return out_syntax

    def get_input(self, msg, err_msg=None, required=True, options=None,
                  default=None, password=False):
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
        :type  options: list
        :param default: The default value if the user just hits enter.
        :type  default: str
        :param password: Determines if the argument is for password entry.
        :type  password: boolean
        
        :return: The value entered by the user.
        :rtype: str
        """

        if password:
            # If the argument is for password entry, hide entry
            in_val = getpass.getpass(prompt='->> %s: ' % msg)
        else:
            opt_str = ''
            if options is not None:
                opt_str = ' (%s)' % '/'.join(options)

            def_str = ''
            if default is not None:
                def_str = ' [%s]' % default

            output = "\n->> %s%s%s: " % (msg, opt_str, def_str)
            if msg.endswith('\n'):
                output = "\n->> %s%s%s:\n" % (msg.strip('\n'), opt_str, def_str)
            in_val = input(output)

        if required and in_val == '':
            eod_util.EodmsOrderDownload().print_support(err_msg)
            self.logger.error(err_msg)
            sys.exit(1)

        if in_val == '' and default is not None and not default == '':
            in_val = default

        return in_val

    def print_syntax(self):
        """
        Prints the command-line syntax for the script.
        """

        print("\nUse this command-line syntax to run the same parameters:")
        cli_syntax = self.build_syntax()
        print(cli_syntax)
        self.logger.info("Command-line Syntax: %s" % cli_syntax)

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
        csv_fields = self.params.get('csv_fields')
        aws = self.params.get('aws')
        overlap = self.params.get('overlap')
        silent = self.params.get('silent')
        no_order = self.params.get('no_order')
        version = self.params.get('version')

        if version:
            print("%s: Version %s" % (__title__, __version__))
            sys.exit(0)

        self.eod.set_silence(silent)

        new_user = False
        new_pass = False

        if username is None or password is None:
            print("\n--------------Enter EODMS Credentials--------------")

        if username is None:

            username = self.config_info.get('RAPI', 'username')
            if username == '':
                msg = "Enter the username for authentication"
                err_msg = "A username is required to order images."
                username = self.get_input(msg, err_msg)
                new_user = True
            else:
                print("\nUsing the username set in the 'config.ini' file...")

        if password is None:

            password = self.config_info.get('RAPI', 'password')

            if password == '':
                msg = 'Enter the password for authentication'
                err_msg = "A password is required to order images."
                password = self.get_input(msg, err_msg, password=True)
                new_pass = True
            else:
                password = base64.b64decode(password).decode("utf-8")
                print("Using the password set in the 'config.ini' file...")

        if new_user or new_pass:
            suggestion = ''
            if self.eod.silent:
                suggestion = " (it is best to store the credentials if " \
                             "you'd like to run the script in silent mode)"

            answer = input("\n->> Would you like to store the credentials "
                           "for a future session%s? (y/n):" % suggestion)
            if answer.lower().find('y') > -1:
                self.config_info.set('RAPI', 'username', username)
                pass_enc = base64.b64encode(password.encode("utf-8")).decode(
                    "utf-8")
                self.config_info.set('RAPI', 'password',
                                     str(pass_enc))

                config_fn = os.path.join(os.path.dirname(
                    os.path.abspath(__file__)),
                    'config.ini')
                cfgfile = open(config_fn, 'w')
                self.config_info.write(cfgfile, space_around_delimiters=True)
                cfgfile.close()

        # Get number of attempts when querying the RAPI
        self.eod.set_attempts(self.config_info.get('RAPI', 'access_attempts'))

        self.eod.create_session(username, password)

        self.params = {'collections': collections,
                       'dates': dates,
                       'input_val': input_val,
                       'maximum': maximum,
                       'process': process}

        print()
        coll_lst = self.eod.eodms_rapi.get_collections(True)

        # print(f"coll_lst: {coll_lst}")

        # print(f"dir(eodms_rapi.eodms): {dir(eodms_rapi.eodms)}")
        # print(f"{isinstance(coll_lst, eodms_rapi.eodms.QueryError)}")

        if coll_lst is None or isinstance(coll_lst,
                                          eodms_rapi.eodms.QueryError):
            msg = "Failed to retrieve a list of available collections."
            self.logger.error(msg)
            self.eod.print_support(msg)
            sys.exit(1)

        print("\n(For more information on the following prompts, please refer"
              " to the README file.)")

        #########################################
        # Get the type of process
        #########################################

        if process is None or process == '':
            self.process = self.ask_process()
        else:
            self.process = process

        self.params['process'] = self.process

        if self.process == 'full':

            self.logger.info("Searching, ordering and downloading images "
                             "using an AOI.")

            # Get the collection(s)
            coll = self.ask_collection(collections)
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

            if not no_order:
                # Get the maximum(s)
                maximum = self.ask_maximum(maximum)
                self.params['maximum'] = maximum

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

            fields = self.eod.get_input_fields(inputs)
            csv_fields = self.ask_fields(csv_fields, fields)
            self.params['csv_fields'] = csv_fields

            # Get the output geospatial filename
            output = self.ask_output(output)
            self.params['output'] = output

            # Ask user if they'd like to order and download
            no_order = self.ask_order(no_order)
            self.params['no_order'] = no_order

            if not no_order:
                # Get the maximum(s)
                maximum = self.ask_maximum(maximum)
                self.params['maximum'] = maximum

                # Get the priority
                priority = self.ask_priority(priority)
                self.params['priority'] = priority

            # Print command-line syntax for future processes
            self.print_syntax()

            # Run the order_csv process
            self.eod.order_csv(self.params)

        elif self.process == 'download_aoi' or self.process == 'search_only':

            if self.process == 'download_aoi':
                self.logger.info("Downloading existing orders using an AOI.")
            else:
                self.logger.info("Searching for images using an AOI.")

            # Get the collection(s)
            coll = self.ask_collection(collections)
            self.params['collections'] = coll

            # Get the AOI file
            inputs = self.ask_aoi(input_val)
            self.params['input_val'] = inputs

            # If an AOI is specified, ask for a minimum overlap percentage
            if inputs is not None:
                overlap = self.ask_overlap(overlap)
                self.params['overlap'] = overlap

            # Get the filter(s)
            filt_dict = self.ask_filter(filters)
            self.params['filters'] = filt_dict

            # Get the date(s)
            dates = self.ask_dates(dates)
            self.params['dates'] = dates

            # Get the output geospatial filename
            output = self.ask_output(output)
            self.params['output'] = output

            # Print command-line syntax for future processes
            self.print_syntax()

            if self.process == 'download_aoi':
                self.eod.download_aoi(self.params)
            else:
                self.eod.search_only(self.params)

        elif self.process == 'download_only':
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
            self.eod.download_only(self.params)

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

        else:
            self.eod.print_support("That is not a valid process type.")
            self.logger.error(
                "An invalid parameter was entered during the prompt.")
            sys.exit(1)


def get_config():
    """
    Gets the configuration information from the config file.
    
    :return: The information extracted from the config file.
    :rtype: configparser.ConfigParser
    """

    config = configparser.ConfigParser(comment_prefixes='/',
                                       allow_no_value=True)

    config_fn = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'config.ini')

    config.read(config_fn)

    return config


def get_option(config_info, section, option):
    if isinstance(section, str):
        section = [section]

    for sec in section:
        if config_info.has_option(sec, option):
            return config_info.get(sec, option)


def print_support(err_str=None):
    """
    Prints the 2 different support message depending if an error occurred.
    
    :param err_str: The error string to print along with support.
    :type  err_str: str
    """

    eod_util.EodmsOrderDownload().print_support(err_str)


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


@click.command(context_settings={'help_option_names': ['-h', '--help']})
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
              help='The maximum number of images to order and download '
                   'and the maximum number of images per order, separated '
                   'by a colon.')
@click.option('--priority', '-pri', '-l', default=None,
              help='The priority level of the order.\nOne of "Low", '
                   '"Medium", "High" or "Urgent" (default "Medium").')
@click.option('--output', '-o', default=None,
              help=output_help)
@click.option('--csv_fields', '-cf', default=None,
              help='The fields in the input CSV file used to get images.')
@click.option('--aws', '-a', is_flag=True, default=None,
              help='Determines whether to download from AWS (only applies '
                   'to Radarsat-1 imagery).')
@click.option('--overlap', '-ov', default=None,
              help='The minimum percentage of overlap between AOI and images '
                   '(if no AOI specified, this parameter is ignored).')
@click.option('--silent', '-s', is_flag=True, default=None,
              help='Sets process to silent which supresses all questions.')
@click.option('--no_order', '-nord', is_flag=True, default=None,
              help='If set, no ordering and downloading will occur.')
@click.option('--version', '-v', is_flag=True, default=None,
              help='Prints the version of the script.')
def cli(username, password, input_val, collections, process, filters, dates,
        maximum, priority, output, csv_fields, aws, overlap, silent, no_order,
        version):
    """
    Search & Order EODMS products.
    """

    cmd_title = "EODMS Orderer-Downloader"
    os.system("title " + cmd_title)
    sys.stdout.write("\x1b]2;%s\x07" % cmd_title)

    if '-v' in sys.argv or '--v' in sys.argv or '--version' in sys.argv:
        print("\n  %s, version %s\n" % (__title__, __version__))
        sys.exit(0)

    print("\n##########################################################"
          "#######################")
    print("# %s v%s                           " 
          "             #" % (__title__, __version__))
    print("############################################################"
          "#####################")

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
                  'csv_fields': csv_fields,
                  'aws': aws,
                  'overlap': overlap,
                  'silent': silent,
                  'no_order': no_order,
                  'version': version}

        # Set all the parameters from the config.ini file
        config_info = get_config()

        abs_path = os.path.abspath(__file__)
        # download_path = config_info.get('Script', 'downloads')
        download_path = get_option(config_info, ['Script', 'Paths'],
                                   'downloads')

        if download_path == '':
            download_path = os.path.join(os.path.dirname(abs_path), 'downloads')
        elif not os.path.isabs(download_path):
            download_path = os.path.join(os.path.dirname(abs_path),
                                         download_path)

        print("\nImages will be downloaded to '%s'." % download_path)

        res_path = get_option(config_info, ['Script', 'Paths'], 'results')
        if res_path == '':
            res_path = os.path.join(os.path.dirname(abs_path), 'results')
        elif not os.path.isabs(res_path):
            res_path = os.path.join(os.path.dirname(abs_path),
                                    res_path)

        log_loc = get_option(config_info, ['Script', 'Paths'], 'log')
        if log_loc == '':
            log_loc = os.path.join(os.path.dirname(abs_path), 'log',
                                   'logger.log')
        elif not os.path.isabs(log_loc):
            log_loc = os.path.join(os.path.dirname(abs_path),
                                   log_loc)

        # Setup logging
        logger = logging.getLogger('EODMSRAPI')

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - '
                                      '%(message)s',
                                      datefmt='%Y-%m-%d %I:%M:%S %p')

        if not os.path.exists(os.path.dirname(log_loc)):
            pathlib.Path(os.path.dirname(log_loc)).mkdir(
                parents=True, exist_ok=True)

        log_handler = handlers.RotatingFileHandler(log_loc,
                                                   maxBytes=500000,
                                                   backupCount=2)
        log_handler.setLevel(logging.DEBUG)
        log_handler.setFormatter(formatter)
        logger.addHandler(log_handler)

        logger.info("Script start time: %s" % start_str)

        timeout_query = get_option(config_info, ['Script', 'RAPI'],
                                   'timeout_query')
        # timeout_order = config_info.get('Script', 'timeout_order')
        timeout_order = get_option(config_info, ['Script', 'RAPI'],
                                   'timeout_order')

        try:
            timeout_query = float(timeout_query)
        except ValueError:
            timeout_query = 60.0

        try:
            timeout_order = float(timeout_order)
        except ValueError:
            timeout_order = 180.0

        keep_results = get_option(config_info, 'Script', 'keep_results')
        keep_downloads = get_option(config_info, 'Script', 'keep_downloads')

        # Get the total number of results per query
        max_results = get_option(config_info, 'RAPI', 'max_results')

        # Get the minimum date value to check orders
        order_check_date = get_option(config_info, 'RAPI', 'order_check_date')

        # Get URL for debug purposes
        rapi_url = get_option(config_info, 'Debug', 'root_url')

        # print("download_path: %s" % download_path)
        # print("res_path: %s" % res_path)
        # print("log_loc: %s" % log_loc)
        # print("timeout_query: %s" % timeout_query)
        # print("timeout_order: %s" % timeout_order)
        # print("max_results: %s" % max_results)
        # print("keep_results: %s" % keep_results)
        # print("keep_downloads: %s" % keep_downloads)
        # print("rapi_url: %s" % rapi_url)

        eod = eod_util.EodmsOrderDownload(download=download_path,
                                          results=res_path, log=log_loc,
                                          timeout_query=timeout_query,
                                          timeout_order=timeout_order,
                                          max_res=max_results,
                                          keep_results=keep_results,
                                          keep_downloads=keep_downloads,
                                          order_check_date=order_check_date,
                                          rapi_url=rapi_url)

        print("\nCSV Results will be placed in '%s'." % eod.results_path)

        eod.cleanup_folders()

        #########################################
        # Get authentication if not specified
        #########################################

        prmpt = Prompter(eod, config_info, params, click)

        prmpt.prompt()

        print("\nProcess complete.")

        eod.print_support()

    except KeyboardInterrupt:
        msg = "Process ended by user."
        print("\n%s" % msg)

        if 'eod' in vars() or 'eod' in globals():
            eod.print_support()
            eod.export_results()
        else:
            eod_util.EodmsOrderDownload().print_support()
        logger.info(msg)
        sys.exit(1)
    except Exception:
        trc_back = "\n%s" % traceback.format_exc()
        if 'eod' in vars() or 'eod' in globals():
            eod.print_support(trc_back)
            eod.export_results()
        else:
            eod_util.EodmsOrderDownload().print_support(trc_back)
        logger.error(traceback.format_exc())


if __name__ == '__main__':
    sys.exit(cli())
