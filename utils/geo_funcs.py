import math
from time import sleep
from requests import Request
import geopandas as gpd
from shapely.geometry import Point
from pyproj import Transformer

import numpy as np
import rasterio
import rasterio.windows
import subprocess
from rasterio.transform import Affine

### WFS FUNCS ###
def unclip_polygon(row):
    centroid = row['geometry'].centroid
    grid_true_center_x = centroid.xy[0][0] - (centroid.xy[0][0] % 100) + 50
    grid_true_center_y = centroid.xy[1][0] - (centroid.xy[1][0] % 100) + 50
    return Point([grid_true_center_x, grid_true_center_y]).buffer(50, cap_style = 3)    

def get_scores(url, year, bbox): 
    str_bbox = ",".join(str(coord) for coord in bbox)

    layer_name = f"lbm3:clippedgridscore{year}"
    params = dict(service='WFS', version="2.0.0", request='GetFeature',
        typeName=layer_name, outputFormat='json', bbox=str_bbox, srsName="EPSG:28992", startIndex=0)
    wfs_request_url = Request('GET', url, params=params).prepare().url
    # wfs_request_url.replace("%2C", ",")
    pts_df = gpd.read_file(wfs_request_url)
    return pts_df

### WMTS FUNCS ###
def bbox_to_web_mercator(bbox):
    transformer = Transformer.from_crs("EPSG:28992", "EPSG:3857") 
    reproj_bbox = (*transformer.transform(bbox[0], bbox[1]), *transformer.transform(bbox[2], bbox[3]))    
    return reproj_bbox

def hotfix_name_error(wmts):
    for i, op in enumerate(wmts.operations):
        if(not hasattr(op, 'name')):
            wmts.operations[i].name = ""

def filter_row_cols_by_bbox(matrix, bbox):
    pixel_size = 0.00028 # Each pixel is assumed to be 0.28mm
    tile_size_m = matrix.scaledenominator * pixel_size

    column_orig = math.floor((float(bbox[0]) - matrix.topleftcorner[0]) / (tile_size_m * matrix.tilewidth))
    row_orig = math.floor((float(bbox[1]) - matrix.topleftcorner[1]) / (-tile_size_m * matrix.tilewidth))

    column_dest = math.floor((float(bbox[2]) - matrix.topleftcorner[0]) / (tile_size_m * matrix.tilewidth))
    row_dest = math.floor((float(bbox[3]) - matrix.topleftcorner[1]) / (-tile_size_m * matrix.tilewidth))

    if (column_orig > column_dest):
        t = column_orig
        column_orig = column_dest
        column_dest = t

    if (row_orig > row_dest):
        t = row_orig
        row_orig = row_dest
        row_dest = t

    column_dest += 1
    row_dest += 1

    return (column_orig, column_dest, row_orig, row_dest)

def calculate_output_raster_size(min_row, max_row, min_col, max_col):
    total_rows = 256 * (max_row - min_row)
    total_cols = 256 * (max_col - min_col)
    return total_rows, total_cols

def calculate_geotransform(tile_matrix, min_col, min_row):
    pixel_size = 0.00028 # Each pixel is assumed to be 0.28mm
    tile_size_m = tile_matrix.scaledenominator * pixel_size
    left = ((min_col * tile_matrix.tilewidth + 0.5) * tile_size_m) + tile_matrix.topleftcorner[0]
    top = ((min_row * tile_matrix.tileheight + 0.5) * -tile_size_m) + tile_matrix.topleftcorner[1]
    geotransform = Affine.translation(left, top) * Affine.scale(tile_size_m, -tile_size_m)
    return geotransform

def create_output_raster(out_dir, total_cols, total_rows, geotransform):
    output_raster = rasterio.open(f"{out_dir}unprojected.tiff", "w",
                                  driver="GTiff",
                                  width=total_cols,
                                  height=total_rows,
                                  count=3, # for RGB
                                  dtype=np.uint8,
                                  crs="EPSG:3857",
                                  transform=geotransform)
    return output_raster

def write_tiles_to_output_raster(wmts, wmts_layer, zoom_level, min_row, max_row, min_col, max_col, output_raster):
    outer_loop = tqdm(range(min_row, max_row))
    for row in outer_loop:
        outer_loop.update() #update outer tqdm
        for col in range(min_col, max_col):
            tries = 0
            downloaded = False
            while (tries <= 3 and not downloaded):
                try:
                    tile = wmts.gettile(
                        layer=wmts_layer,
                        tilematrixset="EPSG:3857",
                        tilematrix=zoom_level,
                        row=row,
                        column=col,
                        format='image/jpeg'
                    )

                    # Read the tile data and store it in the output raster
                    img = rasterio.io.MemoryFile(tile).open().read()
                    output_raster.write(img, window=rasterio.windows.Window(
                        col * 256 - min_col * 256,
                        row * 256 - min_row * 256,
                        256, 256))
                    downloaded = True
                    sleep(0.05)
                except Exception as e:
                    print(e)
                    tries += 1
                    sleep(1)



def reproject_raster(out_dir, filename_prefix, out_pixel_size):
    reproj_cmd = f"gdalwarp -t_srs EPSG:28992 -s_srs EPSG:3857 -tr {out_pixel_size} {out_pixel_size} {out_dir}unprojected.tiff {out_dir}{filename_prefix}_raster.tiff"
    subprocess.call(reproj_cmd, shell=True)                
    subprocess.call(f"rm {out_dir}unprojected.tiff", shell=True) # Remove unprojected raster

