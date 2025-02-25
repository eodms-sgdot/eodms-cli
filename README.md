EODMS Command-line Interface (EODMS-CLI)
============================

## Overview

The **EODMS-CLI** script is used to search, order and download imagery from the EODMS using the REST API (RAPI) service.

## Requirements

### Python

The EODMS-CLI was designed using **Python 3.7** however it has been tested successfully in Python 3.6.10. Using a version prior to Python 3.6 is not recommended as the script will not work properly.

### Python Packages

| Package Name    | Use                                                       | URL                                       |
|-----------------|-----------------------------------------------------------|-------------------------------------------|
| py-eodms-rapi   | The EODMS RAPI Python package.                            | https://pypi.org/project/py-eodms-rapi/   |
| Requests        | Used to access the RAPI URL.                              | https://pypi.org/project/requests/        |
| dateparser      | Used to parse a date like "24 hours".                     | https://pypi.org/project/dateparser/      |
| geomet          | Used to import WKT geometry text.                         | https://pypi.org/project/geomet/          |
| click           | Used for the command-line input.                          | https://pypi.org/project/click/           |
| shapely         | Used to determine the percentage of overlap with the AOI. | https://pypi.org/project/Shapely/         |
| python-dateutil | Used to parse dates.                                      | https://pypi.org/project/python-dateutil/ |
| tqdm            | Used to access the RAPI and download files.               | https://pypi.org/project/tqdm/            |
| numpy           | Used to close polygons.                                   | https://pypi.org/project/numpy/           |
| GDAL            | (Optional) Only required when using AOI shapefiles.       | https://pypi.org/project/GDAL/            |

## Setup

1. Clone the repository:
	
	```bash
	> git clone https://github.com/eodms-sgdot/eodms-cli.git
	```
	
2. Install required packages (GDAL not included):

	```bash
	> cd eodms-cli
	> pip install -r requirements.txt
	```
	
3. Run the script using Python

	```bash
	> python eodms_cli.py
	```
	
NOTE: Depending on your installation of Python, you may have to run ```python3 eodms_cli.py```.
	
## Configuration

Configuration for the script can be found in the **config.ini** file in the home folder under ".eodms".

Configuration options can be changed by running ```python eodms_cli.py --configure```.

In the config file, you can: 

- Store credentials **(these must be entered using the script)**
- Set the paths for downloading images, saving results files and storing log file(s).
- Set the timeout interval for querying and ordering
- Set the minimum dates for keeping downloaded images and results files

For more in-depth information on the configuration file, visit [Config File](https://github.com/eodms-sgdot/eodms-cli/wiki/Config-File).

## Updating

### Update py-eodms-rapi

If you receive one of these messages when running the eodms-cli, follow the instructions (run `pip install py-eodms-rapi -U`).

```bash
**** WARNING ****
The py-eodms-rapi currently installed is not the latest version. 
It is recommended to use the latest version of the package. Please
install it using: 'pip install py-eodms-rapi -U'.
*****************
```

or

```bash
**** ERROR ****
The py-eodms-rapi currently installed is an older version than the
minimum required version. Please install it using: 'pip
install py-eodms-rapi -U'.
*****************
```

### Update eodms-cli

If you need to update the eodms-cli to a new release, follow these steps:

1. Pull from the most recent Github repository

	```bash
	> cd eodms-cli  # your eodms-cli repository file location
	> git pull origin main
	```

2. Install required packages (GDAL not included):

	```bash
	> cd eodms-cli
	> pip install -r requirements.txt
	> pip install py-eodms-rapi -U  # get the latest py-eodms-rapi for best functionality
	```
	
3. Run the script using Python

	```bash
	> python eodms_cli.py
	```

## User Guide

For the full instructions on using the eodms_orderdownload script, please visit the [Wiki](https://github.com/eodms-sgdot/eodms-cli/wiki).

## Contact

If you have any questions or require support, please contact the EODMS Support Team at eodms-sgdot@nrcan-rncan.gc.ca.

## License

MIT License
