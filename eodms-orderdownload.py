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
    
    syntax_params = []
    for p, pv in params.items():
        if pv is None or pv == '': continue
        if p == 'session': continue
        action = actions['--%s' % p]
        flag = action.option_strings[0]
        
        if isinstance(pv, list):
            if flag == '-d':
                pv = '-'.join(['"%s"' % i if i.find(' ') > -1 else i \
                        for i in pv ])
            else:
                pv = ','.join(['"%s"' % i if i.find(' ') > -1 else i \
                        for i in pv ])
        else:
            if isinstance(pv, str) and pv.find(' ') > -1:
                pv = '"%s"' % pv
        
        syntax_params.append('%s %s' % (flag, pv))
        
    out_syntax = "python %s %s" % (os.path.realpath(__file__), \
                    ' '.join(syntax_params))
    
    return out_syntax
                
def run(params):
    """
    Runs all steps: querying, ordering and downloading
    
    @type  params: dict
    @param params: A dictionary containing the arguments and values.
    """
    
    # Get all the values from the parameters
    collections = params['collections']
    dates = params['dates']
    if params['input'].find('.csv') > -1:
        csv_fn = params['input']
        aoi = None
    else:
        aoi = params['input']
        csv_fn = None
    session = params['session']
    order_only = params['order']
    download_only = params['download']
    
    # Create info folder, if it doesn't exist, to store CSV files
    start_time = datetime.datetime.now()
    fn_str = start_time.strftime("%Y%m%d_%H%M%S")
    folder_str = start_time.strftime("%Y-%m-%d")
    # res_folder = os.path.abspath("info\\%s" % folder_str)
    # res_bname = "%s\\%s" % (res_folder, fn_str)
    # if not os.path.exists(res_folder):
        # os.mkdir(res_folder)
        
    if not common.RAPI_COLLECTIONS:
        common.get_collections(session)
    
    # Parse the maximum number of orders and items per order
    max_items = None
    max_images = None
    if params['maximum'] is not None:
        if params['maximum'].find(':') > -1:
            max_images, max_items = params['maximum'].split(':')
        else:
            max_items = None
            max_images = params['maximum']    
    
    if csv_fn is None or csv_fn == '':
        # Check if AOI exists
        if not os.path.exists(aoi):
            err_msg = "The AOI file '%s' cannot be found." % aoi
            common.print_support(err_msg)
            sys.exit(1)
        
        # If no CSV file was specified, search for records using input AOI file
        eodms_query = utils.Query(session, collections, dates, aoi, \
                        max_images)
        query_imgs = eodms_query.query_records()
        
        # Export the results to a GeoJSON
        eodms_geo = geo.Geo()
        # geojson_fn = "%s\\%s_results.geojson" % (res_folder, fn_str)
        # eodms_geo.export_results(query_imgs, geojson_fn)
        
        # Check for any errors
        if isinstance(query_imgs, utils.QueryError):
            err_msg = "Query to RAPI failed due to '%s'" % \
                        query_imgs.get_msg()
            common.print_support(err_msg)
            sys.exit(1)
        
        # If no results were found, inform user and end process
        if query_imgs.count() == 0:
            common.print_support("No results found for given AOI.")
            sys.exit(1)
        
        # Export the query results to the CSV info file
        # query_imgs.export_csv(res_bname)
        
        msg = "%s images returned from search results.\n" % \
                query_imgs.count()
        common.print_footer('Query Results', msg)
        
        if max_images is not None and not max_images == '':
            if (order_only and not download_only) \
                or (not order_only and not download_only):
                common.print_msg("Maximum orders set to %s. Proceeding with the " \
                    "first %s images.\n" % (max_images, max_images))
                query_imgs.trim(max_images)
        
        # Inform the user of the total number of found images and ask if 
        #   they'd like to continue
        if (order_only and not download_only) \
            or (not order_only and not download_only):
            if max_images is None or max_images == '':
                answer = input("\n%s images found intersecting your AOI. " \
                            "Proceed with ordering? (y/n): " % \
                            query_imgs.count())
                if answer.lower().find('n') > -1:
                    print("Exiting process.")
                    common.print_support()
                    sys.exit(0)
        else:
            common.print_msg("Using these results to extract the existing " \
                "order items.")
    else:
        # If the input file is a CSV (from EODMS UI), import it
        eodms_csv = csv_util.EODMS_CSV(csv_fn, session)
        query_imgs = eodms_csv.import_csv()
    
    # Create order object
    eodms_order = utils.Orderer(session, max_items=max_items)
    if (order_only and not download_only) \
        or (not order_only and not download_only):
        # If the user specified they want to order images
        orders = eodms_order.submit_orders(query_imgs)
        #print("orders: %s" % orders)
        # orders.export_csv(res_bname)
    else:
        # If the user only wants to download a previous order
        #   query the RAPI using the AOI and then user the 
        #   query results to get a list of orders
        orders = eodms_order.get_orders(query_imgs)
        
        if orders.count_items() == 0:
            msg = "\nNo existing orders could be found for the given AOI. " \
                    "Would you like to order the images? (y/n): "
            answer = input(msg)
            if answer.lower().find('y') > -1:
                orders = eodms_order.submit_orders(query_imgs)
                # orders.export_csv(res_bname)
            else:
                common.print_support()
                sys.exit(1)
    
    if orders.count_items() == 0:
        # If no orders could be found
        common.print_support("No orders were submitted successfully.")
        sys.exit(1)
    
    if download_only and not order_only \
        or (not order_only and not download_only):
        # If the user specified to download images
        eodms_downloader = utils.Downloader(session, max_images)
        eodms_downloader.download_orders(orders)
        # eodms_downloader.export_csv(res_bname)
    
    return None

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
        sys.exit(1)
        
    return in_val

