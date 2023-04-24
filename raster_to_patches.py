from pathlib import Path

import geopandas as gpd
from osgeo import gdal
from utils.geo_funcs import LBMRasterSegmenter

out_dir = "patches/"
Path(out_dir).mkdir(exist_ok=True, parents=True)
raster = gdal.Open("tiles/utrecht_2020_1m_raster.tiff")
polys = gpd.read_file("tiles/utrecht_2020_1m_labels.geojson")

segmenter = LBMRasterSegmenter(raster, polys)
segmenter.subset_raster_by_lbm_polys(700, 700, out_dir, overwrite_patches=True)