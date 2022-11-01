##############################################################################
# MIT License
#
# Copyright (c) 2020-2022 Her Majesty the Queen in Right of Canada, as
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

__title__ = 'EODMS-CLI Tester'
__author__ = 'Kevin Ballantyne'
__copyright__ = 'Copyright 2020-2022 Her Majesty the Queen in Right of Canada'
__license__ = 'MIT License'
__description__ = 'Performs various tests of the EODMS-CLI.'
__email__ = 'eodms-sgdot@nrcan-rncan.gc.ca'

import sys
import os
import click
import subprocess as sp
import traceback
import eodms_rapi

import unittest
from unittest.mock import patch

# prompt_orders = {'full': ['u', 'p', 'prc', 'c', 'a', 'i', 'ov', 'f', 'd',
#                           'o', 'nord', 'm', 'pri'],
#                 'order_csv': ['u', 'p', 'prc', 'i', 'cf', 'o', 'nord', 'm',
#                               'pri'],
#                 'download_results': ['u', 'p', 'prc', 'i', 'o'],
#                 'download_available': ['u', 'p', 'prc', 'o'],
#                 'record_id': ['u', 'p', 'prc', 'i', 'a', 'o', 'nord', 'pri']}
script_folder = 'C:\\Working\\Development\\EODMS\\eodms-cli\\dev\\'

def convert_collection(in_params):

    coll_ids = in_params['c'].split(',')

    rapi = eodms_rapi.EODMSRAPI(in_params['u'], in_params['p'])
    collections = rapi.get_collections(True, opt='both')
    collections = sorted(collections, key=lambda x: x['title'])

    coll_lst = [c['id'] for c in collections]
    coll_idx = ','.join([str(coll_lst.index(c) + 1) for c in coll_ids])

    return coll_idx

def convert_process(in_params):

    process = in_params['prc']
    prc_idx = str(list(prompt_orders.keys()).index(process) + 1)

    return prc_idx

def split_filters(in_params):
    filters = in_params['f'].split(',')
    filt_dict = {}
    for f in filters:
        coll_id, filt_name = f.split('.')
        filt_lst = []
        if coll_id in filt_dict.keys():
            filt_lst = filt_dict[coll_id]
        filt_lst.append(filt_name)
        filt_dict[coll_id] = filt_lst

    return filt_dict

def run_cli(params):
    print("\n  Running CLI test...")

    cmd = ['python', f'{script_folder}eodms_cli.py']

    for k, v in params.items():
        cmd += [k, v]

    cmd_str = ' '.join(cmd)
    print(f"\n    Command: {cmd_str}")

    process = sp.Popen(cmd, shell=True, bufsize=1,
                       stdout=sp.PIPE, stderr=sp.STDOUT,
                       encoding='utf-8', errors='replace')
    while True:
        realtime_output = process.stdout.readline()
        if realtime_output == '' and process.poll() is not None:
            break
        if realtime_output:
            print(realtime_output.strip(), flush=False)
            sys.stdout.flush()

def run_manual(params):
    print("\n  Running Prompt test...")

    # Order by prompt order
    print(f"params: {params}")
    process = params['prc']
    ordered = {}
    for k in prompt_orders[process]:
        if k in params.keys():
            ordered[k] = params[k]
        else:
            ordered[k] = ''
    # params = {k: params[k] for k in prompt_orders[process]
    #            if k in params.keys()}

    print(f"ordered: {ordered}")

    # Drop AWS if not applicable
    if ordered['c'].find('Radarsat1') == -1:
        ordered.pop('a')

    # Split filters
    ordered['f'] = split_filters(ordered)

    # Convert process to number
    ordered['prc'] = convert_process(ordered)

    # Convert collection to numbers
    ordered['c'] = convert_collection(ordered)

    params_lst = []
    for k, v in ordered.items():
        if isinstance(v, dict):
            for sub_k, sub_v in v.items():
                params_lst.append(','.join(sub_v))
        else:
            params_lst.append(v)

    # print(f"params_lst: {params_lst}")
    # answer = input("Press enter...")

    inputs_str = '\n'.join(params_lst)

    print(f"inputs_str: {inputs_str}")

    print("\n    Parameters:")
    for k, v in ordered.items():
        print(f"      {k}: {v}")

    if inputs_str is None: return None

    print("\n    Running script...")
    p = sp.Popen(['python', f'{script_folder}eodms_cli.py'], stderr=sp.PIPE,
                 stdout=sp.PIPE, stdin=sp.PIPE)

    stdout, stderr = p.communicate(inputs_str.encode('utf-8'))

    print(f"    {stdout.decode('utf-8')}")

