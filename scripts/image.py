##############################################################################
# MIT License
# 
# Copyright (c) His Majesty the King in Right of Canada, as
# represented by the Minister of Natural Resources, 2022.
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
# import traceback
import os
# import re

# from . import csv_util
from . import spatial


def to_camel_case(in_str):
    """
    Converts a string to camelCase.
    
    :param in_str: The input string.
    :type  in_str: str
    
    :return: The input string converted to camelCase.
    :rtype: str
    """

    if in_str.find(' ') > -1:
        words = in_str.split(' ')
    elif in_str.find('_') > -1:
        words = in_str.split('_')
    else:
        return in_str.lower()

    first_word = words[0].lower()
    other_words = ''.join(w.title() for w in words[1:])

    return f'{first_word}{other_words}'


class Image:
    """
    The class to store information for an EODMS image.
    """

    def __init__(self):
        """
        Initializer of the Image class.
        """
        self.metadata = {}
        self.geometry = {'array': None,
                         'geom': None,
                         'wkt': None}

    def get_record_id(self):
        """
        Gets the Record Id of the image.
        
        Returns:
            str or int: The Record Id of the image.
        """
        return self.metadata['recordId']

    def get_coll_id(self):
        """
        Gets the Collection Id of the image.
        
        :return: The Collection Id of the image.
        :rtype: str
        """
        # print("self.metadata: %s" % self.metadata)
        return self.metadata['collectionId']

    def get_title(self):
        """
        Gets the Title of the image.
        
        :return: The Title of the image.
        :rtype: str
        """
        return self.metadata['title']

    def get_coll_title(self):
        """
        Gets the Collection Title of the image.
        
        :return: The Collection Title of the image.
        :rtype: str
        """
        return self.metadata['collectionTitle']

    def get_date(self):
        """
        Gets the Date of the image.
        
        :return: The Date of the image.
        :rtype: str
        """

        date_fields = ['Acquisition Start Date', 'acquisition_start_date',
                       'acquisitionStartDate', 'Date', 'date']

        for f in date_fields:
            found = self.metadata.get(f)
            if found is not None:
                return found

    def get_url(self):
        """
        Gets the URL of the image.
        
        :return: The URL of the image.
        :rtype: str
        """
        return self.metadata['thisRecordUrl']

    def get_metadata(self, entry=None):
        """
        Gets either the metadata or an entry of the metadata.
        
        :param entry: The field (key) of the metadata entry to return.
        :type  entry: str
        
        :return: If an entry is specified, the entry value will be returned.
            Otherwise all entries in the metadata will be returned.
        :rtype: str
        """
        if entry is None:
            return self.metadata

        if entry not in self.metadata.keys():
            return None

        return self.metadata[entry]

    def set_metadata(self, val, entry=None):
        """
        Sets either a value for a specific metadata entry or replaces the 
            entire metadata with the val.
            
        :param val: A value for a specific metadata entry or a dictionary
                containing a set of metadata entries.
        :type  val: str or dict
        :param entry: The field (key) of a specific metadata entry.
        :type  entry: str
        """

        if entry is None:
            self.metadata = val
        else:
            self.metadata[entry] = val

    def get_fields(self):
        """
        Gets a list of all metadata keys.
        
        :return: A list of the metadata keys.
        :rtype: list
        """

        return self.metadata.keys()

    def get_geometry(self, output='array'):
        """
        Gets (and sets) the geometry of the image.
        
        :param output: Specifies the type of geometry to return, can be
                    'array', 'wkt' or 'geom'.
        :type  output: str
        
        :return: The geometry of the image in the specified format.
        :rtype: str or ogr.Geometry
        """

        geo_util = spatial.Geo()

        if self.geometry[output] is None:
            geometry = self.metadata['geometry']

            if isinstance(geometry, str):
                geometry = json.loads(geometry.replace("'", '"'))

            coords = geometry['coordinates']
            self.geometry[output] = geo_util.convert_image_geom(coords, output)

        return self.geometry[output]

    def parse_record(self, in_rec):
        """
        Parses a JSON image record from the RAPI and sets the image.
        
        :param in_rec: A dictionary from a JSON record from the RAPI.
        :type  in_rec: dict
        """

        geo_util = spatial.Geo()

        # print("in_rec: %s" % in_rec)

        self.metadata = {}
        for k, v in in_rec.items():
            if k == 'metadata2':
                continue
            elif k == 'geometry':
                self.metadata['geometry'] = v
                coords = v['coordinates']
                self.metadata['wkt'] = geo_util.convert_image_geom(
                    coords, 'wkt')
            elif k == 'metadata':
                if isinstance(v, list):
                    for m in v:
                        key = to_camel_case(m[0])
                        self.metadata[key] = m[1]
            else:
                self.metadata[k] = v

    def parse_row(self, row):
        """
        Parses a row entry from a CSV file.
        
        :param row: A dictionary from an entry in a CSV file.
        :type  row: dict
        """

        self.metadata = row


