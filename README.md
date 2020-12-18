Search, Order and Download Imagery - eodms-orderdownload.py
===========================================================
<!-- TOC -->
- [How It Works](#how-it-works)
  - [Options](#options)
  - [Input File](#input-file)
  - [Other Parameters](#other-parameters)
  - [Query](#query)
  - [Order](#order)
  - [Download](#download)
- [Usage](#usage)
  - [Option 1 - Search, order and download Images using AOI](#option-1---search-order-and-download-images-using-aoi)
  - [Option 2 - Order & download images using EODMS UI search results](#option-2---order--download-images-using-eodms-ui-search-results)
  - [Option 3 - Download existing orders using AOI file and RAPI query](#option-3---download-existing-orders-using-aoi-file-and-rapi-query)
  - [Option 4 - Download existing orders using a CSV file from a previous order/download process](#option-4---download-existing-orders-using-a-csv-file-from-a-previous-orderdownload-process)
- [Parameters](#parameters)
  - [Syntax Examples](#syntax-examples)
- [Help Example](#help-example)
- [config.ini File](#configini-file)
- [Contact](#contact)

<!-- End of TOC -->

## How It Works

The **eodms-orderdownload.py** script is used to search, order and download imagery from the EODMS using the REST API (RAPI) service.

### Requirements

The eodms-orderdownload.py was designed using **Python 3.7** so it's best to have this version or higher installed.

The **GDAL Python Package** is required if you would like to use shapefiles for AOIs.

### Options

The script has 4 options for ordering and downloading images:

1. Search, order & download images using an AOI
	
	- This option runs the full process using an AOI: querying the RAPI, ordering and downloading images.
	
2. Order & download images using EODMS UI search results (CSV file)
	
	- This option is used for ordering and downloading images already determined using the [EODMS UI](https://www.eodms-sgdot.nrcan-rncan.gc.ca/index_en.jsp).
	
3. Download existing orders using AOI file and RAPI query

	- This option uses an AOI to search for image records, uses existing orders and downloads the images.
	
4. Download existing orders using a CSV file from a previous order/download process (files found under "results" folder)
	
	- This option allows the user to re-download an existing set of images from a previous session (all session results are save in the "results" folder as CSV files).

### Input File

The script accepts either an **AOI with a polygon** (Shapefile, GeoJSON, GML or KML) (options 1 & 3), a **CSV file** containing results **exported from the [EODMS UI](https://www.eodms-sgdot.nrcan-rncan.gc.ca/index_en.jsp)** (option 2) or a **CSV file** from a **previous session** (option 4).

### Other Parameters

The script contains other parameters which help to limit the scope of a search (only when using an AOI):

1. You must provide at least 1 **collection**. However, you also have the choice to search multiple collections.
2. You can specify a **date range** to narrow your search by a given time.
3. You can also specify the **maximum number of images** you'd like to order/download as well as the **maximum number of order items per order**.

### Query

All image queries use the RAPI search service at https://www.eodms-sgdot.nrcan-rncan.gc.ca/wes/rapi/search (see [EODMS APIs - REST Search](https://wiki.gccollab.ca/EODMS_APIs#REST_Search) for more info).

If an **AOI file** is provided, the script will query the RAPI for any images, within a given collection or collections, which intersect the AOI.

If a **EODMS CSV file** is used, the script will extract the entries from the file and query the RAPI for the proper image information.

### Order

Once the RAPI returns search results, the script submits these images to the RAPI order service at https://www.eodms-sgdot.nrcan-rncan.gc.ca/wes/rapi/order (see [EODMS APIs - REST Order](https://wiki.gccollab.ca/EODMS_APIs#REST_Order) for more info).

If a **maximum number of images** was set, only the first set of images up to that number will be ordered. If no limit was set, all images from the search result will be ordered.

If a **maximum number of order items per order** was specified, then each order will contain order items (images) up to this maximum. If no maximum was set, each order will contain 100 order items (this value is set by the EODMS).

### Download

Next, the script will download all the images as they become available for download.

The script continually checks the RAPI every so often for the status of the order items. The more order items you have in your cart, the longer each check will take.

Also, the items can take a while to become available so please be patient and let the script run until it has finished downloading the items. Once done, the script will either let you know the location of the images on your computer or it will let you know if and why the image downloads failed.

## Usage

### Option 1 - Search, order and download Images using AOI

1. Start the process by dragging-and-dropping an AOI (shapefile, GML, KML or GeoJSON) onto the **eodms-orderdownload.bat** batch file.

	- You can also run the batch file without the drag-and-drop, however you will be prompted for the input file (AOI file) after entering the date range (after Step 5).
	- If you would like to use a shapefile, install the **GDAL Python package** before running the script.

2. Enter your username and password when prompted.
	
	- You will be asked if you wish to store the username and password for a future session. If you choose yes, you will not be prompted for credentials in any future sessions. All credentials are stored in the "[config.ini file](#config-username)" (the password is encrypted). If you wish to replace the default username and password, remove the values from the [config file](#config-username), leaving the keys with equal signs, and the script will prompt you again.

3. When prompted ```What would you like to do?```, enter ```1``` (or press enter as ```1``` is the default).

4. Enter the number corresponding to the collections you'd like to query, separating each with a comma.

5. Enter the date range separated with a dash. If you want to search all years, leave blank.
	
	- The entry can have multiple ranges separated by a comma (ex: ```20200601-20200701,20201013-20201113```).
	- Date format is ```YYYYMMDD```.

6. Enter the total number of images you'd like to order/download (leave blank if you wish for no limit).

7. Enter the total number of images you'd like for each order (leave blank for the maximum which is set to 100 by the EODMS).

8. Once the image results are ready, the number of results will be shown and you'll be asked if you'll like to continue.
	
	- This is due to the possible large number of images returned in the results.
	- If you chose to enter a total number of images in Step 6, this question will not be asked and ordering will commence.

9. Next, the orders will be submitted to the RAPI.

10. The script will continue to run until the images are ready for downloading (or if they fail) or until you press Crtl-C.

11. Once the images are ready for download, they will be downloaded to the "downloads" folder in a folder with the date and time the script was started (ex: "20201215_165428").
	
	- A different "downloads" folder can be set in the "[config.ini" file](#config-downloads).
	
12. When the script has finished all downloads, you can find a CSV file containing the information for the downloaded images. This CSV file can be used to download the images again (option 4).

### Option 2 - Order & download images using EODMS UI search results

1. Before running the script: 
	- Go to the [EODMS UI](https://www.eodms-sgdot.nrcan-rncan.gc.ca/index_en.jsp)
	- Search for the images you'd like to order
	- [Save the search results into a CSV file](https://wiki.gccollab.ca/EODMS_How-To_Guide#Is_it_possible_to_export_the_results_including_geometry_.28i.e._spatial_info.29).

2. Drag-and-drop the CSV file created in the previous step onto the **eodms-orderdownload.bat**.

	- You can also run the batch file without the drag-and-drop, however you will be prompted for an input file (the CSV file) after entering your choice of the process (after step 4).

3. Enter your username and password when prompted.
	
	- You will be asked if you wish to store the username and password for a future session. If you choose yes, you will not be prompted for credentials in any future sessions. All credentials are stored in the "[config.ini file](#config-username)" (the password is encrypted). If you wish to replace the default username and password, remove the values from the [config file](#config-username), leaving the keys with equal signs, and the script will prompt you again.

4. When prompted ```What would you like to do?```, enter ```2```.

5. You will not be prompted for any other parameters as they are already provided in the CSV file.

	- The script will query the RAPI to get the proper image records based on the CSV file.

6. The remaining steps are the same as steps 8-12 in [Option 1](#option-1---search-order-and-download-images-using-aoi).

### Option 3 - Download existing orders using AOI file and RAPI query

1. Start the process by dragging-and-dropping an AOI (shapefile, GML, KML or GeoJSON) onto the **eodms-orderdownload.bat** batch file.

	- You can also run the batch file without the drag-and-drop, however you will be prompted for the input file (AOI file) after entering the date range (after Step 5).
	- If you would like to use a shapefile, install the **GDAL Python package** before running the script.
	
2. Enter your username and password when prompted.

3. When prompted ```What would you like to do?```, enter ```3```.
	
	- You will be asked if you wish to store the username and password for a future session. If you choose yes, you will not be prompted for credentials in any future sessions. All credentials are stored in the "[config.ini file](#config-username)" (the password is encrypted). If you wish to replace the default username and password, remove the values from the [config file](#config-username), leaving the keys with equal signs, and the script will prompt you again.

4. Enter the number corresponding to the collections you'd like to query, separating each with a comma.

5. Enter the date range separated with a dash. If you want to search all years, leave blank.
	
	- The entry can have multiple ranges separated by a comma (ex: ```20200601-20200701,20201013-20201113```).
	- The date range can also include a time, separated by a T (ex: ```20200701T153455-20200801T000545```). Make sure the time is in UTC.
	- Date format is ```yyyymmdd``` or ```yyyymmddThhmmss```.
	
6. Enter the total number of images you'd like to order/download (leave blank if you wish for no limit).

7. Enter the total number of images you'd like for each order (leave blank for the maximum which is set to 100 by the EODMS).

8. The process will query the RAPI for the image information, get the order information for the current user and download any existing image items in the orders.

### Option 4 - Download existing orders using a CSV file from a previous order/download process

1. Start the process by dragging-and-dropping a CSV results file from a previous session of this script onto the **eodms-orderdownload.bat** batch file.

	- You can also run the batch file without the drag-and-drop, however you will be prompted for the input file (CSV file) after entering your choice of the process (after Step 3).

2. Enter your username and password when prompted.

3. When prompted ```What would you like to do?```, enter ```4```.
	
	- You will be asked if you wish to store the username and password for a future session. If you choose yes, you will not be prompted for credentials in any future sessions. All credentials are stored in the "[config.ini file](#config-username)" (the password is encrypted). If you wish to replace the default username and password, remove the values from the [config file](#config-username), leaving the keys with equal signs, and the script will prompt you again.

4. The script will download any images with a "downloaded" column value of "False" in the CSV file. However, the script will ask you if you want to re-download images that have already been downloaded (i.e. "downloaded" set to "True").

## Parameters

The script can be run on its own or with a batch file containing specific parameters. Any parameters you do not specify will be prompted during the script.

Here is a list of parameters for the script:

<table style="width: 95%">
	<tr>
		<td style="text-align: center;">
			<b>Parameter</b>
		</td>
		<td style="text-align: center;">
			<b>Tags</b>
		</td>
		<td style="text-align: center;">
			<b>Description</b>
		</td>
	</tr>
	<tr id="username">
		<td>
			Username
		</td>
		<td>
			<pre>-u --username</pre>
		</td>
		<td>
			The username of the EODMS account used for authentication.<br>
			- Using this parameter will bypass the "username" value in the [config.ini file](#config-username).
		</td>
	</tr>
	<tr id="password">
		<td>
			Password
		</td>
		<td>
			<pre>-p --password</pre>
		</td>
		<td>
			The password of the EODMS account used for authentication.<br>
			- Using this parameter will bypass the "password" value in the [config.ini file](#config-password). 
		</td>
	</tr>
	<tr>
		<td>
			Collections
		</td>
		<td>
			<pre>-c --collections</pre>
		</td>
		<td>
			The collection of the images being ordered.<br>
			- Separate multiple collections with a comma.<br>
			- Use either the collection title, ID or part of the ID <br>
			&nbsp;&nbsp;Examples for RCM: <br>
			&nbsp;&nbsp;Collection Name: <code>"RCM Image Products"</code>, <br>
			&nbsp;&nbsp;Collection ID: <code>RCMImageProducts</code> or<br>
			&nbsp;&nbsp;Part of ID:<code>RCM</code> (make sure you use a part of the ID that is unique to the collection)<br>
			- If you use the collection title, surround the title with double-quotes (ex: <code>"RCM Image Products","RADARSAT-1 Open Data Products"</code>)<br>
			- For a list of available collections for your account, go to <a href="https://www.eodms-sgdot.nrcan-rncan.gc.ca/wes/rapi/collections">https://www.eodms-sgdot.nrcan-rncan.gc.ca/wes/rapi/collections</a>.
		</td>
	</tr>
	<tr>
		<td>
			Date Range
		</td>
		<td>
			<pre>-d --dates</pre>
		</td>
		<td>
			The date range for the search in format YYYYMMDD and separated by a dash (ex: <code>20201019-20201119</code>).
		</td>
	</tr>
	<tr>
		<td>
			Input
		</td>
		<td>
			<pre>-i --input</pre>
		</td>
		<td>
			An input file, can either be an AOI (shapefile, KML, or GeoJSON) or a CSV file exported from the EODMS UI.
		</td>
	</tr>
	<tr>
		<td>
			Maximum
		</td>
		<td>
			<pre>-m --maximum</pre>
		</td>
		<td>
			The maxmimum number of images to order and download and the maximum number of images per order, separated by a colon (\<total_orders\>:\<total_images_per_order\>).<br><br>Example:<br>If this parameter is set to <code>20:10</code>, the total number of images that will be ordered overall is 20. These 20 images will be divided into 2 orders containing 10 items each.<br>If this parameter is set to <code>150</code>, only 150 images will be ordered. The maximum number of items per order will be 100 as this is maximum set by the EODMS (so 2 orders will be submitted).
		</td>
	</tr>
	<tr>
		<td>
			Option
		</td>
		<td>
			<pre>-o --option</pre>
		</td>
		<td>
			The type of process to run from this list of options:
			<table style="width: 95%">
				<tr>
					<td style="text-align: center;">
						<b>Option</b>
					</td>
					<td style="text-align: center;">
						<b>Description</b>
					</td>
				</tr>
				<tr>
					<td>
						<pre>full</pre>
					</td>
					<td>
						Option 1 - Search, order & download images using an AOI.
					</td>
				</tr>
				<tr>
					<td>
						<pre>order_csv</pre>
					</td>
					<td>
						Option 2 - Order & download images using EODMS UI search results (CSV file).
					</td>
				</tr>
				<tr>
					<td>
						<pre>download_aoi</pre>
					</td>
					<td>
						Option 3 - Download existing orders using AOI file and RAPI query.
					</td>
				</tr>
				<tr>
					<td>
						<pre>download_only</pre>
					</td>
					<td>
						Option 4 - Download existing orders using a CSV file from a previous order/download process (files found under "results" folder).
					</td>
				</tr>
			</table>
		</td>
	</tr>
	<tr>
		<td>
			Silent
		</td>
		<td>
			<pre>-s --silent</pre>
		</td>
		<td>
			Sets the process to silent which supresses all questions (useful when running a batch file with multiple entries or at scheduled times). When using silent mode, make sure to include your credentials in the command-line statement or the script will crash.
		</td>
	</tr>
</table>

### Syntax Examples

| Type                                                                        | Description                                              |
|-----------------------------------------------------------------------------|----------------------------------------------------------|
| Order & download images using an AOI (Option 1)                             | ```python eodms-orderdownload.py -i "C:\TEMP\AOI.shp"``` |
| Order & download images using an EODMS search results CSV file (Option 2)   | ```python eodms-orderdownload.py -i "C:\TEMP\Results.csv" -o order_csv``` |
| Order & download RCM images within date range                               | ```python eodms-orderdownload.py -i "C:\TEMP\AOI.shp" -d 20201019-20201119 -c RCM``` |
| Order & download only 2 images from search in silent mode                   | ```python eodms-orderdownload.py -u user -p passwrd -i "C:\TEMP\AOI.shp" -m 2 -s``` |
| Order & download only 5 images with maximum number of images per order at 2 | ```python eodms-orderdownload.py -i "C:\TEMP\AOI.shp" -m 5:2``` |
| Download existing orders for a specific AOI (Option 3)                      | ```python eodms-orderdownload.py -i "C:\TEMP\AOI.shp" -o download_aoi``` |
| Download existing orders using CSV from a previous session in silent mode   | ```python eodms-orderdownload.py -u user -p passwrd -i "C:\eodms-rapi-orderdownload\results\20201214_155904_Results.csv" -o download_only -s``` |

## Help Example

```
usage: eodms-orderdownload.py [-h] [-u USERNAME] [-p PASSWORD]
                              [-c COLLECTIONS] [-d DATES] [-i INPUT]
                              [-m MAXIMUM] [-o OPTION] [-s]

Search & Order EODMS products.

optional arguments:
  -h, --help            show this help message and exit
  -u USERNAME, --username USERNAME
                        The username of the EODMS account used for
                        authentication.
  -p PASSWORD, --password PASSWORD
                        The password of the EODMS account used for
                        authentication.
  -c COLLECTIONS, --collections COLLECTIONS
                        The collection of the images being ordered (separate
                        multiple collections with a comma).
  -d DATES, --dates DATES
                        The date ranges for the search.
  -i INPUT, --input INPUT
                        An input file, can either be an AOI or a CSV file
                        exported from the EODMS UI. Valid AOI formats are
                        GeoJSON, KML or Shapefile (Shapefile requires the GDAL
                        Python package).
  -m MAXIMUM, --maximum MAXIMUM
                        The maximum number of images to order and download and
                        the maximum number of images per order, separated by a
                        colon.
  -o OPTION, --option OPTION
                        The type of process to run from this list of options:
                        full: Search, order & download images using an AOI
                        order_csv: Order & download images using EODMS UI
                        search results (CSV file) download_aoi: Download
                        existing orders using AOI file and RAPI query
                        download_only: Download existing orders using a CSV
                        file from a previous order/download process (files
                        found under "results" folder)
  -s, --silent          Sets process to silent which supresses all questions.
```

## config.ini File

The **config.ini** file is located in the same folder as the eodms-rapi-orderdownload.py script.

The following parameters can be set in the config.ini file:

<table>
	<tr>
		<td style="text-align: center;">
			<b>Parameter</b>
		</td>
		<td style="text-align: center;">
			<b>Description</b>
		</td>
	</tr>
	<tr>
		<td id="config-downloads">
			downloads
		</td>
		<td>
			The folder location where the images will be downloaded.<br>
			The path can be a relative path or absolute. If the path is relative, the folder(s) will be put into the script folder.<br>
			Leave this parameter blank if you want to use the default which is the "downloads" folder under the script folder.
		</td>
	</tr>
	<tr>
		<td>
			results
		</td>
		<td>
			The folder location where the CSV files containing the download results will be placed.<br>
			The path can be a relative path or absolute. If the path is relative, the folder(s) will be put into the script folder.<br>
			Leave this parameter blank if you want to use the default which is the "results" folder under the script folder.
		</td>
	</tr>
	<tr>
		<td>
			timeout_query
		</td>
		<td>
			The total timeout time, in seconds, for queries to the RAPI.
		</td>
	</tr>
	<tr>
		<td>
			timeout_order
		</td>
		<td>
			The total timeout time, in seconds, for orders sent to the RAPI.<br>
			There is a separate timeout option for orders since the time to get orders can take quite a while depending on the number of orders for the user.
		</td>
	</tr>
	<tr id="config-username">
		<td>
			username
		</td>
		<td>
			The username of the EODMS account used to search, order and download. Once entered, this username will always be used if no username is <a href="#username">specified in the command-line</a>.<br>
			If left blank, the script will prompt you for a username if no username is <a href="#username">specified in the command-line</a>. The script will then ask if you want to store the username for later sessions; the username will be saved here.
		</td>
	</tr>
	<tr id="config-password">
		<td>
			password
		</td>
		<td>
			The password of the EODMS account used to search, order and download. Once entered, this password will always be used if no password is <a href="#password">specified in the command-line</a>.<br>
			The password is encrypted using Python so you can only enter the password using the script. <b>DO NOT enter your password manually into this file</b>.
		</td>
	</tr>
	<tr>
		<td>
			access_attempts
		</td>
		<td>
			The number of times the script will attempt to send a query to the RAPI before the script exits.</b>.
		</td>
	</tr>
</table>

## Contact

If you have any questions or require support, please contact the EODMS Support Team at nrcan.eodms-sgdot.rncan@canada.ca.