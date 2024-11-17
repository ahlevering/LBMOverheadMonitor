import math
from time import sleep
from tqdm import tqdm
from pathlib import Path
from time import sleep
from concurrent.futures import ThreadPoolExecutor, as_completed

from pyproj import Transformer
import numpy as np
from owslib.wmts import WebMapTileService
from osgeo import gdal
from rasterio.transform import Affine

import rasterio
import rasterio.windows
import subprocess
from rasterio.transform import Affine

import logging

class WMTSManager:
    def __init__(self, year, bbox, pixel_size):
        self.year = year
        self.bbox = bbox

        self.wmts = None
        self.wmts_layer = None
        self.tile_matrix_set = None
        self.epsg = None
        self.set_zoom_level = None
        self.tile_matrix = None

        ## Set above variables
        self.get_wmts_params(pixel_size)

    def hotfix_name_error(self, wmts):
        for i, op in enumerate(wmts.operations):
            if not hasattr(op, "name"):
                wmts.operations[i].name = ""

    def get_wmts_params(self, pixel_size):
        # Set-up WMTS service
        tile_matrix_set = "default028mm"
        set_zoom_lvl = "12"
        epsg = "EPSG:28992"
        if self.year == 8:
            set_zoom_lvl = "12"
            wmts_layer = "Luchtfoto_2008"
            wmts = WebMapTileService(
                "https://tiles.arcgis.com/tiles/nSZVuSZjHpEZZbRo/arcgis/rest/services/Luchtfoto_2008/MapServer/WMTS?"
            )
        elif self.year <= 15:
            if self.year <= 13:
                wmts_layer = f"LuchtfotoNL50cm_20{self.year}"
                wmts = WebMapTileService(
                    f"https://tiles.arcgis.com/tiles/nSZVuSZjHpEZZbRo/arcgis/rest/services/LuchtfotoNL50cm_20{self.year}/MapServer/WMTS?"
                )
            elif self.year == 14:
                wmts_layer = f"LuchtfotoNL_50_cm_2014"
                wmts = WebMapTileService(
                    f"https://tiles.arcgis.com/tiles/nSZVuSZjHpEZZbRo/arcgis/rest/services/LuchtfotoNL_50_cm_2014/MapServer/WMTS/"
                )
            elif self.year == 15:
                wmts_layer = "LuchtfotoNL_2015_50_cm"
                wmts = WebMapTileService(
                    f"https://tiles.arcgis.com/tiles/nSZVuSZjHpEZZbRo/arcgis/rest/services/LuchtfotoNL_2015_50_cm/MapServer/WMTS?"
                )
        else:
            wmts_layer = f"20{self.year}_ortho25"
            tile_matrix_set = "EPSG:28992" #"EPSG:3857"
            epsg = "EPSG:28992" # "EPSG:3857"
            wmts = WebMapTileService("https://service.pdok.nl/hwh/luchtfotorgb/wmts/v1_0")

            if pixel_size >= 1:
                set_zoom_lvl = "12" # 84cm per pixel
            elif pixel_size >= 0.5:
                set_zoom_lvl = "13" # 42cm per pixel
            elif pixel_size >= 0.25:
                set_zoom_lvl = "14" # 21cm per pixel
            else:
                set_zoom_lvl = "15" # Approx 10.5cm per pixel

        # Fix weird WMTS library bug
        self.hotfix_name_error(wmts)

        ### Set params ###
        self.wmts = wmts  # WMTS service interface
        self.wmts_layer = wmts_layer  # Layer from which to download tiles
        self.tile_matrix_set = tile_matrix_set  # Tileset of the layer from which to download (e.g. coordinate sys)
        self.set_zoom_level = set_zoom_lvl  # Zoom level from which to download
        self.epsg = epsg  # Coordinate reference system, needed for saving raster tile
        # Contains geo-transformation parameters
        self.tile_matrix = wmts.tilematrixsets[tile_matrix_set].tilematrix[set_zoom_lvl]

    def get_tile(self, row, col):
        tile = self.wmts.gettile(
            layer=self.wmts_layer,
            tilematrixset=self.tile_matrix_set,
            tilematrix=self.set_zoom_level,
            row=row,
            column=col,
            format="image/jpeg",
        )
        return tile

    def bbox_to_web_mercator(self):
        transformer = Transformer.from_crs("EPSG:28992", "EPSG:3857")
        bbox = self.bbox
        reproj_bbox = (
            *transformer.transform(bbox[0], bbox[1]),
            *transformer.transform(bbox[2], bbox[3]),
        )
        self.bbox = reproj_bbox

    def calculate_output_raster_size(min_row, max_row, min_col, max_col):
        total_rows = 256 * (max_row - min_row)
        total_cols = 256 * (max_col - min_col)
        return total_rows, total_cols


