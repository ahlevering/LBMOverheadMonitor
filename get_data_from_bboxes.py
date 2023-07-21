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

labels_df = gpd.GeoDataFrame()

# Examples. Should be a list of city names & a list of bbox tuples, one for each city
cities = ["utrecht"]  # , "haarlem", "maastricht", "tilburg", "leeuwarden", "den haag", "alkmaar", "zwolle"]
bboxes = [(139267, 456844, 139267 + 4000, 456844 + 4000)]

# years = [8, *list(range(12, 21))]
years = [12, 20]
for year in years:
    for i, _ in enumerate(cities):
        city = cities[i]
        bbox = bboxes[i]
        print(f"Processing {year} {city}")

        # ### DOWNLOAD FROM WFS ###
        if DOWNLOAD_LABELS:
            wfs_url = "https://geo.leefbaarometer.nl/lbm3/ows?service=WFS"
            labels_df = gpd.GeoDataFrame()

            for year in years:
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
            if not Path(f"{out_dir}{city}_{year}.tiff").exists():
                Path(out_dir).mkdir(exist_ok=True, parents=True)

                downloader = WMTSRasterDownloader(year, city, bbox, OFFSET, OUT_PIXEL_SIZE, out_dir)
                downloader.download_raster_tile()

    if DOWNLOAD_LABELS:
        labels_df.to_file(f"{BASE_DIR}/labels.geojson", driver="GeoJSON")
