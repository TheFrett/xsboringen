# -*- coding: utf-8 -*-
# Tom van Steijn, Royal HaskoningDHV

from xsboringen.borehole import Borehole, Segment
from xsboringen import utils

from itertools import chain
from xml.etree import ElementTree
from pathlib import Path
import datetime
import logging
import glob
import csv
import os
import re

log = logging.getLogger(os.path.basename(__file__))


def dino_boreholes_from_xml(folder, version, extra_fields, use_filename):
    xmlfiles = utils.careful_glob(folder, '*{:.1f}.xml'.format(version))
    for xmlfile in xmlfiles:
        xml = XMLBoreholeFile(xmlfile, 'Dino XML Borehole')
        borehole = xml.dino_to_borehole(extra_fields, use_filename)
        if borehole is not None:
            yield borehole

def bro_boreholes_from_xml(folder, extra_fields, use_filename):
    xmlfiles = utils.careful_glob(folder, '*.xml')
    for xmlfile in xmlfiles:
        xml = XMLBoreholeFile(xmlfile, 'BRO XML Borehole')
        borehole = xml.bro_to_borehole(extra_fields, use_filename)
        if borehole is not None:
            yield borehole


class XMLFile(object):
    # format field
    _format = None

    def __init__(self, xmlfile, format):
        self.file = Path(xmlfile).resolve()
        self._format = format
        self.attrs = {
            'source': self.file.name,
            'format': self._format,
            }

        log.debug('reading {s.file.name:}'.format(s=self))
        self.root = ElementTree.parse(xmlfile).getroot()

        # Find namespaces (used in BRO XML format)
        ns = dict([
        node for _, node in ElementTree.iterparse(
         xmlfile, events=['start-ns'])
        ])

        # Convert namespaces to common names (e.g. Wiertsema & Partners uses different namespace ids than BROloket)
        self.ns = utils.find_bro_xml_namespaces(ns)


