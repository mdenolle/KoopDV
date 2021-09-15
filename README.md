# KoopDV: Geospatial and temporal predictions of seismic velocities using Koopman methods

Interpolate and extrapolate in time and space the dv/v measurements to create maps of changes in seismic velocities. These perturbations are proportional to shallow strains of Earth materials. Strains can also be obtained using surface displacements with remote sensing (GPS).
Several factors contribute to altering seismic velocities/strains: changes in air temperature, precipitations (subsurface and as surface loads), earthquake damage, long term tectonic loading.


# Data
* dv/v: Data comes from Clements and Denolle (202?) and can be found as a zip file [here](https://www.dropbox.com/s/tz8e6675ikpinqg/DVV-90-DAY-2.0-4.0.zip?dl=0). They are obtained using 20 years of data from the Southern California Seismic Network, the Northern California Seismic Network, and temporary stations/recordings collected on the IRIS-DMC. They are obtained from 2-4Hz single-station ambient noise cross correlations, which gives an approximate perturbation in shear wavespeed of the upper 200m of the Earth crust.
* Weather data: can be obtained using [PRISM Climate data](https://prism.oregonstate.edu/). Tim Clements wrote a Julia [script](./get_prism.jl) to collet the data into a netcdf file, copied in this repos.
* 

# Installation

pip install dpk-forecast


