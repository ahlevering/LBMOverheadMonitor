import numpy as np
import geopandas as gpd
from owslib.wmts import WebMapTileService
from pathlib import Path
import subprocess
from osgeo import gdal, osr

from utils.geo_funcs import *  # unclip_polygon, get_scores, filter_row_cols_by_bbox
import warnings

warnings.filterwarnings("ignore")  # Silencing repeated Pandas warnings

### SETTINGS ###
OUT_PIXEL_SIZE = 1  # in meters
BASE_DIR = "data/tiles/"

DOWNLOAD_LABELS = False  # Provided label file contains labels of images already
ADD_DOMAIN_SCORES = False
DOWNLOAD_IMAGES = True
OFFSET = 1200  # Pad the raster with extra pixels to allow side-overlap of raster tiles at the edges

# Zoom level - this determines the WMTS resolution to query from the server.
if OUT_PIXEL_SIZE >= 0.6:
    ZOOM_LEVEL = 17  # 19 for ~30cm resolution
else:
    ZOOM_LEVEL = 19

lbm_gdf = gpd.read_file("data/labels_with_splits.geojson")
grouped_cities = lbm_gdf.groupby("set")

labels_df = gpd.GeoDataFrame()
years = [8, *list(range(12, 21))]
for year in years:
    out_df_name = BASE_DIR + "labels_{year}.geojson"
    for city, cells in grouped_cities:
        city = city.split("_")[0]
        print(f"Processing {year} {city}")
        bbox = cells.total_bounds.tolist()

        # ### DOWNLOAD FROM WFS ###
        if DOWNLOAD_LABELS:
            wfs_url = "https://geo.leefbaarometer.nl/lbm3/ows?service=WFS"
            year_labels_df = get_scores(wfs_url, year, bbox, ADD_DOMAIN_SCORES)
            # Points from the WFS are always clipped to buildings, but this is undesirable for further analyses
            year_labels_df["geometry"] = year_labels_df.apply(unclip_polygon, axis=1)
            year_labels_df["set"] = city
            year_labels_df.rename(
                columns={
                    "afw": f"liveability_{year}",
                    "fys": f"phys_env_{year}",
                    "onv": f"safety_{year}",
                    "soc": f"cohesion_{year}",
                    "won": f"buildings_{year}",
                },
                errors="ignore",
                inplace=True,
            )
            to_join = [
                col
                for col in [
                    "id",
                    "geometry",
                    f"liveability_{year}",
                    f"phys_env_{year}",
                    f"safety_{year}",
                    f"cohesion_{year}",
                    f"buildings_{year}",
                ]
                if col in year_labels_df.keys()
            ]

            # Filter repeated rows / stylistic scores, keep only standard deviation scores
            year_labels_df.drop(
                columns=[
                    "scale",
                    "name",
                    "year",
                    "kscore",
                    "kafw",
                    "kfys",
                    "kwon",
                    "konv",
                    "ksoc",
                    "kvrz",
                ],
                errors="ignore",
                inplace=True,
            )
            year_labels_df.dropna(how="any", inplace=True)  # Remove all grid cells where values are missing

            if labels_df.empty:
                labels_df = year_labels_df
            elif year == 16:
                # Append new row to the DataFrame
                labels_df = labels_df.append(year_labels_df, ignore_index=True)
            else:
                # Update specific columns in existing rows with non-null values from year_labels_df
                year_labels_df["geometry"] = year_labels_df["geometry"].centroid
                joined_df = gpd.sjoin(labels_df, year_labels_df[to_join], how="left", op="contains")
                for col in to_join[2:]:
                    if col in labels_df.columns:
                        postfix = "_right"
                        labels_df.loc[~joined_df[col + postfix].isna(), col] = joined_df.loc[
                            ~joined_df[col + postfix].isna(), col + postfix
                        ]
                    else:
                        labels_df[col] = joined_df[col]

        ### WMTS ###
        if DOWNLOAD_IMAGES:
            # File server functions
            # https://gis.stackexchange.com/questions/339484/qwc2-how-to-calculate-wmts-resolutions
            out_dir = f"{BASE_DIR}{year}/"
            if not Path(f"{out_dir}{city}_{year}.tiff").exists():
                Path(out_dir).mkdir(exist_ok=True, parents=True)

                # Set-up WMTS service
                ##### Each year has different WMTS settings #####
                tile_matrix_set = "default028mm"
                set_zoom_lvl = "12"
                if year == 8:
                    set_zoom_lvl = "12"
                    wmts_layer = "Luchtfoto_2008"
                    wmts = WebMapTileService(
                        "https://tiles.arcgis.com/tiles/nSZVuSZjHpEZZbRo/arcgis/rest/services/Luchtfoto_2008/MapServer/WMTS?"
                    )
                    hotfix_name_error(wmts)

                elif year <= 15:
                    if year <= 13:
                        wmts_layer = f"LuchtfotoNL50cm_20{year}"
                        wmts = WebMapTileService(
                            f"https://tiles.arcgis.com/tiles/nSZVuSZjHpEZZbRo/arcgis/rest/services/LuchtfotoNL50cm_20{year}/MapServer/WMTS?"
                        )
                        hotfix_name_error(wmts)
                    elif year == 14:
                        wmts_layer = f"LuchtfotoNL_50_cm_2014"
                        wmts = WebMapTileService(
                            f"https://tiles.arcgis.com/tiles/nSZVuSZjHpEZZbRo/arcgis/rest/services/LuchtfotoNL_50_cm_2014/MapServer/WMTS/"
                        )
                        hotfix_name_error(wmts)
                    elif year == 15:
                        wmts_layer = "LuchtfotoNL_2015_50_cm"
                        wmts = WebMapTileService(
                            f"https://tiles.arcgis.com/tiles/nSZVuSZjHpEZZbRo/arcgis/rest/services/LuchtfotoNL_2015_50_cm/MapServer/WMTS?"
                        )
                        hotfix_name_error(wmts)
                else:
                    set_zoom_lvl = str(ZOOM_LEVEL)
                    wmts_layer = f"20{year}_ortho25"
                    tile_matrix_set = "EPSG:3857"
                    wmts = WebMapTileService("https://service.pdok.nl/hwh/luchtfotorgb/wmts/v1_0")
                    hotfix_name_error(wmts)

                    # Reproject to web mercator, the only CRS that works with the downloader
                    bbox = bbox_to_web_mercator(bbox)
                tile_matrix = wmts.tilematrixsets[tile_matrix_set].tilematrix[set_zoom_lvl]

                min_col, max_col, min_row, max_row = filter_row_cols_by_bbox(tile_matrix, bbox)
                patches_to_pad = int(np.ceil(OFFSET / (256 * OUT_PIXEL_SIZE)))
                min_col = int(min_col - patches_to_pad)
                min_row = int(min_row - patches_to_pad)
                max_col = int(max_col + patches_to_pad)
                max_row = int(max_row + patches_to_pad)

                # Calculate the size of the output raster
                total_rows = 256 * (max_row - min_row)
                total_cols = 256 * (max_col - min_col)

                # Create an empty output raster
                unproj_rastesr = np.zeros((total_rows, total_cols, 3), dtype=np.uint8)

                tile = wmts.gettile(
                    layer=wmts_layer,
                    tilematrixset=tile_matrix_set,
                    tilematrix=set_zoom_lvl,
                    row=min_row,
                    column=min_col,
                    format="image/jpeg",
                )

                # Calculate transformation parameters
                geotransform = calculate_geotransform(tile_matrix, min_col, min_row)

                # create output raster
                unproj_raster = create_output_raster(out_dir, total_cols, total_rows, geotransform)

                # loop through the tiles and write them to the output raster
                write_tiles_to_output_raster(
                    wmts,
                    wmts_layer,
                    tile_matrix_set,
                    set_zoom_lvl,
                    min_row,
                    max_row,
                    min_col,
                    max_col,
                    unproj_raster,
                )
                unproj_raster.close()

                # Define the input and output file paths
                input_file = f"{out_dir}unprojected.tiff"
                output_file = f"{out_dir}{city}_{year}.tiff"

                # Define the target CRS (coordinate reference system) you want to reproject to
                target_crs = "EPSG:28992"

                # Open the input raster
                input_ds = gdal.Open(input_file)

                # Reproject the input raster to the target CRS and save to the output file
                gdal.Warp(f"{out_dir}projected.tiff", input_ds, dstSRS=target_crs)
                remove_cmd_completed = subprocess.run(
                    f"rm {out_dir}unprojected.tiff",
                    shell=True,
                    capture_output=True,
                    timeout=60,
                )

                # Resize
                reproj_cmd = f"gdalwarp -tr {OUT_PIXEL_SIZE} {OUT_PIXEL_SIZE} {out_dir}projected.tiff {out_dir}{city}_{year}.tiff"
                reproj_cmd_completed = subprocess.run(reproj_cmd, shell=True, capture_output=True, timeout=180)

                # Close the dataset
                input_ds = None
                remove_cmd_completed = subprocess.run(
                    f"rm {out_dir}projected.tiff",
                    shell=True,
                    capture_output=True,
                    timeout=60,
                )
    if DOWNLOAD_LABELS:
        labels_df.to_file(f"{out_dir}/labels.geojson", driver="GeoJSON")
