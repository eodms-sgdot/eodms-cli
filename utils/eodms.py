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

import json
import os

from . import csv_util
from . import geo
from . import utils
from . import common

class Image:
    """
    The class to store information for an EODMS image.
    """
    
    def __init__(self, record_id=None, coll_id=None):
    
        self.metadata = {}
        self.geometry = {'array': None,  
                        'geom': None, 
                        'wkt': None}
        
    def get_recordId(self):
        return self.metadata['recordId']
        
    def get_collId(self):
        return self.metadata['collectionId']
        
    def get_title(self):
        return self.metadata['title']
        
    def get_collTitle(self):
        return self.metadata['collectionTitle']
        
    def get_date(self):
        if 'Acquisition Start Date' in self.metadata.keys():
            return self.metadata['Acquisition Start Date']
        else:
            return self.metadata['Date']
    
    def get_url(self):
        return self.metadata['thisRecordUrl']
        
    def get_metadata(self, entry=None):
        
        if entry is None:
            return self.metadata
        
        return self.metadata[entry]
        
    def set_metadata(self, val, entry=None):
        if entry is None:
            self.metadata = val
        else:
            self.metadata[entry] = val
            
    def get_fields(self):
        
        return self.metadata.keys()
        
    def get_geometry(self, output='array'):
        
        geo_util = geo.Geo()
        
        if self.geometry[output] is None:
            geometry = self.metadata['geometry']
            coords = geometry['coordinates']
            self.geometry[output] = geo_util.convert_imageGeom(coords, output)
            
        return self.geometry[output]
        
    def parse_record(self, in_rec):
        
        geo_util = geo.Geo()
        
        self.metadata = {}
        for k, v in in_rec.items():
            if k == 'metadata2': continue
            elif k == 'geometry':
                self.metadata['geometry'] = v
                coords = v['coordinates']
                self.metadata['wkt'] = geo_util.convert_imageGeom(\
                                            coords, 'wkt')
            elif k == 'metadata':
                for m in v:
                    self.metadata[m[0]] = m[1]
            else:
                self.metadata[k] = v
        
class ImageList:
    """
    Class used to hold multiple Image objects and contain methods for 
        accessing the list of objects.
    """
    
    def __init__(self):
        self.img_lst = []
        
    def add_image(self, in_image):
        image = in_image
        if not isinstance(image, Image):
            image = Image()
            image.parse_record(in_image)
        self.img_lst.append(image)
        
    def count(self):
        return len(self.img_lst)
        
    def export_csv(self, res_bname):
        """
        Exports query results to CSV
        
        @type  res_bname: str
        @param res_bname: The base filename for the CSV file.
        """
        
        if not os.path.exists(common.RESULTS_PATH):
            os.mkdir(common.RESULTS_PATH)
        
        # Create the query results CSV
        csv_fn = os.path.join(common.RESULTS_PATH, \
                "%s_QueryResults.csv" % res_bname)
        out_csv = csv_util.EODMS_CSV(csv_fn)
        out_csv.open()
        
        # Add header based on the results
        header = self.get_fields()
        out_csv.add_header(header)
        
        # Export the results to the file
        for img in self.img_lst:
            out_csv.export_record(img)
            
        # Close the CSV
        out_csv.close()
        
        return csv_fn
    
    def get_fields(self):
        return self.img_lst[0].get_fields()
        
    def get_image(self, record_id):
        for img in self.img_lst:
            if img.get_recordId() == str(record_id):
                return img
                
    def get_images(self):
        return self.img_lst
                
    def get_subset(self, start=None, end=None):
        if start is None and end is None:
            return self.img_lst
        elif start is None:
            return self.img_lst[:end]
        elif end is None:
            return self.img_lst[start:]
        else:
            return self.img_lst[start:end]
    
    def ingest_results(self, results):
        
        for r in results:
            image = Image()
            image.parse_record(r)
            # print("metadata: %s" % image.metadata)
            # answer = input("Press enter...")
            self.img_lst.append(image)
            
    def trim(self, val):
        if isinstance(val, str):
            val = int(val)
        self.img_lst = self.img_lst[:val]
    
