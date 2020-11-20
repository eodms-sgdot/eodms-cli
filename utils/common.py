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
from xml.etree import ElementTree

from . import utils

RAPI_DOMAIN = 'https://www.eodms-sgdot.nrcan-rncan.gc.ca'

# For DEBUG:
# RAPI_DOMAIN = 'http://www-pre-prod.eodms.services.global.gc.ca'

RAPI_COLLECTIONS = {}
UNSUPPORT_COLLECTIONS = {}
INDENT = 3

def get_fullCollId(coll_id, unsupported=False):
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
        print("UNSUPPORT_COLLECTIONS: %s" % UNSUPPORT_COLLECTIONS)
        for k in UNSUPPORT_COLLECTIONS.keys():
            if k.find(coll_id) > -1:
                return k
    
    for k in RAPI_COLLECTIONS.keys():
        if k.find(coll_id) > -1:
            return k

def convert_date(in_date):
    """
    Converts a date to ISO standard format.
    
    @type  in_date: str
    @param in_date: A string containing a date in format YYYYMMDD.
    
    @rtype:  str
    @return: The date converted to ISO format.
    """
    
    out_date = '%s-%s-%sT00:00:00Z' % (in_date[:4], in_date[4:6], \
                in_date[6:])
                
    return out_date
    
