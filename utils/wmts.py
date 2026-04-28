import math
from time import sleep
from tqdm import tqdm
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from pyproj import Transformer
import numpy as np
from owslib.wmts import WebMapTileService
import rasterio
import rasterio.windows
import rasterio.warp
from rasterio.transform import Affine
from rasterio.enums import Resampling
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

        self.get_wmts_params(pixel_size)

    def hotfix_name_error(self, wmts):
        for i, op in enumerate(wmts.operations):
            if not hasattr(op, "name"):
                wmts.operations[i].name = ""

    def get_wmts_params(self, pixel_size):
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
                wmts_layer = "LuchtfotoNL_50_cm_2014"
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
            tile_matrix_set = "EPSG:28992"
            epsg = "EPSG:28992"
            wmts = WebMapTileService("https://service.pdok.nl/hwh/luchtfotorgb/wmts/v1_0")

            if pixel_size >= 1:
                set_zoom_lvl = "12"
            elif pixel_size >= 0.5:
                set_zoom_lvl = "13"
            elif pixel_size >= 0.25:
                set_zoom_lvl = "14"
            else:
                set_zoom_lvl = "15"

        self.hotfix_name_error(wmts)

        self.wmts = wmts
        self.wmts_layer = wmts_layer
        self.tile_matrix_set = tile_matrix_set
        self.set_zoom_level = set_zoom_lvl
        self.epsg = epsg
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

    def get_tile_size_meters(self):
        """Return the ground resolution (meters) of a single tile pixel at this zoom level."""
        pixel_size = 0.00028  # 0.28mm per pixel
        tile_size_m = self.tile_matrix.scaledenominator * pixel_size
        return tile_size_m


