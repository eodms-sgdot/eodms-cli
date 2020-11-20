# Search, Order and Download Imagery - eodms-orderdownload.py

The **eodms-orderdownload.py** script is used to search, order and download imagery from the EODMS using the REST API (RAPI) service.

## How It Works

### Input File

The script accepts either an **AOI with a polygon** (Shapefile, GeoJSON, GML or KML) or a **CSV file** containing results exported from the [EODMS UI](https://www.eodms-sgdot.nrcan-rncan.gc.ca/index_en.jsp).

### Other Parameters

The script contains other parameters which help to limit the scope of a search (only when using an AOI):

1. You must provide at least 1 **collection**. However, you also have the choice to search multiple collections.
2. You can specify a **date range** to narrow your search by a given time.
3. You can also specify the **maximum number of images** you'd like to order/download as well as the **maximum number of order items per order**.

### Query

All image queries use the RAPI search service at https://www.eodms-sgdot.nrcan-rncan.gc.ca/wes/rapi/search (see [EODMS APIs - REST Search](https://wiki.gccollab.ca/EODMS_APIs#REST_Search) for more info).

If an **AOI file** is provided, the script will query the RAPI for any images, within a given collection or collections, which intersect the AOI.

If a **CSV file** is used, the script will extract the entries from the file and query the RAPI for the proper image information.

### Order

Once the RAPI returns search results, the script submits these images to the RAPI order service at https://www.eodms-sgdot.nrcan-rncan.gc.ca/wes/rapi/order (see [EODMS APIs - REST Order](https://wiki.gccollab.ca/EODMS_APIs#REST_Order) for more info).

If a **maximum number of images** was set, only the first set of images up to that number will be ordered. If no limit was set, all images from the search result will be ordered.

If a **maximum number of order items per order** was specified, then each order will contain order items (images) up to this maximum. If no maximum was set, each order will contain 100 order items (this value is set by the EODMS).

### Download

Next, the script will download all the images as they become available for download.

The script continually checks the RAPI every so often for the status of the order items. The more order items you have in your cart, the longer each check will take.

Also, the items can take a while to become available so please be patient and let the script run until it has finished downloading the items. Once done, the script will either let you know the location of the images on your computer or it will let you know if and why the image downloads failed.

### Order Only/Download Only

The script also provides the option to **only submit orders** or **only download existing orders**. This is useful in case you have existing orders you'd like to download.

The input file is the same, it can either be an AOI or a CSV.

If you are only downloading, make sure you use the same AOI or CSV file you used to order the images. The script will use the file to query the RAPI which will return the same images as before (and possibly extra). The query results will be used to search for existing image items in your orders.  Once found, the script will download them. If there are duplicate orders (i.e. orders containing the same images), the most recent order will be downloaded.

## Usage

### Search, Order and Download Images

1. Start the process by dragging-and-dropping an AOI (shapefile, KML or GeoJSON) onto the **eodms-orderdownload.bat** batch file.

	**NOTE**: You can also run the batch file without the drag-and-drop, however you will be prompted for the input file (AOI file) after entering your username and password (after step 2).

2. Enter your username and password when prompted.

3. Enter the number corresponding to the collections you'd like to query, separating each with a comma.

4. Enter the date range (in format ```yyyymmdd```) separated with a dash (ex: ```20200915-20201109```). If you want to search all years, leave blank.

5. Enter the total number of images you'd like to order/download (leave blank if you wish for no limit).

6. Enter the total number of images you'd like for each order (leave blank for the maximum which is set to 100 by the EODMS).

7. Once the image results are ready, the number of results will be shown and you'll be asked if you'll like to continue (this is due to the possible large number of images returned in the results).

8. Next, the orders will be submitted to the RAPI.

9. The script will continue to run until the images are ready for downloading (or if they fail) or until you press Crtl-C.

10. Once the images are ready for download, they will be downloaded to an order folder in the "downloads" folder.

11. When the script has finished all downloads, you can find CSV files containing all the results from your query, orders and downloads in the "info" folder. There is also a GeoJSON file containing the extents of your query from step 7.

### Order and Download EODMS CSV

1. Before running the script, use the [EODMS UI](https://www.eodms-sgdot.nrcan-rncan.gc.ca/index_en.jsp), search for the images you'd like to order and [save the search results into a CSV file](https://wiki.gccollab.ca/EODMS_How-To_Guide#Is_it_possible_to_export_the_results_including_geometry_.28i.e._spatial_info.29).

2. Drag-and-drop the CSV file created in the previous step onto the **eodms-orderdownload.bat**.

	**NOTE**: You can also run the batch file without the drag-and-drop, however you will be prompted for an input file (the CSV file) after entering your username and password (after step 2).

3. Enter your username and password when prompted.

4. You will not be prompted for any other parameters as they are already provided in the CSV file.

5. The script will query the RAPI to get the proper image records based on the CSV file.

6. The remaining steps are the same as steps 8-11 in [Search, Order and Download Images](#search-order-and-download-images).

### Order Only

As mentioned [above](#order-onlydownload-only), there is an option to only order images if you wish to download your orders at a later date.

In the batch file, add the flag ```-o``` to apply this option.

The steps are the same as [Search, Order and Download Images](#search-order-and-download-images) except omit steps 9-11.

### Download Only

There is also an option to download images from an existing order (or orders). 

In the batch file, add the flag ```-l``` to use this option.

The steps are the same as [Search, Order and Download Images](#search-order-and-download-images) except omit step 8.

## Parameters

The script can be run on its own or with a batch file containing specific parameters. Any parameters you do not specify will be prompted during the script.

Here is a list of parameters for the script:

| Parameter     | Tags                        | Description                                                                                                                                                                                             | 
|---------------|-----------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Username      | <pre>-u --username</pre>    | The username of the EODMS account used for authentication.                                                                                                                                              |
| Password      | <pre>-p --password</pre>    | The password of the EODMS account used for authentication.                                                                                                                                              |
| Collections   | <pre>-c --collections</pre> | The collection of the images being ordered.<br>- Separate multiple collections with a comma.<br>- Use either the collection title, ID or part of the ID <br>&nbsp;&nbsp;Examples for RCM: <br>&nbsp;&nbsp;Collection Name: ```"RCM Image Products"```, <br>&nbsp;&nbsp;Collection ID: ```RCMImageProducts``` or<br>&nbsp;&nbsp;Part of ID:```RCM``` (make sure you use a part of the ID that is unique to the collection)<br>- If you use the collection title, surround the title with double-quotes (ex: ```"RCM Image Products","RADARSAT-1 Open Data Products"```) |
| Date Range    | <pre>-d --dates</pre>       | The date range for the search in format YYYYMMDD and separated by a dash (ex: ```20201019-20201119```). |
| Input         | <pre>-i --input</pre>       | An input file, can either be an AOI (shapefile, KML, or GeoJSON) or a CSV file exported from the EODMS UI. |
| Maximum       | <pre>-m --maximum</pre>     | The maxmimum number of images to order and download and the maximum number of images per order, separated by a colon (\<total_orders\>:\<total_images_per_order\>).<br><br>Example:<br>If this parameter is set to <code>20:10</code>, the total number of images that will be ordered overall is 20. These 20 images will be divided into 2 orders containing 10 items each.<br>If this parameter is set to <code>150</code>, only 150 images will be ordered. The maximum number of items per order will be 100 as this is maximum set by the EODMS (so 2 orders will be submitted). |
| Order Only    | <pre>-o --order</pre>       | If set, only a query and ordering will be performed, no downloading will occur. |
| Download Only | <pre>-l --download</pre>    | If set, only a query and downloading will be performed, no ordering will occur. |

### Syntax Examples

| Type                                 | Description                                              |
|--------------------------------------|----------------------------------------------------------|
| Order & download images using an AOI | ```python eodms-orderdownload.py -i "C:\TEMP\AOI.shp"``` |
| Order & download images using an EODMS search results CSV file | ```python eodms-orderdownload.py -i "C:\TEMP\Results.csv"``` |
| Order & download RCM images within date range | ```python eodms-orderdownload.py -i "C:\TEMP\AOI.shp" -d 20201019-20201119 -c RCM``` |
| Order & download only 2 images from search | ```python eodms-orderdownload.py -i "C:\TEMP\AOI.shp" -m 2``` |
| Order & download only 5 images with maximum number of images per order at 2 | ```python eodms-orderdownload.py -i "C:\TEMP\AOI.shp" -m 5:2``` |
| Order & download images with maximum number of images per order at 4 | ```python eodms-orderdownload.py -i "C:\TEMP\AOI.shp" -m :4``` |
| Order but don't download images for a specific AOI | ```python eodms-orderdownload.py -i "C:\TEMP\AOI.shp" -o``` |
| Download existing orders for a specific AOI | ```python eodms-orderdownload.py -i "C:\TEMP\AOI.shp" -l``` |

## Help Example

```
usage: eodms-orderdownload.py [-h] [-u USERNAME] [-p PASSWORD] [-c COLLECTIONS]
                           [-d DATES] [-i INPUT] [-m MAXIMUM] [-o] [-l]

Search, Order and Download EODMS products.

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
                        The date range for the search.
  -i INPUT, --input INPUT
                        An input file, can either be an AOI (shapefile, KML or
                        GeoJSON) or a CSV file exported from the EODMS UI.
  -m MAXIMUM, --maximum MAXIMUM
                        The maximum number of images to order and download and
                        the maximum number of images per order, separated by a
                        colon.
  -o, --order           If set, only query and order images, do not download.
  -l, --download        If set, only query and download images, do not order.
```
