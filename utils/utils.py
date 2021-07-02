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
import logging
from inspect import currentframe, getframeinfo
import re
import dateparser

from . import common
from . import geo
from . import eodms
from . import csv_util

class EODMSRAPI:
    
    def __init__(self, username, password):
    
        self.session = requests.Session()
        self.session.auth = (username, password)
        
        self.logger = logging.getLogger('eodms')
        self.rapi_root = "https://www.eodms-sgdot.nrcan-rncan.gc.ca/wes/rapi"
        
        self.rapi_collections = {}
        self.unsupport_collections = {}
        self.download_size = 0
        self.size_limit = None
        
        return None
        
    def print_progress(self, count, blockSize, totalSize):
        self.download_size += blockSize
        
        if self.size_limit is not None:
            if self.download_size >= int(self.size_limit):
                raise Exception("Download aborted!")
        
        sys.stdout.write('%s  Bytes downloaded: %s\r' % (' '*common.INDENT, \
                        self.download_size))
        sys.stdout.flush()
        
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
            msg = "Unexpected error: %s" % traceback.format_exc()
            common.print_msg(msg)
            self.logger.warning(msg)
            pass
            
    def set_downloadSize(self, size):
        self.download_size = size
        
    def get_availableFields(self, collection):
        """
        Gets a dictionary of available fields for a collection from the RAPI.
        
        @type  collection: str
        @param collection: The Collection ID.
        
        @rtype:  dict
        @return: A dictionary containing the available fields for the given 
                collection.
        """
        
        query_url = '%s/collections/%s' % (self.rapi_root, collection)
        
        self.logger.info("Getting Fields for Collection %s (RAPI Query): %s" % \
                    (collection, query_url))
        
        coll_res = self.submit(query_url, timeout=20.0)
        
        # If an error occurred
        if isinstance(coll_res, QueryError):
            print("\n  WARNING: %s" % coll_res.get_msg())
            self.logger.warning(coll_res.get_msg())
            return coll_res
        
        coll_json = coll_res.json()
        
        # Get a list of the searchFields
        fields = {}
        for r in coll_json['searchFields']:
            fields[r['title']] = {'id': r['id'], 'datatype': r['datatype']}
            
        return fields
        
    def get_collections(self, as_list=False, redo=False):
        """
        Gets a list of available collections for the current user.
        
        @type  as_list: boolean
        @param as_list: Determines the type of return. If False, a dictionary
                            will be returned. If True, only a list of collection
                            IDs will be returned.
        
        @rtype:  dict or list (depending on value of as_list)
        @return: Either a dictionary of collections or a list of collection IDs 
                    depending on the value of as_list.
        """
        
        print("\nGetting a list of available collections for the script, please wait...")
        
        if self.rapi_collections and not redo:
            return self.rapi_collections
        
        # List of collections that are either commercial products or not available 
        #   to the general public
        ignore_collNames = ['RCMScienceData', 'Radarsat2RawProducts', 
                            'Radarsat1RawProducts', 'COSMO-SkyMed1', '162', 
                            '165', '164']
        
        # Create the query to get available collections for the current user
        query_url = "%s/collections" % self.rapi_root
        
        self.logger.info("Getting Collections (RAPI Query): %s" % query_url)
        
        # Send the query URL
        coll_res = self.submit(query_url, timeout=20.0)
        
        # If an error occurred
        if isinstance(coll_res, QueryError):
            msg = "Could not get a list of collections due to '%s'.\nPlease try " \
                    "running the script again." % coll_res.get_msg()
            common.print_support(msg)
            self.logger.error(msg)
            sys.exit(1)
        
        # If a list is returned from the query, return it
        if isinstance(coll_res, list):
            return coll_res
        
        # Convert query to JSON
        coll_json = coll_res.json()
        
        # Create the collections dictionary
        for coll in coll_json:
            if 'children' in coll.keys():
                for child in coll['children']:
                    if child['collectionId'] in ignore_collNames:
                        if 'children' in child.keys():
                            for c in child['children']:
                                self.unsupport_collections[c['collectionId']] = c['title']
                    else:
                        if 'children' in child.keys():
                            for c in child['children']:
                                if c['collectionId'] in ignore_collNames:
                                    self.unsupport_collections[c['collectionId']] = c['title']
                                else:
                                    fields = self.get_availableFields(c['collectionId'])
                                    self.rapi_collections[c['collectionId']] = {'title': c['title'], \
                                        'fields': fields}
        
        # If as_list is True, convert dictionary to list of collection IDs
        if as_list:
            collections = [i['title'] for i in self.rapi_collections.values()]
            return collections
            
        if len(collections) == 0:
            msg = "Could not get a list of collections.\nPlease try " \
                    "running the script again."
            common.print_support(msg)
            self.logger.error(msg)
            sys.exit(1)
        
        return self.rapi_collections
        
    def get_collIdByName(self, in_title, unsupported=False):
        """
        Gets the Collection ID based on the tile/name of the collection.
        
        @type  in_title:    str
        @param in_title:    The title/name of the collection.
                            (ex: 'RCM Image Products' for ID 'RCMImageProducts')
        @type  unsupported: boolean
        @param unsupported: Determines whether to check in the unsupported list 
                            or not.
        """
        
        if isinstance(in_title, list):
            in_title = in_title[0]
        
        if unsupported:
            for k, v in self.unsupport_collections.items():
                if v.find(in_title) > -1 or in_title.find(v) > -1 \
                    or in_title.find(k) > -1 or k.find(in_title) > -1:
                    return k
        
        for k, v in self.rapi_collections.items():
            if v['title'].find(in_title) > -1:
                return k
                
        return self.get_fullCollId(in_title)
                
    def get_collectionName(self, in_id):
        """
        Gets the collection name for a specified collection ID.
        
        @type  in_id: str
        @param in_id: The collection ID.
        """
        
        return self.rapi_collections[in_id]
        
    def get_fieldType(self, coll_id, field_id):
        
        for k, v in self.rapi_collections[coll_id]['fields'].items():
            if v['id'] == field_id:
                return v['datatype']
                
    def get_fullCollId(self, coll_id, unsupported=False):
        """
        Gets the full collection ID using the input collection ID which can be a 
            substring of the collection ID.
        
        @type  coll_id:     str
        @param coll_id:     The collection ID to check.
        @type  unsupported: boolean
        @param unsupported: Determines whether to check in the supported or 
                            unsupported collection lists.
        """
        
        if unsupported:
            print("self.unsupport_collections: %s" % self.unsupport_collections)
            for k in self.unsupport_collections.keys():
                if k.find(coll_id) > -1:
                    return k
        
        for k in self.rapi_collections.keys():
            if k.find(coll_id) > -1:
                return k
                
    def get_order(self, itemId):
        
        query = "%s/order?itemId=%s" % (self.rapi_root, itemId)
        self.logger.info("Getting order item %s (RAPI query): %s" % \
                    (itemId, query))
        res = self.submit(query, timeout=common.TIMEOUT_ORDER)
                
        return res
                
    def get_orders(self, maxOrders=10000):
        
        query_url = "%s/order?maxOrders=%s&format=json" % (self.rapi_root,\
                    maxOrders)
                    
        self.logger.info("Searching for images (RAPI query):\n\n%s\n" % \
                        query_url)
                        
        # Send the query to the RAPI
        res = self.submit(query_url, common.TIMEOUT_QUERY, quiet=False)
                
        return res
        
    def send_query(self, collection, query=None, resultField=None, 
                    maxResults=100):
        
        full_query = query.get_query()
        full_queryEnc = urllib.parse.quote(full_query)
        
        params = {'collection': collection}
        
        if query is not None:
            params['query'] = full_query
            
        if resultField is not None:
            if isinstance(resultField, list):
                params['resultField'] = ','.join(resultField)
            else:
                params['resultField'] = resultField
                
        if maxResults is not None:
            params['maxResults'] = maxResults
            
        params['format'] = "json"
        
        query_str = urlencode(params)
        query_url = "%s/search?%s" % (self.rapi_root, query_str)
        
        self.logger.info("Searching for images (RAPI query):\n\n%s\n" % \
                        query_url)
        # Send the query to the RAPI
        res = self.submit(query_url, common.TIMEOUT_QUERY, quiet=False)
                
        return res
        
    def send_order(self, items):
        
        # Add the 'Content-Type' option to the header
        self.session.headers.update({'Content-Type': 'application/json'})
        
        # Create the dictionary for the POST request JSON
        post_dict = {"destinations": [], 
                    "items": items}
                    
        # Dump the dictionary into a JSON object
        post_json = json.dumps(post_dict)
        
        # Set the RAPI URL
        order_url = "%s/order" % self.rapi_root
        
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
            self.logger.info("Process ended by user.")
            sys.exit(1)
        except requests.exceptions.RequestException as err:
            return "Exception: %s" % err
        
        if not order_res.ok:
            err = common.get_exception(order_res)
            if isinstance(err, list):
                return '; '.join(err)
                
        return order_res
        
    def submit(self, query_url, timeout=60.0, record_name=None, 
                quiet=True):
        """
        Send a query to the RAPI.
        
        @type  query_url:   str
        @param query_url:   The query URL.
        @type  timeout:     float
        @param timeout:     The length of the timeout in seconds.
        @type  record_name: str
        @param record_name: A string used to supply information for the record 
                            in a print statement.
        
        @rtype  request.Response
        @return The response returned from the RAPI.
        """
        
        verify = True
        
        if not quiet:
            common.print_msg("RAPI Query URL: %s" % query_url)
        
        res = None
        attempt = 1
        err = None
        # Get the entry records from the RAPI using the downlink segment ID
        while res is None and attempt <= common.ATTEMPTS:
            
            # Continue to attempt if timeout occurs
            try:
                if record_name is None:
                    msg = "Querying the RAPI (attempt %s)..." % attempt
                    if not quiet:
                        common.print_msg(msg)
                else:
                    msg = "Querying the RAPI for '%s' " \
                                "(attempt %s)..." % (record_name, attempt)
                    if not quiet:
                        common.print_msg(msg)
                if self.session is None:
                    res = requests.get(query_url, timeout=timeout, verify=verify)
                else:
                    res = self.session.get(query_url, timeout=timeout, verify=verify)
                res.raise_for_status()
            except requests.exceptions.HTTPError as errh:
                msg = "HTTP Error: %s" % errh
                
                if msg.find('Unauthorized') > -1:
                    err = msg
                    attempt = 4
                
                if attempt < common.ATTEMPTS:
                    msg = "WARNING: %s; attempting to connect again..." % msg
                    common.print_msg(msg)
                    self.logger.warning(msg)
                    res = None
                else:
                    err = msg
                attempt += 1
            except requests.exceptions.ConnectionError as errc:
                msg = "Connection Error: %s" % errc
                if attempt < common.ATTEMPTS:
                    msg = "WARNING: %s; attempting to connect again..." % msg
                    common.print_msg(msg)
                    self.logger.warning(msg)
                    res = None
                else:
                    err = msg
                attempt += 1
            except requests.exceptions.Timeout as errt:
                msg = "Timeout Error: %s" % errt
                if attempt < common.ATTEMPTS:
                    msg = "WARNING: %s; attempting to connect again..." % msg
                    common.print_msg(msg)
                    self.logger.warning(msg)
                    res = None
                else:
                    err = msg
                attempt += 1
            except requests.exceptions.RequestException as err:
                msg = "Exception: %s" % err
                if attempt < common.ATTEMPTS:
                    msg = "WARNING: %s; attempting to connect again..." % msg
                    common.print_msg(msg)
                    self.logger.warning(msg)
                    res = None
                else:
                    err = msg
                attempt += 1
            except KeyboardInterrupt as err:
                print("\nProcess ended by user.")
                self.logger.info("Process ended by user.")
                common.print_support()
                sys.exit(1)
            except:
                msg = "Unexpected error: %s" % traceback.format_exc()
                if attempt < common.ATTEMPTS:
                    msg = "WARNING: %s; attempting to connect again..." % msg
                    common.print_msg(msg)
                    self.logger.warning(msg)
                    res = None
                else:
                    err = msg
                attempt += 1
                
        if err is not None:
            query_err = QueryError(err)
            return query_err
                
        # If no results from RAPI, return None
        if res is None: return None
        
        # Check for exceptions that weren't already caught
        except_err = common.get_exception(res)
        
        if isinstance(except_err, QueryError):
            err_msg = except_err.get_msg()
            if err_msg.find('401 - Unauthorized') > -1:
                # Inform the user if the error was caused by an authentication 
                #   issue.
                err_msg = "An authentication error has occurred while " \
                            "trying to access the EODMS RAPI. Please run this " \
                            "script again with your username and password."
                common.print_support(err_msg)
                self.logger.error(err_msg)
                sys.exit(1)
                
            print("WARNING: %s" % err_msg)
            self.logger.warning(err_msg)
            return except_err
            
        return res

