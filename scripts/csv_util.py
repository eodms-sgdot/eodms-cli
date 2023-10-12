##############################################################################
#
# Copyright (c) His Majesty the King in Right of Canada, as
# represented by the Minister of Natural Resources, 2023
# 
# Licensed under the MIT license
# (see LICENSE or <http://opensource.org/licenses/MIT>) All files in the 
# project carrying such notice may not be copied, modified, or distributed 
# except according to those terms.
# 
##############################################################################

import os
import sys
import csv
import logging

from scripts import image


class EODMS_CSV:

    def __init__(self, eod, csv_fn):
        """
        Initializer for the EODMS_CSV which processes a CSV file exported 
            from the EODMS UI.
        
        :param eod: The parent eod.EodmsOrderDownload object.
        :type  eod: eod.EodmsOrderDownload
        :param csv_fn: The CSV filename.
        :type  csv_fn: str
        """

        self.eod = eod
        self.csv_fn = csv_fn
        self.open_csv = None
        self.header = None
        self.rapi = self.eod.eodms_rapi
        self.coll_id = None
        self.orders = None

        self.logger = logging.getLogger('eodms')

    def add_header(self, header):
        """
        Adds header to a CSV file
        
        :param header: List of header column names.
        :type  header: list
        """
        self.header = header
        header_str = ','.join(header)
        self.open_csv.write(f"{header_str}\n")

    def determine_collection(self, rec):
        """
        Determines the collection of the images in the input CSV file.
        
        :param rec: A record entry from the CSV file.
        :type  rec: dict
        """

        for k in rec.keys():
            if k.lower() == 'collection id':
                self.coll_id = rec[k]

                return self.coll_id

            elif k.lower() == 'collectionid':
                # Get the Collection ID name
                self.coll_id = rec[k]

                return self.coll_id

            elif k.lower() == 'satellite':
                # Get the satellite name
                satellite = rec[k]

                # Set the collection ID name
                self.coll_id = self.eod.get_collid_by_name(satellite)

                if self.coll_id is None:
                    # Check if the collection is supported in this script
                    self.coll_id = self.eod.get_collid_by_name(satellite)
                    msg = f"The satellite/collection '{self.coll_id}'' is " \
                          f"not supported with this script at this time."
                    print(f"\n{msg}")
                    self.logger.warning(msg)
                    return None

                # If the coll_id is a list, return None
                if isinstance(self.coll_id, list):
                    return None

                return self.coll_id

            elif k.lower() == 'title':
                # Get the Collection ID name
                self.coll_id = rec[k]

                return self.coll_id
        else:
            return None

    def export_record(self, img):
        """
        Exports an image to a CSV file.
        
        :param img: An Image object containing image information.
        :type  img: eodms.Image
        """

        out_vals = []
        for h in self.header:
            if h in img.get_fields():
                val = str(img.get_metadata(h))
                if val.find(',') > -1:
                    val_str = val.replace('"', '""')
                    val = f'"{val_str}"'
                out_vals.append(val)
            else:
                out_vals.append('')

        out_str = ','.join([str(i) for i in out_vals])
        self.open_csv.write(f'{out_str}\n')

    def export_results(self, results):
        """
        Exports order results to CSV
        
        :param results: A list of results to export.
        :type  results: ImageList or OrderList
        """

        if not os.path.exists(self.eod.results_path):
            os.mkdir(self.eod.results_path)

        # # Create the query results CSV
        self.open()

        # Add header based on the results
        header = self.eod.sort_fields(results.get_fields())
        self.add_header(header)

        # Export the results to the file
        if isinstance(results, image.ImageList):
            for img in results.get_images():
                self.export_record(img)
        elif isinstance(results, image.OrderList):
            for oi in results.get_order_items():
                self.export_record(oi)

        # Close the CSV
        self.close()

    def get_lines(self, in_f):
        """
        Reads a line from a file and checks for any errors.
        
        :param in_f: The input file to read from.
        :type  in_f: file object
        """

        # Check if the input file is bytes
        try:
            in_lines = in_f.readlines()

            return in_lines
        except Exception:
            err_msg = "The input file cannot be read."
            self.eod.print_support(True, err_msg)
            logger = logging.getLogger('eodms')
            logger.error(err_msg)
            sys.exit(1)

    def import_eodms_csv(self):

        """
        Imports the rows from the EODMS CSV file into a dictionary of records.
        
        :return: A list of records extracted from the CSV file.
        :rtype: list
        """

        # Open the input file
        in_f = open(self.csv_fn, 'r')
        in_lines = self.get_lines(in_f)

        # Get the header from the first row
        in_header = in_lines[0].lower().replace('\n', '').split(',')

        # Check for columns in input file
  #       if 'sequence id' not in in_header and \
  #               'order key' not in in_header and \
  #               'downlink segment id' not in in_header and \
  #               'image id' not in in_header and \
  #               'record id' not in in_header and \
  #               'recordid' not in in_header and \
  #               'image info' not in in_header and \
  #               'photo number' not in in_header and \
  #               'roll number' not in in_header:
  #           err_msg = '''The input file does not contain the proper columns.
  # The input file must contain one of the following columns:
  #   Record ID
  #   recordId
  #   Sequence ID
  #   Image ID
  #   Order Key
  #   Image Info
  #   A combination of Downlink Segment ID and Order Key
  #   A combination of Photo Number and Roll Number'''
  #           self.eod.print_support(True, err_msg)
  #           sys.exit(1)

        # Populate the list of records from the input file
        records = []
        for lne in in_lines[1:]:
            rec = {}
            l_split = lne.replace('\n', '').split(',')

            if len(l_split) < len(in_header):
                continue

            for idx, h in enumerate(in_header):
                prev_val = rec.get(h.lower())
                if prev_val is None or prev_val == '':
                    rec[h.lower()] = l_split[idx]

            # Add the record to the list of records
            records.append(rec)

        # Close the input file
        in_f.close()

        return records

    def import_res_csv(self, in_fn):
        """
        Imports images from a previous results CSV file.
        
        :param in_fn: The results CSV filename.
        :type  in_fn: str
        """

        if in_fn is None:
            return None

        records = self.import_csv()

        self.orders = image.OrderList(self.eod)

        for o_item in records:
            res = self.rapi.get_order(o_item['itemId'])

            # Check for any errors
            if isinstance(res, self.rapi.QueryError):
                err_msg = f"Query to RAPI failed due to '{res.get_msg()}'"
                self.eod.print_support(True, err_msg)
                self.logger.warning(err_msg)
                continue

            res_json = res.json()

            if len(res_json['items']) == 0:
                err_msg = f"No Order exists with Item ID {o_item['itemId']}."
                self.eod.print_support(True, err_msg)
                self.logger.warning(err_msg)
                continue

            order_item = image.OrderItem(self.eod)
            order_item.parse_record(res_json['items'][0])

            order_item.set_metadata('downloaded', o_item['downloaded'])

            self.orders.update_order(order_item.get_order_id(),
                                     order_item)

    def import_csv(self, header_only=False):
        """
        Imports the rows from the CSV file into a dictionary of records.
        
        :return: A list of records extracted from the CSV file.
        :rtype: list
        """

        reader = csv.reader(open(self.csv_fn, 'r', encoding="ISO-8859-1"))
        records = []
        for idx, row in enumerate(reader):
            if idx == 0:
                self.header = row
                if header_only:
                    return self.header
            else:
                rec = {}
                for i, c in enumerate(row):
                    rec[self.header[i]] = c
                records.append(rec)

        return records

    def close(self):
        """
        Closes a CSV file.
        """
        if self.open_csv is not None:
            self.open_csv.close()
            self.open_csv = None

    def open(self, mode='w'):
        """
        Opens a CSV file.
        
        :param mode: The mode of the file object ('r' for read, 'a' to append
                and 'w' to write).
        :type  mode: str
        """

        self.open_csv = open(self.csv_fn, mode)
