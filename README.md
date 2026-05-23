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
| fiona           | Used for vector geospatial file I/O (e.g., shapefiles).  | https://pypi.org/project/Fiona/             |
| shapely         | Used to determine the percentage of overlap with the AOI. | https://pypi.org/project/Shapely/           |
| python-dateutil | Used to parse dates.                                      | https://pypi.org/project/python-dateutil/   |
| tqdm            | Used to access the RAPI and download files.               | https://pypi.org/project/tqdm/              |
| numpy           | Used to close polygons.                                   | https://pypi.org/project/numpy/             |
| packaging       | Used for dependency/version comparisons.                  | https://pypi.org/project/packaging/         |
| colorama        | Used for cross-platform colored terminal output.          | https://pypi.org/project/colorama/          |

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
> python eodms_cli2.py --help                             

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

Listing available collections...

```bash
> python eodms_cli2.py search --list

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

Login w/ authorized account to see restricted collections...

```bash
> python eodms_cli2.py search --list -u %EODMS_USER% -p %EODMS_PASSWORD%

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

```bash
> python eodms_cli2.py search -c rcm-ard -l 20 -o rcm.geojson

Using unauthenticated catalog: https://www.eodms-sgdot.nrcan-rncan.gc.ca/search
Searching up to limit of 20...
https://eodms-sgdot.nrcan-rncan.gc.ca/search/collections/rcm-ard/items?limit=20
Page 1 (MjAyNS0wMy0wNFQyMzowMDoxOS4zNTJa): (20 collected so far)
Found 20 items (limited to 20)
Found 20 item(s).
Saved 20 item(s) to rcm.geojson
```

Take a look...

```json
> cat rcm.geojson

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

```bash
> python eodms_cli2.py search -c Sentinel-1 -d "2026-05-01/2026-05-20" --aoi test/ottawa.geojson -o may-ottawa.geojson

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

Tighten by collection-specifics. What are the queryables?

```bash
> python eodms_cli2.py search -c RCMImageProducts --queryables

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

How about some high-res 5-metre...

```bash
> python eodms_cli2.py search -u %EODMS_USER% -p %EODMS_PASSWORD% -c RCMImageProducts -d "2025-03-01/2026-05-20" --aoi test/ottawa.geojson -f "beam_mnemonic LIKE '5M%'" -o test/rcm_5m.geojson

Loaded 1 polygon(s) from AOI file
Using authenticated catalog: https://www.eodms-sgdot.nrcan-rncan.gc.ca/search
Searching AOI geometry: Ottawa, ON, CA
Searching up to limit of 1000...
https://eodms-sgdot.nrcan-rncan.gc.ca/search/collections/RCMImageProducts/items?limit=1000&datetime=2025-01-01T00:00:00Z/2026-05-20T23:59:59Z&filter=(beam_mnemonic+LIKE+'3M%')+AND+S_INTERSECTS(geometry,+POLYGON+((-75.9+45.2,+-75.5+45.2,+-75.5+45.5,+-75.9+45.5,+-75.9+45.2)))&filter-lang=cql2-text
Page 1 (MjAyNS0wMi0yMFQxMTowNDoyNy42OTVa): (15 collected so far)
Found 15 items (limited to 1000)
Found 15 item(s).
```

Ok, `342ea023-5a9d-5157-b494-e24ec7a3b014 (RCM1_OK3584454_PK3585363_1_5M19_20250429_110414_HH_HV_GRD)` looks good.

### Download

Let us download this (level-1) image

```bash
> python eodms_cli2.py download -c RCMImageProducts --uuid 342ea023-5a9d-5157-b494-e24ec7a3b014 -u %EODMS_USER% -p %EODMS_PASSWORD%      

Downloading UUID: 342ea023-5a9d-5157-b494-e24ec7a3b014
[ eodms_logger ] RCMImageProducts/342ea023-5a9d-5157-b494-e24ec7a3b014 is being prepared; currentstatus is Queued.
Item has no download URL: collection=RCMImageProducts, uuid=342ea023-5a9d-5157-b494-e24ec7a3b014
```

Ok, its `Queued`. Wait 30s... try again:

```
> python eodms_cli2.py download -c RCMImageProducts --uuid 342ea023-5a9d-5157-b494-e24ec7a3b014 -u %EODMS_USER% -p %EODMS_PASSWORD%     

