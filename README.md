# KoopDV: Geospatial and temporal predictions of seismic velocities using Koopman methods

Interpolate and extrapolate in time and space the dv/v measurements to create maps of changes in seismic velocities. These perturbations are proportional to shallow strains of Earth materials. Strains can also be obtained using surface displacements with remote sensing (GPS).
Several factors contribute to altering seismic velocities/strains: changes in air temperature, precipitations (subsurface and as surface loads), earthquake damage, long term tectonic loading.


# Data
* **dv/v**: Data comes from Clements and Denolle (202?) and can be found as a zip file [here](https://www.dropbox.com/s/tz8e6675ikpinqg/DVV-90-DAY-2.0-4.0.zip?dl=0). They are obtained using 20 years of data from the Southern California Seismic Network, the Northern California Seismic Network, and temporary stations/recordings collected on the IRIS-DMC. They are obtained from 2-4Hz single-station ambient noise cross correlations, which gives an approximate perturbation in shear wavespeed of the upper 200m of the Earth crust. The data comes with a daily resolution. Data is characterized by an annual variability (seasonal weather) and a subdecadal (6-7 year) variability controled by El Nino. Data can be gappy. Data does not start and end at the same time depending on station availability.

* **Seismic stations locations**: in a CSV file here, includes lat, long, elevation. 
* **Weather data**: can be obtained using [PRISM Climate data](https://prism.oregonstate.edu/). Tim Clements wrote a Julia [script](./get_prism.jl) to collet the data into a netcdf file, copied in this repos.
* **GPS data**: download daily positions using the [notebook](./get_gps.ipynb). This will save CSV files with north, east, vertical positions for each stations calculated in the [Nevada Geodetic Lab](http://geodesy.unr.edu/). GPS data is position/velocity. UW colleague Brendan Crowell has scripts to convert this to strain, which should be more similar, in theory, to the dv/v measurements.
* **GPS station locations**: is the GPS site lat-long in a csv file here.
* Other attributes that may play a role: rock type, average shear wave velocity.


# Installation
Dependencies are Mallen et al, 2021 Deep Koopman Forecast module.
Create a conda environment:
``conda env create -f environment.yml``

``conda activate koopdv``

``pip install dpk-forecast``


# Initial tests

koop_dv.ipynb is the initial notebook to make a most basic forecast without train/val/test split to get started.
get_gps.ipnyb is the script to download the GPS time series and put them into a CSV file. Same forecast could be done using these time series! Marine seems to be having bandwidth issues, but will download all of the data offline and upload it on dropbox.


# Initial goals

* improve temporal forecast, hindcast, gap filling using DPK or LSTMs/GRUs at individual sites
* Include geospatial information by joining stations, and adding lat-long information of the seismometers. There is some spatial correlation in southern california. Otherdata from colleague could be even smoother (deeper)
* Include temperature, precipitation, to improve temporal forecast/hindcast/gap filling (additional data set that should help the fit)
* Include GPS time series (or their derivative strains) in the mix to improve the geospatial prediction


