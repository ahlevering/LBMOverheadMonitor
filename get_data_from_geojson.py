import geopandas as gpd
from pathlib import Path

from utils.wmts import WMTSRasterDownloader
from utils.labels import download_labels, update_labels_df
import warnings

warnings.filterwarnings("ignore")  # Silencing repeated Pandas warnings

### SETTINGS ###
OUT_PIXEL_SIZE = 1  # in meters
BASE_DIR = "data/tiles/"
DOWNLOAD_LABELS = True
ADD_DOMAIN_SCORES = True
DOWNLOAD_IMAGES = True
OFFSET = 1200  # Pad the raster with extra pixels to allow side-overlap of patches at the edges

lbm_gdf = gpd.read_file("data/labels_with_splits.geojson")
grouped_cities = lbm_gdf.groupby("region_name")

labels_df = gpd.GeoDataFrame()
years = [8, *list(range(12, 21))]
for year in years:
    for city, cells in grouped_cities:
        city = city.split("_")[0]
        print(f"Processing {year} {city}")
        bbox = cells.total_bounds.tolist()
        # bbox = [bbox[0], bbox[1], bbox[0], bbox[1]]

        # ### DOWNLOAD FROM WFS ###
        if DOWNLOAD_LABELS:
            wfs_url = "https://geo.leefbaarometer.nl/lbm3/ows?service=WFS"
            year_labels_df = download_labels(wfs_url, year, bbox, city, ADD_DOMAIN_SCORES)
            to_join = [
                col
                for col in [
                    "id",
                    "geometry",
                    f"liveability_{year}",
                    f"phys_env_{year}",
                    f"safety_{year}",
                    f"amenities_{year}",
                    f"cohesion_{year}",
                    f"buildings_{year}",
                ]
                if col in year_labels_df.keys()
            ]
            labels_df = update_labels_df(labels_df, year_labels_df, to_join, year, years)

        ### WMTS ###
        if DOWNLOAD_IMAGES:
            # File server functions
            # https://gis.stackexchange.com/questions/339484/qwc2-how-to-calculate-wmts-resolutions
            out_dir = f"{BASE_DIR}{year}/"
            if not Path(f"{out_dir}{city}_{year}_test.tiff").exists():
                Path(out_dir).mkdir(exist_ok=True, parents=True)

                downloader = WMTSRasterDownloader(year, city, bbox, OFFSET, OUT_PIXEL_SIZE, out_dir)
                downloader.download_raster_tile()

    if DOWNLOAD_LABELS:
        labels_df.to_file(f"{BASE_DIR}/labels.geojson", driver="GeoJSON")