class ImageList:
    """
    Class used to hold multiple Image objects and contain methods for
        accessing the list of objects.
    """

    def __init__(self, eod):
        """
        The initializer of the ImageList class.
        
        :param eod: The parent Eodms_OrderDownload object.
        :type  eod: Eodms_OrderDownload
        """
        self.eod = eod
        self.img_lst = []

    def add_image(self, in_image):
        """
        Adds an Image object to the ImageList.
        
        :param in_image: The image to add to the ImageList. If the image is 
            a JSON dictionary from the RAPI, it'll be converted to an Image
            object.
        :type  in_image: dict or Image
        """
        image = in_image
        if not isinstance(image, Image):
            image = Image()
            image.parse_record(in_image)
        self.img_lst.append(image)

    def add_images(self, in_imgs):
        """
        Adds a set of Image objects to the ImageList.
        
        :param in_imgs: A list of Image objects to add.
        :type  in_imgs: list
        """

        self.img_lst += in_imgs

    def combine(self, img_list):
        """
        Combines the Images of an ImageList object to the list of Images.
        
        :param img_list: The ImageList object.
        :type  img_list: image.ImageList
        """

        imgs = img_list.get_images()
        self.add_images(imgs)

    def count(self):
        """
        Returns the number of images in the ImageList.
        
        :return: The number of images in the ImageList (img_lst).
        :rtype: int
        """

        return len(self.img_lst)

    def filter_overlap(self, overlap, aoi):

        geo_util = spatial.Geo(self.eod, aoi)

        filter_lst = []
        for img in self.img_lst:
            overlap_aoi, overlap_img = geo_util.get_overlap(img, aoi)
            if overlap_aoi >= float(overlap) or overlap_img >= float(overlap):
                # print("overlap_aoi: %s" % overlap_aoi)
                # print("overlap_img: %s" % overlap_img)
                filter_lst.append(img)

        # print("img_lst: %s" % len(self.img_lst))
        # print("filter_lst: %s" % len(filter_lst))

        self.eod.print_msg(f'Number of images found after filtering for '
                           f'overlap: {len(filter_lst)}')

        self.img_lst = filter_lst

        # answer = input("Press enter...")

    def get_fields(self):
        """
        Gets the list of metadata fields from the first Image.
        
        :return: A list of metadata fields of the first Image.
        :rtype: list
        """

        fields = []
        for img in self.img_lst:
            fields += img.get_fields()

        fields = list(set(fields))

        return fields

    def get_ids(self):
        """
        Gets a list of all the Record IDs from the image list.

        :return: List of Record IDs.
        :rtype: list
        """

        rec_ids = [i.get_record_id() for i in self.img_lst]

        return rec_ids

    def get_image(self, record_id):
        """
        Gets a specific Image based on the Record Id.
        
        :param record_id: The Record Id of the image.
        :type  record_id: str or int
        
        :return: The Image corresponding with the given Record Id.
        :rtype: Image
        """

        for img in self.img_lst:
            if img.get_record_id() == str(record_id):
                return img

    def get_images(self):
        """
        Gets all Images in the ImageList.
        
        :return: Returns the list of Images.
        :rtype: list
        """

        return self.img_lst

    def get_raw(self):
        """
        Gets the raw metadata of all the Images.
        
        :return: A list of dictionaries of each Image's metadata.
        :rtype: list
        """

        return [i.get_metadata() for i in self.img_lst]

    def get_subset(self, start=None, end=None):
        """
        Gets a subset of Images from the ImageList.
        
        :param start: The starting position of the subset of the img_lst.
        :type  start: int
        :param end: The ending position of the subset of the img_lst.
        :type  end: int
        
        :return: Returns a subset of the img_lst based on the start and end
                values.
        :rtype: list
        """

        if start is None and end is None:
            return self.img_lst
        elif start is None:
            return self.img_lst[:end]
        elif end is None:
            return self.img_lst[start:]
        else:
            return self.img_lst[start:end]

    def ingest_results(self, results, is_csv=False):
        """
        Ingests a list of results from the RAPI, converts them to Images and
            adds them to the img_lst.
            
        :param results: A list of image records from the RAPI.
        :type  results: list
        :param is_csv: Determines if the input results are from a CSV file.
        :type  is_csv: list
        """

        img_ids = []
        for r in results:
            if 'errors' in r.keys():
                continue
            rec_id = r.get('recordId')
            if rec_id in img_ids:
                continue

            image = Image()
            if is_csv:
                image.parse_row(r)
            else:
                image.parse_record(r)
            self.img_lst.append(image)
            img_ids.append(rec_id)

    def remove_image(self, rec_id):
        """
        Removes an image from the image list with a given Record ID.

        :param rec_id: The Record ID of the image to remove.
        :type  rec_id: int
        """

        found_idx = None
        for idx, img in enumerate(self.img_lst):
            if img.get_record_id() == rec_id:
                found_idx = idx

        if found_idx is not None:
            del self.img_lst[found_idx]

    def trim(self, val, collections=None):
        """
        Permanently trims the list of Images in the img_lst.
        
        :param val: The upper limit of the trim.
        :type  val: str or int
        :param collections: A list Collection IDs.
        :type  collections: list
        """

        if isinstance(val, str):
            val = int(val)

        if collections is None:
            self.img_lst = self.img_lst[:val]
        else:
            new_imgs = []
            for c in collections:
                imgs = [img for img in self.img_lst
                        if img.get_metadata()['collectionId'] == c]
                if len(imgs) < val:
                    new_imgs += imgs
                else:
                    new_imgs += imgs[:val]

            self.img_lst = new_imgs

    def update_downloads(self, download_items):
        """
        Updates the download information of a list of specific Images.
        
        :param download_items: A list of images after the download from the
            RAPI (each image must contain a recordId).
        :type  download_items: list
        """

        if download_items is None:
            return None

        for item in download_items:
            rec_id = item.get('recordId')
            img = self.get_image(rec_id)

            if img is None:
                img = Image()

            order_id = item.get('orderId')
            item_id = item.get('itemId')
            if item_id is None:
                item_id = item.get('ParentItemId')
            img.set_metadata(item_id, 'itemId')
            img.set_metadata(order_id, 'orderId')
            img.set_metadata(item.get('dateSubmitted'), 'dateSubmitted')
            img.set_metadata(item.get('userDisplayName'), 'userDisplayName')
            img.set_metadata(item.get('status'), 'status')
            img.set_metadata(item.get('orderStatus'), 'orderStatus')
            img.set_metadata(item.get('orderMessage'), 'orderMessage')
            img.set_metadata(item.get('downloaded'), 'downloaded')
            img.set_metadata(item.get('downloadPaths'), 'downloadPaths')
            img.set_metadata(item.get('priority'), 'priority')
            params = item.get('parameters')
            if params is not None:
                for k, v in params.items():
                    img.set_metadata(v, k)


