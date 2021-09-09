##############################################################################
# MIT License
# 
# Copyright (c) 2020-2021 Her Majesty the Queen in Right of Canada, as 
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
__copyright__ = 'Copyright 2020-2021 Her Majesty the Queen in Right of Canada'
__license__ = 'MIT License'
__description__ = 'Script used to search, order and download imagery from the EODMS using the REST API (RAPI) service.'
__version__ = '2.1.0'
__maintainer__ = 'Kevin Ballantyne'
__email__ = 'eodms-sgdot@nrcan-rncan.gc.ca'

import sys
import os
import re
# import requests
import argparse
import traceback
import getpass
import datetime
# import json
import configparser
import base64
import logging
import logging.handlers as handlers
import pathlib

from eodms_rapi import EODMSRAPI

from utils import eod as eod_util
# from utils import csv_util
# from utils import image
# from utils import geo
        
class Prompter():
    
    """
    Class used to prompt the user for all inputs.
    """
    
    def __init__(self, eod, config_info, params):
        """
        Initializer for the Prompter class.
        
        :param eod: The Eodms_OrderDownload object.
        :type  eod: self.Eodms_OrderDownload
        :param config_info: Configuration information taken from the config file.
        :type  config_info: dict
        :param params: An empty dictionary of parameters.
        :type  params: dict
        """
        
        self.eod = eod
        self.config_info = config_info
        self.params = params
        
        self.logger = logging.getLogger('eodms')
        
        self.choices = {'full': 'Search, order & download images using ' \
                    'an AOI', \
                'order_csv': 'Order & download images using EODMS UI ' \
                    'search results (CSV file)', 
                'download_only': '''Download existing orders using a CSV file 
        from a previous order/download process (files found under "results" 
        folder)''', 
                'search_only': 'Run only a search based on an AOI '\
                    'and input parameters'}

    def ask_aoi(self, input_fn):
        """
        Asks the user for the geospatial input filename.
        
        :param input_fn: The geospatial input filename if already set by the command-line.
        :type  input_fn: str
        
        :return: The geospatial filename entered by the user.
        :rtype: str
        """
        
        if input_fn is None or input_fn == '':
                    
            if self.eod.silent:
                err_msg = "No AOI file specified. Exiting process."
                self.eod.print_support(err_msg)
                self.logger.error(err_msg)
                sys.exit(1)
                
            print("\n--------------Enter Input Geospatial File--------------")
            
            msg = "Enter the full path name of a GML, KML, Shapefile or " \
                    "GeoJSON containing an AOI to restrict the search " \
                    "to a specific location\n"
            err_msg = "No AOI specified. Please enter a valid GML, KML, " \
                    "Shapefile or GeoJSON file"
            input_fn = self.get_input(msg, err_msg)
            
        if input_fn.find('.shp') > -1:
            try:
                import ogr
                import osr
                GDAL_INCLUDED = True
            except ImportError:
                try:
                    import osgeo.ogr as ogr
                    import osgeo.osr as osr
                    GDAL_INCLUDED = True
                except ImportError:
                    err_msg = "Cannot open a Shapefile without GDAL. Please install " \
                        "the GDAL Python package if you'd like to use a Shapefile " \
                        "for your AOI."
                    self.eod.print_support(err_msg)
                    self.logger.error(err_msg)
                    sys.exit(1)
                    
        input_fn = input_fn.strip()
        input_fn = input_fn.strip("'")
        input_fn = input_fn.strip('"')
        
        #---------------------------------
        # Check validity of the input file
        #---------------------------------
        
        input_fn = self.eod.validate_file(input_fn, True)
        
        if not input_fn:
            sys.exit(1)
            
        return input_fn
        
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
            
            #---------------------------------------
            # Check validity of the collection entry
            #---------------------------------------
            
            check = self.eod.validate_int(coll_vals, len(coll_lst))
            if not check:
                err_msg = "A valid Collection must be specified. " \
                            "Exiting process."
                self.eod.print_support(err_msg)
                self.logger.error(err_msg)
                sys.exit(1)
            
            coll = [coll_lst[int(i) - 1]['id'] for i in coll_vals if i.isdigit()]
        else:
            coll = coll.split(',')
            
        #------------------------------
        # Check validity of Collections
        #------------------------------
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
                
                msg = "Enter a date range (ex: 20200525-20200630) " \
                        "or a previous time-frame (24 hours) " \
                        "(leave blank to search all years)\n"
                dates = self.get_input(msg, required=False)
                
        #-------------------------------
        # Check validity of filter input
        #-------------------------------
        if dates is not None and not dates == '':
            dates = self.eod.validate_dates(dates)
            
            if not dates:
                err_msg = "The dates entered are invalid. "
                self.eod.print_support(err_msg)
                self.logger.error(err_msg)
                sys.exit(1)
                
        return dates
                
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
                    coll_id = self.eod.get_fullCollId(coll)
                    
                    if coll_id in self.eod.get_fieldMap().keys():
                        field_map = self.eod.get_fieldMap()[coll_id]
                        
                        print("\nAvailable fields for '%s':" % coll)
                        for f in field_map.keys():
                            print("  %s" % f)
                            
                        print("NOTE: Filters must be entered in the format " \
                            "of <field_id>=<value>|<value>|... (field " \
                            "IDs are not case sensitive); separate each " \
                            "filter with a comma. To see a list " \
                            "of field choices, enter '? <field_id>'.")
                            
                        msg = "Enter the filters you would like to apply " \
                                "to the search"
                        
                        filt_items = '?'
                        
                        while filt_items.find('?') > -1:
                            filt_items = input("\n->> %s:\n" % msg)
                            
                            if filt_items.find('?') > -1:
                                field_val = filt_items.replace('?', '').strip()
                                
                                field_title = field_map.get(field_val.upper())
                                
                                if field_title is None:
                                    print("Not a valid field.")
                                    continue
                                
                                field_choices = self.eod.eodms_rapi.\
                                    get_fieldChoices(coll_id, field_title)
                                    
                                if isinstance(field_choices, dict):
                                    field_choices = 'any %s value' % \
                                        field_choices['data_type']
                                else:
                                    field_choices = ', '.join(field_choices)
                                    
                                print("\nAvailable choices for '%s': %s" % \
                                        (field_val, field_choices))
                        
                        #filt_items = self.get_input(msg, required=False)
                        
                        if filt_items == '':
                            filt_dict[coll_id] = []
                        else:
                            
                            #-------------------------------
                            # Check validity of filter input
                            #-------------------------------
                            filt_items = self.eod.validate_filters(filt_items, \
                                            coll_id)
                            
                            if not filt_items:
                                sys.exit(1)
                            
                            filt_items = filt_items.split(',')
                            # In case the user put collections in filters
                            filt_items = [f.split('.')[1] \
                                if f.find('.') > -1 \
                                else f for f in filt_items]
                            filt_dict[coll_id] = filt_items
            
        else:
            # User specified in command-line
            
            # Possible formats:
            #   1. Only one collection: <field_id>=<value>|<value>,<field_id>=<value>&<value>,...
            #   2. Multiple collections but only specifying one set of filters:
            #       <coll_id>.<field_id>=<value>|<value>,...
            #   3. Multiple collections with filters:
            #       <coll_id>.<field_id>=<value>,...<coll_id>.<field_id>=<value>,...
            
            filt_dict = {}
            
            for coll in self.params['collections']:
                # Split filters by comma
                filt_lst = filters.split(',')
                for f in filt_lst:
                    if f == '': continue
                    if f.find('.') > -1:
                        coll, filt_items = f.split('.')
                        filt_items = self.eod.validate_filters(filt_items, \
                                        coll)
                        if not filt_items:
                            sys.exit(1)
                        coll_id = self.eod.get_fullCollId(coll)
                        if coll_id in filt_dict.keys():
                            coll_filters = filt_dict[coll_id]
                        else:
                            coll_filters = []
                        coll_filters.append(filt_items.replace('"', '').\
                            replace("'", ''))
                        filt_dict[coll_id] = coll_filters
                    else:
                        coll_id = self.eod.get_collIdByName(coll)
                        if coll_id in filt_dict.keys():
                            coll_filters = filt_dict[coll_id]
                        else:
                            coll_filters = []
                        coll_filters.append(f)
                        filt_dict[coll_id] = coll_filters
        
        return filt_dict
        
    def ask_inputFile(self, input_fn, msg):
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
        Asks the user for maximum number of order items and the number of items per order.
        
        :param maximum: The maximum if already set by the command-line.
        :type  maximum: str
        
        :return: The maximum number of order items and/or number of items per order, separated by ':'.
        :rtype: str
        """
        
        if maximum is None or maximum == '':
                        
            if not self.eod.silent:
                if not self.process == 'order_csv':
                    
                    print("\n--------------Enter Maximums--------------")
                    
                    msg = "Enter the total number of images you'd " \
                        "like to order (leave blank for no limit)"
                    
                    total_records = self.get_input(msg, required=False)
                    
                    #------------------------------------------
                    # Check validity of the total_records entry
                    #------------------------------------------
                
                    if total_records == '':
                        total_records = None
                    else:
                        total_records = self.eod.validate_int(total_records)
                        if not total_records:
                            self.eod.print_msg("WARNING: Total number of images " \
                                "value not valid. Excluding it.", indent=False)
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
                        self.eod.print_msg("WARNING: Order limit value not " \
                            "valid. Excluding it.", indent=False)
                        order_limit = None
                    else:
                        order_limit = str(order_limit)
                
                maximum = ':'.join(filter(None, [total_records, \
                            order_limit]))
                            
        else:
            
            if self.process == 'order_csv':
                
                print("\n--------------Enter Images per Order--------------")
                
                if maximum.find(':') > -1:
                    total_records, order_limit = maximum.split(':')
                else:
                    total_records = None
                    order_limit = maximum
                    
                maximum = ':'.join(filter(None, [total_records, \
                                order_limit]))
                            
        return maximum
        
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
                print("\n--------------Enter Output Geospatial File--------------")
                
                msg = "\nEnter the path of the output geospatial file " \
                    "(can also be GeoJSON, KML, GML or Shapefile) " \
                    "(default is no output file)\n"
                output = self.get_input(msg, required=False)
                
        return output
        
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
                
                msg = "Enter the priority level for the order ('Low', " \
                        "'Medium', 'High', 'Urgent') [Medium]"
                        
                priority = self.get_input(msg, required=False)
            
        if priority is None or priority == '':
            priority = 'Medium'
        elif priority.lower() not in priorities:
            self.eod.print_msg("WARNING: Not a valid 'priority' entry. " \
                "Setting priority to 'Medium'.", indent=False)
            priority = 'Medium'

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
        
            choices = '\n'.join(["  %s: (%s) %s" % (idx + 1, v[0], \
                        re.sub(r'\s+', ' ', v[1].replace('\n', ''))) \
                        for idx, v in enumerate(self.choices.items())])
            
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
                
                if process > len(self.choices.keys()):
                    err_msg = "Invalid value entered for the 'process' " \
                                "parameter."
                    self.eod.print_support(err_msg)
                    self.logger.error(err_msg)
                    sys.exit(1)
                else:
                    process = list(self.choices.keys())[int(process) - 1]
                    
        return process

    def build_syntax(self):
        """
        Builds the command-line syntax to print to the command prompt.
        
        :return: A string containing the command-line syntax for the script.
        :rtype: str
        """
        
        # Get the actions of the argparse
        actions = self.parser._option_string_actions
        
        syntax_params = []
        for p, pv in self.params.items():
            if pv is None or pv == '': continue
            if p == 'session': continue
            if p == 'eodms_rapi': continue
            action = actions['--%s' % p]
            flag = action.option_strings[0]
            
            if isinstance(pv, list):
                if flag == '-d':
                    pv = '-'.join(['"%s"' % i if i.find(' ') > -1 else i \
                            for i in pv ])
                else:
                    pv = ','.join(['"%s"' % i if i.find(' ') > -1 else i \
                            for i in pv ])
                            
            elif isinstance(pv, dict):
                
                if flag == '-f':
                    filt_lst = []
                    for k, v_lst in pv.items():
                        for v in v_lst:
                            if v is None or v == '': continue
                            v = v.replace('"', '').replace("'", '')
                            filt_lst.append("%s.%s" % (k, v))
                    if len(filt_lst) == 0: continue
                    pv = '"%s"' % ','.join(filt_lst)
            else:
                if isinstance(pv, str) and pv.find(' ') > -1:
                    pv = '"%s"' % pv
            
            syntax_params.append('%s %s' % (flag, pv))
            
        out_syntax = "python %s %s -s" % (os.path.realpath(__file__), \
                        ' '.join(syntax_params))
        
        return out_syntax
        
    def get_input(self, msg, err_msg=None, required=True, password=False):
        """
        Gets an input from the user for an argument.
        
        :param msg: The message used to prompt the user.
        :type  msg: str
        :param err_msg: The message to print when the user enters an invalid input.
        :type  err_msg: str
        :param required: Determines if the argument is required.
        :type  required: boolean
        :param password: Determines if the argument is for password entry.
        :type  password: boolean
        
        :return: The value entered by the user.
        :rtype: str
        """
        
        if password:
            # If the argument is for password entry, hide entry
            in_val = getpass.getpass(prompt='->> %s: ' % msg)
        else:
            output = "\n->> %s: " % msg
            if msg.endswith('\n'):
                output = "\n->> %s:\n" % msg.strip('\n')
            in_val = input(output)
            
        if required and in_val == '':
            eod_util.Eodms_OrderDownload().print_support(err_msg)
            self.logger.error(err_msg)
            sys.exit(1)
            
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
        
        self.parser = argparse.ArgumentParser(description='Search & Order EODMS ' \
                            'products.', \
                            formatter_class=argparse.RawTextHelpFormatter)
        
        self.parser.add_argument('-u', '--username', help='The username of ' \
                        'the EODMS account used for authentication.')
        self.parser.add_argument('-p', '--password', help='The password of ' \
                            'the EODMS account used for authentication.')
        input_help = '''An input file, can either be an AOI or a CSV file 
    exported from the EODMS UI. Valid AOI formats are GeoJSON, 
    KML or Shapefile (Shapefile requires the GDAL Python package).'''
        self.parser.add_argument('-i', '--input', help=input_help)
        coll_help = '''The collection of the images being ordered 
    (separate multiple collections with a comma).'''
        self.parser.add_argument('-c', '--collections', help=coll_help)
        self.parser.add_argument('-f', '--filters', help='A list of ' \
                        'filters for a specific collection.')
        self.parser.add_argument('-l', '--priority', help='The priority ' \
                        'level of the order.\nOne of "Low", "Medium", ' \
                        '"High" or "Urgent" (default "Medium").')
        self.parser.add_argument('-d', '--dates', help='The date ranges ' \
                        'for the search.')
        max_help = '''The maximum number of images to order and download 
    and the maximum number of images per order, separated by a colon.'''
        self.parser.add_argument('-m', '--maximum', help=max_help)
        self.parser.add_argument('-r', '--process', help='The type of ' \
                        'process to run from this list of options:\n- %s' % \
                        '\n- '.join(["%s: %s" % (k, v) for k, v in \
                        self.choices.items()]))
        output_help = '''The output file path containing the results in a geospatial format.
The output parameter can be:
- None (empty): No output will be created (a results CSV file will still be 
    created in the 'results' folder)
- GeoJSON: The output will be in the GeoJSON format 
    (use extension .geojson or .json)
- KML: The output will be in KML format (use extension .kml) (requires GDAL Python package) 
- GML: The output will be in GML format (use extension .gml) (requires GDAL Python package) 
- Shapefile: The output will be ESRI Shapefile (requires GDAL Python package) 
    (use extension .shp)'''
        self.parser.add_argument('-o', '--output', help=output_help)
        self.parser.add_argument('-s', '--silent', action='store_true', \
                        help='Sets process to silent which supresses all ' \
                        'questions.')
        self.parser.add_argument('-v', '--version', action='store_true', \
                        help='Prints the version of the script.')
        
        args = self.parser.parse_args()
        
        user = args.username
        password = args.password
        coll = args.collections
        dates = args.dates
        input_fn = args.input
        filters = args.filters
        priority = args.priority
        maximum = args.maximum
        process = args.process
        output = args.output
        silent = args.silent
        version = args.version
        
        if version:
            print("%s: Version %s" % (__title__, __version__))
            sys.exit(0)
        
        self.eod.set_silence(silent)
                
        new_user = False
        new_pass = False
        
        if user is None or password is None:
            print("\n--------------Enter EODMS Credentials--------------")
        
        if user is None:
            
            user = self.config_info.get('RAPI', 'username')
            if user == '':
                msg = "Enter the username for authentication"
                err_msg = "A username is required to order images."
                user = self.get_input(msg, err_msg)
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
            
            answer = input("\n->> Would you like to store the credentials " \
                    "for a future session%s? (y/n):" % suggestion)
            if answer.lower().find('y') > -1:
                self.config_info.set('RAPI', 'username', user)
                pass_enc = base64.b64encode(password.encode("utf-8")).decode("utf-8")
                self.config_info.set('RAPI', 'password', \
                    str(pass_enc))
                
                config_fn = os.path.join(os.path.dirname(\
                            os.path.abspath(__file__)), \
                            'config.ini')
                cfgfile = open(config_fn, 'w')
                self.config_info.write(cfgfile, space_around_delimiters=False)
                cfgfile.close()
        
        # Get number of attempts when querying the RAPI
        self.eod.set_attempts(self.config_info.get('RAPI', 'access_attempts'))
        
        self.eod.create_session(user, password)
        
        self.params = {'collections': coll, 
                        'dates': dates, 
                        'input': input_fn, 
                        'maximum': maximum, 
                        'process': process}
        
        print()
        coll_lst = self.eod.eodms_rapi.get_collections(True)
        
        if coll_lst is None:
            msg = "Failed to retrieve a list of available collections."
            self.logger.error(msg)
            self.eod.print_support(msg)
            sys.exit(1)
        
        print("\n(For more information on the following prompts, please refer" \
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
            
            self.logger.info("Searching, ordering and downloading images " \
                        "using an AOI.")
                        
            # Get the AOI file
            input_fn = self.ask_aoi(input_fn)
            self.params['input'] = input_fn
            
            # Get the collection(s)
            coll = self.ask_collection(coll)
            self.params['collections'] = coll
            
            # Get the filter(s)
            filt_dict = self.ask_filter(filters)
            self.params['filters'] = filt_dict
            
            # Get the date(s)
            dates = self.ask_dates(dates)
            self.params['dates'] = dates
            
            # Get the output geospatial filename
            output = self.ask_output(output)
            self.params['output'] = output
            
            # Get the maximum(s)
            maximum = self.ask_maximum(maximum)
            self.params['maximum'] = maximum
            
            # Get the priority
            priority = self.ask_priority(priority)       
            self.params['priority'] = priority
            
            # Print command-line syntax for future processes
            self.print_syntax()
            
            self.eod.search_orderDownload(self.params)
            
        elif self.process == 'order_csv':
            
            self.logger.info("Ordering and downloading images using results " \
                        "from a CSV file.")
            
            #########################################
            # Get the CSV file
            #########################################
            
            msg = "Enter the full path of the CSV file exported "\
                        "from the EODMS UI website"
            input_fn = self.ask_inputFile(input_fn, msg)
            self.params['input'] = input_fn
            
            # Get the output geospatial filename
            output = self.ask_output(output)
            self.params['output'] = output
            
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
            
            # Get the AOI file
            input_fn = self.ask_aoi(input_fn)
            self.params['input'] = input_fn
            
            # Get the collection(s)
            coll = self.ask_collection(coll)
            self.params['collections'] = coll
            
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
            
            self.logger.info("Downloading images using results from a CSV " \
                        "file from a previous session.")
            
            # Get the CSV file
            msg = "Enter the full path of the CSV Results file from a " \
                "previous session"
            input_fn = self.ask_inputFile(input_fn, msg)
            self.params['input'] = input_fn
            
            # Get the output geospatial filename
            output = self.ask_output(output)
            self.params['output'] = output
            
            # Print command-line syntax for future processes
            self.print_syntax()
            
            # Run the download_only process
            self.eod.download_only(self.params)
        
        else:
            self.eod.print_support("That is not a valid process type.")
            self.logger.error("An invalid parameter was entered during the prompt.")
            sys.exit(1)

def get_config():
    """
    Gets the configuration information from the config file.
    
    :return: The information extracted from the config file.
    :rtype: configparser.ConfigParser
    """
    
    config = configparser.ConfigParser()
    
    config_fn = os.path.join(os.path.dirname(os.path.abspath(__file__)), \
                'config.ini')
    
    config.read(config_fn)
    
    return config
    
def print_support(err_str=None):
    """
    Prints the 2 different support message depending if an error occurred.
    
    :param err_str: The error string to print along with support.
    :type  err_str: str
    """
    
    eod_util.Eodms_OrderDownload().print_support(err_str)
        
def main():
    
    cmd_title = "EODMS Orderer-Downloader"
    os.system("title " + cmd_title)
    sys.stdout.write("\x1b]2;%s\x07" % cmd_title)
    
    if '-v' in sys.argv or '--v' in sys.argv or '--version' in sys.argv:
        print("\n  %s, version %s\n" % (__title__, __version__))
        sys.exit(0)
    
    print("\n##########################################################" \
            "#######################")
    print("# %s                           " \
            "                    #" % __title__)
    print("############################################################" \
            "#####################")

    # Create info folder, if it doesn't exist, to store CSV files
    start_time = datetime.datetime.now()
    start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        
        params = {}
        
        # Set all the parameters from the config.ini file
        config_info = get_config()
        
        abs_path = os.path.abspath(__file__)
        download_path = config_info.get('Script', 'downloads')
        if download_path == '':
            download_path = os.path.join(os.path.dirname(abs_path), \
                                    'downloads')
        elif not os.path.isabs(download_path):
            download_path = os.path.join(os.path.dirname(abs_path), \
                                    download_path)
            
        print("\nImages will be downloaded to '%s'." % download_path)
        
        res_path = config_info.get('Script', 'results')
        if res_path == '':
            res_path = os.path.join(os.path.dirname(abs_path), \
                                    'results')
        elif not os.path.isabs(res_path):
            res_path = os.path.join(os.path.dirname(abs_path), \
                                    res_path)
            
        log_loc = config_info.get('Script', 'log')
        if log_loc == '':
            log_loc = os.path.join(os.path.dirname(abs_path), \
                                    'log', 'logger.log')
        elif not os.path.isabs(log_loc):
            log_loc = os.path.join(os.path.dirname(abs_path), \
                                    log_loc)
            
        # Setup logging
        logger = logging.getLogger('EODMSRAPI')
        # logger.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - ' \
                    '%(message)s', datefmt='%Y-%m-%d %I:%M:%S %p')
        
        if not os.path.exists(os.path.dirname(log_loc)):
            pathlib.Path(os.path.dirname(log_loc)).mkdir(\
                parents=True, exist_ok=True)
        
        logHandler = handlers.RotatingFileHandler(log_loc, \
                        maxBytes=500000, backupCount=2)
        logHandler.setLevel(logging.DEBUG)
        logHandler.setFormatter(formatter)
        logger.addHandler(logHandler)
        
        logger.info("Script start time: %s" % start_str)
        
        # for k,v in logging.Logger.manager.loggerDict.items()  :
            # print('+ [%s] {%s} ' % (str.ljust( k, 20)  , str(v.__class__)[8:-2]) ) 
            # if not isinstance(v, logging.PlaceHolder):
                # for h in v.handlers:
                    # print('     +++',str(h.__class__)[8:-2] )
            
        timeout_query = config_info.get('Script', 'timeout_query')
        timeout_order = config_info.get('Script', 'timeout_order')
        
        try:
            timeout_query = float(timeout_query)
        except ValueError:
            timeout_query = 60.0
            
        try:
            timeout_order = float(timeout_order)
        except ValueError:
            timeout_order = 180.0
            
        # Get the total number of results per query
        max_results = config_info.get('RAPI', 'max_results')
        
        eod = eod_util.Eodms_OrderDownload(download=download_path, 
                                results=res_path, log=log_loc, 
                                timeout_query=timeout_query, 
                                timeout_order=timeout_order, 
                                max_res=max_results)
            
        print("\nCSV Results will be placed in '%s'." % eod.results_path)
        
        #########################################
        # Get authentication if not specified
        #########################################
        
        prmpt = Prompter(eod, config_info, params)
        
        prmpt.prompt()
            
        print("\nProcess complete.")
        
        eod.print_support()
    
    except KeyboardInterrupt as err:
        msg = "Process ended by user."
        print("\n%s" % msg)
        
        if 'eod' in vars() or 'eod' in globals():
            eod.print_support()
            eod.export_results()
        else:
            eod_util.Eodms_OrderDownload().print_support()
        logger.info(msg)
        sys.exit(1)
    except Exception:
        trc_back = "\n%s" % traceback.format_exc()
        if 'eod' in vars() or 'eod' in globals():
            eod.print_support(trc_back)
            eod.export_results()
        else:
            eod_util.Eodms_OrderDownload().print_support(trc_back)
        logger.error(traceback.format_exc())

if __name__ == '__main__':
	sys.exit(main())