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

import os
# import sys
from geomet import wkt
# from xml.etree import ElementTree
import json
import logging
import shapely.wkt
import numpy as np
from shapely.geometry import MultiPolygon
import shapely
import math

from eodms_rapi import EODMSGeo

try:
    import osgeo.ogr as ogr
    import osgeo.osr as osr

    GDAL_INCLUDED = True
except ImportError:
    # print("error with gdal import")
    try:
        import ogr
        import osr

        GDAL_INCLUDED = True
    except ImportError:
        # print("error with osgeo gdal import")
        GDAL_INCLUDED = False


class Geo:
    """
    The Geo class contains all the methods and functions used to perform
        geographic processes mainly using OGR.
    """

    def __init__(self, eod=None, aoi_fn=None):
        """
        Initializer for the Geo object.
        
        :param aoi_fn: The AOI filename.
        :type  aoi_fn: str
        """

        self.aoi_fn = aoi_fn
        self.eod = eod

        self.logger = logging.getLogger('EODMSRAPI')

    def _check_ogr(self):

        # There is another ogr Python package that might have been imported
        #   Check if its the wrong ogr
        if ogr.__doc__ is not None and \
                ogr.__doc__.find("Module providing one api for multiple git "
                                 "services") > -1:
            self.eod.print_msg("Another package named 'ogr' is installed.", 
                               heading='warning')
            return False

        return True

    def _close_wkt_polygon(self, in_wkt):

        gjson = wkt.loads(in_wkt)
        nc = np.array(gjson['coordinates'])
        coords = np.append(nc, [[nc[0][0]]], axis=1)
        gjson['coordinates'] = coords.tolist()

        return wkt.dumps(gjson)

    def get_centroid(self, in_feat):
        geom = shapely.from_geojson(in_feat)
        return geom.centroid

    def convert_image_geom(self, coords, output='array'):
        """
        Converts a list of coordinates from the RAPI to a polygon geometry, 
            array of points or as WKT.
        
        :param coords: A list of coordinates from the RAPI results.
        :type  coords: list
        :param output: The type of return, can be 'array', 'wkt' or 'geom'.
        :type  output: str
        
        :return: Either a polygon geometry, WKT or array of points.
        :rtype: multiple types
        """

        # Get the points from the coordinates list
        pnt1 = coords[0][0]
        pnt2 = coords[0][1]
        pnt3 = coords[0][2]
        pnt4 = coords[0][3]

        pnt_array = [pnt1, pnt2, pnt3, pnt4]

        if GDAL_INCLUDED and self._check_ogr():

            # Create ring
            ring = ogr.Geometry(ogr.wkbLinearRing)
            ring.AddPoint(pnt1[0], pnt1[1])
            ring.AddPoint(pnt2[0], pnt2[1])
            ring.AddPoint(pnt3[0], pnt3[1])
            ring.AddPoint(pnt4[0], pnt4[1])
            ring.AddPoint(pnt1[0], pnt1[1])

            # Create polygon
            poly = ogr.Geometry(ogr.wkbPolygon)
            poly.AddGeometry(ring)

            # Send specified output
            if output == 'wkt':
                return poly.ExportToWkt()
            elif output == 'geom':
                return poly
            else:
                return pnt_array

        else:
            if output == 'wkt':
                # Convert values in point array to strings
                pnt_array = [[str(p[0]), str(p[1])] for p in pnt_array]

                coords_str = ', '.join([' '.join(pnt) for pnt in pnt_array])
                return f"POLYGON (({coords_str}))"
            else:
                return pnt_array

    # def convert_from_wkt(self, in_feat):
    #     """
    #     Converts a WKT to a polygon geometry.
    #
    #     :param in_feat: The WKT of the polygon.
    #     :type  in_feat: str
    #
    #     :return: The polygon geometry of the input WKT.
    #     :rtype: ogr.Geometry
    #     """
    #
    #     out_poly = None
    #     if GDAL_INCLUDED and self._check_ogr():
    #         out_poly = ogr.CreateGeometryFromWkt(in_feat)
    #
    #     return out_poly

    def export_results(self, img_lst, out_fn='results.geojson'):
        # sourcery skip: extract-method, low-code-quality, merge-comparisons
        """
        Exports the results of the query to a GeoJSON.
        
        :param img_lst: An ImageList of images.
        :type  img_lst: ImageList
        :param out_fn: The output geospatial filename.
        :type  out_fn: str
        """

        fn = self.eod.fn_str

        if out_fn is None or out_fn == '':
            return None

        if out_fn.lower() in ['geojson', 'kml', 'gml', 'shp']:
            out_fn = f'{fn}_outlines.{out_fn.lower()}'

        if os.path.isdir(out_fn):
            out_fn = os.path.join(os.sep, out_fn, f"{fn}_outlines.geojson")

        # If the output GeoJSON exists, remove it
        if os.path.exists(out_fn):
            os.remove(out_fn)

        ext = os.path.splitext(out_fn)[1]
        lyr_name = os.path.basename(out_fn).replace(ext, '')

        if GDAL_INCLUDED and self._check_ogr():

            if ext == '.gml':
                ogr_driver = 'GML'
            elif ext == '.kml':
                ogr_driver = 'KML'
            elif ext in ['.json', '.geojson']:
                ogr_driver = 'GeoJSON'
            elif ext == '.shp':
                ogr_driver = 'ESRI Shapefile'
            else:
                warn_msg = "The format type for the output geospatial file " \
                                   "could not be determined. No geospatial " \
                                   "output will be created."
                self.eod.print_msg(warn_msg, heading='warning')
                return None

            # Create the output Driver
            driver = ogr.GetDriverByName(ogr_driver)

            # Create the output
            # create the spatial reference, WGS84
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(4326)
            ds = driver.CreateDataSource(out_fn)
            lyr = ds.CreateLayer(lyr_name, srs, ogr.wkbPolygon)

            # Get the output Layer's Feature Definition
            feature_defn = lyr.GetLayerDefn()

            fields = img_lst.get_fields()
            for f in fields:
                field_name = ogr.FieldDefn(f, ogr.OFTString)
                field_name.SetWidth(256)
                lyr.CreateField(field_name)

            for r in img_lst.get_images():
                # record_id = r.get_record_id()
                poly = r.get_geometry('geom')

                # Create a new feature
                feat = ogr.Feature(feature_defn)

                # Add field values
                for f in fields:
                    feat.SetField(f, str(r.get_metadata(f)))

                if ext == '.kml':
                    self.reverse_coords(poly)

                # Set new geometry
                feat.SetGeometry(poly)

                # Add new feature to output Layer
                lyr.CreateFeature(feat)

            # Dereference the feature
            feat = None

            # Save and close DataSources
            ds = None

        else:

            if ext == '.gml' or ext == '.kml' or ext == '.shp':
                ext_str = ext.replace('.', '').upper()
                warn_msg = f"GDAL Python package is not installed. " \
                            f"Cannot export geospatial results in " \
                            f"'{ext_str}' format. Exporting results as a " \
                            f"GeoJSON."

                # print(f"\n{warn_msg}")
                self.eod.print_msg(warn_msg, heading='warning')
                self.logger.warning(warn_msg)

                out_fn = out_fn.replace(ext, '.geojson')

            feats = []
            imgs = img_lst.get_images()
            for i in imgs:
                mdata = i.get_metadata()
                f_dict = {"type": "Feature",
                          "properties": mdata,
                          "geometry": mdata['geometry']}
                feats.append(f_dict)

            json_out = {"type": "FeatureCollection",
                        "name": lyr_name,
                        "features": feats}

            with open(out_fn, 'w') as f:
                json.dump(json_out, f)

    def get_overlap(self, img, aoi):
        
        rapi_geo = EODMSGeo(self.eod.eodms_rapi)

        img_wkt = self._close_wkt_polygon(img.get_geometry('wkt'))
        aoi_wkts = [aoi] if self.is_wkt(aoi) else rapi_geo.convert_to_wkt(aoi, 
                    'file')

        img_geom = shapely.wkt.loads(img_wkt)
        if aoi_wkts[0].find('MULTIPOLYGON') > -1:
            aoi_polys = shapely.wkt.loads(aoi_wkts[0])
        else:
            aoi_polys = MultiPolygon(map(shapely.wkt.loads, aoi_wkts))
        
        img_area = img_geom.area
        aoi_area = aoi_polys.area
        overlap_area = img_geom.intersection(aoi_polys).area
        overlap_aoi = (overlap_area / aoi_area) * 100
        overlap_img = (overlap_area / img_area) * 100

        return overlap_aoi, overlap_img

    def is_wkt(self, in_feat):
        """
        Checks if a string is a valid WKT
        
        :param in_feat: Input string containing a WKT.
        :type  in_feat: str
        
        :return: If the input is a valid WKT, return WKT if return_wkt is
                True or return just True; False if not valid.
        :rtype: str or boolean
        """

        try:
            wkt.loads(in_feat.upper())
        except (ValueError, TypeError):
            return False

        return True

    def reverse_coords(self, geom):
        """
        Reverses the lat, long coordinates of a polygon.
        
        :param geom: The polygon to reverse.
        :type  geom: ogr.Geometry
        """

        # Reverse x and y of transformed geometry
        ring = geom.GetGeometryRef(0)
        for i in range(ring.GetPointCount()):
            ring.SetPoint(i, ring.GetY(i), ring.GetX(i))

    def metres_to_degrees(self, metres, lat):
        deg = float(metres) / (111.32 * 1000 * math.cos(lat * (math.pi / 180)))
        return deg

    def degrees_to_metres(self, deg, lat):
        metres = float(deg) * (111.32 * 1000 * math.cos(lat * (math.pi / 180)))
        return metres