# import rasterio
# from rasterio.mask import mask
# def patchify_at_lbm_locations(raster, lbm_polys, out_dir):
#     # Loop through each polygon in the GeoJSON format
#     for feature in lbm_polys.iterrows():
#         # Extract the geometry of the polygon
#         feature = feature[1] # Unpacking..?
#         geom = feature.geometry#.buffer(200, cap_style=3)
#         # Use the mask() function to extract the raster patch over the polygon
#         out_image, out_transform = mask(raster, [geom], crop=True)

#         # Update the metadata of the output raster with the new transform, CRS, and dimensions
#         out_meta = raster.meta.copy()
#         out_meta.update({
#             "height": out_image.shape[1],
#             "width": out_image.shape[2],
#             "transform": out_transform,
#             "crs": raster.crs
#         })

#         # Write the extracted raster patch to the output file
#         with rasterio.open(out_dir+f"{feature['id']}.tif" , "w", **out_meta) as out:
#             out.write(out_image)

from osgeo import gdal
from pathlib import Path
from tqdm import tqdm
class LBMRasterSegmenter():
    def __init__(self, raster_tile, lbm_grid_cells):
        self.RDNEW_OGC_WKT = """PROJCS["Amersfoort / RD New",GEOGCS["Amersfoort",DATUM["Amersfoort",SPHEROID["Bessel 1841",6377397.155,299.1528128,AUTHORITY["EPSG","7004"]],TOWGS84[565.417,50.3319,465.552,-0.398957,0.343988,-1.8774,4.0725],AUTHORITY["EPSG","6289"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4289"]],PROJECTION["Oblique_Stereographic"],PARAMETER["latitude_of_origin",52.15616055555555],PARAMETER["central_meridian",5.38763888888889],PARAMETER["scale_factor",0.9999079],PARAMETER["false_easting",155000],PARAMETER["false_northing",463000],UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["X",EAST],AXIS["Y",NORTH],AUTHORITY["EPSG","28992"]]"""
        self.raster_tile = raster_tile
        self.grid_cells = lbm_grid_cells

    def subset_raster_by_lbm_polys(self, xsize, ysize, out_patches_dir, set_name=None, overwrite_patches=False):
        driver = gdal.GetDriverByName("GTiff")
        Path(out_patches_dir).mkdir(parents=True, exist_ok=True)

        # Get xy ranges for raster
        ulx, xres, xskew, uly, yskew, yres  = self.raster_tile.GetGeoTransform()
        ras_x_range = [ulx, ulx + (self.raster_tile.RasterXSize * xres)]
        ras_y_range = [uly + (self.raster_tile.RasterYSize * yres), uly]

        n_pixels_in_xsize = abs(round(xsize * (1/xres)))
        n_pixels_in_ysize = abs(round(ysize * (1/yres)))

        for i, cell in enumerate(tqdm(self.grid_cells.iterrows())):
            # Get centroid, round to origin of grid
            cell_geom = cell[1]['geometry']
            poly_x_range, poly_y_range = self._get_offset_range_from_centroid(cell_geom)

            in_x_range = poly_x_range[0] > ras_x_range[0] and poly_x_range[1] < ras_x_range[1]
            in_y_range = poly_y_range[0] > ras_y_range[0] and poly_y_range[1] < ras_y_range[1]

            if in_x_range and in_y_range:
                # Create output raster
                grid_id = cell[1]['id']
                out_filepath = out_patches_dir + str(grid_id) +'.tiff'                
                if overwrite_patches or not Path(out_filepath).exists:            
                    out_raster = driver.Create( out_filepath,
                                                xsize=n_pixels_in_xsize,
                                                ysize=n_pixels_in_ysize,
                                                bands=3,
                                                options=["INTERLEAVE=PIXEL", "COMPRESS=JPEG"])

                    # Read & write data by offset data relative to top-left
                    x_offset = int(abs(round((poly_x_range[0] - ras_x_range[0]) * (1/xres))))
                    y_offset = int(abs(round((poly_y_range[1] - ras_y_range[1]) * (1/yres))))
                    raster_data = self.raster_tile.ReadAsArray( x_offset, y_offset,
                                                                n_pixels_in_xsize, n_pixels_in_ysize)[:3,:,:]
                    out_raster.WriteRaster(0,0, n_pixels_in_xsize, n_pixels_in_ysize, raster_data.tostring(),
                                                n_pixels_in_ysize, n_pixels_in_ysize, band_list=[1,2,3])            

                    # Set geotransform
                    out_ul = [poly_x_range[0], poly_y_range[1]]
                    out_raster.SetGeoTransform([out_ul[0], xres, xskew, out_ul[1], yskew, yres])
                    
                    # Set projection
                    out_raster.SetProjection(self.RDNEW_OGC_WKT)           
                    
                    out_raster.FlushCache()
                    out_raster = None
    
    def _get_offset_range_from_centroid(self, poly):
        centroid = poly.centroid.xy
        poly_xmin = centroid[0][0] - centroid[0][0]%100
        poly_ymin = centroid[1][0] - centroid[1][0]%100
        poly_x_range = (poly_xmin, poly_xmin+100)
        poly_y_range = (poly_ymin, poly_ymin+100)
        return poly_x_range, poly_y_range