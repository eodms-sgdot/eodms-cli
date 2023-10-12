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

__title__ = 'EODMS-CLI Prompt Tester'
__author__ = 'Kevin Ballantyne'
__copyright__ = 'Copyright (c) His Majesty the King in Right of Canada, ' \
                'as represented by the Minister of Natural Resources, 2023.'
__license__ = 'MIT License'
__description__ = 'Performs various prompt tests of the EODMS-CLI.'
__email__ = 'eodms-sgdot@nrcan-rncan.gc.ca'

import os
import sys
import unittest
from unittest.mock import Mock, patch
import click
# import argparse

sys.path.insert(0, os.path.dirname(os.getcwd()))

import eodms_cli
from scripts import config_util
from scripts import utils as eod_util

class TestEodmsCli(unittest.TestCase):

    def _print_header(self, title):

        try:
            terminal_sizes = os.get_terminal_size()
            term_width = terminal_sizes.columns - 2
        except:
            term_width = 80

        line = "#" * int(term_width / 2)

        print("\n" + line.center(term_width))
        print("EODMS-CLI - Prompt Test".center(term_width))
        print(title.center(term_width))
        print(line.center(term_width) + "\n")

    def _setup_prompt(self, username=None, password=None):

        if username is None:
            username = os.getenv('EODMS_USER')

        if password is None:
            password = os.environ.get('EODMS_PASSWORD')

        params = {'username': username,
                  'password': password,
                  'input_val': None,
                  'collections': None,
                  'process': None,
                  'filters': None,
                  'dates': None,
                  'maximum': None,
                  'priority': None,
                  'output': None,
                  'csv_fields': None,
                  'aws': None,
                  'overlap': None,
                  'no_order': None,
                  'downloads': None,
                  'silent': None,
                  'version': None}

        conf_util = config_util.ConfigUtils()
        conf_util.import_config()

        config_params = eodms_cli.get_configuration_values(conf_util, None)
        download_path = config_params['download_path']
        res_path = config_params['res_path']
        log_path = config_params['log_path']
        timeout_query = config_params['timeout_query']
        timeout_order = config_params['timeout_order']
        keep_results = config_params['keep_results']
        keep_downloads = config_params['keep_downloads']
        colourize = config_params['colourize']
        max_results = config_params['max_results']
        order_check_date = config_params['order_check_date']
        download_attempts = config_params['download_attempts']
        rapi_url = config_params['rapi_url']

        eod = eod_util.EodmsProcess(version=eodms_cli.__version__, 
                                    download=download_path,
                                    results=res_path, log=log_path,
                                    timeout_order=timeout_order,
                                    timeout_query=timeout_query,
                                    max_res=max_results,
                                    keep_results=keep_results,
                                    keep_downloads=keep_downloads,
                                    colourize=colourize,
                                    order_check_date=order_check_date,
                                    download_attempts=download_attempts,
                                    rapi_url=rapi_url)

        prmpt = eodms_cli.Prompter(eod, conf_util, params, click, testing=True)

        return prmpt

    inputs = {'test1': ['1', '17,13', 'Yes', '', 'BEAM_MNEMONIC LIKE 16M%', '',
                    '', 'files/test1_output.geojson', '', '3', '', 'low'],
              'test2': ['2', 'files/EODMS_Results.csv',
                    'files/test2_output.geojson', 'y', ''],
              'test3': ['3', 'RCMImageProducts:13531983,'
                                'RCMImageProducts:13531917,'
                                'Radarsat2:13532412,'
                                'Radarsat1:5053934',
                        'Yes', 'files/test3_output.geojson', '', 'low'],
              'test4': ['4', '', '3', 'files/test4_output.geojson'],
              'test5': ['5', 'files/20220530_145625_Results.csv',
                        'files/test5_output.geojson'],
              'test6': ['', '17,15', 'files/NCR_AOI.geojson', '30',
                        'beam_mnemonic like 16M%,product_type=SLC',
                        'beam_mnemonic like EH%,transmit_polarization=H',
                        '20170101-20220527', 'files/test6_output.geojson',
                        'y', '']
              }

    @patch('builtins.input', side_effect=inputs['test1'])
    def test_process1(self, mock_input):
        """
        Runs a test of Process 1 with both RCM and Radarsat-1 imagery.
        """

        self._print_header("Process 1")

        prmpt = self._setup_prompt()

        self.assertEqual(prmpt.prompt(), None)
        # self.assertEqual(result)

    @patch('builtins.input', side_effect=inputs['test2'])
    def test_process2(self, mock_input):
        """
        Runs a test of Process 2 with results from the EODMS UI.
        """

        self._print_header("Process 2")

        prmpt = self._setup_prompt()

        self.assertEqual(prmpt.prompt(), None)

    @patch('builtins.input', side_effect=inputs['test3'])
    def test_process3(self, mock_input):
        """
        Runs a test of Process 3 with a set of Record IDs.
        """

        self._print_header("Process 3")

        prmpt = self._setup_prompt()

        self.assertEqual(prmpt.prompt(), None)

    @patch('builtins.input', side_effect=inputs['test4'])
    def test_process4(self, mock_input):
        """
        Runs a test of Process 4 (download AVAILABLE_FOR_DOWNLOAD).
        """

        self._print_header("Process 4")

        prmpt = self._setup_prompt()

        self.assertEqual(prmpt.prompt(), None)

    @patch('builtins.input', side_effect=inputs['test5'])
    def test_process5(self, mock_input):
        """
        Runs a test of Process 5 with previous results.
        """

        self._print_header("Process 5")

        prmpt = self._setup_prompt()

        self.assertEqual(prmpt.prompt(), None)

    @patch('builtins.input', side_effect=inputs['test6'])
    def test_searchonly(self, mock_input):
        """
        Runs a test of Process 1 but without ordering and downloading.
        """

        self._print_header("Search Only")

        prmpt = self._setup_prompt()

        self.assertEqual(prmpt.prompt(), None)

    @patch('builtins.input', side_effect=[])
    def test_wrongcreds(self, mock_input):
        """
        Runs a test with the wrong credentials.
        """

        self._print_header("Wrong Credentials")

        prmpt = self._setup_prompt(username='fdhsdffsd', password='dfghdfsh')

        self.assertEqual(prmpt.prompt(), None)

if __name__ == '__main__':
    unittest.main()