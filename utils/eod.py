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

import sys
import os
import re
import requests
from tqdm.auto import tqdm
# import argparse
# import traceback
# import getpass
import datetime
import dateparser
import dateutil.parser as util_parser
import json
import glob
# import configparser
# import base64
import logging
import logging.handlers as handlers
# import pathlib

from eodms_rapi import EODMSRAPI

try:
    import dateparser
except:
    msg = "Dateparser package is not installed. Please install and run script again."
    common.print_support(msg)
    logger.error(msg)
    sys.exit(1)

from . import csv_util
from . import image
from . import spatial

class Eodms_OrderDownload:
    
    def __init__(self, **kwargs):
        """
        Initializer for the Eodms_OrderDownload.
        
        :param kwargs: Options include:<br>
                username (str): The username of the EODMS account.<br>
                password (str): The password of the EODMS account.<br>
                downloads (str): The path where the image files will be downloaded.<br>
                results (str): The path where the results CSV files will be stored.<br>
                log (str): The path where the log file is stored.<br>
                timeout_query (float): The timeout for querying the RAPI.<br>
                timeout_order (float): The timeout for ordering in the RAPI.<br>
                max_res (int): The maximum number of results to order.<br>
                silent (boolean): False to prompt the user and print info, True to suppress it.<br>
        :type  kwargs: dict
        """
        
        self.rapi_domain = 'https://www.eodms-sgdot.nrcan-rncan.gc.ca'
        self.indent = 3

        self.operators = ['=', '<', '>', '<>', '<=', '>=', ' LIKE ', \
                        ' STARTS WITH ', ' ENDS WITH ', ' CONTAINS ', \
                        ' CONTAINED BY ', ' CROSSES ', ' DISJOINT WITH ', \
                        ' INTERSECTS ', ' OVERLAPS ', ' TOUCHES ', ' WITHIN ']
        
        self.username = kwargs.get('username')
        self.password = kwargs.get('password')
        
        self.logger = logging.getLogger('eodms')
        
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
        
        self.silent = False
        if kwargs.get('silent') is not None:
            self.silent = bool(kwargs.get('silent'))
        
        if self.username is not None and self.password is not None:
            self.eodms_rapi = EODMSRAPI(self.username, self.password)
        
        self.aoi_extensions = ['.gml', '.kml', '.json', '.geojson', '.shp']
        
        self.cur_res = None
        
        self.email = 'eodms-sgdot@nrcan-rncan.gc.ca'
        
        self.eodms_geo = spatial.Geo(self)
            
    def _parse_dates(self, in_dates):
        """
        Parses dates from the user into a format for the EODMSRAPI
        
        :param in_dates: A string containing either a time interval 
                (24 hours, 3 months, etc.) or a range of dates 
                (20200501-20210105T054540,...)
        :type  in_date: str
                
        :return: A list of dictionaries containing keys 'start' and 'end' 
                with the specific date ranges 
                (ex: [{'start': '20200105_045034', 'end': '20210105_000000'}])
        :rtype: list
        """
        
        if in_dates is None or in_dates == '': return ''
            
        time_words = ['hour', 'day', 'week', 'month', 'year']
        
        if any(word in in_dates for word in time_words):
            # start = dateparser.parse(in_dates).strftime("%Y%m%d_%H%M%S")
            # end = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            dates = [in_dates]
        else:
        
            # Modify date for the EODMSRAPI object
            date_ranges = in_dates.split(',')
            
            dates = []
            for rng in date_ranges:
                start, end = rng.split('-')
                if start.lower().find('t') > -1:
                    start = start.lower().replace('t', '_')
                else:
                    start = '%s_000000' % start
                    
                if end.lower().find('t') > -1:
                    end = end.lower().replace('t', '_')
                else:
                    end = '%s_000000' % end
                
            dates.append({'start': start, 'end': end})
            
        return dates
        
    def _parse_filters(self, filters, coll_id=None):
        """
        Parses filters into a format for the EODMSRAPI
        
        :param filters: A list of filters from a user for a specific 
                collection.
        :type  filters: list
        :param coll_id: The Collection ID for the filters.
        :type  coll_id: str
                
        :return: A dictionary containing filters in a format for the 
                EODMSRAPI (ex: {"Beam Mnemonic": {'=': ['16M11', '16M13']}, 
                                "Incidence Angle": {'>': ['45.0']}).
        :rtype: dict
        """
        
        out_filters = {}
        
        for filt in filters:
            
            filt = filt.upper()
                
            if not any(x in filt for x in self.operators):
                print("Filter '%s' entered incorrectly." % filt)
                continue
            
            ops = [x for x in self.operators if x in filt]

            for o in ops:
                filt_split = filt.split(o)
                op = o
                
            if coll_id is None:
                coll_id = self.coll_id
            
            # Convert the input field for EODMS_RAPI
            key = filt_split[0].strip()
            coll_fields = self.get_fieldMap()[coll_id]
            
            if not key in coll_fields.keys():
                err = "Filter '%s' is not available for Collection '%s'." \
                        % (key, coll_id)
                self.print_msg("WARNING: %s" % err)
                self.logger.warning(err)
                continue
                
            field = coll_fields[key]
            
            val = filt_split[1].strip()
            val = val.replace('"', '').replace("'", '')
            
            if val is None or val == '':
                err = "No value specified for Filter ID '%s'." % key
                self.print_msg("WARNING: %s" % err)
                self.logger.warning(err)
                continue
                
            out_filters[field] = (op, val.split('|'))
            
        return out_filters
        
    def _get_eodmsRes(self, csv_fn):
        """
        Gets the results based on a CSV file from the EODMS UI.
        
        :param csv_fn: The filename of the EODMS CSV file.
        :type  csv_fn: str
            
        :return: An ImageList object containing the images returned 
                from the EODMSRAPI.
        :rtype: image.ImageList
        """
        
        eodms_csv = csv_util.EODMS_CSV(self, csv_fn)
        csv_res = eodms_csv.import_eodmsCSV()
        
        ##################################################
        self.print_heading("Retrieving Record IDs for the list of " \
            "entries in the CSV file")
        ##################################################
        
        # Group all records into different collections
        coll_recs = {}
        for rec in csv_res:
            # Get the collection ID for the image
            collection = rec.get('collectionId')
            
            rec_lst = []
            if collection in coll_recs.keys():
                rec_lst = coll_recs[collection]
                
            rec_lst.append(rec)
            
            coll_recs[collection] = rec_lst
        
        all_res = []
        
        for coll, recs in coll_recs.items():
            
            coll_id = self.get_fullCollId(coll)
            
            filters = {}
            
            for idx in range(0, len(recs), 25):
                
                # Get the next 100 images
                if len(recs) < idx + 25:
                    sub_recs = recs[idx:]
                else:
                    sub_recs = recs[idx:25 + idx]
                    
                seq_ids = []
                
                for rec in sub_recs:
                    
                    id_val = None
                    for k in rec.keys():
                        if k.lower() in ['sequence id', 'record id', \
                            'recordid']:
                            # If the Sequence ID is in the image dictionary, 
                            #   return it as the Record ID
                            id_val = rec.get(k)
                    
                    if id_val is None:
                        # If the Order Key is in the image dictionary,
                        #   use it to query the RAPI
                        
                        order_key = rec.get('order key')
                        
                        if order_key is None or order_key == '':
                            msg = "Cannot determine record " \
                                    "ID for Result Number '%s' in the CSV file. " \
                                    "Skipping image." % rec.get('result number')
                            self.print_msg("WARNING: %s" % msg)
                            self.logger.warning(msg)
                            continue
                            
                        f = {'Order Key': ('=', [order_key])}
                        
                        # Send a query to the EODMSRAPI object
                        self.eodms_rapi.search(coll_id, f)
                        
                        res = self.eodms_rapi.get_results()
                        
                        if len(res) > 1:
                            msg = "Cannot determine record " \
                                    "ID for Result Number '%s' in the CSV file. " \
                                    "Skipping image." % rec.get('result number')
                            self.print_msg("WARNING: %s" % msg)
                            self.logger.warning(msg)
                            continue
                        
                        all_res += res
                        
                        continue
                        
                    seq_ids.append(id_val)
                    
                if len(seq_ids) == 0: continue
                
                filters['Sequence Id'] = ('=', seq_ids)
                    
                if coll == 'NAPL':
                    filters['Price'] = ('=', True)
                        
                # Send a query to the EODMSRAPI object
                self.eodms_rapi.search(coll, query=filters)
                
                res = self.eodms_rapi.get_results()
                
                # If the results is a list, an error occurred
                if res is None:
                    self.print_msg("WARNING: %s" % ' '.join(res))
                    self.logger.warning(' '.join(res))
                    continue
                
                # If no results, return as error
                if len(res) == 0:
                    err = "No images could be found."
                    common.print_msg("WARNING: %s" % err)
                    self.logger.warning(err)
                    common.print_msg("Skipping this entry", False)
                    self.logger.warning("Skipping this entry")
                    continue
                
                all_res += res
        
        # Convert results to ImageList
        self.results = image.ImageList(self)
        self.results.ingest_results(all_res)
        
        return self.results
        
    def _get_prevRes(self, csv_fn):
        """
        Creates a EODMSRAPI instance.
        
        :param csv_fn: The filename of the previous results CSV file.
        :type  csv_fn: str
        
        :return: A list of rows from the CSV file.
        :rtype: list
        """
        
        eodms_csv = csv_util.EODMS_CSV(self, csv_fn)
        csv_res = eodms_csv.import_csv()
        
        # Convert results to ImageList
        query_imgs = image.ImageList(self)
        query_imgs.ingest_results(csv_res, True)
        
        return query_imgs
        
    def _print_results(self, images):
        """
        Prints the results of image downloads.
        
        :param images: A list of images after they've been downloaded.
        :type  images: list
        """
        
        success_orders = []
        failed_orders = []
        
        for img in images.get_images():
            if img.get_metadata('status') == 'AVAILABLE_FOR_DOWNLOAD' or \
                img.get_metadata('status') == 'SUCCESS':
                success_orders.append(img)
            else:
                failed_orders.append(img)
        
        if len(success_orders) > 0:
            # Print information for all successful orders
            #   including the download location
            msg = "The following images have been downloaded:\n"
            for img in success_orders:
                rec_id = img.get_recordId()
                order_id = img.get_metadata('orderId')
                orderitem_id = img.get_metadata('itemId')
                dests = img.get_metadata('downloadPaths')
                for d in dests:
                    loc_dest = d['local_destination']
                    src_url = d['url']
                    msg += "\nRecord ID %s\n" % rec_id
                    msg += "    Order Item ID: %s\n" % orderitem_id
                    msg += "    Order ID: %s\n" % order_id
                    msg += "    Downloaded File: %s\n" % loc_dest
                    msg += "    Source URL: %s\n" % src_url
            self.print_footer('Successful Downloads', msg)
            self.logger.info("Successful Downloads: %s" % msg)
        
        if len(failed_orders) > 0:
            msg = "The following images did not download:\n"
            for img in failed_orders:
                rec_id = img.get_recordId()
                order_id = img.get_metadata('orderId')
                orderitem_id = img.get_metadata('itemId')
                status = img.get_metadata('status')
                stat_msg = img.get_metadata('statusMessage')
                
                msg += "\nRecord ID %s\n" % rec_id
                msg += "    Order Item ID: %s\n" % orderitem_id
                msg += "    Order ID: %s\n" % order_id
                msg += "    Status: %s\n" % status
                msg += "    Status Message: %s\n" % stat_msg
            self.print_footer('Failed Downloads', msg)
            self.logger.info("Failed Downloads: %s" % msg)
            
    def _parse_aws(self, query_imgs):
        
        aws_lst = []
        eodms_lst = []
        for res in query_imgs.get_raw():
            downloadLink = res.get('downloadLink')
            if downloadLink is not None and downloadLink.find('aws') > -1:
                aws_lst.append(res)
            else:
                eodms_lst.append(res)
        
        aws_imgs = image.ImageList(self)
        aws_imgs.ingest_results(aws_lst)
        
        eodms_imgs = image.ImageList(self)
        eodms_imgs.ingest_results(eodms_lst)
                
        print("\nNumber of AWS images: %s" % aws_imgs.count())
        print("Number of EODMS images: %s\n" % eodms_imgs.count())
        
        # answer = input("Press enter...")
        
        return eodms_imgs, aws_imgs
            
    def _submit_orders(self, imgs, priority=None, max_items=None):
        
        #############################################
        # Order Images
        #############################################
        
        # Convert results to JSON
        json_res = imgs.get_raw()
        
        # Separated AWS images from order list
        # Convert results to an OrderList
        
        orders = image.OrderList(self, imgs)
        
        # Send orders to the RAPI
        if max_items is None or max_items == 0:
            # Order all images in a single order
            order_res = self.eodms_rapi.order(json_res, priority)
            orders.ingest_results(order_res)
        else:
            # Divide the images into the specified number of images per order
            for idx in range(0, len(json_res), max_items):
                # Get the next 100 images
                if len(json_res) < idx + max_items:
                    sub_recs = json_res[idx:]
                else:
                    sub_recs = json_res[idx:max_items + idx]
                    
                order_res = self.eodms_rapi.order(sub_recs, priority)
                orders.ingest_results(order_res)
                
        # Update the self.cur_res for output results
        self.cur_res = imgs
        
        if orders.count_items() == 0:
            # If no orders could be found
            self.export_results()
            err_msg = "No orders were submitted successfully."
            self.print_support(err_msg)
            self.logger.error(err_msg)
            sys.exit(1)
            
        return orders
            
    def cleanup_folders(self):
        """
        Clean-ups the results and downloads folder.
        """
        
        # Cleanup results folder
        results_start = dateparser.parse(self.keep_results)
        
        if results_start is not None:        
            msg = "Cleaning up files older than %s in 'results' folder..." % \
                    self.keep_results
            print("\n%s" % msg)
            self.logger.info(msg)
            
            res_files = glob.glob(os.path.join(os.sep, self.results_path, '*.*'))
            
            for f in res_files:
                file_date = util_parser.parse(f, fuzzy=True)
                
                if file_date < results_start:
                    os.remove(f)
                
        # Cleanup downloads folder
        downloads_start = dateparser.parse(self.keep_downloads)
        
        if downloads_start is not None:
            msg = "Cleaning up files older than %s in 'downloads' folder..." % \
                    self.keep_downloads
            print(msg)
            self.logger.info(msg)
            
            downloads_files = glob.glob(os.path.join(os.sep, \
                                self.download_path, '*.*'))
                                
            for f in downloads_files:
                file_date = datetime.datetime.fromtimestamp(os.path.getmtime(f))
                
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
            out_date = '%s-%s-%sT%s:%s:%sZ' % (year, mth, day, hour, minute, sec)
        else:
            year = in_date[:4]
            mth = in_date[4:6]
            day = in_date[6:]
            out_date = '%s-%s-%sT00:00:00Z' % (year, mth, day)
                    
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
        
    def download_aws(self, aws_imgs):
        """
        Downloads a set of AWS images.
        
        :param aws_imgs: An ImageList object with a set of Image objects.
        :type  aws_imgs: image.ImageList
        """
        
        self.print_msg("Downloading AWS images first...")
        
        res = []
        for img in aws_imgs.get_images():
            dl_link = img.get_metadata('downloadLink')
            # for k, v in img.get_metadata().items():
            #     print("%s: %s" % (k, v))
            # answer = input("Press enter...")
            
            aws_f = os.path.basename(dl_link)
            dest_fn = os.path.join(self.download_path, aws_f)
            
            # print("dest_fn: %s" % dest_fn)
            
            # Get the file size of the link
            resp = requests.head(dl_link)
            # print("resp: %s" % resp.headers)
            fsize = resp.headers['content-length']
            
            # print("fsize: %s" % type(fsize))
            # print("dest_size: %s" % type(os.stat(dest_fn).st_size))
            # answer = input("Press enter...")
            
            if os.path.exists(dest_fn):
                # if all-good, continue to next file
                if os.stat(dest_fn).st_size == int(fsize):
                    msg = "No download necessary. " \
                        "Local file already exists: %s" % dest_fn
                    self.print_msg(msg)
                    continue
                # Otherwise, delete the incomplete/malformed local file and redownload
                else:
                    msg = 'Filesize mismatch with %s. Re-downloading...' % \
                        os.path.basename(dest_fn)
                    self.print_msg(msg, 'warning')
                    os.remove(dest_fn)
            # answer = input("Press enter...")
            
            # Use streamed download so we can wrap nicely with tqdm
            with requests.get(dl_link, stream=True) as stream:
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
        
    def export_results(self):
        """
        Exports results to a CSV file.
        """
        
        if self.cur_res is None: return None
        
        # Create EODMS_CSV object to export results
        res_fn = os.path.join(self.results_path, \
                "%s_Results.csv" % self.fn_str)
        res_csv = csv_util.EODMS_CSV(self, res_fn)
        
        res_csv.export_results(self.cur_res)
        
        msg = "Results exported to '%s'." % res_fn
        self.print_msg(msg, indent=False)
        
    def export_records(self, csv_f, header, records):
        """
        Exports a set of records to a CSV.
        
        :param csv_f: The CSV file to write to.
        :type  csv_f: (file object)
        :param header: A list containing the header for the file.
        :type  header: list
        :param records: A list of images.
        :type  records: list
        """
        
        # Write the values to the output CSV file
        for rec in records:
            out_vals = []
            for h in header:
                if h in rec.keys():
                    val = str(rec[h])
                    if val.find(',') > -1:
                        val = '"%s"' % val
                    out_vals.append(val)
                else:
                    out_vals.append('')
                    
            out_vals = [str(i) for i in out_vals]
            csv_f.write('%s\n' % ','.join(out_vals))
            
    def get_collIdByName(self, in_title): #, unsupported=False):
        """
        Gets the Collection ID based on the tile/name of the collection.
        
        :param in_title: The title/name of the collection. (ex: 'RCM Image Products' for ID 'RCMImageProducts')
        :type  in_title: str
        
        :return: The full Collection ID.
        :rtype: str
        """
        
        if isinstance(in_title, list):
            in_title = in_title[0]
        
        for k, v in self.eodms_rapi.get_collections().items():
            if v['title'].find(in_title) > -1:
                return k
                
        return self.get_fullCollId(in_title)
        
    def get_fullCollId(self, coll_id):
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
        order_res = self.eodms_rapi.get_ordersByRecords(json_res)
        
        # Convert results to an OrderList
        orders = image.OrderList(self, query_imgs)
        orders.ingest_results(order_res)
        
        if orders.count_items() == 0:
            # If no order are found...
            if self.silent:
                print("\nNo previous orders could be found.")
                # Export polygons of images
                self.eodms_geo.export_results(query_imgs, self.output)
                self.export_results()
                self.print_support()
                self.logger.info("No previous orders could be found.")
                sys.exit(0)
            else:
                # Ask user if they'd like to order the images
                msg = "\nNo existing orders could be found for the given AOI. " \
                        "Would you like to order the images? (y/n): "
                answer = input(msg)
                if answer.lower().find('y') > -1:
                    order_res = self.eodms_rapi.order(json_res)
                else:
                    # Export polygons of images
                    self.eodms_geo.export_results(query_imgs, self.output)
                    
                    self.export_results()
                    self.print_support()
                    self.logger.info("Process ended by user.")
                    sys.exit(0)
                    
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
            json_object = json.loads(my_json)
        except (ValueError, TypeError) as e:
            return False
        return True
        
    def sort_fields(self, fields):
        """
        Sorts a list of fields to include recordId, collectionId
        
        :param fields: A list of fields from an Image.
        :type  fields: list
        
        :return: The sorted list of fields.
        :rtype: list
        """
        
        field_order = ['recordId', 'collectionId']
        
        if 'orderId' in fields: field_order.append('orderId')
        if 'itemId' in fields: field_order.append('itemId')
        
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
        
        :return: The maximum number of images to order and the total number of images per order.
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
            
        return (max_images, max_items)
        
    def print_msg(self, msg, nl=True, indent=True):
        """
        Prints a message to the command prompt.
        
        :param msg: The message to print to the screen.
        :type  msg: str
        :param nl: If True, a newline will be added to the start of the message.
        :type  nl: boolean
        :param indent: A string with the indentation.
        :type  indent: str
        """
        
        indent_str = ''
        if indent:
            indent_str = ' '*self.indent
        if nl: msg = "\n%s%s" % (indent_str, msg)
        else: msg = "%s%s" % (indent_str, msg)
        
        print(msg)
        
    def print_footer(self, title, msg):
        """
        Prints a footer to the command prompt.
        
        :param title: The title of the footer.
        :type  title: str
        :param msg: The message for the footer.
        :type  msg: str
        """
        
        print("\n%s-----%s%s" % (' '*self.indent, title, str((59 - len(title))*'-')))
        msg = msg.strip('\n')
        for m in msg.split('\n'):
            print("%s| %s" % (' '*self.indent, m))
        print("%s--------------------------------------------------------------" \
                "--" % str(' '*self.indent))
        
    def print_heading(self, msg):
        """
        Prints a heading to the command prompt.
        
        :param msg: The msg for the heading.
        :type  msg: str
        """
        
        print("\n**************************************************************" \
                "************")
        print(" %s" % msg)
        print("****************************************************************" \
                "**********")
        
    def print_support(self, err_str=None):
        """
        Prints the 2 different support message depending if an error occurred.
        
        :param err_str: The error string to print along with support.
        :type  err_str: str
        """
        
        if err_str is None:
            print("\nIf you have any questions or require support, " \
                    "please contact the EODMS Support Team at " \
                    "%s" % self.email)
        else:
            print("\nERROR: %s" % err_str)
            
            print("\nExiting process.")
            
            print("\nFor help, please contact the EODMS Support Team at " \
                    "%s" % self.email)
                    
    def get_fieldMap(self, coll_id=None):
        """
        Gets the dictionary containing the field IDs for RAPI query.
        
        :return: A dictionary containing a mapping of the English field name to the fied ID.
        :rtype: dict
        """
        
        mapping = {}
        
        for key in ['COSMO-SkyMed1']:
            mapping[key] = {
                    'ORBIT_DIRECTION': 'Absolute Orbit', 
                    'PIXEL_SPACING': 'Spatial Resolution'
                }
        
        for key in ['DMC', ]:
            mapping[key] = {
                    'CLOUD_COVER': 'Cloud Cover', 
                    'PIXEL_SPACING': 'Spatial Resolution', 
                    'INCIDENCE_ANGLE': 'Incidence Angle'
                }
                
        for key in ['Gaofen-1', 'PlanetScope', 'SPOT']:
            mapping[key] = {
                    'CLOUD_COVER': 'Cloud Cover', 
                    'PIXEL_SPACING': 'Spatial Resolution', 
                    'INCIDENCE_ANGLE': 'Sensor Incidence Angle'
                }
        
        for key in ['GeoEye-1', 'IKONOS', 'IRS', 'QuickBird-2', 'RapidEye', 
            'WorldView-1', 'WorldView-2', 'WorldView-3', 'WV1', 'WV2', 'WV3']:
            mapping[key] = {
                    'CLOUD_COVER': 'Cloud Cover', 
                    'PIXEL_SPACING': 'Spatial Resolution', 
                    'INCIDENCE_ANGLE': 'Sensor Incidence Angle', 
                    'SENSOR_MODE': 'Sensor Mode'
                }
                
        for key in ['TerraSarX']:
            mapping[key] = {
                    'ORBIT_DIRECTION': 'Orbit Direction', 
                    'PIXEL_SPACING': 'Spatial Resolution', 
                    'INCIDENCE_ANGLE': 'Incidence Angle'
                }
                
        for key in ['NAPL']:
            mapping[key] = {
                    'COLOUR': 'Sensor Mode', 
                    'SCALE': 'Scale', 
                    'ROLL': 'Roll Number', 
                    'PHOTO_NUMBER': 'Photo Number' 
                    # 'PREVIEW_AVAILABLE': 'PREVIEW_AVAILABLE'
                }
                
        for key in ['RCMImageProducts', 'RCM']:
            mapping[key] = {
                    'ORBIT_DIRECTION': 'Orbit Direction', 
                    # 'INCIDENCE_ANGLE': 'SENSOR_BEAM_CONFIG.INCIDENCE_LOW,SENSOR_BEAM_CONFIG.INCIDENCE_HIGH', 
                    'PIXEL_SPACING': 'Spatial Resolution', 
                    'INCIDENCE_ANGLE': 'Incidence Angle', 
                    'BEAM_MNEMONIC': 'Beam Mnemonic', 
                    'BEAM_MODE_QUALIFIER': 'Beam Mode Qualifier', 
                    # 'BEAM_MODE_TYPE': 'RCM.SBEAM',
                    'DOWNLINK_SEGMENT_ID': 'Downlink Segment ID', 
                    'LUT_APPLIED': 'LUT Applied', 
                    'OPEN_DATA': 'Open Data', 
                    'POLARIZATION': 'Polarization', 
                    'PRODUCT_FORMAT': 'Product Format', 
                    'PRODUCT_TYPE': 'Product Type', 
                    'RELATIVE_ORBIT': 'Relative Orbit', 
                    'WITHIN_ORBIT_TUBE': 'Within Orbit Tube', 
                    'ORDER_KEY': 'Order Key', 
                    'SEQUENCE_ID': 'Sequence Id', 
                    'SPECIAL_HANDLING_REQUIRED': 'Special Handling Required'
                }
            
        for key in ['RCMScienceData']:
            mapping[key] = {
                    'ORBIT_DIRECTION': 'Orbit Direction', 
                    'INCIDENCE_ANGLE': 'Incidence Angle', 
                    'BEAM_MODE': 'Beam Mode Type', 
                    'BEAM_MNEMONIC': 'Beam Mnemonic', 
                    'TRANSMIT_POLARIZATION': 'Transmit Polarization', 
                    'RECEIVE POLARIZATION': 'Receive Polarization', 
                    'DOWNLINK_SEGMENT_ID': 'Downlink Segment ID'
                }
        
        for key in ['Radarsat1', 'R1']:
            mapping[key] = {
                    'ORBIT_DIRECTION': 'Orbit Direction',
                    'PIXEL_SPACING': 'Spatial Resolution', 
                    # 'INCIDENCE_ANGLE': 'SENSOR_BEAM_CONFIG.INCIDENCE_LOW,SENSOR_BEAM_CONFIG.INCIDENCE_HIGH', 
                    'INCIDENCE_ANGLE': 'Incidence Angle', 
                    # 'BEAM_MODE': 'RSAT1.SBEAM', 
                    'BEAM_MNEMONIC': 'Position', 
                    'ORBIT': 'Absolute Orbit', 
                    'PRODUCT_TYPE': 'Product Type', 
                    'PROCESSING_LEVEL': 'Processing Level'
                }
        
        for key in ['Radarsat1RawProducts']:
            mapping[key] = {
                    'ORBIT_DIRECTION': 'Orbit Direction',
                    'PIXEL_SPACING': 'Spatial Resolution', 
                    'INCIDENCE_ANGLE': 'Incidence Angle', 
                    'DATASET_ID': 'Dataset Id', 
                    'ARCHIVE_FACILITY': 'Reception Facility', 
                    'RECEPTION FACILITY': 'Reception Facility', 
                    'BEAM_MODE': 'Sensor Mode', 
                    'BEAM_MNEMONIC': 'Position', 
                    'ABSOLUTE_ORBIT': 'Absolute Orbit'
                }
                
        for key in ['Radarsat2', 'R2']:
            mapping[key] = {
                    'ORBIT_DIRECTION': 'Orbit Direction', 
                    'PIXEL_SPACING': 'Spatial Resolution', 
                    # 'INCIDENCE_ANGLE': 'SENSOR_BEAM_CONFIG.INCIDENCE_LOW,SENSOR_BEAM_CONFIG.INCIDENCE_HIGH', 
                    'INCIDENCE_ANGLE': 'Incidence Angle', 
                    'SEQUENCE_ID': 'Sequence Id', 
                    # 'BEAM_MODE': 'RSAT2.SBEAM', 
                    'BEAM_MNEMONIC': 'Position', 
                    'LOOK_DIRECTION': 'Look Direction', 
                    'TRANSMIT_POLARIZATION': 'Transmit Polarization', 
                    'RECEIVE_POLARIZATION': 'Receive Polarization', 
                    'IMAGE_ID': 'Image Id', 
                    'RELATIVE_ORBIT': 'Relative Orbit', 
                    'ORDER_KEY': 'Order Key'
                }
                
        for key in ['Radarsat2RawProducts']:
            mapping[key] = {
                    'ORBIT_DIRECTION': 'Orbit Direction', 
                    'PIXEL_SPACING': 'Spatial Resolution', 
                    'INCIDENCE_ANGLE': 'Incidence Angle', 
                    'LOOK_ORIENTATION': 'Look Orientation', 
                    'BEAM_MODE': 'Sensor Mode', 
                    'BEAM_MNEMONIC': 'Position', 
                    'TRANSMIT_POLARIZATION': 'Transmit Polarization', 
                    'RECEIVE_POLARIZATION': 'Receive Polarization', 
                    'IMAGE_ID': 'Image Id'
                }
                
        for key in ['SGBAirPhotos']:
            mapping[key] = {
                    'SCALE': 'Scale', 
                    'ROLL_NUMBER': 'Roll Number', 
                    'PHOTO_NUMBER': 'Photo Number', 
                    'AREA': 'Area'
                }
                
        for key in ['VASP']:
            mapping[key] = {
                    'VASP_OPTIONS': 'Sequence Id'
                }
        
        if coll_id is None:
            return mapping
        else:
            coll_id = self.get_fullCollId(coll_id)
            return mapping[coll_id]
        
        # mapping = {
            # 'COSMO-SkyMed1':
                # {
                    # 'ORBIT_DIRECTION': 'Absolute Orbit', 
                    # 'PIXEL_SPACING': 'Spatial Resolution'
                # }, 
            # 'DMC':
                # {
                    # 'CLOUD_COVER': 'Cloud Cover', 
                    # 'PIXEL_SPACING': 'Spatial Resolution', 
                    # 'INCIDENCE_ANGLE': 'Incidence Angle'
                # }, 
            # 'Gaofen-1':
                # {
                    # 'CLOUD_COVER': 'Cloud Cover', 
                    # 'PIXEL_SPACING': 'Spatial Resolution', 
                    # 'INCIDENCE_ANGLE': 'Sensor Incidence Angle'
                # }, 
            # 'GeoEye-1':
                # {
                    # 'CLOUD_COVER': 'Cloud Cover', 
                    # 'PIXEL_SPACING': 'Spatial Resolution', 
                    # 'INCIDENCE_ANGLE': 'Sensor Incidence Angle', 
                    # 'SENSOR_MODE': 'Sensor Mode'
                # }, 
            # 'IKONOS': 
                # {
                    # 'CLOUD_COVER': 'Cloud Cover', 
                    # 'PIXEL_SPACING': 'Spatial Resolution', 
                    # 'INCIDENCE_ANGLE': 'Sensor Incidence Angle', 
                    # 'SENSOR_MODE': 'Sensor Mode'
                # }, 
            # 'IRS': 
                # {
                    # 'CLOUD_COVER': 'Cloud Cover', 
                    # 'PIXEL_SPACING': 'Spatial Resolution', 
                    # 'INCIDENCE_ANGLE': 'Sensor Incidence Angle', 
                    # 'SENSOR_MODE': 'Sensor Mode'
                # }, 
            # 'NAPL':
                # {
                    # 'COLOUR': 'Sensor Mode', 
                    # 'SCALE': 'Scale', 
                    # 'ROLL': 'Roll Number', 
                    # 'PHOTO_NUMBER': 'Photo Number' 
                    # # 'PREVIEW_AVAILABLE': 'PREVIEW_AVAILABLE'
                # }, 
            # 'PlanetScope': 
                # {
                    # 'CLOUD_COVER': 'Cloud Cover', 
                    # 'PIXEL_SPACING': 'Spatial Resolution', 
                    # 'INCIDENCE_ANGLE': 'Sensor Incidence Angle'
                # }, 
            # 'QuickBird-2': 
                # {
                    # 'CLOUD_COVER': 'Cloud Cover', 
                    # 'PIXEL_SPACING': 'Spatial Resolution', 
                    # 'INCIDENCE_ANGLE': 'Sensor Incidence Angle', 
                    # 'SENSOR_MODE': 'Sensor Mode'
                # }, 
            # 'RCMImageProducts': 
                # {
                    # 'ORBIT_DIRECTION': 'Orbit Direction', 
                    # # 'INCIDENCE_ANGLE': 'SENSOR_BEAM_CONFIG.INCIDENCE_LOW,SENSOR_BEAM_CONFIG.INCIDENCE_HIGH', 
                    # 'PIXEL_SPACING': 'Spatial Resolution', 
                    # 'INCIDENCE_ANGLE': 'Incidence Angle', 
                    # 'BEAM_MNEMONIC': 'Beam Mnemonic', 
                    # 'BEAM_MODE_QUALIFIER': 'Beam Mode Qualifier', 
                    # # 'BEAM_MODE_TYPE': 'RCM.SBEAM',
                    # 'DOWNLINK_SEGMENT_ID': 'Downlink Segment ID', 
                    # 'LUT_APPLIED': 'LUT Applied', 
                    # 'OPEN_DATA': 'Open Data', 
                    # 'POLARIZATION': 'Polarization', 
                    # 'PRODUCT_FORMAT': 'Product Format', 
                    # 'PRODUCT_TYPE': 'Product Type', 
                    # 'RELATIVE_ORBIT': 'Relative Orbit', 
                    # 'WITHIN_ORBIT_TUBE': 'Within Orbit Tube', 
                    # 'ORDER_KEY': 'Order Key', 
                    # 'SEQUENCE_ID': 'Sequence Id', 
                    # 'SPECIAL_HANDLING_REQUIRED': 'Special Handling Required'
                # }, 
            # 'RCMScienceData': 
                # {
                    # 'ORBIT_DIRECTION': 'Orbit Direction', 
                    # 'INCIDENCE_ANGLE': 'Incidence Angle', 
                    # 'BEAM_MODE': 'Beam Mode Type', 
                    # 'BEAM_MNEMONIC': 'Beam Mnemonic', 
                    # 'TRANSMIT_POLARIZATION': 'Transmit Polarization', 
                    # 'RECEIVE POLARIZATION': 'Receive Polarization', 
                    # 'DOWNLINK_SEGMENT_ID': 'Downlink Segment ID'

                # }, 
            # 'Radarsat1': 
                # {
                    # 'ORBIT_DIRECTION': 'Orbit Direction',
                    # 'PIXEL_SPACING': 'Spatial Resolution', 
                    # # 'INCIDENCE_ANGLE': 'SENSOR_BEAM_CONFIG.INCIDENCE_LOW,SENSOR_BEAM_CONFIG.INCIDENCE_HIGH', 
                    # 'INCIDENCE_ANGLE': 'Incidence Angle', 
                    # # 'BEAM_MODE': 'RSAT1.SBEAM', 
                    # 'BEAM_MNEMONIC': 'Position', 
                    # 'ORBIT': 'Absolute Orbit'
                # }, 
            # 'Radarsat1RawProducts': 
                # {
                    # 'ORBIT_DIRECTION': 'Orbit Direction',
                    # 'PIXEL_SPACING': 'Spatial Resolution', 
                    # 'INCIDENCE_ANGLE': 'Incidence Angle', 
                    # 'DATASET_ID': 'Dataset Id', 
                    # 'ARCHIVE_FACILITY': 'Reception Facility', 
                    # 'RECEPTION FACILITY': 'Reception Facility', 
                    # 'BEAM_MODE': 'Sensor Mode', 
                    # 'BEAM_MNEMONIC': 'Position', 
                    # 'ABSOLUTE_ORBIT': 'Absolute Orbit'
                # }, 
            # 'Radarsat2':
                # {
                    # 'ORBIT_DIRECTION': 'Orbit Direction', 
                    # 'PIXEL_SPACING': 'Spatial Resolution', 
                    # # 'INCIDENCE_ANGLE': 'SENSOR_BEAM_CONFIG.INCIDENCE_LOW,SENSOR_BEAM_CONFIG.INCIDENCE_HIGH', 
                    # 'INCIDENCE_ANGLE': 'Incidence Angle', 
                    # 'SEQUENCE_ID': 'Sequence Id', 
                    # # 'BEAM_MODE': 'RSAT2.SBEAM', 
                    # 'BEAM_MNEMONIC': 'Position', 
                    # 'LOOK_DIRECTION': 'Look Direction', 
                    # 'TRANSMIT_POLARIZATION': 'Transmit Polarization', 
                    # 'RECEIVE_POLARIZATION': 'Receive Polarization', 
                    # 'IMAGE_ID': 'Image Id', 
                    # 'RELATIVE_ORBIT': 'Relative Orbit', 
                    # 'ORDER_KEY': 'Order Key'
                # }, 
            # 'Radarsat2RawProducts': 
                # {
                    # 'ORBIT_DIRECTION': 'Orbit Direction', 
                    # 'PIXEL_SPACING': 'Spatial Resolution', 
                    # 'INCIDENCE_ANGLE': 'Incidence Angle', 
                    # 'LOOK_ORIENTATION': 'Look Orientation', 
                    # 'BEAM_MODE': 'Sensor Mode', 
                    # 'BEAM_MNEMONIC': 'Position', 
                    # 'TRANSMIT_POLARIZATION': 'Transmit Polarization', 
                    # 'RECEIVE_POLARIZATION': 'Receive Polarization', 
                    # 'IMAGE_ID': 'Image Id'
                # }, 
            # 'RapidEye': 
                # {
                    # 'CLOUD_COVER': 'Cloud Cover', 
                    # 'PIXEL_SPACING': 'Spatial Resolution', 
                    # 'INCIDENCE_ANGLE': 'Sensor Incidence Angle', 
                    # 'SENSOR_MODE': 'Sensor Mode'
                # }, 
            # 'SGBAirPhotos': 
                # {
                    # 'SCALE': 'Scale', 
                    # 'ROLL_NUMBER': 'Roll Number', 
                    # 'PHOTO_NUMBER': 'Photo Number', 
                    # 'AREA': 'Area'
                # }, 
            # 'SPOT': 
                # {
                    # 'CLOUD_COVER': 'Cloud Cover', 
                    # 'PIXEL_SPACING': 'Spatial Resolution', 
                    # 'INCIDENCE_ANGLE': 'Sensor Incidence Angle'
                # }, 
            # 'TerraSarX': 
                # {
                    # 'ORBIT_DIRECTION': 'Orbit Direction', 
                    # 'PIXEL_SPACING': 'Spatial Resolution', 
                    # 'INCIDENCE_ANGLE': 'Incidence Angle'
                # }, 
            # 'VASP': 
                # {
                    # 'VASP_OPTIONS': 'Sequence Id'
                # }, 
            # 'WorldView-1': 
                # {
                    # 'CLOUD_COVER': 'Cloud Cover', 
                    # 'PIXEL_SPACING': 'Spatial Resolution', 
                    # 'INCIDENCE_ANGLE': 'Sensor Incidence Angle', 
                    # 'SENSOR_MODE': 'Sensor Mode'
                # }, 
            # 'WorldView-2': 
                # {
                    # 'CLOUD_COVER': 'Cloud Cover', 
                    # 'PIXEL_SPACING': 'Spatial Resolution', 
                    # 'INCIDENCE_ANGLE': 'Sensor Incidence Angle', 
                    # 'SENSOR_MODE': 'Sensor Mode'
                # }, 
            # 'WorldView-3': 
                # {
                    # 'CLOUD_COVER': 'Cloud Cover', 
                    # 'PIXEL_SPACING': 'Spatial Resolution', 
                    # 'INCIDENCE_ANGLE': 'Sensor Incidence Angle', 
                    # 'SENSOR_MODE': 'Sensor Mode'
                # }
        #     }  
        
    
    def query_entries(self, collections, **kwargs):
        """
        Sends various image entries to the EODMSRAPI.
        
        :param collection: A list of collections.
        :type  collection: list
        :param kwarg: A dictionary of arguments:
        
                - filters (dict): A dictionary of filters separated by 
                    collection.
                - aoi (str): The filename of the AOI.
                - dates (list): A list of date ranges 
                    ([{'start': <date>, 'end': <date>}]).
                - max_images (int): The maximum number of images to query.
        :type  kwarg: dict
        
        :return: The ImageList object containing the results of the query.
        :rtype: image.ImageList
        """
        
        filters = kwargs.get('filters')
        aoi = kwargs.get('aoi')
        dates = kwargs.get('dates')
        max_images = kwargs.get('max_images')
        
        feats = [('INTERSECTS', aoi)]
        
        all_res = []
        for coll in collections:
            
            # Get the full Collection ID
            self.coll_id = self.get_fullCollId(coll)
            
            # Parse filters
            if filters:
                
                if self.coll_id in filters.keys():
                    coll_filts = filters[self.coll_id]
                    filters = self._parse_filters(coll_filts)
                    if isinstance(filters, str):
                        filters = None
                else:
                    filters = None
            else:
                filters = None
                
            if self.coll_id == 'NAPL':
                filters = {}
                filters['Price'] = ('=', True)
            
            result_fields = []
            if filters is not None:
                av_fields = self.eodms_rapi.get_availableFields(\
                                self.coll_id, 'title')
                
                for k in filters.keys():
                    if k in av_fields['results']:
                        result_fields.append(k)
            
            # Send a query to the EODMSRAPI object
            self.eodms_rapi.search(self.coll_id, filters, feats, dates, \
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
        
        if title is None: title = "Script Parameters"
        
        msg = "%s:\n" % title
        for k, v in params.items():
            msg += "  %s: %s\n" % (k, v)
        self.logger.info(msg)
        
    def set_silence(self, silent):
        """
        Sets the silence of the script.
        
        :param silent: Determines whether the script will be silent. If True, the user is not prompted for info.
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
        
        coll_vals = list(colls.keys()) + [v['title'] for v in \
                    colls.values()]
        
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
        except:
            return False
        
    def validate_int(self, val, limit=None):
        """
        Checks if the number entered by the user is valid.
        
        :param val: A string (or integer) of an integer.
        :type  val: str or int
        :param limit: A number to check whether the val is less than a certain limit.
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
                        err_msg = "WARNING: One of the values entered is " \
                            "invalid."
                        self.print_msg(err_msg, indent=False)
                        self.logger.warning(err_msg)
                        return False
                    out_val = [int(v) for v in val]
                else:
                    out_val = int(val)
            else:
                if limit is not None:
                    if int(val) > limit:
                        err_msg = "WARNING: The values entered are invalid."
                        self.print_msg(err_msg, indent=False)
                        self.logger.warning(err_msg)
                        return False
                
                out_val = int(val)
                    
            return out_val
            
        except ValueError:
            err_msg = "WARNING: Not a valid entry."
            self.print_msg(err_msg, indent=False)
            self.logger.warning(err_msg)
            return False
            
    def validate_file(self, in_fn, aoi=False):
        """
        Checks if a file name entered by the user is valid.
        
        :param in_fn: The filename of the input file.
        :type  in_fn: str
        :param aoi: Determines whether the file is an AOI.
        :type  aoi: boolean
        
        :return: If the file is invalid (wrong format or does not exist), False is returned. Otherwise the original filename is returned.
        :rtype: str or boolean
        """
        
        abs_path = os.path.abspath(in_fn)
        
        if aoi:
            if not any(s in in_fn for s in self.aoi_extensions):
                err_msg = "The AOI file is not a valid file. Please make " \
                            "sure the file is either a GML, KML, GeoJSON " \
                            "or Shapefile."
                self.print_support(err_msg)
                self.logger.error(err_msg)
                return False
        
            if not os.path.exists(abs_path):
                err_msg = "The AOI file does not exist."
                self.print_support(err_msg)
                self.logger.error(err_msg)
                return False
                
        if not os.path.exists(abs_path):
            return False
            
        return abs_path
        
    def validate_filters(self, filt_items, coll_id):
        """
        Checks if a list of filters entered by the user is valid.
        
        :param filt_items: A list of filters entered by the user for a given collection.
        :type  filt_items: list
        :param coll_id: The Collection ID of the filter.
        :type  coll_id: str
        
        :return: If one of the filters is invalid, False is returned. Otherwise the original filters are returned.
        :rtype: boolean or str
        """
        
        # Check if filter has proper operators
        if not any(x in filt_items.upper() for x in self.operators):
            err_msg = "Filter(s) entered incorrectly. Make sure each " \
                        "filter is in the format of <filter_id><operator>" \
                        "<value>[|<value>] and each filter is separated by " \
                        "a comma."
            self.print_support(err_msg)
            self.logger.error(err_msg)
            return False
            
        # Check if filter name is valid
        coll_fields = self.get_fieldMap(coll_id)
        
        filts = filt_items.split(',')
        
        for f in filts:
            if not any(x in f.upper() for x in coll_fields.keys()):
                err_msg = "Filter '%s' is not available for collection " \
                            "'%s'." % (f, coll_id)
                self.print_support(err_msg)
                self.logger.error(err_msg)
                return False
                
        return filt_items
        
    def search_orderDownload(self, params):
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
        aoi = params.get('input')
        filters = params.get('filters')
        process = params.get('process')
        maximum = params.get('maximum')
        self.output = params.get('output')
        priority = params.get('priority')
        aws_download = params.get('aws')
        
        # Validate AOI
        if os.path.exists(aoi):
            aoi_check = self.validate_file(aoi, True)
            if not aoi_check:
                err_msg = "The provided input file is not a valid AOI " \
                        "file. Exiting process."
                self.print_support()
                self.logger.error(err_msg)
                sys.exit(1)
        else:
            if not self.eodms_geo.is_wkt(aoi):
                err_msg = "The provided WKT feature is not valid. " \
                        "Exiting process."
                self.print_support()
                self.logger.error(err_msg)
                sys.exit(1)
            
        # Create info folder, if it doesn't exist, to store CSV files
        start_time = datetime.datetime.now()
        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        self.fn_str = start_time.strftime("%Y%m%d_%H%M%S")
        
        self.logger.info("Process start time: %s" % start_str)
        
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
        query_imgs = self.query_entries(collections, filters=filters, \
            aoi=aoi, dates=dates, max_images=max_images)
            
        # If no results were found, inform user and end process
        if query_imgs.count() == 0:
            msg = "Sorry, no results found for given AOI."
            self.print_msg(msg)
            self.print_msg("Exiting process.")
            self.print_support()
            self.logger.warning(msg)
            sys.exit(1)
            
        # Update the self.cur_res for output results
        self.cur_res = query_imgs
        
        # Print results info
        msg = "%s images returned from search results.\n" % query_imgs.count()
        self.print_footer('Query Results', msg)
        
        if max_images is None or max_images == '':
            # Inform the user of the total number of found images and ask if 
            #   they'd like to continue
            if not self.silent:
                answer = input("\n%s images found intersecting your AOI. " \
                            "Proceed with ordering? (y/n): " % \
                            query_imgs.count())
                if answer.lower().find('n') > -1:
                    self.export_results()
                    print("Exiting process.")
                    self.print_support()
                    self.logger.info("Process stopped by user.")
                    sys.exit(0)
        else:
            # If the user specified a maximum number of orders, 
            #   trim the results
            if len(collections) == 1:
                self.print_msg("Proceeding to order and download the first %s " \
                    "images." % max_images)
                query_imgs.trim(max_images)
            else:
                self.print_msg("Proceeding to order and download the first %s " \
                    "images from each collection." % max_images)
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
        orders = None
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
        if orders:
            items = orders.get_raw()
                
            # Download images using the EODMSRAPI
            download_items = self.eodms_rapi.download(items, self.download_path)
                
            # Update the images with the download info
            eodms_imgs.update_downloads(download_items)
        
        if aws_downloads:
            eodms_imgs.add_images(aws_downloads)
        
        self._print_results(eodms_imgs)
        
        self.eodms_geo.export_results(eodms_imgs, self.output)
        
        # Update the self.cur_res for output results
        self.cur_res = eodms_imgs
        
        self.export_results()
        
        end_time = datetime.datetime.now()
        end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
        
        self.logger.info("End time: %s" % end_str)
        
    def order_csv(self, params):
        """
        Orders and downloads images using the CSV exported from the EODMS UI.
        
        :param params: A dictionary containing the arguments and values.
        :type  params: dict
        """
        
        csv_fn = params.get('input')
        maximum = params.get('maximum')
        priority = params.get('priority')
        self.output = params.get('output')
        
        # Log the parameters
        self.log_parameters(params)
        
        if csv_fn.find('.csv') == -1:
            err_msg = "The provided input file is not a CSV file. " \
                        "Exiting process."
            self.print_support(err_msg)
            self.logger.error(err_msg)
            sys.exit(1)
        
        # Create info folder, if it doesn't exist, to store CSV files
        start_time = datetime.datetime.now()
        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        self.fn_str = start_time.strftime("%Y%m%d_%H%M%S")
        folder_str = start_time.strftime("%Y-%m-%d")
        
        self.logger.info("Process start time: %s" % start_str)
        
        #############################################
        # Search for Images
        #############################################
        
        self.eodms_rapi.get_collections()
        
        # Parse the maximum number of orders and items per order
        max_images, max_items = self.parse_max(maximum)
        
        # Import and query entries from the CSV
        query_imgs = self._get_eodmsRes(csv_fn)
        
        # Update the self.cur_res for output results
        self.cur_res = query_imgs
        
        #############################################
        # Order Images
        #############################################
        
        orders = self._submit_orders(query_imgs, priority)
        
        # Get a list of order items in JSON format for the EODMSRAPI
        items = orders.get_raw()
        
        #############################################
        # Download Images
        #############################################
        
        # Make the download folder if it doesn't exist
        if not os.path.exists(self.download_path):
            os.mkdir(self.download_path)
        
        # Download images using the EODMSRAPI
        download_items = self.eodms_rapi.download(items, self.download_path)
        
        # Update images
        query_imgs.update_downloads(download_items)
        
        # Export polygons of images
        self.eodms_geo.export_results(query_imgs, self.output)
        
        # Update the self.cur_res for output results
        self.cur_res = query_imgs
        self.export_results()
        
        end_time = datetime.datetime.now()
        end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
        
        self.logger.info("End time: %s" % end_str)
        
    def order_ids(self, params):
        """
        Orders and downloads a single or set of images using Record IDs.
        
        :param params: A dictionary containing the arguments and values.
        :type  params: dict
        """
        
        in_ids = params.get('input')
        priority = params.get('priority')
        self.output = params.get('output')
        aws_download = params.get('aws')
        
        # Log the parameters
        self.log_parameters(params)
        
        # Create info folder, if it doesn't exist, to store CSV files
        start_time = datetime.datetime.now()
        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        self.fn_str = start_time.strftime("%Y%m%d_%H%M%S")
        folder_str = start_time.strftime("%Y-%m-%d")
        
        self.logger.info("Process start time: %s" % start_str)
        
        #############################################
        # Search for Images
        #############################################
        
        self.eodms_rapi.get_collections()
        
        ids_lst = in_ids.split(',')
        
        all_res = []
        for i in ids_lst:
            coll, rec_id = i.split(':')
            
            res = self.eodms_rapi.get_record(coll, rec_id)
            
            all_res.append(res)
        
        # print("all_res: %s" % all_res)
        
        query_imgs = image.ImageList(self)
        query_imgs.ingest_results(all_res)
        
        # # Parse the maximum number of orders and items per order
        # max_images, max_items = self.parse_max(maximum)
        
        # # Import and query entries from the CSV
        # query_imgs = self._get_eodmsRes(csv_fn)
        
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
        
        orders = None
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
        if orders:
            items = orders.get_raw()
                
            # Download images using the EODMSRAPI
            download_items = self.eodms_rapi.download(items, self.download_path)
                
            # Update the images with the download info
            eodms_imgs.update_downloads(download_items)
            
        if aws_downloads:
            eodms_imgs.add_images(aws_downloads)
        
        self._print_results(eodms_imgs)
        
        # Export polygons of images
        self.eodms_geo.export_results(eodms_imgs, self.output)
        
        # Update the self.cur_res for output results
        self.cur_res = eodms_imgs
        self.export_results()
        
        end_time = datetime.datetime.now()
        end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
        
        self.logger.info("End time: %s" % end_str)
        
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
        aoi = params.get('input')
        filters = params.get('filters')
        process = params.get('process')
        maximum = params.get('maximum')
        self.output = params.get('output')
        priority = params.get('priority')
        
        # Validate AOI
        if os.path.exists(aoi):
            aoi_check = self.validate_file(aoi, True)
            if not aoi_check:
                err_msg = "The provided input file is not a valid AOI " \
                            "file. Exiting process."
                self.print_support()
                self.logger.error(err_msg)
                sys.exit(1)
        else:
            if not self.eodms_geo.is_wkt(aoi):
                err_msg = "The provided WKT feature is not valid. " \
                        "Exiting process."
                self.print_support()
                self.logger.error(err_msg)
                sys.exit(1)
            
        # Create info folder, if it doesn't exist, to store CSV files
        start_time = datetime.datetime.now()
        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        self.fn_str = start_time.strftime("%Y%m%d_%H%M%S")
        
        self.logger.info("Process start time: %s" % start_str)
        
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
        query_imgs = self.query_entries(collections, filters=filters, \
            aoi=aoi, dates=dates)
            
        # If no results were found, inform user and end process
        if query_imgs.count() == 0:
            msg = "Sorry, no results found for given AOI."
            self.print_msg(msg)
            self.print_msg("Exiting process.")
            self.print_support()
            self.logger.warning(msg)
            sys.exit(1)
            
        # Update the self.cur_res for output results
        self.cur_res = query_imgs
        
        # Print results info
        msg = "%s images returned from search results.\n" % query_imgs.count()
        self.print_footer('Query Results', msg)
        
        #############################################
        # Get Existing Order Results
        #############################################
        
        orders = self.retrieve_orders(query_imgs)
                    
        #############################################
        # Download Images
        #############################################
                    
        # Get a list of order items in JSON format for the EODMSRAPI
        items = orders.get_raw()
        
        # Make the download folder if it doesn't exist
        if not os.path.exists(self.download_path):
            os.mkdir(self.download_path)
        
        # Download images using the EODMSRAPI
        download_items = self.eodms_rapi.download(items, self.download_path)
        
        # Update images with download info
        query_imgs.update_downloads(download_items)
        
        self._print_results(query_imgs)
        
        # Export polygons of images
        self.eodms_geo.export_results(query_imgs, self.output)
        
        # Update the self.cur_res for output results
        self.cur_res = query_imgs
        self.export_results()
        
        end_time = datetime.datetime.now()
        end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
        
        self.logger.info("End time: %s" % end_str)
        
    def download_only(self, params):
        """
        Downloads existing images using the CSV results file from a previous session.
        
        :param params: A dictionary containing the arguments and values.
        :type  params: dict
        """
        
        # Log the parameters
        self.log_parameters(params)
        
        csv_fn = params.get('input')
        self.output = params.get('output')
        
        if csv_fn.find('.csv') == -1:
            msg = "The provided input file is not a CSV file. " \
                "Exiting process."
            self.print_support(msg)
            self.logger.error(msg)
            sys.exit(1)
        
        # Create info folder, if it doesn't exist, to store CSV files
        start_time = datetime.datetime.now()
        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        self.fn_str = start_time.strftime("%Y%m%d_%H%M%S")
        folder_str = start_time.strftime("%Y-%m-%d")
        
        self.logger.info("Process start time: %s" % start_str)
        
        ################################################
        # Get results from Results CSV
        ################################################
        
        query_imgs = self._get_prevRes(csv_fn)
        
        ################################################
        # Get Existing Orders
        ################################################
        
        orders = self.retrieve_orders(query_imgs)
                
        ################################################
        # Download Images
        ################################################
                
        # Get a list of order items in JSON format for the EODMSRAPI
        items = orders.get_raw()
        
        # Make the download folder if it doesn't exist
        if not os.path.exists(self.download_path):
            os.mkdir(self.download_path)
        
        # Download images using the EODMSRAPI
        download_items = self.eodms_rapi.download(items, self.download_path)
        
        # Update images with download info
        query_imgs.update_downloads(download_items)
        
        self._print_results(query_imgs)
        
        # Export polygons of images
        self.eodms_geo.export_results(query_imgs, self.output)
        
        self.export_results()
        
        end_time = datetime.datetime.now()
        end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
        
        self.logger.info("End time: %s" % end_str)
        
    def search_only(self, params):
        """
        Only runs a search on the EODMSRAPI based on user parameters.
        
        :param params: A dictionary of parameters from the user.
        :type  params: dict
        """
        
        # Log the parameters
        self.log_parameters(params)
        
        # Get all the values from the parameters
        collections = params.get('collections')
        dates = params.get('dates')
        aoi = params.get('input')
        filters = params.get('filters')
        process = params.get('process')
        maximum = params.get('maximum')
        self.output = params.get('output')
        priority = params.get('priority')
        
        # Validate AOI
        if os.path.exists(aoi):
            aoi_check = self.validate_file(aoi, True)
            if not aoi_check:
                err_msg = "The provided input file is not a valid AOI " \
                            "file. Exiting process."
                self.print_support()
                self.logger.error(err_msg)
                sys.exit(1)
        else:
            if not self.eodms_geo.is_wkt(aoi):
                err_msg = "The provided WKT feature is not valid. " \
                        "Exiting process."
                self.print_support()
                self.logger.error(err_msg)
                sys.exit(1)
            
        # Create info folder, if it doesn't exist, to store CSV files
        start_time = datetime.datetime.now()
        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        self.fn_str = start_time.strftime("%Y%m%d_%H%M%S")
        
        self.logger.info("Process start time: %s" % start_str)
        
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
        query_imgs = self.query_entries(collections, filters=filters, \
            aoi=aoi, dates=dates, max_images=max_images)
            
        # If no results were found, inform user and end process
        if query_imgs.count() == 0:
            msg = "Sorry, no results found for given AOI."
            self.print_msg(msg)
            self.print_msg("Exiting process.")
            self.print_support()
            self.logger.warning(msg)
            sys.exit(1)
            
        # Update the self.cur_res for output results
        self.cur_res = query_imgs
        
        # Print results info
        msg = "%s images returned from search results.\n" % query_imgs.count()
        self.print_footer('Query Results', msg)
        
        # Export polygons of images
        self.eodms_geo.export_results(query_imgs, self.output)
        
        # Export results to a CSV file and end process.
        self.export_results()
        
        print("\n%s images found intersecting your AOI." % \
            query_imgs.count())
        print("\nPlease check the results folder for more info.")
        print("\nExiting process.")
        
        self.print_support()
        sys.exit(0)