def main():
    
    try:
        parser = argparse.ArgumentParser(description='Search & Order EODMS ' \
                            'products.')
        
        parser.add_argument('-u', '--username', help='The username of the ' \
                            'EODMS account used for authentication.')
        parser.add_argument('-p', '--password', help='The password of the ' \
                            'EODMS account used for authentication.')
        parser.add_argument('-c', '--collections', help='The collection of ' \
                            'the images being ordered (separate multiple ' \
                            'collections with a comma).')
        parser.add_argument('-d', '--dates', help='The date range for the ' \
                            'search.')
        parser.add_argument('-i', '--input', help='An input file, can ' \
                            'either be an AOI (shapefile, KML or GeoJSON) ' \
                            'or a CSV file exported from the EODMS UI.')
        parser.add_argument('-m', '--maximum', help='The maximum number ' \
                            'of images to order and download and the maximum ' \
                            'number of images per order, separated by a colon.')
        parser.add_argument('-o', '--order', help='If set, only query ' \
                            'and order images, do not download.', \
                            action='store_true')
        parser.add_argument('-l', '--download', help='If set, only query ' \
                            'and download images, do not order.', \
                            action='store_true')
        
        # parser.add_argument('-r', '--recordid', help='The record ID for a ' \
                            # 'single image. If this parameter is entered, ' \
                            # 'only the image with this ID will be ordered.')
        # parser.add_argument('-i', '--input', help='A CSV file containing a ' \
                            # 'list of record IDs. The process will only ' \
                            # 'order the images from this file.\nThe file ' \
                            # 'should contain a column called "Record ID", ' \
                            # '"Sequence ID" or "Downlink Segment ID" with ' \
                            # 'an "Order Key" column.')
        # parser.add_argument('-c', '--collection', help='The collection of ' \
                            # 'the images being ordered.')
        
        args = parser.parse_args()
        
        user = args.username
        password = args.password
        coll = args.collections
        dates = args.dates
        input_fn = args.input
        maximum = args.maximum
        order = args.order
        download = args.download
        
        
        print("\n##########################################################" \
                "#######################")
        print("# EODMS API Orderer & Downloader                            " \
                "                    #")
        print("############################################################" \
                "#####################")
        
        params = {}
        
        # Get authentication if not specified
        if user is None:
            msg = "\nEnter the username for authentication"
            err_msg = "A username is required to order images."
            user = get_input(msg, err_msg)
                
        if password is None:
            msg = 'Enter the password for authentication'
            err_msg = "A password is required to order images."
            password = get_input(msg, err_msg, password=True)
            
        session = requests.Session()
        session.auth = (user, password)
        
        params = {'collections': coll, 
                'dates': dates, 
                'input': input_fn, 
                'maximum': maximum, 
                'order': order, 
                'download': download}
        params['session'] = session
        
        # for k, v in params.items():
            # print("%s: %s" % (k, v))
        
        if input_fn is None or input_fn.find('.csv') == -1:
            # If no CSV file was entered, the user wants to conduct a 
            #   search first. Get the required variables from the user.
            
            # Get the collection(s)
            if coll is None:
                
                coll_lst = common.get_collections(session, True)
                
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
                coll = [coll_lst[int(i) - 1] for i in coll_vals]
            else:
                coll = coll.split(',')
                
            params['collections'] = coll
                
            # Get the date range
            date_lst = []
            if dates is None:
                
                msg = "\nEnter to dates, separated by dash, for the date " \
                        "range (format: yyyymmdd) (ex: 20100525-20201013) " \
                        "(leave blank to search all years)"
                dates = get_input(msg, required=False)
                if not dates == '':
                    if dates.find('-') == -1 and not dates == '':
                        common.print_support("No date range was provided. " \
                            "Please enter 2 dates separated by a dash.")
                        sys.exit(1)
                    date_lst = dates.split('-')
            else:
                date_lst = dates.split('-')
                
            params['dates'] = date_lst
                
            # Get the AOI file
            if input_fn is None or input_fn == '':
                
                msg = "\nEnter the full path name of a GML, KML, Shapefile or " \
                        "GeoJSON containing an AOI to restrict the search " \
                        "to a specific location"
                err_msg = "No AOI specified. Please enter a valid GML, KML, " \
                        "Shapefile or GeoJSON file"
                input_fn = get_input(msg, err_msg)
                
            params['input'] = input_fn
            
            # if (order and not download) \
                # or (not order and not download):
                # if sel_val.lower().find('c') > -1:
                    # sel_val = 'choose'
                # else:
                    # sel_val = 'all'
                        
                # params['select'] = sel_val
                
            if maximum is None or maximum == '':
                
                if download and not order:
                    msg = "\nEnter the total number of images you'd like to " \
                        "download (leave blank for no limit)"
                else:
                    msg = "\nEnter the total number of images you'd like to " \
                        "order (leave blank for no limit)"
                
                total_records = get_input(msg, required=False)
                
                #print("download: %s" % download)
                #print("order: %s" % order)
                
                order_limit = None
                if (order and not download) \
                    or (not order and not download):
                    msg = "\nIf you'd like a limit of images per order, enter a " \
                        "value (EODMS sets a maximum limit of 100)"
                
                    order_limit = get_input(msg, required=False)
                
                maximum = ':'.join(filter(None, [total_records, order_limit]))
                
                # print("maximum: %s" % maximum)
                
            params['maximum'] = maximum
                
        print("\nUse this command-line syntax to run the same parameters:")
        print(build_syntax(parser, params))
            
        run(params)
            
        print("\nProcess complete.")
        
        common.print_support()
    
    except KeyboardInterrupt as err:
        print("\nProcess ended by user.")
        common.print_support()
        sys.exit(1)
    except Exception:
        trc_back = "\n%s" % traceback.format_exc()
        common.print_support(trc_back)

if __name__ == '__main__':
	sys.exit(main())