class OrderItem:
    """
    Class used to hold information for an EODMS order item.
    """

    def __init__(self, eod, image=None):
        """
        Initializer for the OrderItem class.
        
        :param eod: The parent Eodms_OrderDownload object.
        :type  eod: Eodms_OrderDownload
        :param image: The Image item related to the Order Item.
        :type  image: Image
        """
        self.eod = eod
        self.image = image
        self.metadata = {}

    def get_fields(self):
        """
        Gets the metadata fields of the OrderItem.
        
        :return: A list of metadata fields.
        :rtype: list
        """
        return list(self.metadata.keys())

    def get_image(self):
        """
        Gets the Image related to the Order Item.
        
        :return: The Image item related to the Order Item.
        :rtype: Image
        """
        return self.image

    def set_image(self, image):
        """
        Sets the Image object for the Order Item.
        
        :param image: The Image object to add to the OrderItem.
        :type  image: Image
        """
        self.image = image

    def get_record_id(self):
        """
        Gets the Record Id of the Image contained in the OrderItem.
        
        :return: The Record Id of the Image.
        :rtyp: int
        """
        return self.metadata['recordId']

    def get_item_id(self):
        """
        Gets the Order Item Id of the OrderItem.
        
        :return: The Order Item Id.
        :rtype: int
        """
        return self.metadata['itemId']

    def get_order_id(self):
        """
        Gets the Order Id of the OrderItem.
        
        :return: The Order Id.
        :rtype: int
        """
        return self.metadata['orderId']

    def get_metadata(self, entry=None):
        """
        Gets either the metadata or an entry of the metadata of the Order Item.
        
        :param entry: The field (key) of the metadata entry to return.
        :type  entry: str
        
        :return: If an entry is specified, the entry value will be returned.
                Otherwise all entries in the metadata will be returned.
        :rtype: str
        """
        if entry is None:
            return self.metadata

        if entry in self.metadata.keys():
            return self.metadata[entry]

    def get_download_path(self, relpath=False):
        """
        Gets the download paths of the Order Item.
        
        :param relpath: Determines whether to return the relative path of the
                download path.
        :type  relpath: boolean
        
        :return: Either the absolute path or the relative path of the
                download location.
        :rtype: str
        """

        if 'downloadPaths' not in self.metadata.keys():
            return None

        paths = self.metadata['downloadPaths']
        path_str = json.dumps(paths)
        path_json = json.loads(path_str)

        download_path = path_json[0]['local_destination']

        if relpath:
            return os.path.relpath(download_path)
        else:
            return download_path

    def add_image(self, in_image):
        """
        Adds an image to the OrderItem.
         
        :param in_image: The image to add to the OrderItem. It can either be
                an Image object or a JSON dictionary from the RAPI.
        :type  in_image: dict or Image
        """
        image = in_image
        if not isinstance(image, Image):
            image = Image()
            image.parse_record(in_image)
        self.image = image

        # fields = self.eod.eodms_rapi.get_collections()[
        #     self.image.get_coll_id()]['fields']

        self.metadata['imageUrl'] = self.image.get_metadata('thisRecordUrl')
        self.metadata['imageMetadata'] = self.image.get_metadata(
            'metadataUrl')
        self.metadata['imageStartDate'] = self.image.get_date()

    def parse_record(self, in_rec):
        """
        Parses the metadata of a specific image.
        
        :param in_rec: The image record dictionary from the RAPI.
        :type  in_rec: dict
        """

        self.metadata = {}
        for k, v in in_rec.items():
            if k == 'parameters':
                for m, mv in v.items():
                    self.metadata[m] = mv
            else:
                self.metadata[k] = v

        if self.image is not None:
            self.metadata['imageUrl'] = self.image.get_metadata(
                'thisRecordUrl')
            self.metadata['imageMetadata'] = self.image.get_metadata(
                'metadataUrl')
            self.metadata['imageStartDate'] = self.image.get_date()

            if 'dateRapiOrdered' not in self.metadata.keys():
                self.metadata['dateRapiOrdered'] = self.image.get_metadata(
                    'dateRapiOrdered')
            self.metadata['orderSubmitted'] = self.image.get_metadata(
                'orderSubmitted')

    def print_item(self, tabs=1):
        """
        Prints the metadata information of the OrderItem.
        
        :param tabs: The amount of tabs used in the print.
        :type  tabs: int
        """

        print(f"\n\tOrder Item Id: {self.metadata['itemId']}")
        print(f"\tOrder Id: {self.metadata['orderId']}")
        print(f"\tRecord Id: {self.metadata['recordId']}")
        for m, v in self.metadata.items():
            if m == 'itemId' or m == 'orderId' or m == 'recordId':
                continue
            print("%s%s: %s" % (str('\t' * tabs), m, v))

    def set_metadata(self, key, val):
        """
        Sets a specific metadata item.
        
        :param key: The field (key) of the metadata entry.
        :type  key: str
        :param val: The value of the metadata entry.
        :type  val: str
        """

        self.metadata[key] = val


