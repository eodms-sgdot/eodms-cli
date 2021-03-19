##############################################################################
# MIT License
# 
# Copyright (c) 2020 Her Majesty the Queen in Right of Canada, as 
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

import sys
import os
import requests
import argparse
import traceback
import getpass
import datetime
import configparser
import base64
import logging
import logging.handlers as handlers
import pathlib

try:
    import dateparser
except:
    msg = "Dateparser package is not installed. Please install and run script again."
    common.print_support(msg)
    logger.error(msg)
    sys.exit(1)

from utils import *

def build_syntax(parser, params):
    """
    Builds the command-line syntax to print to the command prompt.
    
    @type  parser: argparse
    @param parser: The argparse object containing the argument flags of 
                    the script.
    @type  params: dict
    @param params: A dictionary containing the arguments and values.
    
    @rtype:  str
    @return: A string containing the command-line syntax for the script.
    """
    
    # Get the actions of the argparse
    actions = parser._option_string_actions
    
    # print("params: %s" % params)
    
    syntax_params = []
    for p, pv in params.items():
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
                # print("pv: %s" % pv)
                for k, v_lst in pv.items():
                    for v in v_lst:
                        v = v.replace('"', '').replace("'", '')
                        filt_lst.append("%s.%s" % (k, v))
                # print("filt_lst: %s" % filt_lst)
                # answer = input("Press enter...")
                pv = '"%s"' % ','.join(filt_lst)
        else:
            if isinstance(pv, str) and pv.find(' ') > -1:
                pv = '"%s"' % pv
        
        syntax_params.append('%s %s' % (flag, pv))
        
    out_syntax = "python %s %s -s" % (os.path.realpath(__file__), \
                    ' '.join(syntax_params))
    
    return out_syntax
    
def download(params):
    """
    Downloads existing images using the CSV results file from a previous 
        session.
    
    @type  params: dict
    @param params: A dictionary containing the arguments and values.
    """
    
    logger = logging.getLogger('eodms')
    
    # Log the parameters
    log_parameters(params)
    
    csv_fn = params['input']
    # session = params['session']
    
    if csv_fn.find('.csv') == -1:
        msg = "The provided input file is not a CSV file. " \
            "Exiting process."
        common.print_support(msg)
        logger.error(msg)
        sys.exit(1)
    
    # Create info folder, if it doesn't exist, to store CSV files
    start_time = datetime.datetime.now()
    start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
    fn_str = start_time.strftime("%Y%m%d_%H%M%S")
    folder_str = start_time.strftime("%Y-%m-%d")
    
    logger.info("Process start time: %s" % start_str)
    
    eodms_downloader = utils.Downloader(in_csv=csv_fn, fn_str=fn_str)
    eodms_downloader.download_orders()
    
    end_time = datetime.datetime.now()
    end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
    
    logger.info("End time: %s" % end_str)
    
def get_config():
    
    config = configparser.ConfigParser()
    
    config_fn = os.path.join(os.path.dirname(os.path.abspath(__file__)), \
                'config.ini')
    
    config.read(config_fn)
    
    return config

def get_input(msg, err_msg=None, required=True, password=False):
    """
    Gets an input from the user for an argument.
    
    @type  msg:      str
    @param msg:      The message used to prompt the user.
    @type  err_msg:  str
    @param err_msg:  The message to print when the user enters an invalid 
                        input.
    @type  required: boolean
    @param required: Determines if the argument is required.
    @type  password: boolean
    @param password: Determines if the argument is for password entry.
    
    @rtype:  str
    @return: The value entered by the user.
    """
    
    if password:
        # If the argument is for password entry, hide entry
        in_val = getpass.getpass(prompt='%s: ' % msg)
    else:
        in_val = input("%s: " % msg)
        
    if required and in_val == '':
        common.print_support(err_msg)
        logger = logging.getLogger('eodms')
        logger.error(err_msg)
        sys.exit(1)
        
    return in_val
    
def log_parameters(params, title=None):
    
    logger = logging.getLogger('eodms')
    
    if title is None: title = "Script Parameters"
    
    msg = "%s:\n" % title
    for k, v in params.items():
        msg += "  %s: %s\n" % (k, v)
    logger.info(msg)
    
