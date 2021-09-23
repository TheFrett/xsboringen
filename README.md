# XSBoringen

Is a python library for processing and plotting borehole and CPT data,
developed for open data formats in the Netherlands. The library contains
a command line interface called `xsb`, for exporting borehole data can
be exported to CSV or shapefile and plotting 2D cross-sections. The
following input formats are supported:

  - Dinoloket XML 1.4 (boreholes only)
  - BRO XML files (boreholes only)
  - Dinoloket GEF (boreholes and CPT's)
  - CSV (boreholes only)

For the cross-sections additional data can be read from raster or
shapefiles. The library was tested and developed on Windows.

## Installation

XSboringen requires Python 3.0 or higher, and has the following
dependencies:

  - click
  - pyyaml
  - numpy
  - matplotlib
  - gdal
  - fiona
  - rasterio
  - shapely
  - xarray

The packages click, pyyaml, numpy and matplotlib can be installed using
pip or conda without problems. The others can be succesfully installed
using conda-forge or by using pip with prebuild wheels (see Christoph
Gohlke's website). It is recommended to install gdal before fiona and
rasterio are installed.

## Usage

The command line interface contains the following commands.

### write\_csv

Read borehole and CPT datasources and export to CSV table.

```
xsb write_csv write_csv.yaml
```

write\_csv.yaml file contains references to the input datasources and
the output file. See the examples folder.

### write\_shape

Read borehole and CPT datasources and export to shapefile.

```
xsb write_shape write_shape.yaml
```

write\_shape.yaml file contains references to the input datasources and
the output file. See the examples folder.

### plot

Read borehole and CPT datasources and plot to 2D cross-sections based on
a polyline shapefile.

```
xsb plot plot.yaml
```

plot.yaml file contains references to the input datasources and the
output folder. See the examples folder.