class XMLBoreholeFile(XMLFile):

    @staticmethod
    def safe_int(s):
        try:
            return int(s)
        except TypeError:
            return None

    @staticmethod
    def safe_float(s):
        try:
            return float(s)
        except TypeError:
            return None

    @staticmethod
    def find_child(root, namespaces, options):
        """
        find the first valid child in the root based on a number of options
        """
        for option in options:
            result = root.find(option, namespaces)
            if result is not None:
                return result

    @classmethod
    def cast(cls, s, dtype):
        if dtype == 'float':
            return cls.safe_float(s)
        elif dtype == 'int':
            return cls.safe_int(s)
        else:
            return s

    @classmethod
    def read_dino_segments(cls, survey, fields=None):
        '''read segments from XML and yield as Segment'''
        fields = fields or {}
        intervals = survey.findall('borehole/lithoDescr/lithoInterval')
        for interval in intervals:
            # top and base
            top = cls.safe_float(interval.attrib.get('topDepth')) * 1e-2  # to m
            base = cls.safe_float(interval.attrib.get('baseDepth')) * 1e-2  # to m

            # attrs
            attrs = {}

            # lithology
            lithology = interval.find('lithology').attrib.get('code')

            # sandmedianclass
            try:
                sandmedianclass = interval.find(
                    'sandMedianClass').attrib.get('code')[:3]
            except AttributeError:
                sandmedianclass = None

            # sand median
            try:
                attrs['sandmedian'] = cls.safe_float(interval.find(
                    'sandMedian').attrib.get('median'))
            except AttributeError:
                attrs['sandmedian'] = None

            for field in fields:
                path, attrib = field['match'].split('@')
                element = interval.find(path.rstrip('/'))
                if element is None:
                    continue
                value = element.attrib.get(attrib)
                if value is None:
                    continue
                attrs[field['name']] = cls.cast(value, field['dtype'])

            # yield segment
            yield Segment(top, base, lithology, sandmedianclass, **attrs)

    @classmethod
    def read_bro_segments(cls, survey, ns, fields=None, to_5104=True):
        '''read segments from XML and yield as Segment'''
        fields = fields or {}
        find_median = re.compile(r'\d+')
        intervals = survey.findall('bhrgt:boreholeSampleDescription/bhrgtcom:descriptiveBoreholeLog/bhrgtcom:layer', ns)
        for interval in intervals:
            # top and base
            top = cls.safe_float(interval.find('bhrgtcom:upperBoundary', ns).text) 
            base = cls.safe_float(interval.find('bhrgtcom:lowerBoundary', ns).text) 

            # attrs
            attrs = {}

            # lithology
            try:
                lithology = interval.find('bhrgtcom:soil/bhrgtcom:geotechnicalSoilName', ns).text
            except AttributeError:
                yield Segment(top, base, 'NBE', None, **attrs)
                continue

            if to_5104:
                lithology, admix, admix_intensity  = utils.lithoclass_14688_to_5104(lithology)
                if admix is not None:
                    attrs['admix'] = admix
                    attrs['admix_intensity'] = admix_intensity
                    attrs['admix_string'] = admix_intensity + admix

            # sandmedianclass
            try:
                sandmedianclass = interval.find('bhrgtcom:soil/bhrgtcom:sandMedianClass', ns).text
            except AttributeError:
                sandmedianclass = None

            # sand median
            medians = find_median.findall(str(sandmedianclass)) or None
            if medians is not None:
                attrs['sandmedian'] = (int(medians[0]) + int(medians[1])) / 2
                if to_5104:
                    sandmedianclass = utils.sandmedian_to_5104(attrs['sandmedian'])
            else:
                attrs['sandmedian'] = None
            
            # Extra fields only possible in bhrgtcom:soil, not bhrgtcom:layer.
            for field in fields:
                path, attrib = field['match'].split('@')
                element_to_find = 'bhrgtcom:'+ path.rstrip('/')
                element = interval.find(f'bhrgtcom:soil/{element_to_find}', ns)
                if element is None:
                    continue
                value = element.text
                if value is None:
                    continue
                attrs[field['name']] = cls.cast(value, field['dtype'])

            # yield segment
            yield Segment(top, base, lithology, sandmedianclass, **attrs)

    @staticmethod
    def depth_from_segments(segments):
        log.debug('calculating depth from segments')
        return max(s.base for s in segments)

    def dino_to_borehole(self, extra_fields=None, use_filename=False):
        '''read Dinoloket XML file and return Borehole'''
        # extra fields
        extra_fields = extra_fields or {}
        borehole_fields = extra_fields.get('borehole') or None
        segment_fields = extra_fields.get('segments') or None

        # code
        survey = self.root.find('pointSurvey')
        if use_filename:
            code = self.attrs['source'].split('.')[0]
        else:
            code = survey.find('identification').attrib.get('id')

        # timestamp of borehole
        date = survey.find('borehole/date')
        try:
            year = self.safe_int(date.attrib.get('startYear'))
            month = self.safe_int(date.attrib.get('startMonth'))
            day = self.safe_int(date.attrib.get('startDay'))
            if year and month and day:
                timestamp = datetime.datetime(year, month, day).isoformat()
            elif year and month:
                timestamp = datetime.datetime(year, month, 1).isoformat()
            elif year:
                timestamp = datetime.datetime(year, 1, 1).isoformat()
            else:
                timestamp = None
        except AttributeError:
            timestamp = None
        self.attrs['timestamp'] = timestamp

        # segments as list
        segments = [s for s in self.read_dino_segments(survey, segment_fields)]

        # final depth of borehole in m
        basedepth = survey.find('borehole').attrib.get('baseDepth')
        depth = self.safe_float(basedepth)
        try:
            depth *= 1e-2  # to m
        except TypeError:
            depth = self.depth_from_segments(segments)

        # x,y coordinates
        coordinates = survey.find('surveyLocation/coordinates')
        x = self.safe_float(coordinates.find('coordinateX').text)
        y = self.safe_float(coordinates.find('coordinateY').text)

        # elevation in m
        elevation = survey.find('surfaceElevation/elevation')
        if not elevation is None:
            z = self.safe_float(elevation.attrib.get('levelValue'))
            try:
                z *= 1e-2  # to m
            except TypeError:
                z = None
        else:
            z = None

        return Borehole(code, depth,
            x=x, y=y, z=z,
            segments=segments,
            **self.attrs,
            )

    def bro_to_borehole(self, extra_fields=None, use_filename=True):
        '''read Bro XML file and return Borehole'''
        # extra fields
        extra_fields = extra_fields or {}
        borehole_fields = extra_fields.get('borehole') or None
        segment_fields = extra_fields.get('segments') or None

        # code
        survey = self.find_child(self.root, self.ns, ['bhrgt:sourceDocument/bhrgt:BHR_GT_CompleteReport_V1',
                                                  'bhrgt:dispatchDocument/bhrgt:BHR_GT_O'])
        if use_filename:
            code = self.attrs['source'].split('.')[0]
        else: 
            if survey.find('brocom:broId', self.ns) is None:                                         
                code = survey.attrib.get('{'+self.ns['gml']+'}id')
            else:
                code = survey.find('brocom:broId', self.ns).text


        # timestamp of borehole
        date = survey.find('bhrgt:boring/bhrgtcom:boringEndDate/brocom:date', self.ns).text.split('-')
        try:
            year = self.safe_int(date[0])
            month = self.safe_int(date[1])
            day = self.safe_int(date[2])
            if year and month and day:
                timestamp = datetime.datetime(year, month, day).isoformat()
            elif year and month:
                timestamp = datetime.datetime(year, month, 1).isoformat()
            elif year:
                timestamp = datetime.datetime(year, 1, 1).isoformat()
            else:
                timestamp = None
        except AttributeError:
            timestamp = None
        self.attrs['timestamp'] = timestamp

        # segments as list
        segments = [s for s in self.read_bro_segments(survey, self.ns, fields=segment_fields)]

        # final depth of borehole in m
        basedepth = survey.find('bhrgt:boring/bhrgtcom:finalDepthBoring', self.ns).text
        depth = self.safe_float(basedepth)
        try:
            depth *= 1  
        except TypeError:
            depth = self.depth_from_segments(segments)

        # x,y coordinates
        coordinates = survey.find('bhrgt:deliveredLocation/bhrgtcom:location/gml:Point/gml:pos', self.ns).text.split(' ')
        x = self.safe_float(coordinates[0])
        y = self.safe_float(coordinates[1])

        # elevation in m
        elevation = survey.find('bhrgt:deliveredVerticalPosition/bhrgtcom:offset', self.ns).text
        if not elevation is None:
            z = self.safe_float(elevation)
            try:
                z *= 1  # to m
            except TypeError:
                z = None
        else:
            z = None

        return Borehole(code, depth,
            x=x, y=y, z=z,
            segments=segments,
            **self.attrs,
            )
