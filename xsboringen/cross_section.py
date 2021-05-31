# -*- coding: utf-8 -*-
# Tom van Steijn, Royal HaskoningDHV

from shapely.geometry import asShape, Point
from math import atan2, degrees
import numpy as np


class CrossSection(object):
    
    def __init__(self, geometry, buffer_distance, label=None, title=None, 
                 windlabels=None, winddirs=None):
        self.geometry = geometry
        self.buffer_distance = buffer_distance
        self.label = label
        self.title = title

        # geometric buffer with given distance
        self.buffer = self.shape.buffer(buffer_distance)

        # initialize data atttributes to empty lists
        self.boreholes = []
        self.points = []
        self.pois = []
        self.surfaces = []
        self.refplanes = []
        self.solids = []
        
        # initialize bearing and range options
        self.winds = windlabels
        self.dirs = np.array(winddirs)

    def __repr__(self):
        return ('{s.__class__.__name__:}(length={s.length:.2f}, '
                'buffer_distance={s.buffer_distance:.2f}, '
                'label={s.label:})').format(s=self)

    @property
    def shape(self):
        return asShape(self.geometry)

    @property
    def length(self):
        return self.shape.length
    
    @property
    def borehole_density(self):
        return (len(self.boreholes)/self.length)*100
    
    @property
    def cpt_metadata(self):
        cpts = [b[1].format for b in self.boreholes if 'CPT' in b[1].format]
        return (len(cpts), (len(cpts)/self.length)*100)
    
    @property
    def borehole_metadata(self):
        boreholes = [b[1].format for b in self.boreholes if 'Borehole' in b[1].format]
        return (len(boreholes), (len(boreholes)/self.length)*100) 

    @property
    def wind_label_l(self):
        _,label_l = self.wind_label(self.shape.xy[0][0], 
                                    self.shape.xy[1][0],
                                    self.shape.xy[0][1],
                                    self.shape.xy[1][1]
                                    )        
        return(label_l)
    
    @property
    def wind_label_r(self):
        _,label_r = self.wind_label(self.shape.xy[0][1], 
                                    self.shape.xy[1][1],
                                    self.shape.xy[0][0],
                                    self.shape.xy[1][0]
                                    )
        return(label_r)

    def discretize(self, res, start=None):
        '''discretize line to point coords with given distance'''
        d = start or 0.
        while d < self.shape.length:
            p = self.shape.interpolate(d)
            yield d, (p.x, p.y)
            d += res

        p = self.shape.interpolate(self.shape.length)
        yield self.shape.length, (p.x, p.y)

    def add_boreholes(self, boreholes):
        '''add boreholes within buffer distance and project to line'''
        self._add_some_objects(boreholes, self.boreholes)

    def add_points(self, points):
        '''add points within buffer distance and project to line'''
        self._add_some_objects(points, self.points)
        
    def add_pois(self, pois):
        if pois is not None:
            self._add_some_objects(pois, self.pois)

    def _add_some_objects(self, some_objects, dst):
        for an_object in some_objects:
            if asShape(an_object.geometry).within(self.buffer):    
                the_distance = self.shape.project(asShape(an_object.geometry))
                eucli_distance = asShape(an_object.geometry).distance(self.shape)                
                point_on_line = self.shape.interpolate(the_distance)

                xp, yp = asShape(an_object.geometry).xy[0][0], asShape(an_object.geometry).xy[1][0]
                xl, yl = point_on_line.xy[0][0], point_on_line.xy[1][0]
                
                direction, label = self.wind_label(xp, yp, xl, yl)
                
                # explanation: the buffer extends beyond the endpoints of the cross-section
                # points beyond the endpoints but within the buffer are
                # projected at 0. and length distance with a sharp angle
                # these points are not added to the cross-section
                # points exactly at 0. or length distance are also not added
                if (the_distance > 0.) and (the_distance < self.length):
                    an_object.dist_dir = (eucli_distance, direction, label)
                    dst.append((the_distance, an_object))
                    

    def sort(self):
        self.boreholes = [b for b in sorted(self.boreholes)]
        self.points = [p for p in sorted(self.points)]

    def add_surface(self, surface):
        self.surfaces.append(surface)
        
    def add_refplane(self, refplane):
        self.refplanes.append(refplane)

    def add_solid(self, solid):
        self.solids.append(solid)
        
    def wind_label(self, xp, yp, xl, yl):
        angle = atan2(xp-xl, yp-yl)
        bearing = (degrees(angle) + 360) % 360
                       
        wind_dir = self.winds[len(self.dirs)-np.argmax(bearing>self.dirs[::-1])-1]
        
        return(bearing, wind_dir)
        

        