class Order:
    """
    Class used to hold information for an EODMS order. The class also
        contains a list of order items for the order.
    """

    def __init__(self, order_id):
        """
        Initializer of the Order object.
        
        :param order_id: The Order Id of the order.
        :type  order_id: int
        """
        self.order_items = []
        self.order_id = order_id

    def count(self):
        """
        Gets the number of Order Items for the order.
        
        :return: The number of OrderItems in the order_items list.
        :rtyp: int
        """
        return len(self.order_items)

    def get_fields(self):
        """
        Gets the unique list of OrderItem metadata fields.
        
        :return: A list of all unique OrderItem metadata fields.
        :rtype: list
        """
        fields = []
        for items in self.order_items:
            fields += items.get_fields()

        fields = list(set(fields))

        field_order = ['recordId', 'orderId', 'itemId', 'collectionId']

        out_fields = field_order

        for f in fields:
            if f not in field_order:
                out_fields.append(f)

        return out_fields

    def get_order_id(self):
        """
        Gets the Order Id of the order.
        
        :return: The Order Id of the order.
        :rtype: str
        """
        return self.order_id

    def add_item(self, order_item):
        """
        Adds an OrderItem to the order_item list.
        
        :param order_item: The OrderItem object to add.
        :type  order_item: OrderItem
        """
        self.order_items.append(order_item)

    def get_items(self):
        """
        Gets the list of OrderItems.
        
        :return: A list of the the OrderItems.
        :rtype: list
        """
        return self.order_items

    def get_item(self, item_id):
        """
        Gets a specific OrderItem object from the list of order items.
        
        :param item_id: The Order Item Id of the specific order item.
        :type  item_id: str or int
        
        :return: The specific OrderItem based on the Order Item Id.
        :rtype: OrderItem
        """
        for item in self.order_items:
            if item.get_item_id() == item_id:
                return item

    def get_item_by_image_id(self, record_id):
        """
        Gets the Order Item based on the Order Item's Record Id.
        
        :param record_id: The Record Id of the Order Item.
        :type  record_id: str or int
        
        :return: The Order Item containing the Record Id.
        :rtype: OrderItem
        """
        for item in self.order_items:
            img = item.get_image()
            if img.get_item_id() == record_id:
                return item

    def get_image(self, record_id):
        """
        Gets the Image based from the Order Item based on the Record Id.
        
        :param record_id: The Record Id of the Image.
        :type  record_id: str or int
        
        :return: The Image containing the Record Id.
        :rtype: Image
        """
        for item in self.order_items:
            img = item.get_image()
            if img is None:
                return None
            if img.get_record_id() == record_id:
                return img

    def get_image_by_item_id(self, item_id):
        """
        Gets an Image from an OrderItem based on the Order Item Id.
        
        :param item_id: The Order Item Id.
        :type  item_id: int
        
        :return: The Image from the OrderItem with the given Id.
        :rtype: Image
        """
        for item in self.order_items:
            if item.get_item_id() == item_id:
                return item.get_image()

    def get_record_ids(self):
        """
        Gets a list of all Record Ids for the Order.
        
        :return: A list of all the Record Ids of the Order.
        :rtype: list
        """
        record_ids = []
        for item in self.order_items:
            record_ids.append(item.get_record_id())

        return record_ids

    def print_items(self, tabs=1):
        """
        Prints the metadata information of all the OrderItems.
        
        :param tabs: The amount of tabs used in the print.
        :type  tabs: int
        """
        for item in self.order_items:
            item.print_item(tabs)

    def replace_item(self, in_item):
        """
        Replaces an existing Order Item with a given Order Item.
        
        :param in_item: The Order Item with which to replace.
        :type  in_item: OrderItem
        """
        lst_idx = -1
        for idx, item in enumerate(self.order_items):
            rec_id = item.get_record_id()
            if int(rec_id) == int(in_item.get_record_id()):
                lst_idx = idx
                break

        if lst_idx > -1:
            self.order_items[lst_idx] = in_item

    def trim_items(self, val):
        """
        Permanently trims the list of Order Items in the order_items.
        
        :param val: The upper limit of the trim.
        :type  val: str or int
        """
        self.order_items = self.order_items[:val]


