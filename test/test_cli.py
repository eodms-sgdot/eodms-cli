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

__title__ = 'EODMS-CLI Tester'
__author__ = 'Kevin Ballantyne'
__copyright__ = 'Copyright (c) His Majesty the King in Right of Canada, ' \
                'as represented by the Minister of Natural Resources, 2022.'
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


class TestEodmsCli(unittest.TestCase):

    username = os.getenv('EODMS_USER')
    if username is None:
        username = ''

    password = os.environ.get('EODMS_PASSWORD')
    if password is None:
        password = ''

    def _print_header(self, title):

        terminal_sizes = os.get_terminal_size()
        term_width = terminal_sizes.columns - 2

        line = "#" * int(term_width / 2)

        print("\n" + line.center(term_width))
        print("EODMS-CLI - Command-line Test".center(term_width))
        print(title.center(term_width))
        print(line.center(term_width) + "\n")

    def add_creds(self):

        if self.username is not None and not self.username == '':
            self.command.insert(2, '-u')
            self.command.insert(3, self.username)

        if self.password is not None and not self.password == '':
            self.command.insert(2, '-p')
            self.command.insert(3, self.password)

    def capture(self):

        if isinstance(self.command, list):
            self.command_str = ' '.join(self.command)
        else:
            self.command_str = self.command

        # proc = sp.Popen(command, stdout=sp.PIPE, stderr=sp.PIPE)
        # out, err = proc.communicate()

        process = sp.Popen(self.command_str, shell=True, bufsize=1,
                           stdout=sp.PIPE, stderr=sp.STDOUT,
                           encoding='utf-8', errors='replace')
        while True:
            realtime_output = process.stdout.readline()
            if realtime_output == '' and process.poll() is not None:
                break
            if realtime_output:
                print(realtime_output.strip(), flush=False)
                sys.stdout.flush()

        out, err = process.communicate()

        return out, err, process.returncode

    def test_process1(self):

        self._print_header("Process 1")

        self.command = ["python", "../eodms_cli.py",
                   '-c', 'RCMImageProducts,Radarsat2',
                   '-d', '20190101-20220527',
                   '-i', 'files/NCR_AOI.geojson',
                   '-max', '2:1',
                   '-prc', 'full',
                   '-ov', '30',
                   '-f', '"RCMImageProducts.beam_mnemonic like 16M%,'
                         'RCMImageProducts.product_type=SLC,'
                         'Radarsat2.beam_mnemonic like EH%,'
                         'Radarsat2.transmit_polarization=H"',
                   '-o', 'files/test1_output.geojson',
                   '-pri', 'low',
                   '-s']

        self.add_creds()

        # print(f"self.command: {self.command}")

        out, err, exitcode = self.capture()
        assert (not exitcode == 1)

    def test_process2(self):

        self._print_header("Process 2")

        self.command = ["python", "../eodms_cli.py",
                   '-i', 'files/RCMImageProducts_Results.csv',
                   '-max', '4',
                   '-prc', 'order_csv',
                   '-o', 'files/test2_output.geojson',
                   '-pri', 'low',
                   '-s']

        self.add_creds()

        # print(f"self.command: {self.command}")

        out, err, exitcode = self.capture()
        assert (not exitcode == 1)

    def test_process3(self):

        self._print_header("Process 3")

        self.command = ["python", "../eodms_cli.py",
                   '-i', 'RCMImageProducts:13531983,RCMImageProducts:13531917,'
                         'Radarsat2:13532412,Radarsat1:5053934',
                   '-prc', 'record_id',
                   '-a',
                   '-o', 'files/test3_output.geojson',
                   '-pri', 'low',
                   '-s']

        self.add_creds()

        # print(f"self.command: {self.command}")

        out, err, exitcode = self.capture()
        assert (not exitcode == 1)

    def test_process4(self):

        self._print_header("Process 4")

        self.command = ["python", "../eodms_cli.py",
                   '-prc', 'download_available',
                   '-o', 'files/test4_output.geojson',
                   '-m', '3',
                   '-s']

        self.add_creds()

        # print(f"self.command: {self.command}")

        out, err, exitcode = self.capture()
        assert (not exitcode == 1)

    def test_process5(self):

        self._print_header("Process 5")

        self.command = ["python", "../eodms_cli.py",
                   '-i', 'files/20220530_145625_Results.csv',
                   '-prc', 'download_results',
                   '-o', 'files/test5_output.geojson',
                   '-s']

        self.add_creds()

        # print(f"self.command: {self.command}")

        out, err, exitcode = self.capture()
        assert (not exitcode == 1)

    def test_searchonly(self):

        self._print_header("Search Only")

        self.command = ["python", "../eodms_cli.py",
                   '-c', 'RCMImageProducts,Radarsat2',
                   '-d', '20190101-20220527',
                   '-i', 'files/NCR_AOI.geojson',
                   '-prc', 'full',
                   '-max', '5:3',
                   '-ov', '30',
                   '-f', '"RCMImageProducts.beam_mnemonic like 16M%,'
                         'RCMImageProducts.product_type=SLC,'
                         'Radarsat2.beam_mnemonic like EH%,'
                         'Radarsat2.transmit_polarization=H"',
                   '-o', 'files/test6_output.geojson',
                   '-pri', 'low',
                   '-nord',
                   '-s']

        self.add_creds()

        # print(f"self.command: {self.command}")

        out, err, exitcode = self.capture()
        assert (not exitcode == 1)


if __name__ == '__main__':
    unittest.main()
