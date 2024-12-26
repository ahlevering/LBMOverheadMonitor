import geopandas as gpd
from owslib.wfs import WebFeatureService
from pathlib import Path

from utils.wmts import WMTSRasterDownloader
from utils.labels import download_labels, update_labels_df
import warnings

warnings.filterwarnings("ignore")  # Silencing repeated Pandas warnings

### SETTINGS ###
OUT_PIXEL_SIZE = 1  # in meters. Min resolution is ~0.105m (because of tileset).
BASE_DIR = "data/tiles_nl/"
DOWNLOAD_LABELS = True
ADD_DOMAIN_SCORES = True
DOWNLOAD_IMAGES = False
OFFSET = 200  # Pad the raster with extra pixels to allow side-overlap of patches at the edges
MUNICIPALITIES = ['Amsterdam']#['Rotterdam', 'Utrecht', 'Groningen', "\'s-Gravenhage"]
KEEP_ONLY_IN_POLY = True # False == keep all images/labels within square bounding box around each municipality

url = 'https://service.pdok.nl/kadaster/bestuurlijkegebieden/wfs/v1_0?request=GetCapabilities&service=WFS'
wfs = WebFeatureService(url=url, version='2.0.0')
response = wfs.getfeature(typename='bestuurlijkegebieden:Gemeentegebied', outputFormat='application/json')
municipalities_gdf = gpd.read_file(response)
municipalities_gdf = municipalities_gdf[municipalities_gdf['naam'].isin(MUNICIPALITIES)]

labels_df = gpd.GeoDataFrame()
years = [20] #[8, *list(range(12, 21))]
for year in years:
    for municipality in MUNICIPALITIES:
        entry = municipalities_gdf[municipalities_gdf['naam'] == municipality]
        bbox = entry.total_bounds
        # ### DOWNLOAD FROM WFS ###
        wfs_url = "https://geo.leefbaarometer.nl/lbm3/ows?service=WFS"
        year_labels_df = download_labels(wfs_url, year, bbox, municipality, ADD_DOMAIN_SCORES)
        to_keep = [
            col
            for col in [
                'gridcode',
                f"liveability_{year}",
                f"phys_env_{year}",
                f"safety_{year}",
                f"amenities_{year}",
                f"cohesion_{year}",
                f"buildings_{year}",
                'set',
                "municipality",
                "geometry",                
            ]
            if col in year_labels_df.keys()
        ]
        year_labels_df = year_labels_df[to_keep]
        year_labels_df = year_labels_df.dropna()
        labels_df = update_labels_df(labels_df, year_labels_df, to_keep, year, years)
        if KEEP_ONLY_IN_POLY:
            labels_df = labels_df[labels_df['municipality'].isin(MUNICIPALITIES)]

        ### WMTS ###
        if DOWNLOAD_IMAGES:
            # File server functions
            # https://gis.stackexchange.com/questions/339484/qwc2-how-to-calculate-wmts-resolutions
            out_dir = f"{BASE_DIR}{year}/"
            for cell in labels_df.iterrows():
                if not Path(f"{out_dir}{cell[1]['id']}.tiff").exists():
                    try:
                        Path(out_dir).mkdir(exist_ok=True, parents=True)
                        bbox = cell[1]['geometry'].bounds
                        downloader = WMTSRasterDownloader(year, municipality, bbox, OFFSET, OUT_PIXEL_SIZE, out_dir)
                        downloader.download_raster_tile(f"{out_dir}{cell[1]['id']}.tiff")
                    except Exception as e:
                        print(e)

    labels_df.to_file(f"{BASE_DIR}/ams_lbm_labels.gpkg", driver="GPKG")
