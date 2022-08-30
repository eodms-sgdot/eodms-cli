EODMS Command-line Interface
============================

## Overview

The **eodms_cli.py** script is used to search, order and download imagery from the EODMS using the REST API (RAPI) service.

## Requirements

### Python

The eodms_cli.py was designed using **Python 3.7** however it has been tested successfully in Python 3.6.10. Using a version prior to Python 3.6 is not recommended as the script will not work properly.

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
	
	```dos
	> git clone https://github.com/eodms-sgdot/eodms-cli.git
	```
	
2. Install required packages (GDAL not included):

	```dos
	> cd eodms-cli
	> pip install -r requirements.txt
	```
	
3. Either

- run the batch file and enter values when prompted:
	
	```dos
	> eodms_cli.bat
	```
	
- run the script using Python

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

## User Guide

For the full instructions on using the eodms_orderdownload script, please visit the [Wiki](https://github.com/eodms-sgdot/eodms-cli/wiki).

## Contact

If you have any questions or require support, please contact the EODMS Support Team at eodms-sgdot@nrcan-rncan.gc.ca.

## License

MIT License

Copyright (c) 2020-2022 Her Majesty the Queen in Right of Canada, as 
represented by the President of the Treasury Board

Permission is hereby granted, free of charge, to any person obtaining a 
copy of this software and associated documentation files (the "Software"), 
to deal in the Software without restriction, including without limitation 
the rights to use, copy, modify, merge, publish, distribute, sublicense, 
and/or sell copies of the Software, and to permit persons to whom the 
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in 
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING 
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER 
DEALINGS IN THE SOFTWARE.