def export_records(csv_f, header, records):
    """
    Exports a set of records to a CSV.
    
    @type  csv_fn:  file object
    @param csv_fn:  The CSV file to write to.
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
    
def get_availableFields(session, collection):
    """
    Gets a dictionary of available fields for a collection from the RAPI.
    
    @type  session:    request.Session
    @param session:    A request session containing the EODMS authentication.
    @type  collection: str
    @param collection: The Collection ID.
    
    @rtype:  dict
    @return: A dictionary containing the available fields for the given 
            collection.
    """
    
    query_url = '%s/wes/rapi/collections/%s' % (RAPI_DOMAIN, collection)
    
    coll_res = send_query(query_url, session, timeout=20.0)
    
    # If an error occurred
    if isinstance(coll_res, utils.QueryError):
        print("\n  WARNING: %s" % coll_res.get_msg())
        return coll_res
    
    coll_json = coll_res.json()
    
    # Get a list of the searchFields
    fields = {}
    for r in coll_json['searchFields']:
        fields[r['title']] = r['id']
        
    return fields

def get_collections(session, as_list=False):
    """
    Gets a list of available collections for the current user.
    
    @type  session: requests.Session
    @param session: The current session with authentication.
    @type  as_list: boolean
    @param as_list: Determines the type of return. If False, a dictionary
                        will be returned. If True, only a list of collection
                        IDs will be returned.
    
    @rtype:  dict or list (depending on value of as_list)
    @return: Either a dictionary of collections or a list of collection IDs 
                depending on the value of as_list.
    """
    
    print("\nGetting a list of available collections, please wait...")
    
    # List of collections that are either commercial products or not available 
    #   to the general public
    ignore_collNames = ['RCMScienceData', 'Radarsat2RawProducts', 
                        'Radarsat1RawProducts', 'COSMO-SkyMed1', '162', 
                        '165', '164']
    
    # Create the query to get available collections for the current user
    query_url = "%s/wes/rapi/collections" % RAPI_DOMAIN
    
    # Send the query URL
    coll_res = send_query(query_url, session, timeout=20.0)
    
    # If an error occurred
    if isinstance(coll_res, utils.QueryError):
        msg = "Could not get a list of collections due to '%s'.\nPlease try " \
                "running the script again." % coll_res.get_msg()
        print_support(msg)
        sys.exit(1)
    
    # If a list is returned from the query, return it
    if isinstance(coll_res, list):
        return coll_res
    
    # Convert query to JSON
    coll_json = coll_res.json()
    
    # Create the collections dictionary
    #collections = {}
    for coll in coll_json:
        for child in coll['children']:
            if child['collectionId'] in ignore_collNames:
                for c in child['children']:
                    UNSUPPORT_COLLECTIONS[c['collectionId']] = c['title']
            else:
                for c in child['children']:
                    if c['collectionId'] in ignore_collNames:
                        UNSUPPORT_COLLECTIONS[c['collectionId']] = c['title']
                    else:
                        fields = get_availableFields(session, c['collectionId'])
                        RAPI_COLLECTIONS[c['collectionId']] = {'title': c['title'], \
                            'fields': fields}
    
    # If as_list is True, convert dictionary to list of collection IDs
    if as_list:
        collections = [i['title'] for i in RAPI_COLLECTIONS.values()]
        return collections
    
    return RAPI_COLLECTIONS
    
def get_collIdByName(in_title, unsupported=False):
    """
    Gets the Collection ID based on the tile/name of the collection.
    
    @type  in_title:    str
    @param in_title:    The title/name of the collection.
                        (ex: 'RCM Image Products' for ID 'RCMImageProducts')
    @type  unsupported: boolean
    @param unsupported: Determines whether to check in the unsupported list 
                        or not.
    """
    
    if unsupported:
        print("UNSUPPORT_COLLECTIONS: %s" % UNSUPPORT_COLLECTIONS)
        for k, v in UNSUPPORT_COLLECTIONS.items():
            if v.find(in_title) > -1 or in_title.find(v) > -1 \
                or in_title.find(k) > -1 or k.find(in_title) > -1:
                return k
    
    for k, v in RAPI_COLLECTIONS.items():
        if v['title'].find(in_title) > -1:
            return k
            
def get_collectionName(in_id):
    """
    Gets the collection name for a specified collection ID.
    
    @type  in_id: str
    @param in_id: The collection ID.
    """
    
    return RAPI_COLLECTIONS[in_id]

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
        #print("e: %s" % e)
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
    
def send_query(query_url, session=None, timeout=60.0, attempts=4, 
                record_name=None, quiet=True):
    """
    Send a query to the RAPI.
    
    @type  query_url:   str
    @param query_url:   The query URL.
    @type  session:     requests.Session
    @param session:     The current session with authentication.
    @type  timeout:     float
    @param timeout:     The length of the timeout in seconds.
    @type  attempts:    int
    @param attempts:    The maximum number of attempts for query the RAPI.
    @type  record_name: str
    @param record_name: A string used to supply information for the record 
                        in a print statement.
    
    @rtype  request.Response
    @return The response returned from the RAPI.
    """
    
    verify = True
    if query_url.find('www-pre-prod') > -1:
        verify = False
    
    if not quiet:
        print_msg("RAPI Query URL: %s" % query_url)
    
    res = None
    attempt = 1
    err = None
    # Get the entry records from the RAPI using the downlink segment ID
    while res is None and attempt <= attempts:
        # Continue to attempt if timeout occurs
        try:
            if record_name is None:
                if not quiet:
                    print_msg("Querying the RAPI (attempt %s)..." % attempt)
            else:
                if not quiet:
                    print_msg("Querying the RAPI for '%s' " \
                            "(attempt %s)..." % (record_name, attempt))
            if session is None:
                res = requests.get(query_url, timeout=timeout, verify=verify)
            else:
                res = session.get(query_url, timeout=timeout, verify=verify)
            res.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            msg = "HTTP Error: %s" % errh
            
            if msg.find('Unauthorized') > -1:
                err = msg
                attempt = 4
            
            if attempt < attempts:
                print_msg("WARNING: %s; attempting to connect again..." % msg)
                res = None
            else:
                err = msg
            attempt += 1
        except requests.exceptions.ConnectionError as errc:
            msg = "Connection Error: %s" % errc
            if attempt < attempts:
                print_msg("WARNING: %s; attempting to connect again..." % msg)
                res = None
            else:
                err = msg
            attempt += 1
        except requests.exceptions.Timeout as errt:
            msg = "Timeout Error: %s" % errt
            if attempt < attempts:
                print_msg("WARNING: %s; attempting to connect again..." % msg)
                res = None
            else:
                err = msg
            attempt += 1
        except requests.exceptions.RequestException as err:
            msg = "Exception: %s" % err
            if attempt < attempts:
                print_msg("WARNING: %s; attempting to connect again..." % msg)
                res = None
            else:
                err = msg
            attempt += 1
        except KeyboardInterrupt as err:
            print("\nProcess ended by user.")
            print_support()
            sys.exit(1)
        except:
            msg = "Unexpected error: %s" % sys.exc_info()[0]
            if attempt < attempts:
                print_msg("WARNING: %s; attempting to connect again..." % msg)
                res = None
            else:
                err = msg
            attempt += 1
            
    if err is not None:
        query_err = utils.QueryError(err)
        return query_err
            
    # If no results from RAPI, return None
    if res is None: return None
    
    # Check for exceptions that weren't already caught
    except_err = get_exception(res)
    
    if isinstance(except_err, utils.QueryError):
        err_msg = except_err.get_msg()
        if err_msg.find('401 - Unauthorized') > -1:
            # Inform the user if the error was caused by an authentication 
            #   issue.
            print_support("An authentication error has occurred while " \
                        "trying to access the EODMS RAPI. Please run this " \
                        "script again with your username and password.")
            sys.exit(1)
            
        print("WARNING: %s" % err_msg)
        return except_err
        
    return res