# LBMOverheadMonitor

Scripts to access and pre-process liveability monitoring data over the entirety of The Netherlands.

## Dataset description
The dataset is comprised of two components, namely the liveability reference data and the overhead imagery.

### Liveability reference data
The liveability reference data is derived from the Leefbaarometer (lit: liveability barometer) project undertaken by the Dutch government. This project models both resident opinions on their environment and the price they are willing to pay for it (hedonic pricing). The models use variables from 5 domain scores which A combination of the two models is the final reference dataset that is released to the public. The results are verified to be accurate through conversations with policy makers in several cities. The reference dataset also contains the contribution of each domain to the overall liveability of the area. The dataset is released through a 100x100-meter resolution grid with square cells that is available for every built-up area across the country. Between 2012 and 2020 it is available in yearly timesteps, and it is due to continue being updated.

### Aerial images
The matching aerial overhead images are made available free of charge by the Dutch government. From 2014 onward there is a yearly single aerial image at 0.25m resolution with RGB and near-infrared bands. Through these scripts, custom datasets can be downloaded at the desired resolution.

CAVEATS: The provided scripts are poorly optimized and slow as they download tiles and adds them to a single raster image in a single-threaded manner. A sufficiently technical person can download the raster image through a GIS much faster. These scripts will do the job, but for the highest resolution (25cm) it is advised to use a GIS to download the images.

### Patching
We also provide a script which generates a raster patch overlapping with each grid cell. The resulting patches have 700m total patch size by default with 300m effective side-overlap. This is done to match the most common feature distance inclusion (e.g. "number of houses" within 300m). It can go up to 500-1'000 meters though, so some information will not be seen in the image.