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
import json
import requests
import logging
from xml.etree import ElementTree
import re

from . import utils

RAPI_DOMAIN = 'https://www.eodms-sgdot.nrcan-rncan.gc.ca'

# For DEBUG:
# RAPI_DOMAIN = 'http://www-pre-prod.eodms.services.global.gc.ca'

INDENT = 3
SILENT = False
DOWNLOAD_PATH = "downloads"
RESULTS_PATH = "results"
TIMEOUT_QUERY = 60.0
TIMEOUT_ORDER = 180.0
ATTEMPTS = 4
MAX_RESULTS = 1000

OPERATORS = ['=', '<', '>', '<>', '<=', '>=', ' LIKE ', ' STARTS WITH ', \
            ' ENDS WITH ', ' CONTAINS ', ' CONTAINED BY ', ' CROSSES ', \
            ' DISJOINT WITH ', ' INTERSECTS ', ' OVERLAPS ', ' TOUCHES ', \
            ' WITHIN ']

FILT_MAP = {'RCMImageProducts': 
                {
                    'ORBIT_DIRECTION': 'RCM.ORBIT_DIRECTION', 
                    # 'INCIDENCE_ANGLE': 'SENSOR_BEAM_CONFIG.INCIDENCE_LOW,SENSOR_BEAM_CONFIG.INCIDENCE_HIGH', 
                    'INCIDENCE_ANGLE': 'RCM.INCIDENCE_ANGLE', 
                    'BEAM_MNEMONIC': 'RCM.BEAM_MNEMONIC', 
                    'BEAM_MODE_QUALIFIER': 'SENSOR_BEAM_CONFIG.BEAM_MODE_QUALIFIER', 
                    # 'BEAM_MODE_TYPE': 'RCM.SBEAM',
                    'DOWNLINK_SEGMENT_ID': 'RCM.DOWNLINK_SEGMENT_ID', 
                    'LUT_Applied': 'LUTApplied', 
                    'OPEN_DATA': 'CATALOG_IMAGE.OPEN_DATA', 
                    'POLARIZATION': 'RCM.POLARIZATION', 
                    'PRODUCT_FORMAT': 'PRODUCT_FORMAT.FORMAT_NAME_E', 
                    'PRODUCT_TYPE': 'ARCHIVE_IMAGE.PRODUCT_TYPE', 
                    'RELATIVE_ORBIT': 'RCM.ORBIT_REL', 
                    'WITHIN_ORBIT_TUBE': 'RCM.WITHIN_ORBIT_TUBE', 
                    'ORDER_KEY': 'ARCHIVE_IMAGE.ORDER_KEY', 
                    'SEQUENCE_ID': 'CATALOG_IMAGE.SEQUENCE_ID', 
                    'SPECIAL_HANDLING_REQUIRED': 'RCM.SPECIAL_HANDLING_REQUIRED'
                }, 
            'Radarsat1': 
                {
                    'ORBIT_DIRECTION': 'RSAT1.ORBIT_DIRECTION',
                    'PIXEL_SPACING': 'ARCHIVE_RSAT1.SAMPLED_PIXEL_SPACING_PAN', 
                    # 'INCIDENCE_ANGLE': 'SENSOR_BEAM_CONFIG.INCIDENCE_LOW,SENSOR_BEAM_CONFIG.INCIDENCE_HIGH', 
                    'INCIDENCE_ANGLE': 'RSAT1.INCIDENCE_ANGLE', 
                    # 'BEAM_MODE': 'RSAT1.SBEAM', 
                    'BEAM_MNEMONIC': 'RSAT1.BEAM_MNEMONIC', 
                    'ORBIT': 'RSAT1.ORBIT_ABS'
                }, 
            'Radarsat2':
                {
                    'ORBIT_DIRECTION': 'RSAT2.ORBIT_DIRECTION', 
                    'PIXEL_SPACING': 'ARCHIVE_RSAT2.SAMPLED_PIXEL_SPACING_PAN', 
                    # 'INCIDENCE_ANGLE': 'SENSOR_BEAM_CONFIG.INCIDENCE_LOW,SENSOR_BEAM_CONFIG.INCIDENCE_HIGH', 
                    'INCIDENCE_ANGLE': 'RSAT2.INCIDENCE_ANGLE', 
                    'SEQUENCE_ID': 'CATALOG_IMAGE.SEQUENCE_ID', 
                    # 'BEAM_MODE': 'RSAT2.SBEAM', 
                    'BEAM_MNEMONIC': 'RSAT2.BEAM_MNEMONIC', 
                    'LOOK_DIRECTION': 'RSAT2.ANTENNA_ORIENTATION', 
                    'TRANSMIT_POLARIZATION': 'RSAT2.TR_POL', 
                    'RECEIVE_POLARIZATION': 'RSAT2.REC_POL', 
                    'IMAGE_ID': 'RSAT2.IMAGE_ID', 
                    'RELATIVE_ORBIT': 'RSAT2.ORBIT_REL', 
                    'ORDER_KEY': 'ARCHIVE_IMAGE.ORDER_KEY'
                }, 
            'NAPL':
                {
                    'COLOUR': 'PHOTO.SBEAM', 
                    'SCALE': 'FLIGHT_SEGMENT.SCALE', 
                    'ROLL': 'ROLL.ROLL_NUMBER', 
                    'PHOTO_NUMBER': 'PHOTO.PHOTO_NUMBER' 
                    # 'PREVIEW_AVAILABLE': 'PREVIEW_AVAILABLE'
                }
            }
            
