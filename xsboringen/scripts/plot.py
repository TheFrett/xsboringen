#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Tom van Steijn, Royal HaskoningDHV
# Erik van Onselen, Deltares

from xsboringen import cross_section
from xsboringen.calc import SandmedianClassifier, AdmixClassifier, LithologyClassifier
from xsboringen.csvfiles import cross_section_to_csv
from xsboringen.datasources import boreholes_from_sources, points_from_sources
from xsboringen.point import PointsOfInterest
from xsboringen.surface import Surface, RefPlane
from xsboringen.solid import Solid
from xsboringen.groundlayermodel import GroundLayerModel
from xsboringen.utils import input_or_default
from xsboringen import plotting
from xsboringen import shapefiles
from xsboringen import styles

import click
import yaml

from collections import ChainMap
from pathlib import Path
import logging
import os

log = logging.getLogger(os.path.basename(__file__))


def plot_cross_section(**kwargs):
    # args
    datasources = kwargs['datasources']
    cross_section_lines = kwargs['cross_section_lines']
    result = kwargs['result']
    config = kwargs['config']

    # optional args
    points_of_interest = kwargs.get('points_of_interest')
    min_depth = kwargs.get('min_depth', 0.)
    buffer_distance = kwargs.get('buffer_distance', 0.)
    xtickstep = kwargs.get('xtickstep')
    ylim = kwargs.get('ylim')
    xlabel = kwargs.get('xlabel')
    ylabel = kwargs.get('ylabel')
    metadata = kwargs.get('metadata')
    
    # optional args for bearing/range labels
    if buffer_distance < 100:
        # labels short enough for horizontal plot
        dist_txt = (kwargs.get('distance_labels'), 0, 'double_line', 'center', 'bottom')
    else:
        # labels must be plot vertically if they become too long
        dist_txt = (kwargs.get('distance_labels'), 90, 'single_line', 'center', 'bottom')
    windlabels = kwargs.get('windlabels')
    winddirs = kwargs.get('winddirs')

    # create image folder
    folder = Path(result['folder'])
    folder.mkdir(exist_ok=True)

    # read boreholes and CPT's from data folders
    admixclassifier = AdmixClassifier(
        config['admix_fieldnames']
        )
    borehole_sources = datasources.get('boreholes') or []
    boreholes = boreholes_from_sources(borehole_sources, admixclassifier)

    # segment styles lookup
    segmentstyles = styles.SegmentStylesLookup(**input_or_default(config, ['styles', 'segments']))

    # vertical styles lookup
    verticalstyles = styles.SimpleStylesLookup(**input_or_default(config, ['styles', 'verticals']))

    # surface styles lookup
    surfacestyles = styles.SimpleStylesLookup(**input_or_default(config, ['styles', 'surfaces']))
    
    # reference plane styles lookup
    referenceplanestyles = styles.SimpleStylesLookup(**input_or_default(config, ['styles', 'referenceplanes']))

    # solid styles lookup
    solidstyles = styles.SimpleStylesLookup(**input_or_default(config, ['styles', 'solids']))

    # translate CPT to lithology if needed
    if result.get('translate_cpt', False):
        ruletype = result.get('cpt_classifier') or 'isbt'
        table = config['cpt_classification']
        lithologyclassifier = LithologyClassifier(table, ruletype=ruletype)
        boreholes = (
            b.to_lithology(lithologyclassifier, admixclassifier)
            for b in boreholes
            )

    # classify sandmedian if needed
    if result.get('classify_sandmedian', False):
        bins = config['sandmedianbins']
        sandmedianclassifier = SandmedianClassifier(bins)
        boreholes = (
            b.update_sandmedianclass(sandmedianclassifier) for b in boreholes
            )

    # simplify if needed
    if result.get('simplify'):
        min_thickness = result.get('min_thickness')
        by_legend = lambda s: {'record': segmentstyles.lookup(s)}

        boreholes = (
            b.simplified(min_thickness=min_thickness, by=by_legend) if b.format in result.get('simplify') 
            else b
            for b in boreholes
            )

    # read points
    point_sources = datasources.get('points') or []
    points = points_from_sources(point_sources)

    # surfaces
    surfaces = datasources.get('surfaces') or []
    
    # reference planes
    refplanes = datasources.get('referenceplanes') or []

    # solids
    solids = datasources.get('solids') or []

    # regis
    regismodel = datasources.get('regismodel')
    if regismodel is not None:
        regismodel = GroundLayerModel.from_folder(
            folder=regismodel['folder'],
            indexfile=regismodel['indexfile'],
            fieldnames=regismodel['fieldnames'],
            delimiter=regismodel.get('delimiter') or ',',
            res=regismodel.get('res', 10.),
            default=config['cross_section_plot']['regis_style'],
            name='Regis',
            )

        # sort regis by layer number
        regismodel.sort()

    # filter missing coordinates and less than minimal depth
    boreholes = [
        b for b in boreholes
        if
        (b.x is not None) and
        (b.y is not None) and
        (b.z is not None) and
        (b.depth is not None) and
        (b.depth >= min_depth)
        ]

    points = [
        p for p in points
        if
        ((p.top is not None) or (p.base is not None))
        ]
    
    if points_of_interest is not None:
        poi = []
        for row in shapefiles.read(points_of_interest['file']):
            poi.append(PointsOfInterest(row, 
                                        row['properties'][points_of_interest.get('labelfield')],
                                        points_of_interest.get('ylim'),
                                        )
                       )
    else:
        poi = None

    # default labels
    defaultlabels = iter(config['defaultlabels'])
    if windlabels is None:
        windlabels = config['defaultwindlabels']
    if winddirs is None:
        winddirs = config['defaultwinddirs']

    # selected set
    selected = cross_section_lines.get('selected')
    if selected is not None:
        selected = set(selected)

    css = []
    for row in shapefiles.read(cross_section_lines['file']):
        # get label
        if cross_section_lines.get('labelfield') is not None:
            label = row['properties'][cross_section_lines['labelfield']]
        else:
            label = next(defaultlabels)

        if (selected is not None) and (label not in selected):
            log.warning('skipping {label:}'.format(label=label))
            continue
        
        if cross_section_lines.get('titlefield') is not None:
            title = row['properties'][cross_section_lines['titlefield']]
        else:
            title = None
            
        if cross_section_lines.get('labeloption') is not None:
            label_option = cross_section_lines['labeloption']
        else:
            label_option = config['defaultlabeloption']  

        # log message
        log.info('cross-section {label:}'.format(label=label))

        # define cross-section
        cs = cross_section.CrossSection(
            geometry=row['geometry'],
            label=label,
            title=title,
            windlabels=windlabels,
            winddirs=winddirs,
            buffer_distance=buffer_distance,
            )

        # add boreholes to cross-section and optionally filter points too close to eachother
        cs.add_boreholes(boreholes)
        if result.get('min_borehole_dist') is not None:
            cs.filter_close_boreholes(result.get('min_borehole_dist'))

        # add points to cross_section
        cs.add_points(points)
        
        # add points of interest
        cs.add_pois(poi)

        # add surfaces to cross-section            
        for surface in surfaces:
            cs.add_surface(Surface(
                name=surface['name'],
                surfacefile=surface['file'],
                res=surface['res'],
                stylekey=surface.get('style') or 'default',
                ))
            
        # add reference planes to cross-section and optionally find and pass 
        # the Surface instance that the reference plane is tied to.
        for refplane in refplanes:  
            tied = refplane.get('tied')
            if tied is not None:
                tied_surface = cs.surfaces[[s.name for s in cs.surfaces].index(tied)] 
            else:
                tied_surface=None
            
            cs.add_refplane(RefPlane(
                name=refplane['name'],
                value=refplane['value'],
                tied_surface=tied_surface,
                stylekey=refplane.get('style') or 'default',
                ))

        # add solids to cross-section
        for solid in solids:
            cs.add_solid(Solid(
                name=solid['name'],
                topfile=solid['topfile'],
                basefile=solid['basefile'],
                res=solid['res'],
                stylekey=solid('style') or 'default',
                ))

        # add regis solids to cross-section
        solidstyles_with_regis = solidstyles.copy(deep=True)
        if regismodel is not None:
            # get coordinates along cross-section line
            _, coords = zip(*cs.discretize(regismodel.res))

            # add solids to cross-section
            for number, solid in regismodel.solids:
                if not regismodel.solid_has_values(solid, coords, ylim):
                    continue
                cs.add_solid(solid)
                solidstyles_with_regis.add(
                    key=solid.name,
                    label=solid.name,
                    record=regismodel.styles.get(solid.name) or {},
                    )

        # definest styles lookup
        plotting_styles = {
            'segments': segmentstyles,
            'verticals': verticalstyles,
            'surfaces': surfacestyles,
            'referenceplanes': referenceplanestyles,
            'solids': solidstyles_with_regis,
            }

        # define plot
        plt = plotting.CrossSectionPlot(
            cross_section=cs,
            config=config['cross_section_plot'],
            styles=plotting_styles,
            xtickstep=xtickstep,
            ylim=ylim,
            xlabel=xlabel,
            ylabel=ylabel,
            dist_txt=dist_txt,
            label_option=label_option,
            metadata=metadata,
            legend_ncol=int(regismodel is not None) + 1,
            )

        # plot and save to PNG file
        if title:
            file_label = title
        else:
            file_label = label        
        
        imagefilename = config['image_filename_format'].format(label=file_label)
        imagefile = folder / imagefilename
        log.info('saving {f.name:}'.format(f=imagefile))
        plt.to_image(str(imagefile))

        # save to CSV file
        csvfilename = config['csv_filename_format'].format(label=file_label)
        csvfile = folder / csvfilename
        log.info('saving {f.name:}'.format(f=csvfile))
        extra_fields = result.get('extra_fields') or {}
        extra_fields = {k: tuple(v) for k, v in extra_fields.items()}
        cross_section_to_csv(cs, str(csvfile),
            extra_fields=extra_fields,
            )

        # collect cross-sections
        css.append(cs)

    # export endpoints
    endpointsfile = folder / 'endpoints.shp'
    shapefiles.export_endpoints(str(endpointsfile), css,
        **config['shapefile'],
        )

    # export projection lines
    projectionlinesfile = folder / 'projectionlines.shp'
    shapefiles.export_projectionlines(str(projectionlinesfile), css,
        **config['shapefile'],
        )
