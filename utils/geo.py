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
import ogr
import osr

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
            return [pnt1, pnt2, pnt3, pnt4]
            
    def convert_fromWKT(self, in_feat):
        """
        Converts a WKT to a polygon geometry.
        
        @type  in_feat: str
        @param in_feat: The WKT of the polygon.
        
        @rtype:  ogr.Geometry
        @return: The polygon geometry of the input WKT.
        """
        
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
            common.print_support("The AOI file type could not be determined.")
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
            
            if not s_crs.IsSame(t_crs) and not epsg_sCrs == epsg_tCrs:
                # Create the CoordinateTransformation
                coordTrans = osr.CoordinateTransformation(s_crs, t_crs)
                geom.Transform(coordTrans)
            
            # Convert multipolygon to polygon (if applicable)
            if geom.GetGeometryType() == 6:
                geom = geom.UnionCascaded()
            
            # Convert to WKT
            aoi_feat = geom.ExportToWkt()
            
        return aoi_feat