class OrderItem:
    """
    Class used to hold information for an EODMS order item.
    """

    def __init__(self, image=None, item_id=None, order_id=None):
        self.image = image
        self.metadata = {}
        
    def get_fields(self):
        return list(self.metadata.keys())
                         
    def get_image(self):
        return self.image
        
    def set_image(self, image):
        self.image = image
        
    def get_recordId(self):
        return self.metadata['recordId']
        
    def get_itemId(self):
        return self.metadata['itemId']
        
    def get_orderId(self):
        # print("self.metadata: %s" % self.metadata)
        return self.metadata['orderId']
        
    def get_metadata(self, entry=None):
        
        if entry is None:
            return self.metadata
        
        if entry in self.metadata.keys():
            return self.metadata[entry]
            
    def get_downloadPath(self, relpath=False):
        
        if 'download_paths' not in self.metadata.keys(): return None
        
        paths = self.metadata['download_paths']
        path_str = json.dumps(paths)
        path_json = json.loads(path_str)
        
        download_path = path_json[0]['local_destination']
        
        if relpath:
            return os.path.relpath(download_path)
        else:
            return download_path
        
    def add_image(self, in_image):
        image = in_image
        if not isinstance(image, Image):
            image = Image()
            image.parse_record(in_image)
        self.image = image
        
        fields = common.EODMS_RAPI.get_collections()[self.image.get_collId()]\
                ['fields']
        
        self.metadata['imageUrl'] = self.image.get_metadata('thisRecordUrl')
        self.metadata['imageMetadata'] = self.image.get_metadata(\
                                        'metadataUrl')
        self.metadata['imageStartDate'] = self.image.get_date()
        
    def parse_record(self, in_rec):
        self.metadata = {}
        for k, v in in_rec.items():
            if k == 'parameters':
                for m, mv in v.items():
                    self.metadata[m] = mv
            else:
                self.metadata[k] = v
                
        if self.image is not None:
            self.metadata['imageUrl'] = self.image.get_metadata(\
                                        'thisRecordUrl')
            self.metadata['imageMetadata'] = self.image.get_metadata(\
                                        'metadataUrl')
            self.metadata['imageStartDate'] = self.image.get_date()
    
    def print_item(self, tabs=1):
        print("\n\tOrder Item ID: %s" % self.metadata['itemId'])
        print("\tOrder ID: %s" % self.metadata['orderId'])
        print("\tRecord ID: %s" % self.metadata['recordId'])
        for m, v in self.metadata.items():
            if m == 'itemId' or m == 'orderId' or m == 'recordId': continue
            print("%s%s: %s" % (str('\t' * tabs), m, v))
    
    def set_metadata(self, key, val):
        self.metadata[key] = val

class Order:
    """
    Class used to hold information for an EODMS order. The class also 
        contains a list of order items for the order.
    """

    def __init__(self, order_id):
        self.order_items = []
        self.order_id = order_id
        
    def count(self):
        return len(self.order_items)
        
    def get_fields(self):
        fields = []
        for items in self.order_items:
            fields += items.get_fields()
            
        fields = list(set(fields))
        
        return fields
        
    def get_orderId(self):
        return self.order_id
        
    def add_item(self, order_item):
        self.order_items.append(order_item)
        
    def get_items(self):
        return self.order_items
        
    def get_item(self, item_id):
        for item in self.order_items:
            if item.get_itemId() == item_id:
                return item
                
    def get_itemByImageId(self, record_id):
        for item in self.order_items:
            img = item.get_image()
            if img.get_itemId() == record_id:
                return item
                
    def get_image(self, record_id):
        for item in self.order_items:
            img = item.get_image()
            if img is None: return None
            if img.get_recordId() == record_id:
                return img
                
    def get_imageByItemId(self, item_id):
        for item in self.order_items:
            if item.get_itemId() == item_id:
                return item.get_image()
        
    def get_recordIds(self):
        record_ids = []
        for item in self.order_items:
            record_ids.append(item.get_recordId())
            
        return record_ids
        
    def print_items(self, tabs=1):
        for item in self.order_items:
            item.print_item(tabs)
        
    def replace_item(self, in_item):
        lst_idx = -1
        for idx, item in enumerate(self.order_items):
            rec_id = item.get_recordId()
            if int(rec_id) == int(in_item.get_recordId()):
                lst_idx = idx
                break
        
        if lst_idx > -1:
            self.order_items[lst_idx] = in_item
            
    def trim_items(self, val):
        self.order_items = self.order_items[:val]