class WMTSRasterDownloader:
    def __init__(self, year, city, bbox, offset_meters, out_pixel_size, out_dir):
        """
        Parameters
        ----------
        offset_meters : float
            Padding around the bbox in **meters** (CRS units of EPSG:28992).
        out_pixel_size : float
            Output pixel size in meters.
        """
        self.year = year
        self.city = city
        self.offset_meters = offset_meters
        self.out_pixel_size = out_pixel_size

        logging.basicConfig(filename="downloading.log", level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        self.out_dir = out_dir
        Path(out_dir).mkdir(exist_ok=True, parents=True)

        self.wmts_manager = WMTSManager(year, bbox, out_pixel_size)

        # Thread-safety lock for rasterio writes
        self._write_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Tile index helpers
    # ------------------------------------------------------------------

    def filter_row_cols_by_bbox(self):
        bbox = self.wmts_manager.bbox
        matrix = self.wmts_manager.tile_matrix
        tile_size_m = self.wmts_manager.get_tile_size_meters()

        column_orig = math.floor((float(bbox[0]) - matrix.topleftcorner[0]) / (tile_size_m * matrix.tilewidth))
        row_orig = math.floor((float(bbox[1]) - matrix.topleftcorner[1]) / (-tile_size_m * matrix.tileheight))

        column_dest = math.floor((float(bbox[2]) - matrix.topleftcorner[0]) / (tile_size_m * matrix.tilewidth))
        row_dest = math.floor((float(bbox[3]) - matrix.topleftcorner[1]) / (-tile_size_m * matrix.tileheight))

        if column_orig > column_dest:
            column_orig, column_dest = column_dest, column_orig
        if row_orig > row_dest:
            row_orig, row_dest = row_dest, row_orig

        column_dest += 1
        row_dest += 1

        return column_orig, column_dest, row_orig, row_dest

    def calculate_geotransform(self, min_col, min_row):
        tile_matrix = self.wmts_manager.tile_matrix
        tile_size_m = self.wmts_manager.get_tile_size_meters()
        left = (min_col * tile_matrix.tilewidth * tile_size_m) + tile_matrix.topleftcorner[0]
        top = (min_row * tile_matrix.tileheight * (-tile_size_m)) + tile_matrix.topleftcorner[1]
        geotransform = Affine.translation(left, top) * Affine.scale(tile_size_m, -tile_size_m)
        return geotransform

    # ------------------------------------------------------------------
    # Raster creation
    # ------------------------------------------------------------------

    def create_output_raster(self, total_cols, total_rows, geotransform):
        return rasterio.open(
            f"{self.out_dir}unprojected.tiff",
            "w",
            driver="GTiff",
            width=total_cols,
            height=total_rows,
            count=3,
            dtype=np.uint8,
            crs=self.wmts_manager.epsg,
            transform=geotransform,
        )

    # ------------------------------------------------------------------
    # Tile downloading
    # ------------------------------------------------------------------

    def download_tile(self, row, col, min_row, min_col):
        """Download a single tile and return (row, col, img_array)."""
        tries = 0
        while tries <= 10:
            try:
                tile = self.wmts_manager.get_tile(row, col)
                with rasterio.io.MemoryFile(tile) as memfile:
                    img = memfile.open().read()
                sleep(0.025)
                return row, col, img
            except Exception as e:
                self.logger.warning(str(e))
                print(f"Tile ({row},{col}) failed: {e}. Retry {tries+1}/10")
                tries += 1
                sleep(3 ** tries)
        self.logger.error(f"Tile ({row},{col}) permanently failed after 10 retries.")
        return row, col, None

    def write_tiles_to_output_raster(self, output_raster, min_row, max_row, min_col, max_col):
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(self.download_tile, row, col, min_row, min_col): (row, col)
                for row in range(min_row, max_row)
                for col in range(min_col, max_col)
            }
            for future in tqdm(as_completed(futures), total=len(futures), desc=f"{self.city} {self.year}"):
                row, col, img = future.result()
                if img is None:
                    continue
                # Serialize writes — rasterio file objects are NOT thread-safe
                with self._write_lock:
                    output_raster.write(
                        img,
                        window=rasterio.windows.Window(
                            col * 256 - min_col * 256,
                            row * 256 - min_row * 256,
                            256,
                            256,
                        ),
                    )

    # ------------------------------------------------------------------
    # Post-processing: reproject + exact crop
    # ------------------------------------------------------------------

    def postprocess_raster(self, filename, target_bbox):
        """
        Resample to ``out_pixel_size`` and crop exactly to ``target_bbox``
        (minx, miny, maxx, maxy) in EPSG:28992, using rasterio only.
        """
        minx, miny, maxx, maxy = target_bbox
        dst_crs = rasterio.CRS.from_epsg(28992)

        # Compute exact output dimensions from the target bbox and desired pixel size
        out_width  = round((maxx - minx) / self.out_pixel_size)
        out_height = round((maxy - miny) / self.out_pixel_size)

        # Build the affine transform for the output: top-left corner, pixel size
        dst_transform = Affine.translation(minx, maxy) * Affine.scale(self.out_pixel_size, -self.out_pixel_size)

        input_file = f"{self.out_dir}unprojected.tiff"
        with rasterio.open(input_file) as src:
            out_profile = src.profile.copy()
            out_profile.update(
                crs=dst_crs,
                transform=dst_transform,
                width=out_width,
                height=out_height,
                compress="lzw",
            )

            with rasterio.open(filename, "w", **out_profile) as dst:
                for band_idx in range(1, src.count + 1):
                    rasterio.warp.reproject(
                        source=rasterio.band(src, band_idx),
                        destination=rasterio.band(dst, band_idx),
                        src_transform=src.transform,
                        src_crs=src.crs,
                        dst_transform=dst_transform,
                        dst_crs=dst_crs,
                        resampling=Resampling.bilinear,
                    )

        # Clean up intermediary file
        Path(input_file).unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def download_raster_tile(self, filename):
        bbox = self.wmts_manager.bbox  # (minx, miny, maxx, maxy) in EPSG:28992

        # --- Compute target bbox with meter-based offset ---
        target_bbox = (
            bbox[0] - self.offset_meters,
            bbox[1] - self.offset_meters,
            bbox[2] + self.offset_meters,
            bbox[3] + self.offset_meters,
        )

        # --- Expand to tile grid (to cover target_bbox fully) ---
        # Temporarily replace wmts_manager.bbox with the padded bbox for tile selection
        original_bbox = self.wmts_manager.bbox
        self.wmts_manager.bbox = target_bbox
        min_col, max_col, min_row, max_row = self.filter_row_cols_by_bbox()
        self.wmts_manager.bbox = original_bbox

        # Calculate total size of tile mosaic
        total_rows = 256 * (max_row - min_row)
        total_cols = 256 * (max_col - min_col)

        geotransform = self.calculate_geotransform(min_col, min_row)

        # Create and fill unprojected raster
        unproj_raster = self.create_output_raster(total_cols, total_rows, geotransform)
        self.write_tiles_to_output_raster(unproj_raster, min_row, max_row, min_col, max_col)
        unproj_raster.close()

        # Reproject, resample, and crop exactly to target_bbox
        self.postprocess_raster(filename, target_bbox)