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

import os
import sys
import time
import datetime
from xml.etree import ElementTree
import urllib
import json
from urllib.parse import urlencode
from urllib.parse import urlparse
import traceback
import requests
from inspect import currentframe, getframeinfo

from . import common
from . import geo
from . import eodms
from . import csv_util

class Downloader:
    """
    The Downloader class contains all the methods and functions used to 
        download EODMS images.
    """
    
    def __init__(self, session, max_images=None, fn_str='', 
                in_csv=None, size_limit=None):
        """
        Initializer for the Downloader object.
        
        @type  session: request.Session
        @param session: The request session containing EODMS authentication.
        """
        
        self.session = session
        self.completed_orders = []
        self.download_size = 0
        self.max_images = max_images
        self.size_limit = size_limit
        self.fn_str = fn_str
        self.csv_fn = in_csv
        self.orders = None
        
        self.import_csv()
        
    def download_image(self, url, dest_fn):
        """
        Downloads an image from the EODMS.
        
        @type  url:     str
        @param url:     The URL where the image is stored on the EODMS.
        @type  dest_fn: str
        @param dest_fn: The destination filename where the image will be 
                        saved.
        """
        
        # Get authentication info and extract the username and password
        auth = self.session.auth
        user = auth[0]
        pwd = auth[1]
        
        # Setup basic authentication before downloading the file
        pass_man = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        pass_man.add_password(None, url, user, pwd)
        authhandler = urllib.request.HTTPBasicAuthHandler(pass_man)
        opener = urllib.request.build_opener(authhandler)
        urllib.request.install_opener(opener)
        
        # Download the file from the EODMS server
        try:
            urllib.request.urlretrieve(url, dest_fn, \
                reporthook=self.print_progress)
        except:
            pass
        
    def download_orders(self, cur_orders=None):
        """
        Downloads a set of orders from the EODMS server.
        
        @type  cur_orders: dict
        @param cur_orders: A dictionary of orders to download.
        """
        
        ##################################################
        common.print_heading("Downloading orders")
        ##################################################
        
        # Create list trackers for orders that have been processed 
        #   (completed_orders) and orders which were successful.
        success_orders = []
        failed_orders = []
        self.completed_orders = []
        
        if cur_orders is None:
            cur_orders = self.orders
            
        if cur_orders is None:
            print("\nNo orders provided for download.")
            return None
        
        self.orders_obj = cur_orders
        
        redownload = False
        if self.orders_obj.check_downloaded():
            if not common.SILENT:
                answer = input("\n\tWould you like to re-download images that " \
                        "have already been downloaded? (y/n): ")
                if answer.lower().find('y'):
                    redownload = True
        
        try:
            while len(self.completed_orders) < cur_orders.count_items():
                
                if self.max_images is not None and not self.max_images == '':
                    if len(self.completed_orders) >= int(self.max_images):
                        break
                
                for order in cur_orders.get_orders():
                    
                    if self.max_images is not None and not self.max_images == '':
                        if len(self.completed_orders) >= int(self.max_images):
                            break
                    
                    # Keep looping until all processed order items have been 
                    #   checked
                    
                    # Get the current order ID
                    ord_id = order.get_orderId()
                    
                    # Get a list of order items in this order
                    ord_items = self.get_latestItems(ord_id)
                    
                    # Track order items which have been newly processed this time 
                    #   around
                    new_complete = []
                    
                    for item in ord_items:
                        
                        if self.max_images is not None and not self.max_images == '':
                            if len(self.completed_orders) >= int(self.max_images):
                                break
                        
                        # Get item info
                        record_id = item['recordId']
                        order_id = item['orderId']
                        orderitem_id = item['itemId']
                        img_status = item['status']
                        
                        if record_id not in order.get_recordIds():
                            continue
                        
                        prev_path = None
                        prev_orderItem = order.get_item(item['itemId'])
                        if prev_orderItem is not None:
                            prev_path = prev_orderItem.get_downloadPath()
                            downloaded = prev_orderItem.get_metadata('downloaded')
                            downloaded = str(downloaded)
                            if downloaded == 'True' and redownload:
                                common.print_msg("Skipping download of " \
                                    "image with Record ID %s. Image already " \
                                    "downloaded." % record_id)
                                # Add order item to newly completed list
                                new_complete.append(prev_orderItem)
                                continue
                        
                        # Get the image from the original order item
                        img_obj = order.get_image(record_id)
                        
                        # Create new order item
                        orderItem_obj = eodms.OrderItem()
                        orderItem_obj.set_image(img_obj)
                        orderItem_obj.parse_record(item)
                        
                        # If the order item has already been processed/downloaded
                        if record_id in [i.get_recordId() for i in \
                            self.completed_orders] \
                            or record_id in [i.get_recordId() for i in \
                            new_complete]:
                            continue
                        
                        if img_status == 'AVAILABLE_FOR_DOWNLOAD':
                            
                            # Get the list of destinations
                            dests = item['destinations']
                            download_paths = []
                            for d in dests:
                                
                                # Get the string value of the destination
                                str_val = d['stringValue']
                                str_val = str_val.replace('</br>', '')
                                
                                # Parse the HTML text of the destination string
                                root = ElementTree.fromstring(str_val)
                                url = root.text
                                fn = os.path.basename(url)
                                
                                if not os.path.exists(common.DOWNLOAD_PATH):
                                    os.mkdir(common.DOWNLOAD_PATH)
                                
                                # Download the image
                                common.print_msg("Downloading image with " \
                                        "Record ID %s (%s)." % (record_id, \
                                        os.path.basename(url)))
                                
                                # # Save the image contents to the 'downloads' folder
                                if prev_path is None:
                                    out_fn = os.path.join(common.DOWNLOAD_PATH, \
                                            self.fn_str, fn)
                                else:
                                    out_fn = prev_path
                                full_path = os.path.realpath(out_fn)
                                
                                if not os.path.exists(os.path.dirname(full_path)):
                                    os.mkdir(os.path.dirname(full_path))
                                
                                self.download_size = 0
                                self.download_image(url, out_fn)
                                print('')
                                self.download_size = 0
                                
                                # Record the URL and downloaded file to a dictionary
                                dest_info = {}
                                dest_info['url'] = url
                                dest_info['local_destination'] = full_path
                                download_paths.append(dest_info)
                                
                                resp = None
                                
                            # Add download paths to the item dictionary
                            orderItem_obj.set_metadata('download_paths', \
                                download_paths)
                            orderItem_obj.set_metadata('downloaded', "True")
                            
                            # Add order item to newly completed list
                            new_complete.append(orderItem_obj)
                            
                            # Add the image to a list of successful orders
                            success_orders.append(orderItem_obj)
                            
                            # Replace existing order item in order list
                            self.orders_obj.replace_item(order_id, orderItem_obj)
                        else:
                            if img_status == 'CANCELLED' or \
                                img_status == 'FAILED' or \
                                img_status == 'EXPIRED' or \
                                img_status == 'DELIVERED' or \
                                img_status == 'MEDIA_ORDER_SUBMITTED':
                                
                                orderItem_obj.set_metadata('downloaded', "False")
                                failed_orders.append(orderItem_obj)
                                
                                # Add order item to newly completed list
                                new_complete.append(orderItem_obj)
                                
                                # Replace existing order item in order list
                                self.orders_obj.replace_item(order_id, orderItem_obj)
                        
                    if len(new_complete) == 0:
                        # If no new images are ready, let the user know
                        if len(self.completed_orders) == 0:
                            common.print_msg("No images ready to download " \
                                    "yet. Please wait...")
                        else:
                            common.print_msg("No new images are ready to " \
                                    "download yet. Please wait...")
                    else:
                        # Add newly completed orders to completed list
                        self.completed_orders += new_complete
                
                if self.max_images is None or self.max_images == '':
                    tot_msg = "Total order items to download: %s" % \
                            cur_orders.count_items()
                else:
                    tot_msg = "Total order items to download: %s" % \
                            self.max_images
                common.print_msg(tot_msg)
                common.print_msg("Completed items: %s" % \
                        len(self.completed_orders), False)
                
            if len(success_orders) > 0:
                # Print information for all successful orders
                #   including the download location
                msg = "The following images have been downloaded:\n"
                for o in success_orders:
                    rec_id = o.get_recordId()
                    order_id = o.get_orderId()
                    orderitem_id = o.get_itemId()
                    dests = o.get_metadata('download_paths')
                    for d in dests:
                        loc_dest = d['local_destination']
                        src_url = d['url']
                        msg += "\nRecord ID %s\n" % rec_id
                        msg += "    Order Item ID: %s\n" % orderitem_id
                        msg += "    Order ID: %s\n" % order_id
                        msg += "    Downloaded File: %s\n" % loc_dest
                        msg += "    Source URL: %s\n" % src_url
                common.print_footer('Successful Downloads', msg)
            
            if len(failed_orders) > 0:
                msg = "The following images did not download:\n"
                for o in failed_orders:
                    rec_id = o.get_recordId()
                    order_id = o.get_orderId()
                    orderitem_id = o.get_itemId()
                    status = o.get_metadata('status')
                    stat_msg = o.get_metadata('statusMessage')
                    
                    msg += "\nRecord ID %s\n" % rec_id
                    msg += "    Order Item ID: %s\n" % orderitem_id
                    msg += "    Order ID: %s\n" % order_id
                    msg += "    Status: %s\n" % status
                    msg += "    Status Message: %s\n" % stat_msg
                common.print_footer('Failed Downloads', msg)
            
        except KeyboardInterrupt as err:
            self.export_csv()
            print("\nProcess ended by user.")
            common.print_support()
            sys.exit(1)
        except Exception:
            trc_back = "\n%s" % traceback.format_exc()
            common.print_support(trc_back)
            
    def export_csv(self):
        """
        Exports download results to CSV
        """
        
        self.orders_obj.export_csv(self.fn_str)
                    
    def get_results(self):
        """
        Returns the download results.
        
        @rtype:  list
        @return: A list containing the download results.
        """
        
        return self.completed_orders
                    
    def get_latestItems(self, order_id):
        """
        Gets a list of order items from an order with a specified Order ID.
        
        @type  order_id: str
        @param order_id: The Order ID used to get the order items.
        
        @rtype:  list
        @return: A list of order items with the specified Order ID.
        """
        
        common.print_msg("Getting order information to check the status " \
                "of orders. This may take a while...")
        
        # Send a query to the order RAPI, set the maximum to 10000 to ensure
        #   all order items are processed (unless the user has more than 10000 
        #   order items)
        time_start = datetime.datetime.now()
        query = "%s/wes/rapi/order?maxOrders=10000" % common.RAPI_DOMAIN
        res = common.send_query(query, self.session, \
                timeout=common.TIMEOUT_ORDER)
        res_json = res.json()
        time_end = datetime.datetime.now()
        
        total_time = time_end - time_start
        secds = total_time.total_seconds()
        
        if secds < 20:
            sleep_time = 20 - secds
            time.sleep(sleep_time)
        
        order_items = []
        
        # Filter out order items that do not include the Order ID
        for r in res_json['items']:
            if r['orderId'] == int(order_id):
                order_items.append(r)
                
        return order_items
        
    def import_csv(self):
        
        if self.csv_fn is None: return None
        
        eodms_csv = csv_util.EODMS_CSV(self.csv_fn, self.session)
        records = eodms_csv.import_csv()
        
        self.orders = eodms.OrderList()
        
        for o_item in records:
            query = "%s/wes/rapi/order?itemId=%s" % (common.RAPI_DOMAIN, \
                    o_item['itemId'])
            res = common.send_query(query, self.session, \
                    timeout=common.TIMEOUT_ORDER)
            
            # Check for any errors
            if isinstance(res, QueryError):
                err_msg = "Query to RAPI failed due to '%s'" % \
                            res.get_msg()
                common.print_support(err_msg)
                continue
            
            res_json = res.json()
            
            order_item = eodms.OrderItem()
            order_item.parse_record(res_json['items'][0])
            
            order_item.set_metadata('downloaded', o_item['downloaded'])
            
            self.orders.update_order(order_item.get_orderId(), \
                order_item)
        
    def print_progress(self, count, blockSize, totalSize):
        self.download_size += blockSize
        
        if self.size_limit is not None:
            if self.download_size >= int(self.size_limit):
                raise Exception("Download aborted!")
        
        sys.stdout.write('%s  Bytes downloaded: %s\r' % (' '*common.INDENT, \
                        self.download_size))
        sys.stdout.flush()
        
