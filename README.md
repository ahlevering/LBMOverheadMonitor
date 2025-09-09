# LBMOverheadMonitor
Scripts to access and pre-process liveability monitoring data over the entirety of The Netherlands.

## Dataset description
The dataset is comprised of two components, namely the liveability reference data and the overhead imagery. Both sources are available yearly from 2016 onwards as open data. For 2012 to 2016 the aerial images need to be downloaded from ArcGIS Online.

### Liveability reference data
The liveability reference data is derived from the [Leefbaarometer](https://www.leefbaarometer.nl/) (lit: liveability barometer) project undertaken by the Dutch government. This project models both resident opinions on their environment and the price they are willing to pay for it (hedonic pricing). The models use variables from 5 domains (LIST). The overall liveability score of each data point is given as the average z-score between these two models. The contribution of each domain to the overall liveability of a data point can be traced back by assessing the cumulative positive and negative contributions of all variables belonging to each domain. Both the domain scores and the overall liveability scores are released to the public. The dataset is released through a 100x100-meter resolution grid with square cells that is available for every built-up area across the country. Between 2012 and 2020 it is available in yearly timesteps, and it is due to continue being updated. The results of the liveability model is verified to be accurate through conversations with policy makers in several cities. More information about how the LBM 3.0 project was designed can be found in its [instrument development manual](https://www.leefbaarometer.nl/resources/LBM3Instrumentontwikkeling.pdf)

#### Download links
The easiest way to access the data is through the web feature service (WFS). The WFS link can be opened in any GIS software.

https://geo.leefbaarometer.nl/lbm3/ows


[A limited amount of the data is available without using the WFS](https://www.leefbaarometer.nl/page/Open%20data) and can be downloaded directly as a ZIP file.

The provided scripts will query the WFS, download all grid cells within a given area, and translate fields.

### Aerial images
The matching aerial overhead images are made available free of charge by the Dutch government. Data from 2012 to 2015 are available through ArcGIS Online, while images from 2016 onwards are published directly as open data.

**2012-2015:** https://www.arcgis.com/home/item.html?id=fd0e5e9397784a23a0f642cfb80ab434 (requires ArcGIS Online access)

**2016-current:** https://opendata.beeldmateriaal.nl/pages/webservices (open data)

The provided scripts query the Web Map Tile Service (WMTS) and download images for a given bounding box. While it gets the job done, it is slower than other downloading solutions, so it is provided as a band-aid solution. This is mostly an issue when downloading high-resolution data (e.g. 30cm or higher).

### Data pre-processing
We provide scripts to pre-process the data that users have downloaded into a dataset that can be used for deep learning tasks. The data is split up into patches of 600 by 600 meters. While the grid cells are released at 100 x 100 meters, they are scaled to 700 by 700 meters in order to match the Leefbaarometer input variables which are over _300 meters walking distance_. As such, there is 300 meters overlap with neighbouring grid cells in every direction. Below is a graphical overview of the contents of each patch.

<img src="https://github.com/Bixbeat/LBMOverheadMonitor/blob/main/lbm_3_gt.png" height="300"> 

### Patching
We also provide a script which generates a raster patch overlapping with each LBM grid cell. The resulting patches have 700m total patch size by default with 300m effective side-overlap. The number of pixels depends on the resolution of the raster tile. This is done to match the most common feature distance inclusion (e.g. "number of houses" within 300m). It can go up to 500-1'000 meters for some indicator variables used by the LBM workflow though, so some information will not be seen in the image.

The output of the script is a GeoJSON file which contains all the labels for all grid cells in the reference dataset, as well as a folder containing the patches for the given bounding box.

**DISCLAIMER**
This project is not affiliated with or endorsed by the Dutch government or the Leefbaarometer. Any work and adaptations to the source data is performed done by the authors without consultation.