def order_download(params):
    """
    Orders and downloads images using the CSV exported from the EODMS UI.
    
    @type  params: dict
    @param params: A dictionary containing the arguments and values.
    """
    
    csv_fn = params['input']
    #session = params['session']
    
    logger = logging.getLogger('eodms')
    
    # Log the parameters
    log_parameters(params)
    
    if csv_fn.find('.csv') == -1:
        err_msg = "The provided input file is not a CSV file. " \
                    "Exiting process."
        common.print_support(err_msg)
        logger.error(err_msg)
        sys.exit(1)
    
    # Create info folder, if it doesn't exist, to store CSV files
    start_time = datetime.datetime.now()
    start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
    fn_str = start_time.strftime("%Y%m%d_%H%M%S")
    folder_str = start_time.strftime("%Y-%m-%d")
    
    logger.info("Process start time: %s" % start_str)
    
    common.EODMS_RAPI.get_collections()
    
    # Parse the maximum number of orders and items per order
    max_items = None
    max_images = None
    if params['maximum'] is not None:
        if params['maximum'].find(':') > -1:
            max_images, max_items = params['maximum'].split(':')
        else:
            max_items = None
            max_images = params['maximum']
    
    eodms_csv = csv_util.EODMS_CSV(csv_fn)
    query_imgs = eodms_csv.import_eodmsCSV()
    
    # Create order object
    eodms_order = utils.Orderer(max_items=max_items)
    
    orders = eodms_order.submit_orders(query_imgs)
    
    if not isinstance(orders, eodms.OrderList):
        common.print_support(orders)
        sys.exit(1)
    
    if orders.count_items() == 0:
        # If no orders could be found
        err_msg = "No orders were submitted successfully."
        common.print_support(err_msg)
        logger.error(err_msg)
        sys.exit(1)
    
    # Download images
    eodms_downloader = utils.Downloader(max_images, fn_str)
    eodms_downloader.download_orders(orders)
    eodms_downloader.export_csv()
    
    end_time = datetime.datetime.now()
    end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
    
    logger.info("End time: %s" % end_str)
    
    return None
    