class Downloader:
    """
    The Downloader class contains all the methods and functions used to 
        download EODMS images.
    """
    
    def __init__(self, max_images=None, fn_str='', 
                in_csv=None, size_limit=None):
        """
        Initializer for the Downloader object.
        
        @type  eodms_rapi: EODMSRAPI
        @param eodms_rapi: The EODMSRAPI object used to query the RAPI
        """
        
        self.eodms_rapi = common.EODMS_RAPI
        self.completed_orders = []
        self.max_images = max_images
        self.size_limit = size_limit
        self.fn_str = fn_str
        self.csv_fn = in_csv
        self.orders = None
        
        self.logger = logging.getLogger('eodms')
        
        self.import_csv()
        
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
            msg = "No orders provided for download."
            print("\n%s" % msg)
            self.logger.warning(msg)
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
                        
                order_lst = cur_orders.get_orders()
                
                if order_lst is None:
                    warn_msg = "Could not get a list of orders."
                    logger.warning(warn_msg)
                    continue
                
                for order in order_lst:
                    
                    if self.max_images is not None and not self.max_images == '':
                        if len(self.completed_orders) >= int(self.max_images):
                            break
                    
                    # Keep looping until all processed order items have been 
                    #   checked
                    
                    # Get the current order ID
                    ord_id = order.get_orderId()
                    
                    # Get a list of order items in this order
                    ord_items = self.get_latestItems(ord_id)
                    
                    if ord_items is None:
                        err_msg = "Could not retrieve orders. Trying again..."
                        common.print_msg(err_msg, False)
                        self.logger.warning(err_msg)
                        continue
                    
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
                                msg = "Skipping download of " \
                                    "image with Record ID %s. Image already " \
                                    "downloaded." % record_id
                                common.print_msg(msg)
                                self.logger.info(msg)
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
                        
                        if img_status == 'AVAILABLE_FOR_DOWNLOAD' or \
                            img_status == 'EXPANDED':
                            
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
                                msg = "Downloading image with " \
                                        "Record ID %s (%s)." % (record_id, \
                                        os.path.basename(url))
                                common.print_msg(msg)
                                self.logger.info(msg)
                                
                                # # Save the image contents to the 'downloads' folder
                                if prev_path is None:
                                    out_fn = os.path.join(common.DOWNLOAD_PATH, \
                                            self.fn_str, fn)
                                else:
                                    out_fn = prev_path
                                full_path = os.path.realpath(out_fn)
                                
                                if not os.path.exists(os.path.dirname(full_path)):
                                    os.mkdir(os.path.dirname(full_path))
                                
                                self.eodms_rapi.set_downloadSize(0)
                                self.eodms_rapi.download_image(url, out_fn)
                                print('')
                                self.eodms_rapi.set_downloadSize(0)
                                
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
                            msg = "No images ready to download " \
                                    "yet. Please wait..."
                            common.print_msg(msg)
                        else:
                            msg = "No new images are ready to " \
                                    "download yet. Please wait..."
                            common.print_msg(msg)
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
                self.logger.info(tot_msg)
                common.print_msg("Completed items: %s" % \
                        len(self.completed_orders), False)
                self.logger.info("Completed items: %s" % len(self.completed_orders))
                
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
                self.logger.info("Successful Downloads: %s" % msg)
            
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
                self.logger.info("Failed Downloads: %s" % msg)
            
        except KeyboardInterrupt as err:
            self.export_csv()
            msg = "Process ended by user."
            print("\n%s" % msg)
            self.logger.warning(msg)
            common.print_support()
            sys.exit(1)
        except Exception:
            trc_back = "\n%s" % traceback.format_exc()
            common.print_support(trc_back)
            self.logger.error(traceback.format_exc())
            
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
        
        res = self.eodms_rapi.get_orders()        
        
        # Check for any errors
        if isinstance(res, QueryError):
            err_msg = "Query to RAPI failed due to '%s'" % \
                        res.get_msg()
            common.print_msg(err_msg, False)
            self.logger.warning(err_msg)
            return None
        
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
        
        eodms_csv = csv_util.EODMS_CSV(self.csv_fn)
        records = eodms_csv.import_csv()
        
        self.orders = eodms.OrderList()
        
        cur_orders = None
        
        for o_item in records:
            item_id = o_item.get('itemId')
            
            if item_id is None:
                common.print_msg("The Order Item ID cannot be extracted " \
                    "from the CSV file. Make sure the file has a column " \
                    "named 'itemId'.")
                return None
                    
            res = self.eodms_rapi.get_order(item_id)
            
            # Check for any errors
            if isinstance(res, QueryError):
                err_msg = "Query to RAPI failed due to '%s'" % \
                            res.get_msg()
                common.print_msg(err_msg)
                self.logger.warning(err_msg)
                continue
            
            res_json = res.json()
            
            item_json = None
            if len(res_json['items']) == 0:
                
                # Get all orders
                if cur_orders is None:
                    cur_orders = self.eodms_rapi.get_orders()
                    
                if isinstance(cur_orders, QueryError):
                    err_msg = "Query to RAPI failed due to '%s'" % \
                                cur_orders.get_msg()
                    common.print_msg(err_msg)
                    self.logger.warning(err_msg)
                    continue
                
                # Determine Order Item using ParentItemId
                cur_orders = cur_orders.json()
                for o in cur_orders.get('items'):
                    params = o.get('parameters')
                    
                    if params is None: continue
                    
                    parentItemId = params.get('ParentItemId')
                    
                    if parentItemId is None: continue
                    
                    if int(parentItemId) == int(item_id):
                        item_json = o
            else:
                item_json = res_json['items'][0]
                
            if item_json is None:
                err_msg = "No Order Item exists with Item ID %s." % \
                    o_item.get('itemId')
                common.print_msg(err_msg)
                self.logger.warning(err_msg)
                continue
            
            order_item = eodms.OrderItem()
            order_item.parse_record(item_json)
            
            if 'downloaded' in o_item.keys():
                downloaded = o_item.get('downloaded')
            else:
                downloaded = 'False'
            order_item.set_metadata('downloaded', downloaded)
            
            self.orders.update_order(order_item.get_orderId(), \
                order_item)
        
