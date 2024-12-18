from requests import Request
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


### WFS FUNCS ###
def unclip_polygon(row):
    centroid = row["geometry"].centroid
    grid_true_center_x = centroid.xy[0][0] - (centroid.xy[0][0] % 100) + 50
    grid_true_center_y = centroid.xy[1][0] - (centroid.xy[1][0] % 100) + 50
    return Point([grid_true_center_x, grid_true_center_y]).buffer(50, cap_style=3)


def get_scores(url, year, bbox, add_domain_scores):
    str_bbox = ",".join(str(coord) for coord in bbox)

    # Check if special subscore endpoint can be used
    if year in [14, 18, 20] and add_domain_scores:        
        layer_name = f"lbm3:clippedgridscore{year}_won" # Any subscore returns entire set now, apparently
        params = dict(
            service="WFS",
            version="2.0.0",
            request="GetFeature",
            typeName=layer_name,
            outputFormat="json",
            bbox=str_bbox,
            srsName="EPSG:28992",
            startIndex=0,
        )
        wfs_request_url = Request("GET", url, params=params).prepare().url
        scores_df = gpd.read_file(wfs_request_url)
    else:
        if year < 10:
            year = "0" + str(year)
        layer_name = f"lbm3:clippedgridscore{year}"
        params = dict(
            service="WFS",
            version="2.0.0",
            request="GetFeature",
            typeName=layer_name,
            outputFormat="json",
            bbox=str_bbox,
            srsName="EPSG:28992",
            startIndex=0,
        )
        wfs_request_url = Request("GET", url, params=params).prepare().url
        scores_df = gpd.read_file(wfs_request_url)        
        
    return scores_df

### LABEL FUNCTIONS ###
def download_labels(wfs_url, year, bbox, city, ADD_DOMAIN_SCORES):
    year_labels_df = get_scores(wfs_url, year, bbox, ADD_DOMAIN_SCORES)
    if len(year_labels_df) > 0:
        year_labels_df["geometry"] = year_labels_df.apply(unclip_polygon, axis=1) # Turn polys back to square
        year_labels_df["set"] = city
        year_labels_df.rename(
            columns={
                "afw": f"liveability_{year}",
                "fys": f"phys_env_{year}",
                "onv": f"safety_{year}",
                "vrz": f"amenities_{year}",
                "soc": f"soc_cohesion_{year}",
                "won": f"building_qual_{year}",
            },
            errors="ignore",
            inplace=True,
        )
    return year_labels_df


def update_labels_df(labels_df, year_labels_df, to_join, year, years):
    if labels_df.empty:
        labels_df = year_labels_df
    elif year == years[0]:
        labels_df = pd.concat([labels_df, year_labels_df], ignore_index=True)
    else:
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
    return labels_df