Downloading UUID: 342ea023-5a9d-5157-b494-e24ec7a3b014
[ eodms_logger ] Successfully got item RCMImageProducts/342ea023-5a9d-5157-b494-e24ec7a3b014
[ eodms_logger ] Downloading image to .\RCM1_OK3584454_PK3585363_1_5M19_20250429_110414_HH_HV_GRD.zip...
```

There it goes!

### Process

Ok, let us instead now pre-process this scene. What processes are available?

```bash
> python eodms_cli2.py process --list_processes                                           

[ eodms_processes ] Successfully listed available processes

### EODMS Processing Service.

Radarsat1CEOSL0RAW (v0.0.1): Generate a Radarsat-1 CEOS L0 RAW product
Radarsat1GAMMAL1SLC (v0.0.1): Generate a Radarsat-1 L1 product in GAMMA SLC format - Maximum of 2 frames per process request - Use 'start_time' and 'stop_time' to limit the frames processed
Echo (v0.0.1): N/A
Radarsat1CEOSL1SLC (v0.0.1): Generate Radarsat-1 L1 product in CEOS SLC (16-bit) - Maximum of 2 frames per process request - Use 'start_time' and 'stop_time' to limit the frames processed

### EODMS SAR Toolbox

SAR_Toolbox (vX.X): Filters, Ortho-rectification and mosaic Radiometry, Polarimetry, Interferometry, Analysis Ready Data. Support for RADARSAT-2, RCMImageProducts.
```

Ok, `Analysis Ready Data` looks good. How is it called?

```bash
> py eodms_cli2.py process --process_id SAR_Toolbox --input-structure

Coming soon....
```

At the moment, `SAR_Toolbox`'s `items` block takes `recordId`, which we don't have for our 3m image. Let us look it up using `uuid` from above:

```bash
> python eodms_cli2.py search --uuid2record -c RCMImageProducts --uuid 342ea023-5a9d-5157-b494-e24ec7a3b014 -u %EODMS_USER% -p %EODMS_PASSWORD%

...
| EODMSRAPI | 2026-05-22 16:08:00 | RAPI Query URL: https://www.eodms-sgdot.nrcan-rncan.gc.ca/wes/rapi/search?collection=RCMImageProducts&query=%28CATALOG_IMAGE.START_DATETIME%3E%3D%272025-02-20T11%3A04%3A27Z%27+AND+CATALOG_IMAGE.START_DATETIME%3C%3D%272025-02-21T11%3A04%3A27Z%27%29+AND+ARCHIVE_IMAGE.ORDER_KEY%3D%27RCM2_OK3294733_PK3492600_1_3MCP36_20250220_110427_CH_CV_GRD%27&resultField=CATALOG_IMAGE.THE_GEOM_4326%2CSENSOR_BEAM.SPATIAL_RESOLUTION%2CARCHIVE_IMAGE.UNIQUE_IDENTIFIER&format=json&maxResults=5
| EODMSRAPI | 2026-05-22 16:08:04 | Number of RCMImageProducts images returned from RAPI: 1
3fa6cf78-0de9-572b-b735-52f5b9a4e284: order_key=RCM2_OK3294733_PK3492600_1_3MCP36_20250220_110427_CH_CV_GRD; record_id=31756869
```

Ok `record_id=32522100`. Plug this into the provided `./test/st_ard.json`, along with label for the `sequence_1`, `LabelName` fields. Submit the ARD request using this:

```bash
py eodms_cli2.py process -pi SAR_Toolbox --inputs_json test\st_ard.json -u %EODMS_USER% -p %EODMS_PASSWORD% --submit

| EODMSRAPI | 2026-05-22 18:05:20 | Submitting order items...
| EODMSRAPI | 2026-05-22 18:05:20 | RAPI URL:

https://www.eodms-sgdot.nrcan-rncan.gc.ca/wes/rapi/order

