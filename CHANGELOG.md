# Changelog

## 4.0.0 (2026-02-)

- Implementation of the EODMS DDS API for ordering and downloading images using the py-eodms-dds Python package.
- CSV results files will no longer be exported with every run, instead the user can choose to export the results as a geospatial file or CSV file.
- Moved prompt for output file to the end of prompts. Since there's no results file anymore, the user can decide after choosing to suppress ordering to save output file.
- Existing Processes 4 and 5 have been removed since the results files no longer exist (Process 5) and downloading orders is now done with the DDS API and not the EODMS RAPI (Process 4).
- New Process 4 to download restored items. 
    - Some items returned from the DDS will have the status `ItemsRestoring` which can take 12 hours or longer to restore. If items grabbed using other Processes has this status, the item will be added to a ItemsRestored.csv file in the "results" folder.
    - The user would run Process 4 with the ItemsRestored.csv file to download the restored images at a later time.

## 3.6.3 (2025-03-04)

- Enabled configuration parameter RAPI.order_check_date found in the configuration file.

## 3.6.2 (2024-11-01)

- Changed schema location to the EODMS website (https://eodms-sgdot.nrcan-rncan.gc.ca/schemas/st/sar-toolbox-schema.json).
- Moved constants dictionary to JSON schema.
- Fixed extracting Record Ids from a JSON request file.

## 3.6.1 (2024-10-28)

- Added Order Key input entry for SAR Toolbox ordering ([Process 6](https://github.com/eodms-sgdot/eodms-cli/wiki/Process-6)).

## 3.6.0 (2024-10-22)

- Fixed issues [#54](https://github.com/eodms-sgdot/eodms-cli/issues/54) and [#52](https://github.com/eodms-sgdot/eodms-cli/issues/52).
- Added SAR Toolbox ordering and downloading (for instructions, see [Process 6 - Order and Download a SAR Toolbox Request](https://github.com/eodms-sgdot/eodms-cli/wiki/Process-6)).

## 3.5.0 (2024-02-28)

- Added a hit count check to determine the number of results for a search.
- Fixed case-insensitive for filters (issue [#50](https://github.com/eodms-sgdot/eodms-cli/issues/50)).
- Added restriction for a maximum of 1500 image results for a single search request (issue [#49](https://github.com/eodms-sgdot/eodms-cli/issues/49)).
- Removed hardcoded open_data=true for NAPL images (issue [#48](https://github.com/eodms-sgdot/eodms-cli/issues/48)).

## 3.4.2 (2023-11-29)

- Fixed issue [#44](https://github.com/eodms-sgdot/eodms-cli/issues/44)

## 3.4.1 (2023-11-14)

- Added option for the output geospatial file to be a folder as well as a file.

## 3.4.0 (2023-11-01)

- Fixed Maximum Cloud Cover field ([Issue #38](https://github.com/eodms-sgdot/eodms-cli/issues/38))
- Added colours to prompts and outputs
- Added exit_cli function in order to facilitate logging out of EODMS account (requires py-eodms-rapi v1.5.7 or higher)
- Raised the minimum required py-eodms-rapi from 1.4.5 to 1.5.0
- Fixed issue with case sensitive choices for filters ([Issue #41](https://github.com/eodms-sgdot/eodms-cli/issues/41))

## 3.3.0 (2023-06-08)
- Fixed error which occurs when using a WKT as an input AOI ([Issue #36](https://github.com/eodms-sgdot/eodms-cli/issues/36))
- Modified description for the "filters" prompt and added an example

## 3.2.2 (2023-02-15)

- Added AWS COGs download option for Process 2 when using a CSV file from the EODMS

## 3.2.1 (2022-11-07)

- Fixed issue when using EODMS UI CSV results file with ALOS-2 collections
- Added 'maximum' number of images to search for after setting 'no_order' to True
- Fixed and updated testing scripts
- Added 'packaging' to requirements.txt

## 3.2.0 (2022-10-17)

- Modified EODMS UI field mappings since they are now mapped in py-eodms-rapi
- Added checks for specific collections which cannot be ordered/downloaded
- Added new parameter to config file which can limit the number of times the script checks for orders that are AVAILABLE_FOR_DOWNLOAD (new parameter: download_attempts, default is blank meaning no limit)
- Extended --configure options to allow for a single edit of a parameter in one command (ex: python eodms_cli.py --configure RAPI.download_attempts=10)

## 3.1.0 (2022-09-06)

- Moved configuration 'gets' to separate methods in eodms_cli.py
- Added error check for 64base conversion of password
- Removed CSV field option when running Process #2 and now automatically determines EODMS UI CSV results
- For Process 4, added maximum number of downloads and the ability to list specific Order Ids and Order Item Ids

## 3.0.2 (2022-06-21)

- Fixed percentage overlap issue

## 3.0.1 (2022-06-16)

- Updated 'configure' option to choose a specific section in config.ini
- Added check for latest version of py-eodms-rapi
- Added a message when the BRB page is returned from the EODMS RAPI

## 3.0.0 (2022-05-19)

- Changes to scripts and folder structure
    - main script renamed eodms-cli.py
    - renamed utils folder to scripts
    - renamed eod.py to utils.py
    - changed class EodmsOrderDownload to EodmsUtils
    - moved process methods to new class EodmsProcess
    - moved config.ini to /~/.eodms
- Removed 'search_only' from process list as there is now a flag (--no_order|-nord) to suppress ordering and downloading
- Added "downloads" parameter to command-line which will override the downloads folder location in the configuration file
- Added a "--configure" flag to script to provide an easy way to the edit the config.ini
- Renamed "download_only" process to "download_results" to reflect that the process downloads previous results using the CSV produced by the eodms-cli

## 2.5.2 (2022-05-10)

- Added 'orderId' for existing orders when saving to results CSV for use in 'download_only' process
- For 'silent' mode, 'download_only' process will now submit orders automatically if none exist
- Fixed issue [#17](https://github.com/eodms-sgdot/eodms-cli/issues/17)

## 2.5.1 (2022-04-27)

- Updated methods to reflect changes of py-eodms-rapi to version 1.4.0

## 2.5.0 (2022-04-19)

- Added new parameter "overlap" which will filter out results with overlaps less than the specified percentage
- Python package "shapely" is now required for the eodms-rapi-orderdownload script. Run "pip install -r requirements.txt" from the script folder
- Added the new max_downloads parameter when downloading images
- Fixed issue [#14](https://github.com/eodms-sgdot/eodms-cli/issues/14)
- Remove date range (for now) when getting a list of orders

## 2.4.0 (2022-03-14)

- Added a date range for query orders to config file
- Rearranged config file into new headings
- Changed full name of '--input' for the command-line to '--input_val' due to issue with Python's reserved names.

## 2.3.2 (2022-01-27)

- Modified script to remove duplicate images from search results

## 2.3.1 (2022-01-10)

- Fixed the following error:

```python
Traceback (most recent call last):
  File "eodms-rapi-orderdownload-main\eodms_orderdownload.py", line 1320, in cli
    prmpt.prompt()
  File "eodms-rapi-orderdownload-main\eodms_orderdownload.py", line 887, in prompt
    answer = input("\n->> Would you like to store the credentials "
TypeError: 'str' object is not callable
```

- Added new parameter "no_order" to command-line

## 2.3.0 (2021-12-22)

- Changed command-line syntax to allow for flags with multiple characters. Parameters that have changed (all backwards compatible):
    - Process: flag is now -prc
    - Maximums: flag is now -max
    - Priority Level: flag is now -pri
- New parameter added to specify which columns in a EODMS UI CSV file will be used to get images from the RAPI.

## 2.2.1 (2021-11-24)

- Modified import of EODMS UI CSV to support other fields like Image ID and Dataset ID.

## v2.2.0 (2021-11-22)

- Changed AOI filter to optional instead of required.
- Changed order of prompting to ask for Collection before AOI.
- Created new classes for field mapping.

## 2.1.3 (2021-10-28)

- Added a check to see if the input is a file

## 2.1.2 (2021-10-15)

- Fixed ogr and GetDriverByName issue by reversing import to include "import osgeo.ogr" first.

## 2.1.1 (2021-09-21)

- Changed the values keep_downloads and keep_results in the config file to empty so the user has to enter the amount they want.

## 2.1.0 (2021-09-09)

- The output parameter now allows the file type ('geojson', 'kml', 'gml' or 'shp') which will save a file to the location of the AOI file.
- Add 'keep_results' and 'keep_downloads' parameters to config.ini to specify the minimum date to keep existing results and downloaded files.

## 2.0.1 (2021-09-08)

- Fixed issue [#8](https://github.com/eodms-sgdot/eodms-cli/issues/8)

## 2.0.0 (2021-09-07)

- script and batch file renamed to eodms_orderdownload ("-" substituted with "_")
- script uses the new EODMS RAPI Python package (py-eodms-rapi) to access the RAPI
- 2 new input parameters:
    - priority level for ordering (-o or --output)
    - output geospatial file (-l or --priority)
- flag for the process (what used to be called "option") is now -r or --process
- added ability to print the available options for filters (see Filters)