import copy
from pathlib import Path

import geopandas as gpd
from osgeo import gdal
from utils.geo_funcs import LBMRasterSegmenter

years = [8, *list(range(12, 21))]
years = [y for y in years if not y in [20]]
# years = [20]
polys = gpd.read_file("data/tiles/labels.geojson")
tiles_dir = "data/tiles/"

if not Path("data/source/labels_with_splits.geojson").exists():
    labels_with_splits = gpd.read_file("data/source/grid_geosplit_not_rescaled.geojson")

    # Convert to centroid & join
    labels_with_splits["geometry"] = labels_with_splits["geometry"].centroid
    labels_with_splits.set_crs("EPSG:28992", allow_override=True)
    polys = gpd.sjoin(polys, labels_with_splits[["split", "geometry"]], how="inner", op="contains")
    polys.dropna(how="any", axis=0, subset=["split"], inplace=True)  # Remove all where splits aren't defined
    polys.to_file(f"data/source/labels_with_splits.geojson", driver="GeoJSON")


for year in years:
    # Remove all grid cells where values are missing
    year_polys = copy.deepcopy(polys)
    year_polys.dropna(how="any", axis=0, subset=[f"liveability_{year}"], inplace=True)

    p = Path(f"{tiles_dir}{year}").glob("**/*")
    rasters = [x for x in p if x.is_file()]
    for raster in rasters:
        set_name = raster.name.split("_")[0]  # Get just the city name
        set_polys = year_polys[year_polys["set"].isin([set_name])]
        out_dir = f"data/patches/{set_name}/{year}/"
        Path(out_dir).mkdir(exist_ok=True, parents=True)

        raster = gdal.Open(str(raster))
        segmenter = LBMRasterSegmenter(raster, set_polys)

        segmenter.subset_raster_by_lbm_polys(700, 700, out_dir, overwrite_patches=True)
