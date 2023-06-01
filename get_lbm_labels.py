import numpy as np
from owslib.wmts import WebMapTileService
from pathlib import Path
import subprocess

from utils.geo_funcs import * # unclip_polygon, get_scores, filter_row_cols_by_bbox
import warnings
warnings.filterwarnings("ignore") # Silencing repeated Pandas warnings

### SETTINGS ###
# NOTE: The WFS has data from 2016 onwards. For the 2012-2015 data, please check the ArcGIS Online link in the repository
# Alternatively, contact the authors for assistance
year = "20" 
out_pixel_size = 0.6 # in meters
filename_prefix = 'utrecht_2020_60cm'
out_dir = "tiles/"
# Input CRS is RD New, 28992
subset_bbox = (139267, 456844, 139267+4000, 456844+4000) # test coords
DOWNLOAD_LABELS: True
DOWNLOAD_IMAGES: True
  
# Zoom level - this determines the WMTS resolution to query from the server. 
if out_pixel_size >= 0.6: 
    zoom_level = 18 # 19 for ~30cm resolution
else: 
    zoom_level = 19  

# File server functions
# https://gis.stackexchange.com/questions/339484/qwc2-how-to-calculate-wmts-resolutions
wmts_layer = f"20{year}_ortho25"
offset = 900 # Pad the raster with extra pixels to allow side-overlap of patches at the edges
Path(out_dir).mkdir(exist_ok=True, parents=True)

# ### DOWNLOAD FROM WFS ###
if DOWNLOAD_LABELS:
    wfs_url = "https://geo.leefbaarometer.nl/lbm3/ows?service=WFS"
    labels_df = get_scores(wfs_url, year, subset_bbox)
    # Points from the WFS are always clipped to buildings, but this is undesirable for further analyses
    labels_df['geometry'] = labels_df.apply(unclip_polygon, axis=1)
    labels_df.rename(columns={"afw": "liveability",
                           "fys": "phys_env",
                           "onv": "safety",
                           "soc": "cohesion",
                           "won": "buildings"}, errors="raise")
    # Filter repeated rows / stylistic scores, keep only standard deviation scores
    labels_df = labels_df.drop(columns=["scale", "name", "kscore", "kafw", "kfys", "kwon", "konv", "ksoc", "kvrz"])
    labels_df = labels_df.dropna(how='any') # Remove all grid cells where values are missing
    labels_df.to_file(f"{out_dir}/{filename_prefix}_labels.geojson", driver="GeoJSON")

### WMTS ###
if DOWNLOAD_IMAGES:
    # Reproject to web mercator, the only CRS that works with the downloader
    reproj_bbox = bbox_to_web_mercator(subset_bbox)

    # Set-up WMTS service
    wmts = WebMapTileService("https://service.pdok.nl/hwh/luchtfotorgb/wmts/v1_0")
    hotfix_name_error(wmts)
    tile_matrix = wmts.tilematrixsets["EPSG:3857"].tilematrix[str(zoom_level)]

    min_col, max_col, min_row, max_row = filter_row_cols_by_bbox(tile_matrix, reproj_bbox)
    patches_to_pad = int(np.ceil(offset / (256 * out_pixel_size)))
    min_col = int(min_col - patches_to_pad)
    min_row = int(min_row - patches_to_pad)
    max_col = int(max_col + patches_to_pad)
    max_row = int(max_row + patches_to_pad)

    # Calculate the size of the output raster
    total_rows = 256 * (max_row - min_row)
    total_cols = 256 * (max_col - min_col)

    # Create an empty output raster
    output_raster = np.zeros((total_rows, total_cols, 3), dtype=np.uint8)

    tile = wmts.gettile(
        layer=wmts_layer,
        tilematrixset="EPSG:3857",
        tilematrix=zoom_level,
        row=min_row,
        column=min_col,
        format='image/jpeg'
    )

    # Calculate transformation parameters
    geotransform = calculate_geotransform(tile_matrix, min_col, min_row)

    # create output raster
    output_raster = create_output_raster(out_dir, total_cols, total_rows, geotransform)

    # loop through the tiles and write them to the output raster
    write_tiles_to_output_raster(wmts, wmts_layer, zoom_level, min_row, max_row, min_col, max_col, output_raster)
    output_raster.close()

    # Reproject raster to Dutch national system
    # Didn't manage to quickly do this with rasterio.
    # Using command-line GDAL instead, which means a temporary 2x storage space requirement.
    # Sorry.
    reproj_cmd = f"gdalwarp -t_srs EPSG:28992 -s_srs EPSG:3857 -tr {out_pixel_size} {out_pixel_size} {out_dir}unprojected.tiff {out_dir}{filename_prefix}_raster.tiff"
    subprocess.call(reproj_cmd, shell=True)
    subprocess.call("rm tiles/unprojected.tiff", shell=True)
