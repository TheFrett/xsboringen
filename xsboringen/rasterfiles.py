# -*- coding: utf-8 -*-
# Tom van Steijn, Royal HaskoningDHV

try:
    import idfpy
    idfpy_imported = True
except ImportError:
    idfpy_imported = False

import xarray as xr
import numpy as np

from functools import partial
import logging
import os

log = logging.getLogger(os.path.basename(__file__))

def sample_raster(rasterfile, coords):
    log.debug('reading rasterfile {}'.format(os.path.basename(rasterfile)))
    da = xr.open_rasterio(rasterfile).squeeze()
    x_samples = [c[0] for c in coords]
    y_samples = [c[1] for c in coords]  
    profile_y = da.sel(y=y_samples, x=x_samples, method='nearest').values.diagonal()
    
    for value in profile_y:
        if any(np.isclose(value, da.nodatavals)):
            yield np.nan
        elif np.isnan(value):
            yield np.nan
        else:
            yield value


def sample_idf(idffile, coords):
    '''sample IDF file at coords'''
    log.debug('reading idf file {}'.format(os.path.basename(idffile)))
    with idfpy.open(idffile) as src:
        for value in src.sample(coords):
            if value[0] == src.header['nodata']:
                yield np.nan
            elif np.isnan(value[0]) and any(np.isnan(src.header['nodata'])):
                yield np.nan
            else:
                yield float(value[0])


def sample(gridfile, coords):
    '''sample gridfile at coords'''
    if idfpy_imported and gridfile.lower().endswith('.idf'):
        sample = partial(sample_idf)
    else:
        sample = partial(sample_raster)
    return sample(gridfile, coords)
