# LBMOverheadMonitor
Scripts to access and pre-process liveability monitoring data over the entirety of The Netherlands.

## Dataset description
The dataset is comprised of two components, namely the liveability reference data and the overhead imagery. Both sources are available yearly from 2016 onwards as open data. For 2012 to 2016 the aerial images need to be downloaded from ArcGIS Online.

### Liveability reference data
The liveability reference data is derived from the Leefbaarometer (lit: liveability barometer) project undertaken by the Dutch government. This project models both resident opinions on their environment and the price they are willing to pay for it (hedonic pricing). The models use variables from 5 domains (LIST). The overall liveability score of each data point is given as the average z-score between these two models. The contribution of each domain to the overall liveability of a data point can be traced back by assessing the cumulative positive and negative contributions of all variables belonging to each domain. Both the domain scores and the overall liveability scores are released to the public. The dataset is released through a 100x100-meter resolution grid with square cells that is available for every built-up area across the country. Between 2012 and 2020 it is available in yearly timesteps, and it is due to continue being updated. The results of the liveability model is verified to be accurate through conversations with policy makers in several cities. 

### Aerial images
The matching aerial overhead images are made available free of charge by the Dutch government. From 2016 onward there is a yearly single aerial image at 0.25m resolution with RGB and near-infrared bands. The aerial images are made available through the Dutch open data repository:

2012-2015: https://www.arcgis.com/home/item.html?id=fd0e5e9397784a23a0f642cfb80ab434 (requires ArcGIS Online access)
2016-now: https://opendata.beeldmateriaal.nl/pages/webservices (open data)

From 2016 onwards the aerial images are made available through a WMTS. It can be loaded into any GIS software such as QGIS and extracted from there.

### Data pre-processing
We provide scripts to pre-process the data that users have downloaded into a dataset that can be used for deep learning tasks. Below is a graphical overview of the contents of each patch.

<img src="https://github.com/Bixbeat/LBMOverheadMonitor/blob/main/figures/lbm_3_gt.png" height="300"> 

**Workflow**
1. Download the reference dataset in the areas of interest from the LBM WFS
2. Download the aerial overhead image for the areas of interest at the reference year of choice from its respective WMS
3. Add your folders in the path of the script ""
4. Run the script

The output of the script is a GeoJSON file which contains all the labels for all grid cells in the reference dataset, as well as a folder containing the patches for the given region. We provide a PyTorch dataloader implementation with which the cells can be loaded.
