EODMS Command-line Interface (EODMS-CLI)
============================

## Overview

The **EODMS-CLI** is used to search, order and download imagery from the EODMS using API interfaces.

## Requirements

### Python

The EODMS-CLI was designed using **Python 3.10**.

### Python Packages

| Package Name    | Use                                                       | URL                                         |
|-----------------|-----------------------------------------------------------|---------------------------------------------|
| py-eodms-rapi   | The EODMS RAPI Python package.                            | https://pypi.org/project/py-eodms-rapi/     |
| eodms-py        | The EODMS Python package.                                 | https://github.com/eodms-sgdot/eodms-py     |
| Requests        | Used to access the RAPI URL.                              | https://pypi.org/project/requests/          |
| dateparser      | Used to parse a date like "24 hours".                     | https://pypi.org/project/dateparser/        |
| geomet          | Used to import WKT geometry text.                         | https://pypi.org/project/geomet/            |
| click           | Used for the command-line input.                          | https://pypi.org/project/click/             |
| shapely         | Used to determine the percentage of overlap with the AOI. | https://pypi.org/project/Shapely/           |
| python-dateutil | Used to parse dates.                                      | https://pypi.org/project/python-dateutil/   |
| tqdm            | Used to access the RAPI and download files.               | https://pypi.org/project/tqdm/              |
| numpy           | Used to close polygons.                                   | https://pypi.org/project/numpy/             |
| GDAL            | (Optional) Only required when using AOI shapefiles.       | https://pypi.org/project/GDAL/              |

## Setup

1. Clone the repository:
	
	```bash
	> git clone https://github.com/eodms-sgdot/eodms-cli.git
	```
	
2. Install required packages (GDAL not included):

	```bash
	> cd eodms-cli
	> pip install -r requirements.txt --upgrade
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

### List Commands

```
python eodms_cli2.py --help                             
Usage: eodms_cli2.py [OPTIONS] COMMAND [ARGS]...

  EODMS CLI v2: STAC/DDS-first with targeted legacy ports.

Options:
  -h, --help  Show this message and exit.

Commands:
  search    Search STAC and optionally write results to GeoJSON.
  process   OGC Processes command: list, inspect, submit, track, and...
  download  Port of legacy option 6: download order items with...
```

### Search

Exploring the `search` command...

```bash
python eodms_cli2.py search --help
```

```
Usage: eodms_cli2.py search [OPTIONS]

  Search STAC and optionally write results to GeoJSON.

Options:
  -u, --username TEXT    EODMS username.
  -p, --password TEXT    EODMS password.
  -c, --collection TEXT  Collection name.
  --list                 List available STAC collections and exit.
  --datetime TEXT        Temporal filter as ISO 8601 string/range (example:
                         "2023-01-01/2023-12-31").
  -b, --bbox TEXT        Bounding box as west,south,east,north
  -l, --limit INTEGER    Maximum number of items to fetch (default: 1000).
  -f, --filter TEXT      CQL2 text filter expression.
  --s-intersect TEXT     WKT geometry used with S_INTERSECTS.
  --aoi PATH             Path to geospatial AOI file with 1-5 polygons.
  -o, --output TEXT      Output GeoJSON file for search results.
  -e, --env TEXT         Environment (default: "prod").
  -h, --help             Show this message and exit.