EODMS_RAPI = None

def convert_date(in_date):
    """
    Converts a date to ISO standard format.
    
    @type  in_date: str
    @param in_date: A string containing a date in format YYYYMMDD.
    
    @rtype:  str
    @return: The date converted to ISO format.
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
    
def export_records(csv_f, header, records):
    """
    Exports a set of records to a CSV.
    
    @type  csv_f:   file object
    @param csv_f:   The CSV file to write to.
    @type  header:  list
    @param header:  A list containing the header for the file.
    @type  records: list
    @param records: A list of images.
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

def get_lines(in_f):
    """
    Reads a line from a file and checks for any errors.
    
    @type  in_f: file object
    @param in_f: The input file to read from.
    """
    
    # Check if the input file is bytes
    try:
        in_lines = in_f.readlines()
        
        return in_lines
    except Exception:
        err_msg = "The input file cannot be read."
        print_support(err_msg)
        logger = logging.getLogger('eodms')
        logger.error(err_msg)
        sys.exit(1)

def get_exception(res, output='str'):
    """
    Gets the Exception text (or XML) from an request result.
    
    @type  in_xml: xml.etree.ElementTree.Element
    @param in_xml: The XML which will be checked for an exception.
    @type  output: str
    @param output: Determines what type of output should be returned 
                    (default='str').
                   Options:
                   - 'str': returns the XML Exception as a string
                   - 'tree': returns the XML Exception as a 
                                xml.etree.ElementTree.Element
                                
    @rtype:        str or xml.etree.ElementTree.Element
    @return:       The Exception XML text or element depending on 
                    the output variable.
    """
    
    in_str = res.text

    # If the input XML is None, return None
    if in_str is None: return None
    
    if is_json(in_str): return None
    
    # If the input is a string, convert it to a xml.etree.ElementTree.Element
    if isinstance(in_str, str):
        root = ElementTree.fromstring(in_str)
    else:
        root = in_str
    
    # Cycle through the input XML and location the ExceptionText element
    out_except = []
    for child in root.iter('*'):
        if child.tag.find('ExceptionText') > -1:
            if output == 'tree':
                return child
            else:
                return child.text
        elif child.tag.find('p') > -1:
            out_except.append(err)
            
    except_txt = ' '.join(out_except)
    
    query_err = utils.QueryError(except_txt)
            
    return query_err

def is_json(my_json):
    """
    Checks to see in the input item is in JSON format.
    
    @type  my_json: str
    @param my_json: A string value from the requests results.
    """
    try:
        json_object = json.loads(my_json)
    except (ValueError, TypeError) as e:
        return False
    return True
    
def print_msg(msg, nl=True):
    
    if nl: msg = "\n%s%s" % (' '*INDENT, msg)
    else: msg = "%s%s" % (' '*INDENT, msg)
    
    print(msg)
    
def print_footer(title, msg):
    print("\n%s-----%s%s" % (' '*INDENT, title, str((59 - len(title))*'-')))
    msg = msg.strip('\n')
    for m in msg.split('\n'):
        print("%s| %s" % (' '*INDENT, m))
    print("%s--------------------------------------------------------------" \
            "--" % str(' '*INDENT))
    
def print_heading(msg):
    print("\n**************************************************************" \
            "************")
    print(" %s" % msg)
    print("****************************************************************" \
            "**********")
    
def print_support(err_str=None):
    """
    Prints the 2 different support message depending if an error occurred.
    
    @type  err_str: str
    @param err_str: The error string to print along with support.
    """
    
    if err_str is None:
        print("\nIf you have any questions or require support, " \
                "please contact the EODMS Support Team at " \
                "nrcan.eodms-sgdot.rncan@canada.ca")
    else:
        print("\nERROR: %s" % err_str)
        
        print("\nExiting process.")
        
        print("\nFor help, please contact the EODMS Support Team at " \
                "nrcan.eodms-sgdot.rncan@canada.ca")