| EODMSRAPI | 2026-05-22 18:05:20 | RAPI POST:

{"items": [{"collectionId": "RCMImageProducts", "recordId": "32522100", "parameters": {}}], "destinations": [], "vapRequest": {"sequence": {"sequence_1": "32522100_ard"}, "method": {"method-901-1": {"Category": "900", "Method": "901", "LabelName": "32522100_ard"}}, "deliveryLocation": "DOWNLOAD", "AllPol": "on", "pr_users_username": null}}

[
  {
    "recordId": "32522100",
    "itemId": "10948941",
    "orderId": "3168001",
    "collectionId": "RCMImageProducts",
    "status": "AVAILABLE_FOR_STREAM",
    "dateRapiOrdered": "2026-05-22T18:05:20.531184-04:00"
  }
]
```

We can check on it using...

```bash
> python eodms_cli2.py download -c RCMImageProducts -u %EODMS_USER% -p %EODMS_PASSWORD% --list

...
  [4]  order_id : 3168001
        status   : AVAILABLE_FOR_STREAM
        items    : 1
        priority : Medium
        submitted: 2026-05-22T22:05:58Z
        name     : RAPI_Order_d1fa1655-4b76-4dd7-81b0-f44e070d62ef
        record_id: 32522100
        collection: RCMImageProducts
...
```

Not ready yet. Check again later


```bash
> python eodms_cli2.py download -c RCMImageProducts -u %EODMS_USER% -p %EODMS_PASSWORD% --list

...
  "order_id": "3168001",
  "status": "AVAILABLE_FOR_DOWNLOAD",
  "submitted": "2026-05-22T22:05:58Z",
...
  "destinations": [
    "https://data.eodms-sgdot.nrcan-rncan.gc.ca/rcm/carts/1bf52c4e-ecd7-4eb5-8948-2fd7b68f6d08/10948941/d1fa1655-4b76-4dd7-81b0-f44e070d62ef"
...
```

All done. Download the whole directory using

```bash
> python eodms_cli2.py download -c RCMImageProducts -u %EODMS_USER% -p %EODMS_PASSWORD% --order-items order:3168001       

Found 1 AVAILABLE_FOR_DOWNLOAD item(s).
Downloading 1 item(s) to .\downloads

| EODMSRAPI | 2026-05-22 20:58:50 | Downloading images...
| EODMSRAPI | 2026-05-22 20:59:00 | Getting list of current orders...
| EODMSRAPI | 2026-05-22 20:59:08 | Downloading image from Collection RCMImageProducts with Record Id 32522100 (RCM1_OK3584454_PK3585363_1_5M19_20250429_110414_HH_HV_GRD\RCM1_OK3584454_PK3585363_1_5M19_20250429_110414_HH.tif).
...
```

The whole package now locally, ready to use.

```bash
> ls .\downloads\RCM1_OK3584454_PK3585363_1_5M19_20250429_110414_HH_HV_GRD               
RCM1_OK3584454_PK3585363_1_5M19_20250429_110414_bitmask.tif
RCM1_OK3584454_PK3585363_1_5M19_20250429_110414_gammaToSigmaRatio.tif
RCM1_OK3584454_PK3585363_1_5M19_20250429_110414_HH.tif
RCM1_OK3584454_PK3585363_1_5M19_20250429_110414_HH_quickLook.tif
RCM1_OK3584454_PK3585363_1_5M19_20250429_110414_HV.tif
RCM1_OK3584454_PK3585363_1_5M19_20250429_110414_HV_quickLook.tif
RCM1_OK3584454_PK3585363_1_5M19_20250429_110414_localContributingArea.tif
RCM1_OK3584454_PK3585363_1_5M19_20250429_110414_localIncAngle.tif
RCM1_OK3584454_PK3585363_1_5M19_20250429_110414_product.xml
RCM_EULA_GC_v3-1_20210202_UNCLASSIFIED.pdf
```


## Contact

If you have any questions or require support, please contact the EODMS Support Team at eodms-sgdot@nrcan-rncan.gc.ca.

## License

MIT License