class Orderer:
    """
    The Orderer class contains all the methods and functions used to order 
        image results.
    """
    
    def __init__(self, session, results=None, max_items=100):
        """
        Initializer for Orderer.
        
        @type  session:   request.Session
        @param session:   A request session with authentication.
        @type  record_id: int
        @param record_id: The record ID for a single order.
        @type  coll:      str
        @param coll:      The collection ID name (ex: RCMImageProducts).
        
        @rtype:  n/a
        @return: None
        """
        
        self.session = session
        self.results = results
        if max_items is None:
            self.max_items = 100
        else:
            self.max_items = int(max_items)
        
        self.timeout = 120.0
        self.orders_header = ['Record ID', 'Order Key', 'Date', 'Collection ID', \
                                'Exception', 'Order ID', 'Order Item ID', 'Order ' \
                                'Status', 'Time Ordered']
                              
        
    def export_csv(self, res_bname):
        """
        Exports order results to the CSV file.
        
        @type  res_bname: str
        @param res_bname: The base filename for the CSV file.
        """
        
        # Create the order results CSV
        csv_fn = "%s_OrderResults.csv" % res_bname
        csv_f = open(csv_fn, 'w')
        
        # Add header based on keys of results
        header = list(self.final_results.values())[0][0].keys()
        csv_f.write("%s\n" % ','.join(header))
        
        # Export the results to the file
        for ord_id, rec in self.final_results.items():
            common.export_records(csv_f, header, rec)
        
    def get_results(self):
        """
        Returns the order results.
        
        @rtype:  list
        @return: A list containing the order results.
        """
        return self.final_results
        
    def get_orders(self, img_lst, max_images=None):
        """
        Gets a list of orders for a given set of results.
        
        @type  img_lst: list
        @param img_lst: A list of results used to get the list of orders.
        
        @rtype:  dict
        @return: A dictionary containing a list of order items divided up 
                into their orders.
        """
        
        ##################################################
        common.print_heading("Getting existing orders from the RAPI")
        ##################################################
        
        common.print_msg("Getting order information. This may take a while...")
        
        # Send a query to the order RAPI, set the maximum to 10000 to ensure
        #   all order items are processed (unless the user has more than 10000 
        #   order items)
        query = "%s/wes/rapi/order?maxOrders=10000" % common.RAPI_DOMAIN
        res = common.send_query(query, self.session, \
                timeout=common.TIMEOUT_ORDER)
        res_json = res.json()
        
        order_results = []
        
        # Filter using the Record IDs of the input results
        for r in img_lst.get_images():
            record_id = r.get_recordId()
            for o in res_json['items']:
                if record_id == o['recordId']:
                    order_results.append(o)
        
        self.final_results = eodms.OrderList(img_lst)
        self.final_results.ingest_results(order_results)
        
        self.final_results.get_latest()
        
        if not max_images is None and not max_images == '':
            self.final_results.trim_items(max_images)
        
        order_info = "The following orders were extracted from your cart:\n"
        order_info += self.final_results.print_orders(True)
        common.print_footer('Order Results', order_info)
            
        return self.final_results
        
    def submit_orders(self, img_lst):
        """
        Sends a POST request to the RAPI in order to order images.
        
        @type  img_lst: ImageList
        @param img_lst: A list of records.
        
        @rtype:  dict
        @return: The order information from the order request.
        """
        
        ##################################################
        common.print_heading("Submitting orders to the EODMS")
        ##################################################
        
        try:
            
            order_results = []
            for idx in range(0, img_lst.count(), self.max_items):
                
                # Get the next 100 images
                if img_lst.count() < idx + self.max_items:
                    sub_recs = img_lst.get_subset(idx)
                else:
                    sub_recs = img_lst.get_subset(idx, self.max_items + idx)
            
                # Add the 'Content-Type' option to the header
                self.session.headers.update({'Content-Type': 'application/json'})
                
                items = []
                for r in sub_recs:
                    if not isinstance(r, eodms.Image): continue
                    
                    item = {"collectionId": r.get_collId(), 
                            "recordId": r.get_recordId()}
                            
                    items.append(item)
                
                # If there are no items, return None
                if len(items) == 0: return None
                
                # Create the dictionary for the POST request JSON
                post_dict = {"destinations": [], 
                            "items": items}
                
                # Dump the dictionary into a JSON object
                post_json = json.dumps(post_dict)
                
                # Set the RAPI URL
                order_url = "%s/wes/rapi/order" % common.RAPI_DOMAIN
                
                common.print_msg("Submitting orders for images %s-%s..." % \
                        (str(idx + 1), str(idx + len(items))))
                
                # Send the JSON request to the RAPI
                try:
                    order_res = self.session.post(url=order_url, data=post_json)
                    order_res.raise_for_status()
                except requests.exceptions.HTTPError as errh:
                    return "Http Error: %s" % errh
                except requests.exceptions.ConnectionError as errc:
                    return "Error Connecting: %s" % errc
                except requests.exceptions.Timeout as errt:
                    return "Timeout Error: %s" % errt
                except KeyboardInterrupt as err:
                    print("\nProcess ended by user.")
                    common.print_support()
                    sys.exit(1)
                except requests.exceptions.RequestException as err:
                    return "Exception: %s" % err
                
                if not order_res.ok:
                    err = common.get_exception(order_res)
                    if isinstance(err, list):
                        return '; '.join(err)
                
                order_results += order_res.json()['items']
                
            common.print_msg("Number of order items: %s" % len(order_results))
            
            # Convert results to ImageList
            self.final_results = eodms.OrderList(img_lst)
            self.final_results.ingest_results(order_results)
            
            order_info = "The following orders were submitted to the EODMS:\n"
            order_info += self.final_results.print_orders(True)
            common.print_footer('Submitted Orders', order_info)
            
            return self.final_results
            
        except Exception as err:
            traceback.print_exc(file=sys.stdout)
            return err
            