class Orderer:
    """
    The Orderer class contains all the methods and functions used to order 
        image results.
    """
    
    def __init__(self, results=None, max_items=100, fn_str=''):
        """
        Initializer for Orderer.
        
        @type  record_id:  int
        @param record_id:  The record ID for a single order.
        @type  coll:       str
        @param coll:       The collection ID name (ex: RCMImageProducts).
        
        @rtype:  n/a
        @return: None
        """
        
        self.eodms_rapi = common.EODMS_RAPI
        self.results = results
        self.fn_str = fn_str
        if max_items is None:
            self.max_items = 100
        else:
            self.max_items = int(max_items)
        
        self.timeout = 120.0
        self.orders_header = ['Record ID', 'Order Key', 'Date', 'Collection ID', \
                                'Exception', 'Order ID', 'Order Item ID', 'Order ' \
                                'Status', 'Time Ordered']
                                
        self.logger = logging.getLogger('eodms')
                              
        
    def export_csv(self):
        """
        Exports order results to the CSV file.
        """
            
        self.final_results.export_csv(self.fn_str)
        
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
                
        res = self.eodms_rapi.get_orders(10000)
        
        # Check for any errors
        if isinstance(res, QueryError):
            err_msg = "Query to RAPI failed due to '%s'" % \
                        res.get_msg()
            common.print_msg(err_msg, False)
            self.logger.warning(err_msg)
            return None
                
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
        
        self.logger.info("Order Results: %s" % order_info)
            
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
                
                items = []
                for r in sub_recs:
                    if not isinstance(r, eodms.Image): continue
                    
                    item = {"collectionId": r.get_collId(), 
                            "recordId": r.get_recordId()}
                            
                    items.append(item)
                
                # If there are no items, return None
                if len(items) == 0: return None
                
                msg = "Submitting orders for images %s-%s..." % \
                        (str(idx + 1), str(idx + len(items)))
                common.print_msg(msg)
                self.logger.info(msg)
                
                res = self.eodms_rapi.send_order(items)
                
                if isinstance(res, str):
                    return res
                    
                # Check for any errors
                if isinstance(res, QueryError):
                    err_msg = "Query to RAPI failed due to '%s'" % \
                                res.get_msg()
                    common.print_msg(err_msg, False)
                    self.logger.warning(err_msg)
                    continue
                
                order_results += res.json()['items']
                
            msg = "Number of order items: %s" % len(order_results)
            common.print_msg(msg)
            self.logger.info(msg)
            
            # Convert results to ImageList
            self.final_results = eodms.OrderList(img_lst)
            self.final_results.ingest_results(order_results)
            
            order_info = "The following orders were submitted to the EODMS:\n"
            order_info += self.final_results.print_orders(True)
            common.print_footer('Submitted Orders', order_info)
            self.logger.info("Submitted Orders: %s" % order_info)
            
            self.export_csv()
            
            return self.final_results
            
        except Exception as err:
            self.export_csv()
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
    
    def __init__(self, coll=None, dates=None, aoi=None, 
                max_images=None, filters={}):
        """
        Initializer for the Query object.
        
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
        self.eodms_rapi = common.EODMS_RAPI
        if max_images is not None and not max_images == '':
            max_images = int(max_images)
        self.max_images = max_images
        self.filters = filters
        
        self.logger = logging.getLogger('eodms')
        
    def get_results(self):
        """
        Returns the query results.
        
        @rtype:  list
        @return: A list containing the query results.
        """
        
        return self.results
        
    def get_dates(self):
        """
        Gets the date range based on the user's value
        """
        
        if self.dates is None or self.dates == '':
            return ''
            
        time_words = ['hour', 'day', 'week', 'month', 'year']
        
        if any(word in self.dates for word in time_words):
            start = dateparser.parse(self.dates).strftime("%Y%m%dT%H%M%S")
            end = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
            return [[start, end]]
        else:
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
            collection = rec['collection id']
            
            rec_lst = []
            if collection in coll_recs.keys():
                rec_lst = coll_recs[collection]
                
            rec_lst.append(rec)
            
            coll_recs[collection] = rec_lst
        
        all_res = []
        
        for coll, recs in coll_recs.items():
            
            coll_filts = common.FILT_MAP[coll]
            
            for idx, rec in enumerate(recs):
                
                query_build = QueryBuilder(common.EODMS_RAPI.\
                            get_collIdByName(coll))
                
                id_val = None
                
                # Check if record contains a sequence id, record id 
                #   or recordid and add to QueryBuilder
                for i in ['sequence id', 'record id', 'recordid']:
                    if id_val is None:
                        id_val = rec.get(i)
                        
                if id_val is not None:
                    rapi_id = coll_filts['SEQUENCE_ID']
                    query_build.add_filter(rapi_id, id_val)
                    
                else:
                    
                    order_key = rec.get('order key')
                    
                    if order_key is None or order_key == '':
                        msg = "Cannot determine record " \
                                "ID for Result Number '%s' in the CSV file. " \
                                "Skipping image." % rec.get('result number')
                        self.print_msg("WARNING: %s" % msg)
                        self.logger.warning(msg)
                        continue
                    
                    rapi_id = coll_filts['ORDER_KEY']
                    query_build.add_filter(rapi_id, order_key)
                
                common.print_msg("Getting information for image %s out of " \
                    "%s..." % (idx + 1, len(recs)))
                res = self.eodms_rapi.send_query(collection, query_build)
                        
                # If an error occurred
                if isinstance(res, QueryError):
                    common.print_msg("WARNING: %s" % res.get_msg())
                    self.logger.warning(res.get_msg())
                    continue
                
                # If the results is a list, an error occurred
                if isinstance(res, list):
                    common.print_msg("WARNING: %s" % ' '.join(res))
                    self.logger.warning(' '.join(res))
                    continue
                
                # Convert RAPI results to JSON
                res_json = res.json()
                
                # Get the results from the JSON
                cur_res = res_json['results']
                
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
        self.aoi_feats = eodms_geo.get_features()
        
        all_res = []
        for coll in self.collections:
            # Get results for each collection
            
            common.print_msg("Getting results from RAPI for '%s' collection..." % coll)
            
            query_lst = []
            
            # Get the collection ID
            coll_id = self.eodms_rapi.get_collIdByName(coll)
            
            if coll_id is None:
                # Get the full collection ID
                coll_id = self.eodms_rapi.get_fullCollId(coll)
                
                # If the collection ID is not supported by this script, skip it
                if coll_id is None:
                    continue
                    
            query_build = QueryBuilder(coll_id)
            
            # Create query parameter for AOI
            collections = self.eodms_rapi.get_collections()
            footprint_id = collections[coll_id]['fields']['Footprint']['id']
            query_build.add_aoi(footprint_id, self.aoi_feats)
            
            # Create query parameters for dates
            date_rngs = self.get_dates()
            date_queries = []
            for rng in date_rngs:
                
                if len(rng) < 2: continue
                
                # Separate date range
                start = common.convert_date(rng[0])
                end = common.convert_date(rng[1])
                
                # Get the specific Creation Date field for this collection
                fields = collections[coll_id]['fields']
                if 'Acquisition Start Date' in fields.keys():
                    field_id = fields['Acquisition Start Date']['id']
                else:
                    field_id = fields['Start Date']['id']
                
                # Add query parameter to list
                query_build.add_dates(field_id, [start, end])
            
            if coll_id == 'NAPL':
                # If the collection is NAPL, add an open data parameter
                query_build.set_open(True)  
            
            # Add filters specified by user
            user_filts = []
            for k, v in self.filters.items():
                if coll_id.find(k) > -1:
                    user_filts = v
            
            filt_queries = []
            for filt in user_filts:
                
                if not any(x in filt for x in common.OPERATORS):
                    print("Filter '%s' entered incorrectly." % filt)
                    continue
                
                ops = [x for x in common.OPERATORS if x in filt]

                for o in ops:
                    filt_split = filt.split(o)
                    op = o
                
                key = filt_split[0].strip()
                val = filt_split[1].strip()
                
                val = val.replace('"', '').replace("'", '')
                
                if val is None or val == '':
                    err = "No value specified for Filter ID '%s'." % key
                    common.print_msg("ERROR: %s" % err)
                    return err
                
                # Get the RAPI key using the filter map
                coll_filts = common.FILT_MAP[coll_id]
                rapi_id = coll_filts[key]
                
                if val.find('|') > -1:
                    vals = val.split('|')
                    
                    query_build.add_filter(rapi_id, vals, op)
                    
                else:
                    query_build.add_filter(rapi_id, val, op)
            
            if self.max_images is None or self.max_images == '':
                maxResults = common.MAX_RESULTS
            else:
                maxResults = self.max_images
            
            for fk, fv in collections[coll_id]['fields'].items():
                if fv['id'].find('BEAM_MNEMONIC') > -1:
                    beam_mnem = fv['id']
            
            res = self.eodms_rapi.send_query(coll_id, query_build, beam_mnem, \
                    maxResults)
            
            # If an error occurred
            if isinstance(res, QueryError):
                common.print_msg("WARNING: %s" % res.get_msg())
                self.logger.warning(res.get_msg())
                return res
            
            # Add this collection's results to all results
            all_res += res.json()['results']
        
        # Convert results to ImageList
        self.results = eodms.ImageList()
        self.results.ingest_results(all_res)
        
        return self.results

class QueryBuilder:
    
    """
    The QueryBuilder class is used to store information and build the query 
    string for searching the RAPI.
    """
    
    class QueryFilter:
        
        def __init__(self, query_builder, field=None, value=None, 
                    operator='=', val_range=False):
            """
            Initializer for the Filter object.
            
            @type  field:    str
            @param field:    The field of the filter.
            @type  value:    str, list or list of lists
            @param value:    A value, a list representing a range or a list 
                                of lists containing multiple ranges.
            @type  operator: str
            @param operator: The operator for the filter.
            """
            
            self.query_builder = query_builder
            self.field = field
            self.value = value
            self.operator = operator
            self.val_range = val_range
            
        def convert_operator(self, op):
            # Convert the operator
            for o in common.OPERATORS:
                if o.strip().upper() == self.operator.strip().upper():
                    op = o
                    
            return op
            
        def get_field(self):
            return self.field
        
        def set_field(self, field):
            self.field = field
        
        def get_value(self):
            return self.value
            
        def set_value(self, val):
            self.value = value
            
        def get_operator(self):
            return self.operator
            
        def set_operator(self, op):
            self.operator = op
            
        def build_query(self, sub_val=None):
            
            if sub_val is None:
                sub_val = self.value
                
            # Convert the operator
            op = self.convert_operator(self.operator)
                
            if isinstance(sub_val, list) and len(sub_val) > 1:
            
                if self.val_range:
                    try:
                        float(sub_val[0])
                        is_float = True
                    except ValueError:
                        is_float = False
                        
                    if is_float:
                        filter_query = '(%s>=%s AND %s<=%s)' % (self.field, \
                                        sub_val[0], self.field, sub_val[1])
                    else:
                        filter_query = "(%s>='%s' AND %s<='%s')" % \
                                        (self.field, sub_val[0], self.field, \
                                        sub_val[1])
                else:
                    sub_queries = []
                    wkt_types = geo.Geo().wkt_types
                    for v in sub_val:
                        if any(t in v.lower() for t in wkt_types):
                            sub_queries.append("%s%s%s" % (self.field, op, v))
                        else:
                            sub_queries.append("%s%s'%s'" % \
                                    (self.field, op, v))
                    filter_query = '(%s)' % ' OR '.join(sub_queries)
            else:
                if isinstance(sub_val, list):
                    sub_val = sub_val[0]
                
                # Get the field type from the list of fields
                if common.EODMS_RAPI.get_fieldType(self.query_builder.coll, \
                    self.field) == 'String':
                    sub_val = "'%s'" % sub_val
                
                filter_query = "%s%s%s" % (self.field, op, sub_val)
                        
            return filter_query
            
        def get_fullQuery(self):
            
            self.query_lst = []
            
            if isinstance(self.value, list):
                if isinstance(self.value[0], list):
                    sub_lst = []
                    for v in self.value:
                        sub_query = self.build_query(v)
                        sub_lst.append(sub_query)
                    sub_str = "(%s)" % ' OR '.join(filter(None, sub_lst))
                    
                    self.query_lst.append(sub_str)
                else:
                    self.query_lst.append(self.build_query())
            else:
                self.query_lst.append(self.build_query())
                
            self.full_query = ' AND '.join(filter(None, self.query_lst))
            
            return self.full_query
            
        def print_filter(self, as_string=False):
            
            if as_string:
                output = "Field: %s\n" % self.field
                output += "Operator: %s\n" % self.operator
                output += "Value: %s" % self.value
                
                return output
            else:
                print("Field: %s" % self.field)
                print("Operator: %s" % self.operator)
                print("Value: %s" % self.value)
            
    def __init__(self, coll):
        
        self.coll = coll
        self.aoi = None
        self.dates = None
        self.open_data = None
        self.angle_str = None
        self.filters = []
        self.query_list = []
        
    def add_aoi(self, field, wkt, operator='INTERSECTS'):
        
        self.aoi = self.QueryFilter(self, field, wkt, operator)
        
    def add_dates(self, field, dates):
        
        self.dates = self.QueryFilter(self, field, dates, val_range=True)
                            
    def set_open(self, val):
        
        self.open_data = self.QueryFilter(self, 'CATALOG_IMAGE.OPEN_DATA', \
                        str(val).upper())
        
    def add_filter(self, field, val, operator='=', replace=False):
        
        if replace:
            # Remove existing filter field
            remove_idx = None
            for idx, f in enumerate(self.filters):
                if f.get_field() == field:
                    remove_idx = idx
                    
            if remove_idx is not None:
                self.filters.pop(remove_idx)
        
        filt = self.QueryFilter(self, field, val, operator)
        self.filters.append(filt)
        
    def add_incidenceAngle(self, fields, vals):
        
        low_angle = self.QueryFilter(self, fields[0], vals)
        high_angle = self.QueryFilter(self, fields[1], vals)
        
        angle_queries = []
        for f in fields:
            qf = self.QueryFilter(self, f, vals, val_range=True)
            angle_queries.append(qf.get_fullQuery())
            
        self.angle_str = "(%s)" % " OR ".join(filter(None, angle_queries))
        
    def filter_count(self):
        
        return len(self.filters)
    
    def get_query(self):
        
        self.query_list = []
        
        if self.aoi is not None:
            self.query_list.append(self.aoi.get_fullQuery())
            
        if self.dates is not None:
            self.query_list.append(self.dates.get_fullQuery())
            
        if self.angle_str is not None:
            self.query_list.append(self.angle_str)
            
        self.query_list += [qf.get_fullQuery() for qf in self.filters]
        
        self.query_str = " AND ".join(filter(None, self.query_list))
        
        return self.query_str
        
    def print_params(self):
        
        print("\nList of query parameters:")
        
        if self.aoi is not None: self.aoi.print_filter()
        if self.dates is not None: self.dates.print_filter()
        if self.angle_str is not None: self.angle_str
        
        for f in self.filters:
            f.print_filter()
            