class OrderList:
    
    """
    Class used to hold a list of Order objects and methods to access the 
        order list.
    """
    
    def __init__(self, img_lst=None):
        self.order_lst = []
        self.img_lst = img_lst
        
    def check_downloaded(self):
        for o in self.order_lst:
            for item in o.get_items():
                mdata = item.get_metadata()
                if 'downloaded' in mdata.keys():
                    if str(mdata['downloaded']) == 'True':
                        return True
                            
        return False
        
    def count(self):
        return len(self.order_lst)
        
    def count_items(self):
        count = 0
        for o in self.order_lst:
            count += o.count()
            
        return count
        
    def export_csv(self, res_bname):
        """
        Exports order results to CSV
        
        @type  res_bname: str
        @param res_bname: The base filename for the CSV file.
        """
        
        if not os.path.exists(common.RESULTS_PATH):
            os.mkdir(common.RESULTS_PATH)
        
        # Create the query results CSV
        csv_fn = os.path.join(common.RESULTS_PATH, \
                "%s_DownloadResults.csv" % res_bname)
        out_csv = csv_util.EODMS_CSV(csv_fn)
        out_csv.open()
        
        # Add header based on the results
        header = self.get_fields()
        out_csv.add_header(header)
        
        # Export the results to the file
        for order in self.order_lst:
            for item in order.get_items():
                out_csv.export_record(item)
            
        # Close the CSV
        out_csv.close()
        
    def get_fields(self):
        
        fields = []
        for order in self.order_lst:
            fields += order.get_fields()
            
        fields = list(set(fields))
        
        field_order = ['recordId', 'orderId', 'itemId', 'collectionId']
        
        out_fields = field_order
        
        for f in fields:
            if f not in field_order:
                out_fields.append(f)
        
        return out_fields
        
    def get_latest(self):
        
        duplicates = {}
        
        for order in self.order_lst:
            order_id = order.get_orderId()
            key = '-'.join(order.get_recordIds())
            
            orders = []
            if key in duplicates.keys():
                orders = duplicates[key]
                
            orders.append(order_id)
            duplicates[key] = orders
        
        if duplicates:
        
            dups_sort = {x:sorted(duplicates[x]) for x in duplicates.keys()}
            
            for k, v in dups_sort.items():
                for d in v[1:]:
                    self.remove_order(d)
        
    def get_order(self, order_id):
        for o in self.order_lst:
            if o.get_orderId() == order_id:
                return o
                
    def get_orders(self):
        return self.order_lst
        
    def get_orderItem(self, itemId):
        for o in self.order_lst:
            return o.get_item(itemId)
    
    def ingest_results(self, results):
        
        for r in results:
            # First get the image from the ImageList
            record_id = r['recordId']
            image = None
            if self.img_lst is not None:
                image = self.img_lst.get_image(record_id)
            
            # Create the OrderItem
            order_item = OrderItem()
            if image is not None:
                order_item.add_image(image)
            order_item.parse_record(r)
            
            # Update or create Order
            order_id = order_item.get_orderId()
            order = self.get_order(order_id)
            if order is None:
                order = Order(order_id)
                order.add_item(order_item)
                self.order_lst.append(order)
            else:
                order.add_item(order_item)
    
    def print_orderItems(self, tabs=1):
        
        print("Number of orders: %s" % len(self.order_lst))
        
        for o in self.order_lst:
            ord_id = o.get_orderId()
            item_count = o.count()
            o.print_items()
    
    def print_orders(self, as_var=False, tabs=1):
        
        out_str = ''
        for o in self.order_lst:
            ord_id = o.get_orderId()
            item_count = o.count()
            out_str += "\n%sOrder ID: %s\n" % (str('\t' * tabs), ord_id)
            
        if as_var: return out_str
        
        print(out_str)
    
    def remove_order(self, order_id):
        for idx, o in enumerate(self.order_lst):
            if o.get_orderId() == order_id:
                rem_idx = idx
                
        self.order_lst.pop(rem_idx)
        
    def replace_item(self, order_id, item_obj):
        
        for order in self.order_lst:
            if int(order.get_orderId()) == int(order_id):
                order.replace_item(item_obj)
                
    def trim_items(self, max_images):
        
        if max_images is not None:
            counter = int(max_images)
            for order in self.order_lst:
                items = order.get_items()
                if len(items) < counter:
                    trim_val = len(items)
                    order.trim_items(trim_val)
                    counter -= trim_val
                else:
                    order.trim_items(counter)
                    counter = 0
                    
    def update_order(self, orderId, order_item):
        
        for order in self.order_lst:
            if int(order.get_orderId()) == int(orderId):
                order.add_item(order_item)
                return None
                
        new_order = Order(orderId)
        new_order.add_item(order_item)
        self.order_lst.append(new_order)
        