def run(username, password, test, test_type='both'):
    cmd = []
    params = {}
    if test == '1':
        print("\nLaunching Test 1: Search, Order and Download")
        params = {'u': username,
                  'p': password,
                  'prc': 'full',
                  'c': 'RCMImageProducts,Radarsat2',
                  'i': 'files/NCR_AOI.geojson',
                  'ov': '30',
                  'f': 'RCMImageProducts.beam_mnemonic like 16M%,'
                       'RCMImageProducts.product_type=SLC,'
                       'Radarsat2.beam_mnemonic like EH%,'
                       'Radarsat2.transmit_polarization=H',
                  'd': '20190101-20220527',
                  'o': 'files/test1_output.geojson',
                  'm': '2:1',
                  'pri': 'low'}
        # cmd = ['python', 'C:\\Working\\Development\\EODMS\\eodms-cli\\dev'
        #                  '\\eodms_cli.py',
        #        '-u', username,
        #        '-p', password,
        #        '-c', 'RCMImageProducts,Radarsat2',
        #        '-d', '20190101-20220527',
        #        '-i', 'files/NCR_AOI.geojson',
        #        '-max', '2:1',
        #        '-prc', 'full',
        #        '-ov', '30',
        #        '-f', '"RCMImageProducts.beam_mnemonic like 16M%%,'
        #              'RCMImageProducts.product_type=SLC,'
        #              'Radarsat2.beam_mnemonic like EH%%,'
        #              'Radarsat2.transmit_polarization=H"',
        #        '-o', 'files/test1_output.geojson',
        #        '-pri', 'low',
        #        '-s']
    elif test == '2':
        cmd = ['python', 'C:\\Working\\Development\\EODMS\\eodms-cli\\dev'
                         '\\eodms_cli.py',
               '-u', username,
               '-p', password,
               '-i', 'files/RCMImageProducts_Results.csv',
               '-max', '4',
               '-prc', 'order_csv',
               '-cf', '"sequence id"',
               '-o', 'files/test2_output.geojson',
               '-pri', 'low',
               '-s']
    elif test == '3':
        cmd = ['python', 'C:\\Working\\Development\\EODMS\\eodms-cli\\dev'
                         '\\eodms_cli.py',
               '-u', username,
               '-p', password,
               '-i', 'RCMImageProducts:13531983,RCMImageProducts:13531917,'
                     'Radarsat2:13532412,Radarsat1:5053934',
               '-prc', 'record_id',
               '-a',
               '-o', 'files/test3_output.geojson',
               '-pri', 'low',
               '-s']
    elif test == '4':
        cmd = ['python', 'C:\\Working\\Development\\EODMS\\eodms-cli\\dev'
                         '\\eodms_cli.py',
               '-u', username,
               '-p', password,
               '-prc', 'download_available',
               '-o', 'files/test4_output.geojson',
               '-s']
    elif test == '5':
        return None
    elif test == '6':
        return None
    elif test == '7':
        return None
    elif test == '8':
        return None

    if test_type == 'cli' or test_type == 'both':
        run_cli(params)
    if test_type == 'manual' or test_type == 'both':
        run_manual(params)

    # cmd_str = ' '.join(cmd)
    # print(f"cmd_str: {cmd_str}")
    # p = sp.Popen(cmd_str, stderr=sp.PIPE, stdout=sp.PIPE, stdin=sp.PIPE)
    # p.wait()
    # stdout, stderr = p.communicate()

    # p = sp.Popen(cmd, stdout=sp.PIPE, bufsize=1)
    # for line in iter(p.stdout.readline, b''):
    #     print(line.decode('utf-8').strip())
    # p.stdout.close()
    # p.wait()

    # invoke process
    # process = sp.Popen(cmd, shell=False, stdout=sp.PIPE)

    # while True:
    #     out = process.stdout.read(1)
    #     if out == '' and process.poll() != None:
    #         break
    #     if out != '':
    #         sys.stdout.write(out.decode('utf-8'))
    #         sys.stdout.flush()

    # Poll process.stdout to show stdout live
    # while True:
    #     output = process.stdout.readline()
    #     if process.poll() is not None:
    #         break
    #     if output:
    #         print(output.strip().decode('utf-8'))
    # rc = process.poll()

    # process = sp.Popen(cmd, shell=True, bufsize=1,
    #                    stdout=sp.PIPE, stderr=sp.STDOUT,
    #                    encoding='utf-8', errors='replace')
    # while True:
    #     realtime_output = process.stdout.readline()
    #     if realtime_output == '' and process.poll() is not None:
    #         break
    #     if realtime_output:
    #         print(realtime_output.strip(), flush=False)
    #         sys.stdout.flush()

    # print(f"stdout: {stdout.decode('utf-8')}")
    # print(f"stderr: {stderr.decode('utf-8')}")

@click.command(context_settings={'help_option_names': ['-h', '--help']})
@click.option('--username', '-u', default=None,
              help='The username of the EODMS account used for '
                   'authentication.')
@click.option('--password', '-p', default=None,
              help='The password of the EODMS account used for '
                   'authentication.')
@click.option('--test', '-t', default=None,
              help='The test number (or all).')
@click.option('--test_type', '-tt', default=None,
              help='The type of tests to run ("cli", "manual" or "both").')
def cli(username, password, test, test_type):
    try:
        if test_type is None or test_type == '':
            test_type = 'both'
        run(username, password, test, test_type)
    except Exception:
        print(traceback.format_exc())

if __name__ == '__main__':
    sys.exit(cli())