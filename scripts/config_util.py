import configparser
import os
import getpass
import base64


class ConfigUtils:

    def __init__(self):
        # Set the configuration filepath
        self.config_fn = os.path.join(os.sep, os.path.expanduser('~'), '.eodms',
                                      'config.ini')
        # Create configparser
        self.config_info = configparser.ConfigParser(comment_prefixes='/',
                                                     allow_no_value=True)

        # The contents of the configuration file
        self.config_contents = {'Paths':
                [
                    {
                        'name': 'downloads',
                        'desc': 'Path of the image files downloaded from the '
                                'RAPI; if blank, files will be saved in the '
                                'script folder under "downloads"',
                        'default': '',
                        'value': None
                    },
                    {
                        'name': 'results',
                        'desc': 'Path of the results CSV files from the '
                                'script; if blank, files will be saved in the '
                                'script folder under "results"',
                        'default': '',
                        'value': None
                    },
                    {
                        'name': 'log',
                        'desc': 'Path of the log files; if blank, log files '
                                'will be saved in the script folder under '
                                '"log"',
                        'default': '',
                        'value': None
                    }
                ],
            'Script':
            [

                {
                    'name': 'keep_results',
                    'desc': 'The minimum date the CSV result files will be '
                            'kept; all files prior to this date will be '
                            'deleted (format: yyyy-mm-dd)',
                    'default': '',
                    'value': None
                },
                {
                    'name': 'keep_downloads',
                    'desc': 'The minimum date the download files will be kept; '
                            'all files prior to this date will be deleted '
                            '(format: yyyy-mm-dd)',
                    'default': '',
                    'value': None
                }
            ],
            'RAPI':
                [
                    {
                        'name': 'username',
                        'desc': 'Username of the EODMS account used to access '
                                'the RAPI',
                        'default': '',
                        'value': None
                    },
                    {
                        'name': 'password',
                        'desc': 'Password of the EODMS account used to access '
                                'the RAPI',
                        'default': '',
                        'value': None
                    },
                    {
                        'name': 'access_attempts',
                        'desc': 'Number of attempts made to the rapi when a '
                                'timeout occurs',
                        'default': 4,
                        'value': None
                    },
                    {
                        'name': 'max_results',
                        'desc': 'Maximum number of results to return from the '
                                'RAPI',
                        'default': 1000,
                        'value': None
                    },
                    {
                        'name': 'timeout_query',
                        'desc': 'Number of seconds before a timeout occurs '
                                'when querying the RAPI',
                        'default': 120.0,
                        'value': None
                    },
                    {
                        'name': 'timeout_order',
                        'desc': 'Number of seconds before a timeout occurs '
                                'when ordering using the RAPI',
                        'default': 180.0,
                        'value': None
                    },
                    {
                        'name': 'order_check_date',
                        'desc': 'When checking for AVAILABLE_FOR_DOWNLOAD '
                                'orders, this date is the earliest they '
                                'will be checked. Can be hours, days, '
                                'months or years',
                        'default': '3 days',
                        'value': None
                    },
                ]
        }

    def ask_user(self):
        """
        Asks the user for all the configuration values.

        :return: n/a
        """

        self.import_config()

        for section, opts in self.config_contents.items():
            for opt in opts:
                def_val = None
                if section in self.config_info.sections():
                    def_val = self.config_info.get(section, opt['name'])
                # print(f"section: {section}")
                # print(f"option: {opt['name']}")
                # print(f"def_val: {def_val}")
                if def_val is None or def_val == '':
                    def_val = opt['default']

                # Ask user for new configuration value
                if opt['name'] == 'password':
                    val = getpass.getpass(f"\n->> {opt['desc']}: ")
                    if val == '':
                        val = self.config_info.get(section, opt['name'])
                    else:
                        val = base64.b64encode(val.encode("utf-8")).decode(
                            "utf-8")
                else:
                    val = input(f"\n->> {opt['desc']} [{def_val}]: ")

                if val is None or val == '':
                    val = self.config_info.get(section, opt['name'])

                if val is None or val == '':
                    val = opt['default']
                # print(f"value: {val}")

                self.config_info.set(section, opt['name'], str(val))

        cfgfile = open(self.config_fn, 'w')
        self.config_info.write(cfgfile, space_around_delimiters=True)
        cfgfile.close()

        # out_str = self.create_config_str()

        # print(f"out_str: {out_str}")

        # return out_str

    def create_config_str(self):
        """
        Creates the configuration string with default values

        :return: The configuration string
        :type: str
        """

        os.makedirs(os.path.dirname(self.config_fn), exist_ok=True)

        out_str = ''
        for section, opts in self.config_contents.items():
            out_str += f'[{section}]\n'
            for opt in opts:
                val = opt['value']
                if opt['value'] is None:
                    val = opt['default']
                out_str += f"# {opt['desc']}\n{opt['name']} = {val}\n"
            out_str += '\n'

        # print(f"out_str: {out_str}")
        # answer = input("Press enter...")

        return out_str

    def get_info(self):
        """
        Gets the configuration parser object

        :return: The configuration parser object
        :type: configparser
        """

        return self.config_info

    def get_option(self, section, option):
        """
        Gets the configuration option based on the given section

        :param section: The section in the configuration file
        :type  section: str
        :param option: The option in the section
        :type  option: str

        :return: The value in the given section and option
        :type: str
        """

        if isinstance(section, str):
            section = [section]

        for sec in section:
            if self.config_info.has_option(sec, option):
                return self.config_info.get(sec, option)

    def import_config(self):
        """
        Gets the configuration information from the config file.

        :return: The information extracted from the config file.
        :rtype: configparser.ConfigParser
        """

        if not os.path.exists(self.config_fn):
            config_str = self.create_config_str()
            with open(self.config_fn, "w") as f:
                f.write(config_str)

        self.config_info.read(self.config_fn)

        return self.config_info
