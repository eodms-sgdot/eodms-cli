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
import csv
import logging

from . import common
from . import utils
from . import eodms

class EODMS_CSV:
    
    def __init__(self, csv_fn, session=None):
        """
        Initializer for the EODMS_CSV which processes a CSV file exported 
            from the EODMS UI.
            
        @type  session: request.Session
        @param session: A request session with authentication.
        @type  csv_fn:  string
        @param csv_fn:  The CSV filename.
        """
        
        self.csv_fn = csv_fn
        self.session = session
        self.open_csv = None
        self.header = None
        
        self.logger = logging.getLogger('eodms')
        
    def add_header(self, header):
        """
        Adds header to a CSV file
        
        @type  header: list
        @param header: List of header column names.
        """
        
        self.header = header
        self.open_csv.write("%s\n" % ','.join(header))
        
    def determine_collection(self, rec):
        """
        Determines the collection of the images in the input
            CSV file.
            
        @type  rec: dict
        @param rec: A record entry from the CSV file.
        """
        
        if 'Collection ID' in rec.keys():
            # Get the Collection ID name
            self.coll_id = rec['Collection ID']
            
            return self.coll_id
            
        elif 'collectionId' in rec.keys():
            # Get the Collection ID name
            self.coll_id = rec['collectionId']
            
            return self.coll_id
            
        elif 'Satellite' in rec.keys():
            # Get the satellite name
            satellite = rec['Satellite']
            
            # Set the collection ID name
            self.coll_id = common.get_collIdByName(satellite)
            
            if self.coll_id is None:
                # Check if the collection is supported in this script
                self.coll_id = common.get_collIdByName(satellite, True)
                msg = "The satellite/collection '%s' is not supported " \
                        "with this script at this time." % self.coll_id
                print("\n%s" % msg)
                self.logger.warning(msg)
                return None
            
            # If the coll_id is a list, return None
            if isinstance(self.coll_id, list): return None
            
            return self.coll_id
        else:
            return None
            
    def export_record(self, img):
        """
        Exports an image to a CSV file.
        
        @type  img: eodms.Image
        @param img: An Image object containing image information.
        """
        
        out_vals = []
        for h in self.header:
            if h in img.get_fields():
                val = str(img.get_metadata(h))
                if val.find(',') > -1:
                    val = '"%s"' % val.replace('"', '""')
                out_vals.append(val)
            else:
                out_vals.append('')
                
        out_vals = [str(i) for i in out_vals]
        self.open_csv.write('%s\n' % ','.join(out_vals))
        
    def import_eodmsCSV(self):
        
        """
        Imports the rows from the EODMS CSV file into a dictionary of 
            records.
            
        @rtype:  list
        @return: A list of records extracted from the CSV file.
        """
        
        query_obj = utils.Query(self.session)
        
        # Open the input file
        in_f = open(self.csv_fn, 'r')
        in_lines = common.get_lines(in_f)
        
        # Get the header from the first row
        in_header = in_lines[0].replace('\n', '').split(',')
        
        # Check for columns in input file
        if 'Sequence ID' not in in_header and \
            'Order Key' not in in_header and \
            'Downlink Segment ID' not in in_header and \
            'Image Id' not in in_header and \
            'Record ID' not in in_header and \
            'recordId' not in in_header and \
            'Image Info' not in in_header:
            err_msg = '''The input file does not contain the proper columns.
  The input file must contain one of the following columns:
    Record ID
    recordId
    Sequence ID
    Image ID
    Order Key
    Image Info
    A combination of Downlink Segment ID and Order Key'''
            common.print_support(err_msg)
            sys.exit(1)
        
        # Populate the list of records from the input file
        records = []
        for l in in_lines[1:]:
            rec = {}
            l_split = l.replace('\n', '').split(',')
            
            if len(l_split) < len(in_header):
                continue
            
            for idx, h in enumerate(in_header):
                rec[h] = l_split[idx]
                
            coll_id = self.determine_collection(rec)
            
            if coll_id is None: continue
            
            rec['Collection ID'] = coll_id
            
            # Add the record to the list of records
            records.append(rec)
        
        # Close the input file
        in_f.close()
        
        out_recs = query_obj.query_csvRecords(records)
        
        return out_recs
        
    def import_csv(self, required=[]):
        """
        Imports the rows from the CSV file into a dictionary of 
            records.
            
        @rtype:  list
        @return: A list of records extracted from the CSV file.
        """
        
        query_obj = utils.Query(self.session)
        
        reader = csv.reader(open(self.csv_fn, 'r'))
        records = []
        for idx, row in enumerate(reader):
            if idx == 0:
                header = row
            else:
                rec = {}
                for i, c in enumerate(row):
                    rec[header[i]] = c
                records.append(rec)
            
        return records
        
    def close(self):
        """
        Closes a CSV file
        """
        
        if self.open_csv is not None:
            self.open_csv.close()
            self.open_csv = None
        
    def open(self, mode='w'):
        
        self.open_csv = open(self.csv_fn, mode)