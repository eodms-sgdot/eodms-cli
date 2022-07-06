import os
import sys
import unittest
from unittest.mock import Mock, patch
import click
import argparse

sys.path.insert(0, os.path.dirname(os.getcwd()))

import eodms_cli
from scripts import config_util
from scripts import utils as eod_util

class TestEodmsCli(unittest.TestCase):

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

        print(f"params: {params}")

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
        max_results = config_params['max_results']
        order_check_date = config_params['order_check_date']
        rapi_url = config_params['rapi_url']

        eod = eod_util.EodmsProcess(download=download_path,
                                    results=res_path, log=log_path,
                                    timeout_order=timeout_order,
                                    timeout_query=timeout_query,
                                    max_res=max_results,
                                    keep_results=keep_results,
                                    keep_downloads=keep_downloads,
                                    order_check_date=order_check_date,
                                    rapi_url=rapi_url)

        prmpt = eodms_cli.Prompter(eod, conf_util, params, click, testing=True)

        return prmpt

    inputs = {'test1': ['1', '17,13', 'Yes', '', 'BEAM_MNEMONIC LIKE 16M%', '',
                    '', 'files/test1_output.geojson', '', '3', '', 'low'],
              'test2': ['2', 'files/RCMImageProducts_Results.csv',
                    'files/test2_output.geojson', '', '4', 'low'],
              'test3': ['3', 'RCMImageProducts:13531983,'
                                'RCMImageProducts:13531917,'
                                'Radarsat2:13532412,'
                                'Radarsat1:5053934',
                        'Yes', 'files/test3_output.geojson', '', 'low'],
              'test4': ['4', 'files/test4_output.geojson'],
              'test5': ['5', 'files/20220530_145625_Results.csv',
                        'files/test5_output.geojson'],
              'test6': ['', '17,15', 'files/NCR_AOI.geojson', '30',
                        'beam_mnemonic like 16M%,product_type=SLC',
                        'beam_mnemonic like EH%,transmit_polarization=H',
                        '20170101-20220527', 'files/test6_output.geojson',
                        'y', 'low']
              }

    @patch('builtins.input', side_effect=inputs['test1'])
    def test_process1(self, mock_input):
        """
        Runs a test of Process 1 with both RCM and Radarsat-1 imagery.
        """

        prmpt = self._setup_prompt()

        self.assertEqual(prmpt.prompt(), None)
        # self.assertEqual(result)

    @patch('builtins.input', side_effect=inputs['test2'])
    def test_process2(self, mock_input):
        """
        Runs a test of Process 2 with results from the EODMS UI.
        """

        prmpt = self._setup_prompt()

        self.assertEqual(prmpt.prompt(), None)

    @patch('builtins.input', side_effect=inputs['test3'])
    def test_process3(self, mock_input):
        """
        Runs a test of Process 3 with a set of Record IDs.
        """

        prmpt = self._setup_prompt()

        self.assertEqual(prmpt.prompt(), None)

    @patch('builtins.input', side_effect=inputs['test4'])
    def test_process4(self, mock_input):
        """
        Runs a test of Process 4 (download AVAILABLE_FOR_DOWNLOAD).
        """

        prmpt = self._setup_prompt()

        self.assertEqual(prmpt.prompt(), None)

    @patch('builtins.input', side_effect=inputs['test5'])
    def test_process5(self, mock_input):
        """
        Runs a test of Process 5 with previous results.
        """

        prmpt = self._setup_prompt()

        self.assertEqual(prmpt.prompt(), None)

    @patch('builtins.input', side_effect=inputs['test6'])
    def test_searchonly(self, mock_input):
        """
        Runs a test of Process 1 but without ordering and downloading.
        """

        prmpt = self._setup_prompt()

        self.assertEqual(prmpt.prompt(), None)

    @patch('builtins.input', side_effect=[])
    def test_wrongcreds(self, mock_input):
        """
        Runs a test with the wrong credentials.
        """

        prmpt = self._setup_prompt(username='fdhsdffsd', password='dfghdfsh')

        self.assertEqual(prmpt.prompt(), None)

if __name__ == '__main__':
    unittest.main()