class OrderList:
    """
    Class used to hold a list of Order objects and methods to access the
        order list.
    """

    def __init__(self, eod, img_lst=None):
        """
        Initializer for the OrderList object.
        """
        self.eod = eod
        self.order_lst = []
        self.img_lst = img_lst

    def add_order(self, json_res):

        # print(json.dumps(json_res, indent=4, sort_keys=True))
        # answer = input("Press enter...")

        self.parse_order_item(json_res)

    def check_downloaded(self):
        """
        Checks if one of the Order Items has been downloaded.
        
        :return: True if one Order Item has been downloaded, otherwise False.
        :rtype: boolean
        """
        for o in self.order_lst:
            for item in o.get_items():
                mdata = item.get_metadata()
                if 'downloaded' in mdata.keys():
                    if str(mdata['downloaded']) == 'True':
                        return True

        return False

    def count(self):
        """
        Gets the number of Orders in the order_lst.
        
        :return: The number of Orders in the order_lst.
        :rtype: int
        """
        return len(self.order_lst)

    def count_items(self):
        """
        Gets the number of Order Items in the order_lst.
        
        :return: The number of Order Items in the order_lst.
        :rtype: int
        """
        count = 0
        for o in self.order_lst:
            count += o.count()

        return count

    def get_fields(self):
        """
        Gets the fields of the Orders.
        
        :return: A list of fields.
        :rtype: list
        """

        fields = []
        for order in self.order_lst:
            fields += order.get_fields()

        fields = list(set(fields))

        out_fields = self.eod.sort_fields(fields)

        return out_fields

    def get_images(self):
        """
        Gets a list of images from the Order Items in self.order_lst
        
        :return: A list of images.
        :rtype: list
        """

        images = []
        for order in self.order_lst:
            o_items = order.get_items()
            images.append(o_items.get_image())

        return images

    def get_latest(self):
        """
        Returns the orders sorted by date.
        """

        duplicates = {}

        for order in self.order_lst:
            order_id = order.get_order_id()
            key = '-'.join(order.get_record_ids())

            orders = []
            if key in duplicates.keys():
                orders = duplicates[key]

            orders.append(order_id)
            duplicates[key] = orders

        if duplicates:

            dups_sort = {x: sorted(duplicates[x]) for x in duplicates.keys()}

            for k, v in dups_sort.items():
                for d in v[1:]:
                    self.remove_order(d)

    def get_order(self, order_id):
        """
        Gets a particular Order with a given Order Id.
        
        :param order_id: The Order Id.
        :type  order_id: int
        
        :return: The Order object with the given Order Id.
        :rtype: Order
        """
        for o in self.order_lst:
            if o.get_order_id() == order_id:
                return o

    def get_orders(self):
        """
        Gets all the Orders in the order_lst.
        
        :return: A list of Order objects.
        :rtype: list
        """

        return self.order_lst

    def get_order_item(self, item_id):
        """
        Gets a particular Order Item with a given Order Item Id.
        
        :param item_id: The Order Item Id.
        :type  item_id: int
        
        :return: The OrderItem object with the given Order Item Id.
        :rtype: Order
        """

        for o in self.order_lst:
            return o.get_item(item_id)

    def get_order_items(self):
        """
        Gets a list of Order Items in the OrderList.
        
        :return: A list of OrderItem objects.
        :rtype: list
        """

        out_list = []
        for o in self.order_lst:
            out_list += o.get_items()

        return out_list

    def get_raw(self):
        """
        Gets the raw metadata of all Order Items.
        
        :return: A list of the raw metadata for each Order Items.
        :rtype: list
        """

        out_items = []
        for order in self.order_lst:
            out_items += [i.get_metadata() for i in order.get_items()]

        return out_items

    def ingest_results(self, results):
        """
        Ingests the order results from the RAPI.
        
        :param results: A list of order results from the RAPI.
        :type  results: list
        """

        if isinstance(results, dict):
            if 'items' in results.keys():
                results = results['items']

        if results is None:
            return None

        for idx, r in enumerate(results):
            self.parse_order_item(r)

    def merge_ordlist(self, ord_list):
        orders = ord_list.get_orders()

        for order in orders:
            self.order_lst.append(order)

    def parse_order_item(self, rec):
        """
        Parses a single order item into the order list.

        :param rec: The order item record in JSON.
        :type  rec: JSON
        """

        # First get the image from the ImageList
        record_id = rec['recordId']
        image = None
        if self.img_lst is not None:
            image = self.img_lst.get_image(record_id)
            image.set_metadata('Yes', 'orderSubmitted')

        # Create the OrderItem
        order_item = OrderItem(self.eod)
        if image is not None:
            order_item.add_image(image)
        order_item.parse_record(rec)

        # Update or create Order
        order_id = order_item.get_order_id()
        order = self.get_order(order_id)
        if order is None:
            order = Order(order_id)
            order.add_item(order_item)
            self.order_lst.append(order)
        else:
            order.add_item(order_item)

        if image is not None:
            image.set_metadata(order_id, 'orderId')
            image.set_metadata(rec.get('status'), 'orderStatus')
            image.set_metadata(rec.get('statusMessage'), 'statusMessage')
            image.set_metadata(rec.get('dateRapiOrdered'),
                               'dateRapiOrdered')

    def print_order_items(self):
        """
        Prints all the Order Items to the terminal.
        """

        print(f"Number of orders: {len(self.order_lst)}")

        for o in self.order_lst:
            # ord_id = o.get_order_id()
            # item_count = o.count()
            o.print_items()

    def print_orders(self, as_var=False, tabs=1):
        """
        Gets or prints all the Order Ids to the terminal.
        
        :param as_var: If True, return the message as a variable, False to
                print to screen.
        :type  as_var: boolean
        :param tabs: The number of tabs to include in the printed statement.
        :type  tabs: int
        
        :return: If as_var is True, returns the printed statement as a variable.
        :rtype: str
        """

        out_str = ''
        for o in self.order_lst:
            ord_id = o.get_order_id()
            # item_count = o.count()
            tab_str = str('\t' * tabs)
            out_str += f"\n{tab_str}Order Id: {ord_id}\n"

        if as_var:
            return out_str

        print(out_str)

    def remove_order(self, order_id):
        """
        Removes a specific order from the order_lst.
        
        :param order_id: The Order Id of the order to remove.
        :type  order_id: str or int
        """

        rem_idx = None
        for idx, o in enumerate(self.order_lst):
            if o.get_order_id() == order_id:
                rem_idx = idx

        if rem_idx is not None:
            self.order_lst.pop(rem_idx)

    def replace_item(self, order_id, item_obj):
        """
        Replaces a specific order from the order_lst.
        
        :param order_id: The Order Id of the order to replace.
        :type  order_id: str or int
        :param item_obj: The Order with which to replace.
        :type  item_obj: Order
        """
        for order in self.order_lst:
            if int(order.get_order_id()) == int(order_id):
                order.replace_item(item_obj)

    def trim_items(self, max_images):
        """
        Trims the number of images in each order.
        
        :param max_images: The image limit.
        :type  max_images: int
        """

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

    def update_order(self, order_id, order_item):
        """
        Updates a specific Order Item.
        
        :param order_id: The Order Id for which the item will be added.
        :type  order_id: int
        :param order_item: The Order Item to add.
        :type  order_item: OrderItem
        """

        for order in self.order_lst:
            if int(order.get_order_id()) == int(order_id):
                order.add_item(order_item)
                return None

        new_order = Order(order_id)
        new_order.add_item(order_item)
        self.order_lst.append(new_order)
