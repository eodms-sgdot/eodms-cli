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

import configparser
import os
import shutil
import getpass
import base64
import logging


class ConfigUtils:

    def __init__(self):
        # Set the configuration filepath
        old_config_fn = os.path.join(os.sep, os.path.expanduser('~'), '.eodms',
                                      'eodmscli_config.ini')

        self.config_fn = os.path.join(os.sep, os.path.expanduser('~'), '.eodms',
                                      'config.ini')

        if os.path.exists(old_config_fn):
            os.rename(old_config_fn, self.config_fn)

        if not os.path.exists(os.path.dirname(self.config_fn)):
            os.makedirs(os.path.dirname(self.config_fn), exist_ok=True)

        # Create configparser
        self.config_info = configparser.ConfigParser(comment_prefixes='/',
                                                     allow_no_value=True)

        self.logger = logging.getLogger('eodms')

        self.config_dict = {"Paths":
                                {"# Path of the image files downloaded from "
                                 "the rapi; if blank, files will be saved "
                                 "in the script folder under "
                                 "\"downloads\"": None,
                                 "downloads": '',
                                 "# Path of the results csv files from the "
                                 "script; if blank, files will be saved in "
                                 "the script folder under \"results\"": None,
                                 "results": '',
                                 "# Path of the log files; if blank, log "
                                 "files will be saved in the script folder "
                                 "under \"log\"": None,
                                 "log": ''},
                            "Script":
                                {"# The minimum date the csv result files "
                                 "will be kept; all files prior to this date "
                                 "will be deleted (format = yyyy-mm-dd)": None,
                                 "keep_results": '',
                                 "# The minimum date the download files will "
                                 "be kept; all files prior to this date will "
                                 "be deleted (format = yyyy-mm-dd)": None,
                                 "keep_downloads": '', 
                                 "# Determines whether to use colours in the "
                                 "CLI output": None, 
                                 "colourize": 'True'},
                            "Credentials":
                                {"# Username of the eodms account used to "
                                 "access the rapi": None,
                                 "username": '',
                                 "# Password of the eodms account used to "
                                 "access the rapi": None,
                                 "password": ''},
                            "RAPI":
                                {"# Number of attempts made to the rapi when "
                                 "a timeout occurs": None,
                                 "access_attempts": '4',
                                 "# Maximum number of results to return from "
                                 "the rapi": None,
                                 "max_results": '1000',
                                 "# Number of seconds before a timeout occurs "
                                 "when querying the rapi": None,
                                 "timeout_query": '120.0',
                                 "# Number of seconds before a timeout occurs "
                                 "when ordering using the rapi": None,
                                 "timeout_order": '180.0',
                                 "# When checking for available_for_download "
                                 "orders, this date is the earliest they will "
                                 "be checked. can be hours, days, months or "
                                 "years": None,
                                 "order_check_date": "3 days",
                                 "# Maximum number of attempts to download "
                                 "images while waiting for orders to become "
                                 "AVAILABLE_FOR_DOWNLOAD": None,
                                 "download_attempts": ""
                                 }
                            }

    def _set_dict(self, dict_sect, sections, option):
        """
        Sets a value in the config_dict based on an option from the config_info

        :param dict_sect: The dictionary section name.
        :type  dict_sect: str
        :param sections: A list of sections from the configuration file.
        :type  sections: str
        :param option: The option
        :type  option: str

        :return: n/a
        """

        if dict_sect not in self.config_dict.keys():
            self.config_dict[dict_sect] = {}

        if isinstance(sections, str):
            sections = [sections]

        for sec in sections:
            if self.config_info.has_option(sec, option):
                val = self.config_info.get(sec, option)
                if val.lower() == 'true' or val.lower() == 'false':
                    val = eval(val)
                self.config_dict[dict_sect][option] = val

    def _ask_input(self, section, in_opts):

        for idx, opt in enumerate(in_opts.keys()):
            if opt.startswith("#"): continue

            desc = list(in_opts.keys())[idx - 1].replace("# ", "")
            prev_val = in_opts[opt]

            if opt == 'password':
                val = getpass.getpass(f"\n->> {desc}: ")
                if val == '':
                    val = prev_val
                else:
                    val = base64.b64encode(val.encode("utf-8")).decode(
                        "utf-8")
            else:
                val = input(f"\n->> {desc} ({opt}) [{prev_val}]: ")
                if val == '':
                    val = prev_val

            self.config_dict[section][opt] = val

    def ask_user(self, in_sect='all'):
        """
        Asks the user for all the configuration values.

        :return: n/a
        """

        self.import_config()

        sections = '\n'.join([f'    {k}\t\t\tAsks user for parameters under '
                              f'section {k}.'
                              for k in self.config_dict.keys()])

        options = []
        for section, opts in self.config_dict.items():
            for opt, val in opts.items():
                if opt.find('#') > -1: continue

                options.append(f"    {section}.{opt}=<value>\t\t\tSets "
                               f"parameter {opt} in section {section} to "
                               f"<value>.")

        opt_str = '\n'.join(options)

        if in_sect == '-h':
            print(f"""
Usage: eodms_cli.py --configure [OPTIONS]
            
    Sets the parameters in the configuration file
    
Options:
    all\t\t\t\tAsks user for all parameters in the configuration file.
{sections}
{opt_str}
            """)
        elif in_sect == 'all':
            for section, opts in self.config_dict.items():
                self._ask_input(section, opts)
        else:
            if in_sect.find('.') > -1:
                sect_title, opt = in_sect.split('.')

                if sect_title not in self.config_dict.keys():
                    err = f"The section '{sect_title}' does not exist in the " \
                          f"configuration file."
                    print(f"WARNING: {err}")
                    self.logger.warning(err)
                    return None

                opt_key, opt_val = opt.split('=')

                self.config_dict[sect_title][opt_key] = opt_val

                print(f"\nParameter '{opt_key}' in section '{sect_title}' "
                      f"has been changed to '{opt_val}' in the configuration "
                      f"file.")
            else:
                sect_opts = None
                sect_key = None
                for k, v in self.config_dict.items():
                    if k.lower() == in_sect.lower():
                        sect_key = k
                        sect_opts = v

                if sect_opts is None:
                    err = f"The section '{in_sect}' does not exist in the " \
                          f"configuration file."
                    print(f"WARNING: {err}")
                    self.logger.warning(err)
                    return None

                self._ask_input(sect_key, sect_opts)

        # for section, opts in self.config_contents.items():
        #     for opt in opts:
        #         def_val = None
        #         if section in self.config_info.sections():
        #             def_val = self.config_info.get(section, opt['name'])
        #
        #         if def_val is None or def_val == '':
        #             def_val = opt['default']
        #
        #         # Ask user for new configuration value
        #         if opt['name'] == 'password':
        #             val = getpass.getpass(f"\n->> {opt['desc']}: ")
        #             if val == '':
        #                 val = self.config_info.get(section, opt['name'])
        #             else:
        #                 val = base64.b64encode(val.encode("utf-8")).decode(
        #                     "utf-8")
        #         else:
        #             val = input(f"\n->> {opt['desc']} [{def_val}]: ")
        #
        #         if val is None or val == '':
        #             val = self.config_info.get(section, opt['name'])
        #
        #         if val is None or val == '':
        #             val = opt['default']
        #         # print(f"value: {val}")
        #
        #         self.config_info.set(section, opt['name'], str(val))

        self.write()

        # out_str = self.create_config_str()

        # print(f"out_str: {out_str}")

        # return out_str

    # def create_config_str(self):
    #     """
    #     Creates the configuration string with default values
    #
    #     :return: The configuration string
    #     :type: str
    #     """
    #
    #     os.makedirs(os.path.dirname(self.config_fn), exist_ok=True)
    #
    #     out_str = ''
    #     for section, opts in self.config_contents.items():
    #         out_str += f'[{section}]\n'
    #         for opt in opts:
    #             val = opt['value']
    #             if opt['value'] is None:
    #                 val = opt['default']
    #             out_str += f"# {opt['desc']}\n{opt['name']} = {val}\n"
    #         out_str += '\n'
    #
    #     return out_str

    def get_filename(self):
        """
        Gets the filename and path of the configuration file being used.

        :return: The path of the configuration file.
        :rtype: str
        """

        return self.config_fn

    def get_info(self):
        """
        Gets the configuration parser object

        :return: The configuration parser object
        :type: configparser
        """

        return self.config_info

    def get(self, section, option):
        """
        Gets the config_dict option based on the given section

        :param section: The section in the dictionary
        :type  section: str
        :param option: The option in the section
        :type  option: str

        :return: The value in the given section and option
        :type: str
        """

        # if isinstance(section, str):
        #     section = [section]
        #
        # for sec in section:
        #     if self.config_info.has_option(sec, option):
        #         return self.config_info.get(sec, option)

        if section in self.config_dict.keys():
            if option in self.config_dict[section].keys():
                return self.config_dict[section][option]

    def set(self, section, option, value):
        """
        Sets a value in the config_dict

        :param section: The section in the dictionary
        :type  section: str
        :param option: The option in the section.
        :type  option: str
        :param value: The value to set
        :type  value: str

        :return: n/a
        """

        if section in self.config_dict.keys():
            self.config_dict[section][option] = value

    def update_dict(self):
        """
        Updates the config_dict based on config_info

        :return: n/a
        """

        sp = ['Script', 'Paths']  # For backwards compatibility
        self._set_dict('Paths', sp, 'downloads')
        self._set_dict('Paths', sp, 'results')
        self._set_dict('Paths', sp, 'log')

        self._set_dict('Script', 'Script', 'keep_results')
        self._set_dict('Script', 'Script', 'keep_downloads')
        self._set_dict('Script', 'Script', 'colourize')

        cr = ['Credentials', 'RAPI']  # For backwards compatibility
        self._set_dict('Credentials', cr, 'username')
        self._set_dict('Credentials', cr, 'password')

        sr = ['Script', 'RAPI']  # For backwards compatibility
        self._set_dict('RAPI', 'RAPI', 'access_attempts')
        self._set_dict('RAPI', 'RAPI', 'max_results')
        self._set_dict('RAPI', sr, 'timeout_query')
        self._set_dict('RAPI', sr, 'timeout_order')
        self._set_dict('RAPI', 'RAPI', 'order_check_date')
        self._set_dict('RAPI', 'RAPI', 'download_attempts')

        # If any hidden parameters exist in the current config file, keep it
        if self.config_info.has_section('Debug'):
            if self.config_info.has_option('Debug', 'rapi_url'):
                self._set_dict('Debug', 'Debug', 'rapi_url')

    def write(self):
        """
        Writes the config_dict to the config.ini file.
        """

        self.config_info.clear()
        self.config_info.read_dict(self.config_dict)

        cfgfile = open(self.config_fn, 'w')
        self.config_info.write(cfgfile, space_around_delimiters=True)
        cfgfile.close()

    def import_config(self):
        """
        Gets the configuration information from the config file.

        :return: The information extracted from the config file.
        :rtype: configparser.ConfigParser
        """

        if not os.path.exists(self.config_fn):
            # Get the path of the eodms_cli folder
            file_path = os.path.dirname(
                os.path.dirname(
                    os.path.abspath(__file__)))
            # Get configuration file path eodms_cli folder
            script_config = os.path.join(os.sep, file_path, 'config.ini')

            if os.path.exists(script_config):
                # If there is a config.ini in the eodms_cli, move it to
                #   home folder to preserve existing configurations
                print(f"\nMoving existing config.ini from script folder to "
                      f"{os.path.dirname(self.config_fn)}")
                shutil.move(script_config, os.path.dirname(self.config_fn))

        if os.path.exists(self.config_fn):
            # print(f"self.config_fn: {self.config_fn}")
            self.config_info.read(self.config_fn)
            self.update_dict()

        self.config_info.clear()
        self.config_info.read_dict(self.config_dict)

        self.write()

        return self.config_info