class QueryError:
    """
    The QueryError class is used to store error information for a query.
    """
    
    def __init__(self, msg):
        """
        Initializer for QueryError object which stores an error message.
        
        @type  msg: str
        @param msg: The error message to print.
        """
        
        self.msg = msg
        
    def get_msg(self):
        return self.msg
        
    def set_msg(self, msg):
        self.msg = msg

class Query:
    """
    The Query class contains all the functions and methods used to send 
        queries to the RAPI.
    """
    
    def __init__(self, session, coll=None, dates=None, aoi=None, 
                max_images=None):
        """
        Initializer for the Query object.
        
        @type  session:    request.Session
        @param session:    The request session containing the EODMS 
                            creditentials.
        @type  coll:       list
        @param coll:       A list of collections for the query.
        @type  dates:      str
        @param dates:      A range of dates separated by a dash.
        @type  aoi:        str
        @param aoi:        The path of the AOI file.
        @type  max_images: int
        @param max_images: The maximum number of images to return for 
                            ordering/downloading.
        """
        
        if not isinstance(coll, list):
            coll = [coll]
        self.collections = coll
        self.dates = dates
        self.aoi = aoi
        self.session = session
        if max_images is not None and not max_images == '':
            max_images = int(max_images)
        self.max_images = max_images
        
    def get_results(self):
        """
        Returns the query results.
        
        @rtype:  list
        @return: A list containing the query results.
        """
        
        return self.results
        
    def parse_dates(self):
        #print("dates: %s" % self.dates)
        
        if self.dates is None or self.dates == '':
            return ''
        
        ranges = self.dates.split(',')
        
        out_dates = []
        for rng in ranges:
            out_dates.append(rng.split('-'))
            
        return out_dates
        
    def query_csvRecords(self, records):
        """
        Queries a previous list of records.
        """
        
        ##################################################
        common.print_heading("Retrieving Record IDs for the list of " \
            "entries in the CSV file")
        ##################################################
        
        # Group all records into different collections
        coll_recs = {}
        for rec in records:
            # Get the collection ID for the image
            collection = rec['Collection ID']
            
            rec_lst = []
            if collection in coll_recs.keys():
                rec_lst = coll_recs[collection]
                
            rec_lst.append(rec)
            
            coll_recs[collection] = rec_lst
        
        all_res = []
        
        for coll, recs in coll_recs.items():
            
            for idx in range(0, len(recs), 25):
                
                # Get the next 100 images
                if len(recs) < idx + 25:
                    sub_recs = recs[idx:]
                else:
                    sub_recs = recs[idx:25 + idx]
            
                queries = []
                
                for rec in sub_recs:
                    
                    if 'Sequence ID' in rec.keys():
                        # If the Sequence ID is in the image dictionary, 
                        #   return it as the Record ID
                        query = "CATALOG_IMAGE.SEQUENCE_ID='%s'" % \
                                rec['Sequence ID']
                    elif 'Record ID' in rec.keys():
                        # If the Record ID is in the image dictionary, return it
                        query = "CATALOG_IMAGE.SEQUENCE_ID='%s'" % \
                                rec['Record ID']
                    elif 'Image Info' in rec.keys() and \
                        not rec['Image Info'] == '':
                        # Parse Image Info
                        img_info = rec['Image Info'].replace(' ', ', ')
                        img_info = img_info.replace('""', '"')
                        img_info = img_info.replace('"{', '{').replace('}"', \
                                    '}')
                        json_imgInfo = json.loads(img_info)
                        query = "CATALOG_IMAGE.SEQUENCE_ID='%s'" % \
                                json_imgInfo['imageID']
                    else:
                        # # If the Order Key is in the image dictionary,
                        # #   use it to query the RAPI
                        common.print_msg("WARNING: Cannot determine record " \
                                "ID for Result Number '%s' in the CSV file. " \
                                "Skipping image." % rec['Result Number'])
                        continue
                                        
                    queries.append(query)
                    
                if len(queries) == 0: continue
                    
                full_query = ' or '.join(queries)
                
                if coll == 'NAPL':
                    full_query += ' and CATALOG_IMAGE.OPEN_DATA=TRUE'
                
                full_queryEnc = urllib.parse.quote(full_query)
                query_url = "%s/wes/rapi/search?collection=%s&query=%s" \
                            "&maxResults=100" % (common.RAPI_DOMAIN, \
                            collection, full_queryEnc)
            
                # Send the query to the RAPI
                res = common.send_query(query_url, self.session, \
                        common.TIMEOUT_QUERY, quiet=False)
                
                # If an error occurred
                if isinstance(res, QueryError):
                    common.print_msg("WARNING: %s" % res.get_msg())
                    continue
                
                # If the results is a list, an error occurred
                if isinstance(res, list):
                    common.print_msg("WARNING: %s" % ' '.join(res))
                    continue
                
                # Convert RAPI results to JSON
                res_json = res.json()
                
                # Get the results from the JSON
                cur_res = res_json['results']
                
                # If no results, return as error
                if len(cur_res) == 0:
                    err = "No images could be found."
                    common.print_msg("WARNING: %s" % err)
                    common.print_msg("Skipping this entry", False)
                    continue
                
                all_res += cur_res
        
        # Convert results to ImageList
        self.results = eodms.ImageList()
        self.results.ingest_results(all_res)
            
        return self.results
        
    def query_records(self):
        """
        Gets a list of records from the RAPI using an AOI.
        
        @rtype:  list
        @return: A list of all the records from the RAPI query.
        """
        
        ##################################################
        common.print_heading("Retrieving images from RAPI using the AOI")
        ##################################################
        
        eodms_geo = geo.Geo(self.aoi)
        
        # Get the polygon from the AOI file
        self.aoi_feat = eodms_geo.get_polygon()
        
        all_res = []
        for coll in self.collections:
            # Get results for each collection
            
            common.print_msg("Getting results from RAPI for '%s' collection..." % coll)
            
            query_lst = []
            
            # Get the collection ID
            coll_id = common.get_collIdByName(coll)
            
            if coll_id is None:
                # Get the full collection ID
                coll_id = common.get_fullCollId(coll)
                
                # If the collection ID is not supported by this script, skip it
                if coll_id is None:
                    continue
            
            # Create query parameter for AOI
            ft_prt_id = common.RAPI_COLLECTIONS[coll_id]['fields']['Footprint']
            query_lst.append('%s INTERSECTS %s' % (ft_prt_id, self.aoi_feat))
            
            # Create query parameters for dates
            date_rngs = self.parse_dates()
            date_queries = []
            for rng in date_rngs:
                
                if len(rng) < 2: continue
                
                # Separate date range
                start = common.convert_date(rng[0])
                end = common.convert_date(rng[1])
                
                # Get the specific Creation Date field for this collection
                field_id = common.RAPI_COLLECTIONS[coll_id]['fields']\
                            ['Creation Date']
                
                # Add query parameter to list
                date_queries.append("%s between DT'%s' and DT'%s'" % (field_id, \
                    start, end))
                    
            query_lst.append("(%s)" % ' or '.join(date_queries))
            
            if coll_id == 'NAPL':
                # If the collection is NAPL, add an open data parameter
                query_lst.append('CATALOG_IMAGE.OPEN_DATA=TRUE')
            
            # Combine all query parameters
            full_query = ' and '.join(query_lst)
            
            if self.max_images is None or self.max_images == '':
                maxResults = 10000
            else:
                maxResults = self.max_images
            
            # Build the query URL
            params = {'collection': coll_id, 
                    'query': full_query, 
                    'resultField': ft_prt_id, 
                    'maxResults': maxResults, 
                    'format': "json"}
            query_str = urlencode(params)
            query_url = '%s/wes/rapi/search?%s' % \
                        (common.RAPI_DOMAIN, query_str)
            
            res = common.send_query(query_url, self.session, \
                    common.TIMEOUT_QUERY)
            
            # If an error occurred
            if isinstance(res, QueryError):
                common.print_msg("WARNING: %s" % res.get_msg())
                return res
            
            # Add this collection's results to all results
            all_res += res.json()['results']
        
        # Convert results to ImageList
        self.results = eodms.ImageList()
        self.results.ingest_results(all_res)
        
        return self.results