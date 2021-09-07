EODMS RAPI Search, Order & Download Python Script
=================================================

## Overview

The **eodms_orderdownload.py** script is used to search, order and download imagery from the EODMS using the REST API (RAPI) service.

## Requirements

### Python

The eodms_orderdownload.py was designed using **Python 3.7** however it has been tested successfully in Python 3.6.10. Using a version prior to Python 3.6 is not recommended as the script will not work properly.

### Python Packages

| Package Name  | Use                                                 | URL                                     |
|---------------|-----------------------------------------------------|-----------------------------------------|
| py-eodms-rapi | The EODMS RAPI Python package.                      | https://pypi.org/project/py-eodms-rapi/ |
| Requests      | Used to access the RAPI URL.                        | https://pypi.org/project/requests/      |
| dateparser    | Used to parse a date like "24 hours".               | https://pypi.org/project/dateparser/    |
| geomet        | Used to import WKT geometry text.                   | https://pypi.org/project/geomet/        |
| GDAL          | (Optional) Only required when using AOI shapefiles. | https://pypi.org/project/GDAL/          |

## Setup

1. Clone the repository:
	
	```dos
	> git clone https://github.com/nrcan-eodms-sgdot-rncan/eodms-rapi-orderdownload.git
	```
	
2. Install required packages (GDAL not included):

	```dos
	> cd eodms-rapi-orderdownload
	> pip install -r requirements.txt
	```
	
3. Run the batch file and enter values when prompted:
	
	```dos
	> eodms_orderdownload.bat
	```

## User Guide

For the full instructions on using the eodms_orderdownload script, please visit the [Search, Order & Download Image User Gude](https://github.com/nrcan-eodms-sgdot-rncan/eodms-rapi-orderdownload/wiki/Search,-Order-and-Download-Imagery-Script---Guide).

## Contact

If you have any questions or require support, please contact the EODMS Support Team at nrcan.eodms-sgdot.rncan@canada.ca.

## License

MIT License

Copyright (c) 2020-2021 Her Majesty the Queen in Right of Canada, as 
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