def search_orderDownload(params):
    """
    Runs all steps: querying, ordering and downloading
    
    @type  params: dict
    @param params: A dictionary containing the arguments and values.
    """
    
    logger = logging.getLogger('eodms')
    
    # Log the parameters
    log_parameters(params)
    
    # Get all the values from the parameters
    collections = params['collections']
    dates = params['dates']
    aoi = params['input']
    filters = params['filters']
    # eodms_rapi = params['eodms_rapi']
    option = params['option']
    
    if aoi.find('.shp') == -1 and aoi.find('.gml') == -1 \
        and aoi.find('.kml') == -1 and aoi.find('.json') == -1 \
        and aoi.find('.geojson') == -1:
        err_msg = "The provided input file is not a valid AOI " \
                    "file. Exiting process."
        common.print_support()
        logger.error(err_msg)
        sys.exit(1)
    
    # Create info folder, if it doesn't exist, to store CSV files
    start_time = datetime.datetime.now()
    start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
    fn_str = start_time.strftime("%Y%m%d_%H%M%S")
    folder_str = start_time.strftime("%Y-%m-%d")
    
    logger.info("Process start time: %s" % start_str)
        
    common.EODMS_RAPI.get_collections()
    
    # Parse the maximum number of orders and items per order
    max_items = None
    max_images = None
    if params['maximum'] is not None:
        if params['maximum'].find(':') > -1:
            max_images, max_items = params['maximum'].split(':')
        else:
            max_items = None
            max_images = params['maximum']
            
    # Check if AOI exists
    if not os.path.exists(aoi):
        err_msg = "The AOI file '%s' cannot be found." % aoi
        common.print_support(err_msg)
        logger.error(err_msg)
        sys.exit(1)
    
    # Search for records using input AOI file
    eodms_query = utils.Query(collections, dates, aoi, \
                    max_images, filters)
    query_imgs = eodms_query.query_records()
    
    if not isinstance(query_imgs, eodms.ImageList):
        logger.error(query_imgs)
        print("\nExiting process.")
        sys.exit(1)
    
    # Export the results to a GeoJSON
    eodms_geo = geo.Geo()
    
    if aoi.find('.shp') > -1 and not geo.GDAL_INCLUDED:
        err_msg = "\nCannot open a Shapefile without GDAL. Please install " \
            "the GDAL Python package if you'd like to use a Shapefile " \
            "for your AOI."
        print(err_msg)
        logger.error(err_msg)
        sys.exit(1)
    
    # Check for any errors
    if isinstance(query_imgs, utils.QueryError):
        err_msg = "Query to RAPI failed due to '%s'" % \
                    query_imgs.get_msg()
        common.print_support(err_msg)
        logger.error(err_msg)
        sys.exit(1)
    
    # If no results were found, inform user and end process
    if query_imgs.count() == 0:
        err_msg = "No results found for given AOI."
        common.print_support(err_msg)
        logger.error(err_msg)
        sys.exit(1)
    
    # Export the query results to the CSV info file
    # query_imgs.export_csv(res_bname)
    
    msg = "%s images returned from search results.\n" % \
            query_imgs.count()
    common.print_footer('Query Results', msg)
    
    # # Inform the user of the total number of found images and ask if 
    # #   they'd like to continue
    if max_images is None or max_images == '':
        # print("option: %s" % option)
        if not option == 'download_only' and not option == 'search_only':
            if not common.SILENT:
                answer = input("\n%s images found intersecting your AOI. " \
                            "Proceed with ordering? (y/n): " % \
                            query_imgs.count())
                if answer.lower().find('n') > -1:
                    print("Exiting process.")
                    common.print_support()
                    logger.info("Process stopped by user.")
                    sys.exit(0)
                    
        elif option == 'search_only':
            query_imgs.export_csv(fn_str)
            print("\n%s images found intersecting your AOI." % query_imgs.count())
            print("\nPlease check the results folder for more info.")
            print("\nExiting process.")
            common.print_support()
            sys.exit(0)
        else:
            common.print_msg("Proceeding to download the %s images." % \
                query_imgs.count())
    else:
        common.print_msg("Proceeding to download the first %s images." % \
            max_images)
        query_imgs.trim(max_images)
    
    # Create order object
    eodms_order = utils.Orderer(max_items=max_items)
    if option == 'download_only':
        # If the user only wants to download a previous order
        #   query the RAPI using the AOI and then user the 
        #   query results to get a list of orders
        orders = eodms_order.get_orders(query_imgs, max_images)
        
        if orders.count_items() == 0:
            if common.SILENT:
                print("\nNo previous orders could be found.")
                common.print_support()
                logger.info("No previous orders could be found.")
                sys.exit(0)
            else:
                msg = "\nNo existing orders could be found for the given AOI. " \
                        "Would you like to order the images? (y/n): "
                answer = input(msg)
                if answer.lower().find('y') > -1:
                    orders = eodms_order.submit_orders(query_imgs)
                else:
                    common.print_support()
                    logger.info("Process ended by user.")
                    sys.exit(0)
    else:
        orders = eodms_order.submit_orders(query_imgs)
    
    if not isinstance(orders, eodms.OrderList):
        common.print_support(orders)
        logger.error(orders)
        sys.exit(1)
    
    if orders.count_items() == 0:
        # If no orders could be found
        err_msg = "No orders were submitted successfully."
        common.print_support(err_msg)
        logger.error(err_msg)
        sys.exit(1)
    
    # Download images
    eodms_downloader = utils.Downloader(max_images, fn_str)
    eodms_downloader.download_orders(orders)
    eodms_downloader.export_csv()
    
    end_time = datetime.datetime.now()
    end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
    
    logger.info("End time: %s" % end_str)
    
    return None