class WMTSRasterDownloader:
    def __init__(self, year, city, bbox, offset, out_pixel_size, out_dir):
        self.year = year
        self.city = city
        self.offset = offset
        self.out_pixel_size = out_pixel_size

        logging.basicConfig(filename='downloading.log', level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        # Determined during downloading
        self.set_zoom_level = None

        self.out_dir = out_dir
        if not Path(f"{out_dir}{city}_{year}.tiff").exists():
            Path(out_dir).mkdir(exist_ok=True, parents=True)

        self.wmts_manager = WMTSManager(year, bbox, out_pixel_size)

    def filter_row_cols_by_bbox(self):
        bbox = self.wmts_manager.bbox
        matrix = self.wmts_manager.tile_matrix
        pixel_size = 0.00028  # Each pixel is assumed to be 0.28mm
        tile_size_m = matrix.scaledenominator * pixel_size

        column_orig = math.floor((float(bbox[0]) - matrix.topleftcorner[0]) / (tile_size_m * matrix.tilewidth))
        row_orig = math.floor((float(bbox[1]) - matrix.topleftcorner[1]) / (-tile_size_m * matrix.tilewidth))

        column_dest = math.floor((float(bbox[2]) - matrix.topleftcorner[0]) / (tile_size_m * matrix.tilewidth))
        row_dest = math.floor((float(bbox[3]) - matrix.topleftcorner[1]) / (-tile_size_m * matrix.tilewidth))

        if column_orig > column_dest:
            t = column_orig
            column_orig = column_dest
            column_dest = t

        if row_orig > row_dest:
            t = row_orig
            row_orig = row_dest
            row_dest = t

        column_dest += 1
        row_dest += 1

        return (column_orig, column_dest, row_orig, row_dest)

    def calculate_geotransform(self, min_col, min_row):
        tile_matrix = self.wmts_manager.tile_matrix
        pixel_size = 0.00028  # Each pixel is assumed to be 0.28mm
        tile_size_m = tile_matrix.scaledenominator * pixel_size
        left = ((min_col * tile_matrix.tilewidth + 0.5) * tile_size_m) + tile_matrix.topleftcorner[0]
        top = ((min_row * tile_matrix.tileheight + 0.5) * -tile_size_m) + tile_matrix.topleftcorner[1]
        geotransform = Affine.translation(left, top) * Affine.scale(tile_size_m, -tile_size_m)
        return geotransform

    def create_output_raster(self, total_cols, total_rows, geotransform):
        output_raster = rasterio.open(
            f"{self.out_dir}unprojected.tiff",
            "w",
            driver="GTiff",
            width=total_cols,
            height=total_rows,
            count=3,  # for RGB
            dtype=np.uint8,
            crs=self.wmts_manager.epsg,
            transform=geotransform,
        )
        return output_raster

    def download_tile(self, row, col, output_raster, min_row, min_col):
        tries = 0
        downloaded = False
        while tries <= 10 and not downloaded:
            try:
                tile = self.wmts_manager.get_tile(row, col)
                # Read the tile data and store it in the output raster
                img = rasterio.io.MemoryFile(tile).open().read()
                output_raster.write(
                    img,
                    window=rasterio.windows.Window(
                        col * 256 - min_col * 256,
                        row * 256 - min_row * 256,
                        256,
                        256,
                    ),
                )
                downloaded = True
                sleep(0.025)
            except Exception as e:
                self.logger.warning(str(e))
                print(e)
                tries += 1
                sleep(3 ** tries)
        return {"Row": row, "Col": col}

    def write_tiles_to_output_raster(
        self,
        output_raster,
        min_row,
        max_row,
        min_col,
        max_col,
    ):
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for row in range(min_row, max_row):
                for col in range(min_col, max_col):
                    futures.append(executor.submit(self.download_tile, row, col, output_raster, min_row, min_col))
            for future in tqdm(as_completed(futures), total=len(futures), desc=f"{self.city} {self.year}"):
                result = future.result()  # blocks until the future is done
                # print(f"Downloaded tile at row {result['Row']}, col {result['Col']}")

    def postprocess_raster(self, filename):
        # Define the input and output file paths
        input_file = f"{self.out_dir}unprojected.tiff"

        # Define the target CRS (coordinate reference system) you want to reproject to
        target_crs = "EPSG:28992"

        input_ras = gdal.Open(input_file)

        # Reproject the input raster to the target CRS and save to the output file
        if self.year > 15:
            warp_options = gdal.WarpOptions(format='GTiff', 
                                            # dstSRS=target_crs,
                                            creationOptions=['COMPRESS=LZW'], 
                                            xRes=self.out_pixel_size, 
                                            yRes=self.out_pixel_size)

            gdal.Warp(#f"{self.out_dir}{self.city}_{self.year}.tiff", 
                    filename,
                    input_ras,
                    options=warp_options)

            # OWSLIB IS THE PROBLEM, FIGURE IT OUT FROM THERE
            remove_cmd_completed = subprocess.run(
                f"rm {self.out_dir}unprojected.tiff",
                shell=True,
                capture_output=True,
                timeout=60,
            )
        else:
            remove_cmd_completed = subprocess.run(
                f"mv {self.out_dir}unprojected.tiff",
                shell=True,
                capture_output=True,
                timeout=60,
            )

        # Resize
        # warp_cmd = f"gdalwarp -co compress=LZW -tr {self.out_pixel_size} {self.out_pixel_size} {self.out_dir}projected.tiff {self.out_dir}{self.city}_{self.year}.tiff"
        # warp_cmd_completed = subprocess.run(warp_cmd, shell=True, capture_output=True, timeout=180)

        # Close the dataset
        input_ras = None
        remove_cmd_completed = subprocess.run(
            f"rm {self.out_dir}projected.tiff", # rm {self.out_dir}warped.tiff ",
            shell=True,
            capture_output=True,
            timeout=60,
        )

    def download_raster_tile(self, filename):
        min_col, max_col, min_row, max_row = self.filter_row_cols_by_bbox()

        # Calculate parameters
        patches_to_pad = int(np.ceil(self.offset / (256 * self.out_pixel_size)))
        min_col = int(min_col - patches_to_pad)
        min_row = int(min_row - patches_to_pad)
        max_col = int(max_col + patches_to_pad)
        max_row = int(max_row + patches_to_pad)

        # Calculate the size of the output raster
        total_rows = 256 * (max_row - min_row)
        total_cols = 256 * (max_col - min_col)

        # Calculate transformation parameters
        geotransform = self.calculate_geotransform(min_col, min_row)

        # create output raster
        unproj_raster = self.create_output_raster(total_cols, total_rows, geotransform)

        self.write_tiles_to_output_raster(
            unproj_raster,
            min_row,
            max_row,
            min_col,
            max_col,
        )
        unproj_raster.close()
        self.postprocess_raster(filename)
