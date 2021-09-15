using ArchGDAL
using Dates
using Glob
using NetCDF
using LightXML

function get_bounds(xml)
    xdoc = parse_file(xml)
    xroot = root(xdoc)
    ces = collect(child_elements(xroot))
    e1 = ces[1]
    t = find_element(e1,"spdom")
    t1 = find_element(t,"bounding")
    westbc = content(find_element(t1,"westbc"))
    eastbc = content(find_element(t1,"eastbc"))
    northbc = content(find_element(t1,"northbc"))
    southbc = content(find_element(t1,"southbc"))
    bounds = parse.(Float64,[westbc,eastbc,southbc,northbc])
    free(xdoc)
    return bounds
end

function read_bil(bil)
    ArchGDAL.read(bil) do dataset
        arr = ArchGDAL.read(dataset)
    end
    arr = arr[:,:,1]
    return rotl90(arr)
end

#### PRECIP #####
# get PRISM data and sort by date 
PRISM = "/media/FOUR/data/PRISMPPT/"
filedirs = glob("*",PRISM)
days = [split(basename(f),"_")[5] for f in filedirs]
ind = sortperm(days)
filedirs = filedirs[ind]
N = length(filedirs)
filename = "/media/FOUR/data/ppt.nc"
isfile(filename) && rm(filename)
varname = "ppt"
all_data = zeros(191,300,N)
lat = zeros(191)
lon = zeros(300)
t = Array{Date}(undef,N)

for ii in eachindex(filedirs)
    date = Date(split(basename(filedirs[ii]),"_")[5],"YYYYmmdd")
    println("Reading $date $ii of $(length(filedirs))")
    xml = glob("*bil.xml",filedirs[ii])[1]
    bounds = get_bounds(xml)
    bil = glob("*bil.bil",filedirs[ii])[1]
    A = read_bil(bil)
    x = range(bounds[1],stop=bounds[2],length=size(A,2))
    y = range(bounds[3],stop=bounds[4],length=size(A,1))


    # extract southern california section
    xind = findall( (x .> -125.) .& (x .< -112.5))
    yind = findall( (y .> 32.) .& (y .< 40.))
    lon[:] = x[xind]
    lat[:] = y[yind]
    A = A[yind,xind]
    all_data[:,:,ii] = A
    t[ii] = date
end

tim = [Dates.datetime2unix(DateTime(d)) for d in t]
attribs = Dict("units" => "mm", "data_min" => -9999., "data_max" =>maximum(all_data))
lonatts = Dict("longname" => "Longitude",
          "units"    => "degrees east")
latatts = Dict("longname" => "Latitude",
          "units"    => "degrees north")
timatts = Dict("longname" => "Time",
          "units"    => "Seconds since 1970")

# convert to netcdf file
nccreate(filename,varname,"lat",lat,latatts,"lon",lon,lonatts,"t",tim,timatts,atts=attribs)
ncwrite(all_data,filename,varname)

#### TEMP #####
# get PRISM data and sort by date 
PRISM = "/media/FOUR/data/PRISMTMEAN/"
filedirs = glob("*",PRISM)
days = [split(basename(f),"_")[5] for f in filedirs]
ind = sortperm(days)
days = days[ind]
filedirs = filedirs[ind]
# only use data after 1999/1/1
dayind = findfirst(days .== "19990101")
days = days[dayind:end]
filedirs = filedirs[dayind:end]
N = length(filedirs)
filename = "/media/FOUR/data/tmean.nc"
isfile(filename) && rm(filename)
varname = "tmean"
all_data = zeros(191,300,N)
lat = zeros(191)
lon = zeros(300)
t = Array{Date}(undef,N)

for ii in eachindex(filedirs)
    date = Date(split(basename(filedirs[ii]),"_")[5],"YYYYmmdd")
    println("Reading $date $ii of $(length(filedirs))")
    xml = glob("*bil.xml",filedirs[ii])[1]
    bounds = get_bounds(xml)
    bil = glob("*bil.bil",filedirs[ii])[1]
    A = read_bil(bil)
    x = range(bounds[1],stop=bounds[2],length=size(A,2))
    y = range(bounds[3],stop=bounds[4],length=size(A,1))


    # extract southern california section
    xind = findall( (x .> -125.) .& (x .< -112.5))
    yind = findall( (y .> 32.) .& (y .< 40.))
    lon[:] = x[xind]
    lat[:] = y[yind]
    A = A[yind,xind]
    all_data[:,:,ii] = A
    t[ii] = date
end

tim = [Dates.datetime2unix(DateTime(d)) for d in t]
attribs = Dict("units" => "C", "data_min" => -9999., "data_max" =>maximum(all_data))
lonatts = Dict("longname" => "Longitude",
          "units"    => "degrees east")
latatts = Dict("longname" => "Latitude",
          "units"    => "degrees north")
timatts = Dict("longname" => "Time",
          "units"    => "Seconds since 1970")

# convert to netcdf file
nccreate(filename,varname,"lat",lat,latatts,"lon",lon,lonatts,"t",tim,timatts,atts=attribs)
ncwrite(all_data,filename,varname)