def main():

    # Create info folder, if it doesn't exist, to store CSV files
    start_time = datetime.datetime.now()
    start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        choices = {'full': 'Search, order & download images using ' \
                    'an AOI', \
                'order_csv': 'Order & download images using EODMS UI ' \
                    'search results (CSV file)', 
                'download_aoi': 'Download existing orders using AOI ' \
                    'file and RAPI query', 
                'download_only': 'Download existing orders using a ' \
                    'CSV file from a previous order/download process ' \
                    '(files found under "results" folder)', 
                'search_only': 'Run only a search based on an AOI '\
                    'and input parameters'}
        
        parser = argparse.ArgumentParser(description='Search & Order EODMS ' \
                            'products.')
        
        parser.add_argument('-u', '--username', help='The username of the ' \
                            'EODMS account used for authentication.')
        parser.add_argument('-p', '--password', help='The password of the ' \
                            'EODMS account used for authentication.')
        parser.add_argument('-i', '--input', help='An input file, can ' \
                            'either be an AOI or a CSV file exported from ' \
                            'the EODMS UI. Valid AOI formats are GeoJSON, ' \
                            'KML or Shapefile (Shapefile requires the GDAL ' \
                            'Python package).')
        parser.add_argument('-c', '--collections', help='The collection of ' \
                            'the images being ordered (separate multiple ' \
                            'collections with a comma).')
        parser.add_argument('-f', '--filters', help='A list of filters for ' \
                            'a specific collection.')
        parser.add_argument('-d', '--dates', help='The date ranges for the ' \
                            'search.')
        parser.add_argument('-m', '--maximum', help='The maximum number ' \
                            'of images to order and download and the maximum ' \
                            'number of images per order, separated by a colon.')
        parser.add_argument('-o', '--option', help='The type of process to run ' \
                            'from this list of options:\n%s' % \
                            '\n'.join(["%s: %s" % (k, v) for k, v in \
                            choices.items()]))
        parser.add_argument('-s', '--silent', action='store_true', \
                            help='Sets process to silent ' \
                            'which supresses all questions.')
        
        args = parser.parse_args()
        
        user = args.username
        password = args.password
        coll = args.collections
        dates = args.dates
        input_fn = args.input
        filters = args.filters
        maximum = args.maximum
        option = args.option
        common.SILENT = args.silent
        
        print("\n##########################################################" \
                "#######################")
        print("# EODMS API Orderer & Downloader                            " \
                "                    #")
        print("############################################################" \
                "#####################")
        
        params = {}
        
        # Set all the parameters from the config.ini file
        config_info = get_config()
        
        abs_path = os.path.abspath(__file__)
        download_path = config_info.get('Script', 'downloads')
        if download_path == '':
            common.DOWNLOAD_PATH = os.path.join(os.path.dirname(abs_path), \
                                    'downloads')
        elif not os.path.isabs(download_path):
            common.DOWNLOAD_PATH = os.path.join(os.path.dirname(abs_path), \
                                    download_path)
        else:
            common.DOWNLOAD_PATH = download_path
            
        print("\nImages will be downloaded to '%s'." % common.DOWNLOAD_PATH)
        
        res_path = config_info.get('Script', 'results')
        if res_path == '':
            common.RESULTS_PATH = os.path.join(os.path.dirname(abs_path), \
                                    'results')
        elif not os.path.isabs(res_path):
            common.RESULTS_PATH = os.path.join(os.path.dirname(abs_path), \
                                    res_path)
        else:
            common.RESULTS_PATH = res_path
            
        log_loc = config_info.get('Script', 'log')
        if log_loc == '':
            common.LOG_PATH = os.path.join(os.path.dirname(abs_path), \
                                    'log', 'logger.log')
        elif not os.path.isabs(log_loc):
            common.LOG_PATH = os.path.join(os.path.dirname(abs_path), \
                                    log_loc)
        else:
            common.LOG_PATH = log_loc
            
        # Setup logging
        logger = logging.getLogger('eodms')
        logger.setLevel(logging.DEBUG)
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - ' \
                    '%(message)s', datefmt='%Y-%m-%d %I:%M:%S %p')
        
        if not os.path.exists(os.path.dirname(common.LOG_PATH)):
            pathlib.Path(os.path.dirname(common.LOG_PATH)).mkdir(\
                parents=True, exist_ok=True)
        
        logHandler = handlers.RotatingFileHandler(common.LOG_PATH, \
                        maxBytes=500000, backupCount=2)
        logHandler.setLevel(logging.DEBUG)
        logHandler.setFormatter(formatter)
        logger.addHandler(logHandler)
        
        logger.info("Script start time: %s" % start_str)
            
        common.TIMEOUT_QUERY = config_info.get('Script', 'timeout_query')
        common.TIMEOUT_ORDER = config_info.get('Script', 'timeout_order')
        
        try:
            common.TIMEOUT_QUERY = float(common.TIMEOUT_QUERY)
        except ValueError:
            common.TIMEOUT_QUERY = 60.0
            
        try:
            common.TIMEOUT_ORDER = float(common.TIMEOUT_ORDER)
        except ValueError:
            common.TIMEOUT_ORDER = 180.0
            
        # Get the total number of results per query
        common.MAX_RESULTS = config_info.get('RAPI', 'max_results')
            
        print("\nCSV Results will be placed in '%s'." % common.RESULTS_PATH)
            
        # Get authentication if not specified
        new_user = False
        new_pass = False
        
        if user is None:
            
            user = config_info.get('RAPI', 'username')
            if user == '':
                msg = "\nEnter the username for authentication"
                err_msg = "A username is required to order images."
                user = get_input(msg, err_msg)
                new_user = True
            else:
                print("\nUsing the username set in the 'config.ini' file...")
                
        if password is None:
            
            password = config_info.get('RAPI', 'password')
            
            if password == '':
                msg = 'Enter the password for authentication'
                err_msg = "A password is required to order images."
                password = get_input(msg, err_msg, password=True)
                new_pass = True
            else:
                password = base64.b64decode(password).decode("utf-8")
                print("Using the password set in the 'config.ini' file...")
                
        if new_user or new_pass:
            suggestion = ''
            if common.SILENT:
                suggestion = " (it is best to store the credentials if " \
                            "you'd like to run the script in silent mode)"
            
            answer = input("\nWould you like to store the credentials " \
                    "for a future session%s? (y/n):" % suggestion)
            if answer.lower().find('y') > -1:
                config_info.set('RAPI', 'username', user)
                pass_enc = base64.b64encode(password.encode("utf-8")).decode("utf-8")
                config_info.set('RAPI', 'password', \
                    str(pass_enc))
                
                config_fn = os.path.join(os.path.dirname(\
                            os.path.abspath(__file__)), \
                            'config.ini')
                cfgfile = open(config_fn, 'w')
                config_info.write(cfgfile, space_around_delimiters=False)
                cfgfile.close()
        
        # Get number of attempts when querying the RAPI
        common.ATTEMPTS = config_info.get('RAPI', 'access_attempts')
        
        try:
            common.ATTEMPTS = int(common.ATTEMPTS)
        except ValueError:
            common.ATTEMPTS = 4
            
            
        session = requests.Session()
        session.auth = (user, password)
        common.EODMS_RAPI = utils.EODMSRAPI(session)
        
        params = {'collections': coll, 
                'dates': dates, 
                'input': input_fn, 
                'maximum': maximum, 
                'option': option}
        # params['eodms_rapi'] = eodms_rapi
        
        coll_lst = common.EODMS_RAPI.get_collections(True)
        
        print("\n(For more information on the following prompts, please refer" \
                " to the README file.)")
        
        if option is None:
            if common.SILENT:
                option = 'full'
            else:
                option = input("\nWhat would you like to do?\n%s\nPlease choose " \
                        "an option [1]: " % '\n'.join(["%s: %s" % (idx + 1, v) \
                            for idx, v in enumerate(choices.values())]))
                        
                if option == '':
                    option = 'full'
                elif int(option) > len(choices.keys()):
                    common.print_support("Not a valid option choice.")
                    logger.error("Invalid value entered for the 'option' " \
                                "parameter.")
                    sys.exit(1)
                else:
                    option = list(choices.keys())[int(option) - 1]
                    
        params['option'] = option
        
        if option == 'full' or option == 'download_aoi' \
            or option == 'search_only':
            # Search, order & download using an AOI
            
            if option == 'download_aoi':
                logger.info("Downloading existing orders using an AOI.")
            elif option == 'search_only':
                logger.info("Searching for images using an AOI.")
            else:
                logger.info("Searching, ordering and downloading images " \
                            "using an AOI.")
            
            # Get the AOI file
            if input_fn is None or input_fn == '':
                
                if common.SILENT:
                    err_msg = "No AOI file specified. Exiting process."
                    common.print_support(err_msg)
                    logger.error(err_msg)
                    sys.exit(1)
                
                msg = "\nEnter the full path name of a GML, KML, Shapefile or " \
                        "GeoJSON containing an AOI to restrict the search " \
                        "to a specific location"
                err_msg = "No AOI specified. Please enter a valid GML, KML, " \
                        "Shapefile or GeoJSON file"
                input_fn = get_input(msg, err_msg)
            else:
                if input_fn.find('.shp') > -1:
                    try:
                        import ogr
                    except ImportError:
                        err_msg = "Cannot open a Shapefile without GDAL. Please install " \
                            "the GDAL Python package if you'd like to use a Shapefile " \
                            "for your AOI."
                        print("\n%s" % err_msg)
                        logger.error(err_msg)
                        sys.exit(1)
                        
            input_fn = input_fn.strip()
            input_fn = input_fn.strip("'")
            input_fn = input_fn.strip('"')
            input_fn = os.path.abspath(input_fn)
                
            params['input'] = input_fn
            
            # Get the collection(s)
            if coll is None:
                
                if common.SILENT:
                    err_msg = "No collection specified. Exiting process."
                    common.print_support(err_msg)
                    logger.error(err_msg)
                    sys.exit(1)
                
                # List available collections for this user
                print("\nAvailable Collections:")
                for idx, c in enumerate(coll_lst):
                    if c == 'National Air Photo Library':
                        c += ' (open data only)'
                    print("%s. %s" % (idx + 1, c))
                
                # Prompted user for number(s) from list
                msg = "Enter the number of a collection from the list " \
                        "above (for multiple collections, enter each number " \
                        "separated with a comma)"
                err_msg = "At least one collection must be specified."
                in_coll = get_input(msg, err_msg)
                
                # Convert number(s) to collection name(s)
                coll_vals = in_coll.split(',')
                coll = [coll_lst[int(i) - 1] for i in coll_vals if i.isdigit()]
            else:
                coll = coll.split(',')
                
            params['collections'] = coll
            
            if filters is None:
                filt_dict = {}
                # Ask for the filters for the given collection(s)
                for coll in params['collections']:
                    coll_id = common.EODMS_RAPI.get_collIdByName(coll)
                    if coll_id in common.FILT_MAP.keys():
                        print("\nAvailable filters for '%s':" % coll)
                        for c in common.FILT_MAP[coll_id].keys():
                            print("  %s" % c)
                        msg = "Enter the filters you would like to apply " \
                                "to the query (in the format of " \
                                "<filter_id>=<value>|<value>|...; " \
                                "separate each filter property with a comma)"
                        
                        filt_items = input("%s:\n" % msg)
                        
                        #filt_items = get_input(msg, required=False)
                        
                        if filt_items == '':
                            filt_dict[coll_id] = []
                        else:
                            filt_items = filt_items.split(',')
                            # In case the user put collections in filters
                            filt_items = [f.split('.')[1] if f.find('.') > -1 \
                                else f for f in filt_items]
                            filt_dict[coll_id] = filt_items
            else:
                # User specified in command-line
                
                # Possible formats:
                #   1. Only one collection: <field_id>=<value>|<value>,<field_id>=<value>&<value>,...
                #   2. Multiple collections but only specifying one set of filters:
                #       <coll_id>.<filter_id>=<value>|<value>,...
                #   3. Multiple collections with filters:
                #       <coll_id>.<filter_id>=<value>,...<coll_id>.<filter_id>=<value>,...
                
                filt_dict = {}
                
                # Split filters by comma
                filt_lst = filters.split(',')
                for f in filt_lst:
                    if f.find('.') > -1:
                        coll_id, filt_items = f.split('.')
                        if coll_id in filt_dict.keys():
                            coll_filters = filt_dict[coll_id]
                        else:
                            coll_filters = []
                        coll_filters.append(filt_items.replace('"', '').\
                            replace("'", ''))
                        filt_dict[coll_id] = coll_filters
                    else:
                        coll_id = common.EODMS_RAPI.get_collIdByName(coll)
                        if coll_id in filt_dict.keys():
                            coll_filters = filt_dict[coll_id]
                        else:
                            coll_filters = []
                        coll_filters.append(f)
                        filt_dict[coll_id] = coll_filters
            
            params['filters'] = filt_dict
            
            # Get the date range
            #date_lst = []
            if dates is None:
                
                if not common.SILENT:
                    msg = "\nEnter a date range (ex: 20200525-20200630) " \
                            "or a previous time-frame (24 hours) " \
                            "(leave blank to search all years)"
                    dates = get_input(msg, required=False)
            
            params['dates'] = dates
            
            if not option == 'search_only':
                if maximum is None or maximum == '':
                    
                    if not common.SILENT:
                        msg = "\nEnter the total number of images you'd like to " \
                            "order (leave blank for no limit)"
                        
                        total_records = get_input(msg, required=False)
                        
                        msg = "\nIf you'd like a limit of images per order, enter a " \
                            "value (EODMS sets a maximum limit of 100)"
                    
                        order_limit = get_input(msg, required=False)
                        
                        maximum = ':'.join(filter(None, [total_records, order_limit]))
                    
                params['maximum'] = maximum
            
            #print("params: %s" % params)
            print("\nUse this command-line syntax to run the same parameters:")
            cli_syntax = build_syntax(parser, params)
            print(cli_syntax)
            logger.info("Command-line Syntax: %s" % cli_syntax)
            search_orderDownload(params)
            
        elif option == 'order_csv':
            # Order & download images using EODMS UI CSV file
            
            logger.info("Ordering and downloading images using results " \
                        "from a CSV file.")
            
            # Get the CSV file
            if input_fn is None or input_fn == '':
                
                if common.SILENT:
                    err_msg = "No CSV file specified. Exiting process."
                    common.print_support(err_msg)
                    logger.error(err_msg)
                    sys.exit(1)
                
                msg = "\nEnter the full path name of the CSV file exported "\
                        "from the EODMS UI website"
                err_msg = "No CSV specified. Please enter a valid CSV file"
                input_fn = get_input(msg, err_msg)
                
            params['input'] = input_fn
            
            print("\nUse this command-line syntax to run the same parameters:")
            cli_syntax = build_syntax(parser, params)
            print(cli_syntax)
            logger.info("Command-line Syntax: %s" % cli_syntax)
            
            order_download(params)
            
        elif option == 'download_only':
            # Download existing orders using CSV file from previous session
            
            logger.info("Downloading images using results from a CSV file " \
                        "from a previous session.")
            
            # Get the CSV file
            if input_fn is None or input_fn == '':
                
                if common.SILENT:
                    err_msg = "No CSV file specified. Exiting process."
                    common.print_support(err_msg)
                    logger.error(err_msg)
                    sys.exit(1)
                
                msg = "\nEnter the full path name the CSV file export from " \
                        "the EODMS UI website"
                err_msg = "No CSV specified. Please enter a valid CSV file"
                input_fn = get_input(msg, err_msg)
                
            params['input'] = input_fn
            
            print("\nUse this command-line syntax to run the same parameters:")
            cli_syntax = build_syntax(parser, params)
            print(cli_syntax)
            logger.info("Command-line Syntax: %s" % cli_syntax)
            
            download(params)
        else:
            common.print_support("That is not a valid option.")
            logger.error("An invalid parameter was entered during the prompt.")
            sys.exit(1)
            
        print("\nProcess complete.")
        
        common.print_support()
    
    except KeyboardInterrupt as err:
        msg = "Process ended by user."
        print("\n" % msg)
        common.print_support()
        logger.info(msg)
        sys.exit(1)
    except Exception:
        trc_back = "\n%s" % traceback.format_exc()
        common.print_support(trc_back)
        logger.error(traceback.format_exc())

if __name__ == '__main__':
	sys.exit(main())