# LBMOverheadMonitor

Scripts to access and pre-process liveability monitoring data over the entirety of The Netherlands.

## Dataset description
The dataset is comprised of two components, namely the liveability reference data and the overhead imagery.

### Liveability reference data
The liveability reference data is derived from the Leefbaarometer (lit: liveability barometer) project undertaken by the Dutch government. This project models both resident opinions on their environment and the price they are willing to pay for it (hedonic pricing). The models use variables from 5 domains (LIST). The overall liveability score of each data point is given as the average z-score between these two models. The contribution of each domain to the overall liveability of a data point can be traced back by assessing the cumulative positive and negative contributions of all variables belonging to each domain. Both the domain scores and the overall liveability scores are released to the public. The dataset is released through a 100x100-meter resolution grid with square cells that is available for every built-up area across the country. Between 2012 and 2020 it is available in yearly timesteps, and it is due to continue being updated. The results of the liveability model is verified to be accurate through conversations with policy makers in several cities. 

### Aerial images
The matching aerial overhead images are made available free of charge by the Dutch government. From 2014 onward there is a yearly single aerial image at 0.25m resolution with RGB and near-infrared bands.

### Data processing
We provide scripts to pre-process the data that users have downloaded into a dataset that can be used for deep learning tasks. Below is a graphical overview of the contents of each patch.
![Figure showing the contents of each datapoint after processing](https://github.com/Bixbeat/LBMOverheadMonitor/blob/main/figures/lbm_3_gt.png?raw=true)

