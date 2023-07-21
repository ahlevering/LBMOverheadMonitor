import subprocess
from PIL import Image

from osgeo import gdal
from pathlib import Path
from tqdm import tqdm


class LBMRasterSegmenter:
    def __init__(self, raster_tile, lbm_grid_cells):
        self.RDNEW_OGC_WKT = """PROJCS["Amersfoort / RD New",GEOGCS["Amersfoort",DATUM["Amersfoort",SPHEROID["Bessel 1841",6377397.155,299.1528128,AUTHORITY["EPSG","7004"]],TOWGS84[565.417,50.3319,465.552,-0.398957,0.343988,-1.8774,4.0725],AUTHORITY["EPSG","6289"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4289"]],PROJECTION["Oblique_Stereographic"],PARAMETER["latitude_of_origin",52.15616055555555],PARAMETER["central_meridian",5.38763888888889],PARAMETER["scale_factor",0.9999079],PARAMETER["false_easting",155000],PARAMETER["false_northing",463000],UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["X",EAST],AXIS["Y",NORTH],AUTHORITY["EPSG","28992"]]"""
        self.raster_tile = raster_tile
        self.grid_cells = lbm_grid_cells

    def subset_raster_by_lbm_polys(
        self, xsize, ysize, out_patches_dir, set_name=None, overwrite_patches=False, compress=True
    ):
        driver = gdal.GetDriverByName("GTiff")
        Path(out_patches_dir).mkdir(parents=True, exist_ok=True)

        # Get xy ranges for raster
        ulx, xres, xskew, uly, yskew, yres = self.raster_tile.GetGeoTransform()
        ras_x_range = [ulx, ulx + (self.raster_tile.RasterXSize * xres)]
        ras_y_range = [uly + (self.raster_tile.RasterYSize * yres), uly]

        n_pixels_in_xsize = abs(round(xsize * (1 / xres)))
        n_pixels_in_ysize = abs(round(ysize * (1 / yres)))

        for i, cell in enumerate(tqdm(self.grid_cells.iterrows())):
            # Get centroid, round to origin of grid
            cell_geom = cell[1]["geometry"]
            poly_x_range, poly_y_range = self._get_offset_range_from_centroid(cell_geom)

            in_x_range = poly_x_range[0] > ras_x_range[0] and poly_x_range[1] < ras_x_range[1]
            in_y_range = poly_y_range[0] > ras_y_range[0] and poly_y_range[1] < ras_y_range[1]

            if in_x_range and in_y_range:
                # Create output raster
                grid_id = cell[1]["id"]
                filepath_tiff = out_patches_dir + str(grid_id) + ".tiff"
                filepath_webp = out_patches_dir + str(grid_id) + ".webp"

                if overwrite_patches or (not Path(filepath_tiff).exists() and not Path(filepath_webp).exists()):
                    out_raster = driver.Create(
                        filepath_tiff,
                        xsize=n_pixels_in_xsize,
                        ysize=n_pixels_in_ysize,
                        bands=3,
                        options=["INTERLEAVE=PIXEL"],  # , "COMPRESS=LZW"],
                    )

                    # Read & write data by offset data relative to top-left
                    x_offset = int(abs(round((poly_x_range[0] - ras_x_range[0]) * (1 / xres))))
                    y_offset = int(abs(round((poly_y_range[1] - ras_y_range[1]) * (1 / yres))))
                    raster_data = self.raster_tile.ReadAsArray(
                        x_offset - (n_pixels_in_xsize / 2) + 50,
                        y_offset - (n_pixels_in_ysize / 2) + 50,
                        n_pixels_in_xsize,
                        n_pixels_in_ysize,
                    )[:3, :, :]
                    out_raster.WriteRaster(
                        0,
                        0,
                        n_pixels_in_xsize,
                        n_pixels_in_ysize,
                        raster_data.tostring(),
                        n_pixels_in_ysize,
                        n_pixels_in_ysize,
                        band_list=[1, 2, 3],
                    )

                    # Set geotransform
                    out_ul = [
                        poly_x_range[0] - (n_pixels_in_xsize / 2) + 50,  # - 50,
                        poly_y_range[1] + (n_pixels_in_ysize / 2) - 50,  # + 50,
                    ]
                    out_raster.SetGeoTransform([out_ul[0], xres, xskew, out_ul[1], yskew, yres])

                    # Set projection
                    out_raster.SetProjection(self.RDNEW_OGC_WKT)

                    out_raster.FlushCache()
                    out_raster = None

                    if compress:
                        img = Image.open(filepath_tiff)
                        img.save(filepath_webp, "WEBP")
                        remove_cmd_completed = subprocess.run(
                            f"rm {filepath_tiff}",
                            shell=True,
                            capture_output=True,
                            timeout=60,
                        )

    def _get_offset_range_from_centroid(self, poly):
        centroid = poly.centroid.xy
        poly_xmin = centroid[0][0] - centroid[0][0] % 100
        poly_ymin = centroid[1][0] - centroid[1][0] % 100
        poly_x_range = (poly_xmin, poly_xmin + 100)
        poly_y_range = (poly_ymin, poly_ymin + 100)
        return poly_x_range, poly_y_range
