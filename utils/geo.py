##############################################################################
# MIT License
# 
# Copyright (c) 2020 Her Majesty the Queen in Right of Canada, as 
# represented by the President of the Treasury Board
# 
# Permission is hereby granted, free of charge, to any person obtaining a 
# copy of this software and associated documentation files (the "Software"), 
# to deal in the Software without restriction, including without limitation 
# the rights to use, copy, modify, merge, publish, distribute, sublicense, 
# and/or sell copies of the Software, and to permit persons to whom the 
# Software is furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in 
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING 
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER 
# DEALINGS IN THE SOFTWARE.
# 
##############################################################################

import os
import sys
from xml.etree import ElementTree
import json
import logging
try:
    import ogr
    import osr
    GDAL_INCLUDED = True
except ImportError:
    
    try:
        import osgeo.ogr as ogr
        import osgeo.osr as osr
        GDAL_INCLUDED = True
    except ImportError:
        
        GDAL_INCLUDED = False
    
from . import common

class Geo:
    """
    The Geo class contains all the methods and functions used to perform 
        geographic processes mainly using OGR.
    """
    
    def __init__(self, aoi_fn=None):
        """
        Initializer for the Geo object.
        
        @type  aoi_fn: str
        @param aoi_fn: The AOI filename.
        """
        self.aoi_fn = aoi_fn
        
        self.logger = logging.getLogger('eodms')
        
    def convert_imageGeom(self, coords, output='array'):
        """
        Converts a list of coordinates from the RAPI to a polygon geometry, 
            array of points or as WKT.
        
        @type  coords: list
        @param coords: A list of coordinates from the RAPI results.
        @type  output: str
        @param output: The type of return, can be 'array', 'wkt' or 'geom'.
        
        @rtype:  multiple
        @return: Either a polygon geometry, WKT or array of points.
        """
        
        # Get the points from the coordinates list
        pnt1 = coords[0][0]
        pnt2 = coords[0][1]
        pnt3 = coords[0][2]
        pnt4 = coords[0][3]
        
        pnt_array = [pnt1, pnt2, pnt3, pnt4]
        
        if GDAL_INCLUDED:
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
                
                return "POLYGON ((%s))" % ', '.join([' '.join(pnt) \
                    for pnt in pnt_array])
            else:
                return pnt_array
            
    def convert_fromWKT(self, in_feat):
        """
        Converts a WKT to a polygon geometry.
        
        @type  in_feat: str
        @param in_feat: The WKT of the polygon.
        
        @rtype:  ogr.Geometry
        @return: The polygon geometry of the input WKT.
        """
        
        if GDAL_INCLUDED:
            out_poly = ogr.CreateGeometryFromWkt(in_feat)
        
        return out_poly
            
    def export_results(self, img_lst, out_fn='results.geojson'):
        """
        Exports the results of the query to a GeoJSON.
        
        @type  res: list
        @param res: A list of results containing coordinates.
        """
        
        # If the output GeoJSON exists, remove it
        if os.path.exists(out_fn):
            os.remove(out_fn)
        
        if GDAL_INCLUDED:
            # Create the output Driver
            driver = ogr.GetDriverByName('GeoJSON')

            # Create the output GeoJSON
            ds = driver.CreateDataSource(out_fn)
            lyr = ds.CreateLayer(out_fn.replace('.geojson', ''), \
                    geom_type=ogr.wkbPolygon)

            # Get the output Layer's Feature Definition
            featureDefn = lyr.GetLayerDefn()
            
            fields = img_lst.get_fields()
            for f in fields:
                field_name = ogr.FieldDefn(f, ogr.OFTString)
                field_name.SetWidth(256)
                lyr.CreateField(field_name)
            
            for r in img_lst.get_images():
                record_id = r.get_recordId()
                poly = r.get_geometry('geom')

                # Create a new feature
                feat = ogr.Feature(featureDefn)
                
                # Add field values
                for f in fields:
                    feat.SetField(f, str(r.get_metadata(f)))

                # Set new geometry
                feat.SetGeometry(poly)

                # Add new feature to output Layer
                lyr.CreateFeature(feat)

            # Dereference the feature
            feat = None

            # Save and close DataSources
            ds = None
        
    def get_polygon(self):
        """
        Extracts the polygon from an AOI file.
        
        @rtype:  str
        @return: The AOI in WKT format.
        """
        
        if GDAL_INCLUDED:
            # Determine the OGR driver of the input AOI
            if self.aoi_fn.find('.gml') > -1:
                ogr_driver = 'GML'
            elif self.aoi_fn.find('.kml') > -1:
                ogr_driver = 'KML'
            elif self.aoi_fn.find('.json') > -1 or self.aoi_fn.find('.geojson') > -1:
                ogr_driver = 'GeoJSON'
            elif self.aoi_fn.find('.shp') > -1:
                ogr_driver = 'ESRI Shapefile'
            else:
                err_msg = "The AOI file type could not be determined."
                common.print_support(err_msg)
                self.logger.error(err_msg)
                sys.exit(1)
                
            # Open AOI file and extract AOI
            driver = ogr.GetDriverByName(ogr_driver)
            ds = driver.Open(self.aoi_fn, 0)
            
            # Get the layer from the file
            lyr = ds.GetLayer()
            
            # Set the target spatial reference to WGS84
            t_crs = osr.SpatialReference()
            t_crs.ImportFromEPSG(4326)
            
            for feat in lyr:
                # Create the geometry
                geom = feat.GetGeometryRef()
                
                # Convert the geometry to WGS84
                s_crs = geom.GetSpatialReference()
                
                # Get the EPSG codes from the spatial references
                epsg_sCrs = s_crs.GetAttrValue("AUTHORITY", 1)
                epsg_tCrs = t_crs.GetAttrValue("AUTHORITY", 1)
                
                if not str(epsg_sCrs) == '4326':
                    if epsg_tCrs is None:
                        print("\nCannot reproject AOI.")
                        sys.exit(1)
                        
                    if not s_crs.IsSame(t_crs) and not epsg_sCrs == epsg_tCrs:
                        # Create the CoordinateTransformation
                        print("\nReprojecting input AOI...")
                        coordTrans = osr.CoordinateTransformation(s_crs, t_crs)
                        geom.Transform(coordTrans)
                        
                        # Reverse x and y of transformed geometry
                        ring = geom.GetGeometryRef(0)
                        for i in range(ring.GetPointCount()):
                            ring.SetPoint(i, ring.GetY(i), ring.GetX(i))
                
                # Convert multipolygon to polygon (if applicable)
                if geom.GetGeometryType() == 6:
                    geom = geom.UnionCascaded()
                
                # Convert to WKT
                aoi_feat = geom.ExportToWkt()
                
        else:
            # Determine the OGR driver of the input AOI
            if self.aoi_fn.find('.gml') > -1 or self.aoi_fn.find('.kml') > -1:
                
                with open(self.aoi_fn, 'rt') as f:
                    tree = ElementTree.parse(f)
                    root = tree.getroot()
                
                if self.aoi_fn.find('.gml') > -1:
                    coord_lst = []
                    for coords in root.findall('.//{http://www.opengis.net/' \
                        'gml}coordinates'):
                        coord_lst.append(coords.text)
                else:
                    coord_lst = []
                    for coords in root.findall('.//{http://www.opengis.net/' \
                        'kml/2.2}coordinates'):
                        coord_lst.append(coords.text)
                        
                pnts_array = []
                for c in coord_lst:
                    pnts = [p.strip('\n').strip('\t').split(',') for p in \
                            c.split(' ') if not p.strip('\n').strip('\t') == '']
                    pnts_array += pnts
                
                aoi_feat = "POLYGON ((%s))" % ', '.join([' '.join(pnt[:2]) \
                    for pnt in pnts_array])
                
            elif self.aoi_fn.find('.json') > -1 or self.aoi_fn.find('.geojson') > -1:
                with open(self.aoi_fn) as f:
                    data = json.load(f)
                
                feats = data['features']
                for f in feats:
                    geo_type = f['geometry']['type']
                    if geo_type == 'MultiPolygon':
                        coords = f['geometry']['coordinates'][0][0]
                    else:
                        coords = f['geometry']['coordinates'][0]
                
                # Convert values in point array to strings
                coords = [[str(p[0]), str(p[1])] for p in coords]
                aoi_feat = "POLYGON ((%s))" % ', '.join([' '.join(pnt) \
                            for pnt in coords])
                            
            elif self.aoi_fn.find('.shp') > -1:
                msg = "Could not open shapefile. The GDAL Python Package " \
                        "must be installed to use shapefiles."
                common.print_support(msg)
                self.logger.error(msg)
                sys.exit(1)
            else:
                common.print_support("The AOI file type could not be determined.")
                self.logger.error(msg)
                sys.exit(1)
            
        return aoi_feat