```

Listing available collections...

```
eodms_cli2.py search --list
```

```
Using unauthenticated catalog: https://www.eodms-sgdot.nrcan-rncan.gc.ca/search
Found 10 collection(s):
- Radarsat-1-L1-COG
- Sentinel-1
- Radarsat-2_Tropical_Forest_Products
- RCMImageProducts
- rcm-ard: RADARSAT Constellation Mission, CEOS-ARD
- Radarsat-1-FRED
- SGBAirPhotos
- NAPL
- Sentinel-2
- Radarsat-1-Raw
```

Login w/ authorized account to see even more collections...

```bash
▥ python eodms_cli2.py search --list -u %EODMS_USER% -p %EODMS_PASSWORD%
```

```
[ eodms_aaa ] Current Refresh Token has expired. Getting new Tokens...
[ eodms_aaa ] Successfully logged in using AAA API
[ eodms_aaa ] Updating Access Token...
[ eodms_aaa ] Updating Refresh Token...
[ eodms_aaa ] Updating Access Expiration as 2026-05-21 16:35:45.715067...
[ eodms_aaa ] Updating Refresh Expiration as 2026-05-21 17:24:45.715067...
Using authenticated catalog: https://www.eodms-sgdot.nrcan-rncan.gc.ca/search
Found 20 collection(s):
- Radarsat-1-L1-COG
- Sentinel-1
- Radarsat-2_Tropical_Forest_Products
- RCMImageProducts
- rcm-ard: RADARSAT Constellation Mission, CEOS-ARD
- ALOS-2
- WorldView-4
- Radarsat-1-FRED
- PlanetScope
- SGBAirPhotos
- WorldView-2
- RapidEye
- Radarsat2
- NAPL
- WorldView-1
- WorldView-3
- Sentinel-2
- Radarsat-1-Raw
- Pleiades
- GeoEye-1
```

Grab 20 results from the rcm-ard collection...

```
▥ python eodms_cli2.py search -c rcm-ard -l 20 -o rcm.geojson
```

```
Using unauthenticated catalog: https://www.eodms-sgdot.nrcan-rncan.gc.ca/search
Searching up to limit of 20...
https://eodms-sgdot.nrcan-rncan.gc.ca/search/collections/rcm-ard/items?limit=20
Page 1 (MjAyNS0wMy0wNFQyMzowMDoxOS4zNTJa): (20 collected so far)
Found 20 items (limited to 20)
Found 20 item(s).
Saved 20 item(s) to rcm.geojson
```

Take a look...

`▥ type rcm.geojson` (on linux, `cat rcm.geojson`)
```json
...
        "rl_thumbnail": {
          "href": "https://rcm-ceos-ard.s3.ca-central-1.amazonaws.com/MLC/2025/03/04/RCM3_OK3308170_PK3507604_1_SC30MCPC_20250304_230019_CH_CV_MLC/RCM3_OK3308170_PK3507604_1_SC30MCPC_20250304_230019_RL_quickLook.tif",
          "title": "Backscatter RL Polarization Quicklook",
          "description": null,
          "type": "image/tiff; application=geotiff",
          "roles": null
        },
        "rrrl": {
          "href": "https://rcm-ceos-ard.s3.ca-central-1.amazonaws.com/MLC/2025/03/04/RCM3_OK3308170_PK3507604_1_SC30MCPC_20250304_230019_CH_CV_MLC/RCM3_OK3308170_PK3507604_1_SC30MCPC_20250304_230019_RRRL.tif",
          "title": "Normalized Polarimetric Radar Covariance Matrix (CovMat)",
          "description": null,
          "type": "image/tiff; application=geotiff; profile=cloud-optimized",
          "roles": [
            "data",
            "covmat"
          ]
        }
      },
      "bbox": [
        -78.067174,
        44.281466,
        -76.312189,
        45.112074
      ]
    }
  ]
}
```

Refine the search. Supply some geotemporal criteria...

```
▥ python eodms_cli2.py search -c Sentinel-1 -d "2026-05-01/2026-05-20" --aoi test/ottawa.geojson -o may-ottawa.geojson 
Loaded 1 polygon(s) from AOI file
Using unauthenticated catalog: https://www.eodms-sgdot.nrcan-rncan.gc.ca/search
Searching AOI geometry: Ottawa, ON, CA
Searching up to limit of 1000...
https://eodms-sgdot.nrcan-rncan.gc.ca/search/collections/Sentinel-1/items?limit=1000&datetime=2026-05-01T00:00:00Z/2026-05-20T23:59:59Z&filter=S_INTERSECTS(geometry,+POLYGON+((-75.9+45.2,+-75.5+45.2,+-75.5+45.5,+-75.9+45.5,+-75.9+45.2)))&filter-lang=cql2-text
Page 1 (MjAyNi0wNS0yMFQyMjo1MToyNi43MDFa): (10 collected so far)
Detected repeated page token during pagination; stopping to avoid an infinite loop.
Found 10 items (limited to 1000)
Found 10 item(s).
Saved 10 item(s) to may-ottawa.geojson
```

TIghten by collection-specifics. What are the queryables?

```
▥ python eodms_cli2.py search -c RCMImageProducts --queryables
Using unauthenticated catalog: https://www.eodms-sgdot.nrcan-rncan.gc.ca/search
      * pixel_data_type (string) e.g. pixel_data_type = 'Floating-Point' | constraints: enum=[Floating-Point, Integer]
      * beam_mnemonic (string) e.g. beam_mnemonic = 'example' | constraints: pattern=\w{2,13}
      * orbit_direction (string) e.g. orbit_direction = 'Ascending' | constraints: enum=[Ascending, Descending]
      * datetime (string) e.g. datetime >= DATE('2019-06-29')
      * order_key (string) e.g. order_key = 'example'
      * stop_datetime (string) e.g. stop_datetime >= DATE('2019-06-29')
      * relative_orbit (integer) e.g. relative_orbit = 1 | constraints: min=1 max=179
      * product:type (string) e.g. product:type = 'GCC' | constraints: enum=[GCC, GCD, GRC, GRD, MLC, ...]
      * geometry (geometry-any) e.g. S_INTERSECTS(geometry, POLYGON((-100 45, -95 45, -95 50, -100 50, -100 45)))
      * sample_type (string) e.g. sample_type = 'Complex' | constraints: enum=[Complex, Magnitude Detected, Mixed]
      * applied_lut (string) e.g. applied_lut = 'example'
      * polarization (string) e.g. polarization = 'CH CV' | constraints: enum=[CH CV, HH, HH HV, HH HV VH VV, HH VV, ...]
```

How about some high-res 5-metre data...

```
▥ python eodms_cli2.py search -u %EODMS_USER% -p %EODMS_PASSWORD% -c RCMImageProducts -d "2025-01-01/2026-05-20" --aoi test/ottawa.geojson -f "beam_mnemonic LIKE '3M%'"
Loaded 1 polygon(s) from AOI file
Using authenticated catalog: https://www.eodms-sgdot.nrcan-rncan.gc.ca/search
Searching AOI geometry: Ottawa, ON, CA
Searching up to limit of 1000...
https://eodms-sgdot.nrcan-rncan.gc.ca/search/collections/RCMImageProducts/items?limit=1000&datetime=2025-01-01T00:00:00Z/2026-05-20T23:59:59Z&filter=(beam_mnemonic+LIKE+'3M%')+AND+S_INTERSECTS(geometry,+POLYGON+((-75.9+45.2,+-75.5+45.2,+-75.5+45.5,+-75.9+45.5,+-75.9+45.2)))&filter-lang=cql2-text
Page 1 (MjAyNS0wMi0yMFQxMTowNDoyNy42OTVa): (15 collected so far)
Found 15 items (limited to 1000)
Found 15 item(s).
```



## Contact

If you have any questions or require support, please contact the EODMS Support Team at eodms-sgdot@nrcan-rncan.gc.ca.

## License

MIT License
