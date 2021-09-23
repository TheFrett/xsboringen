#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Tom van Steijn, Royal HaskoningDHV
# Erik van Onselen, Deltares

from pathlib import Path
import glob
import sys
import os
import re

def input_or_default(chainmap_object, keys):
    """Take a chainmap object and try to find keys until the key combination is found
    in one of the maps. In this program it allows a fallback to default styles
    if the styles dict is missing one or more items"""
    def iterate_keys(chainmap, keys):
        for key in keys:
            chainmap = chainmap[key]
            if key == keys[-1]:
                return chainmap    
    
    chainmap_object_maps = chainmap_object.maps    
    
    for i in range(len(chainmap_object_maps)):
        try:
            return iterate_keys(chainmap_object_maps[i], keys)
        except KeyError:
            try:
                return iterate_keys(chainmap_object_maps[i+1], keys)
            except KeyError:
                continue
    return None       


def careful_glob(folder, pattern):
    baseparts = []
    for part in folder.parts:
        if part == '*':
            break
        baseparts.append(part)

    basefolder = Path(*baseparts)
    if not basefolder.exists():
        raise ValueError('folder \'{f:}\' does not exist'.format(
            f=folder,
            ))
    return glob.glob(str(folder / pattern))


def careful_open(filepath, mode):
    return CarefulFileOpener(filepath=filepath, mode=mode)


class CarefulFileOpener(object):
    def __init__(self, filepath, mode):
        self.filepath = Path(filepath)
        self.mode = mode
        self.handle = None

    def __repr__(self):
        return ('{s.__class__.__name__:}(file=\'{s.filepath.name:}\', '
                'mode=\'{s.mode:}\')').format(s=self)

    def retry_dialog(self):
        response = None
        while response not in {'r', 'a'}:
            user_input = input(
                'cannot access \'{fp.name:}\'\n(R)etry, (A)bort?'.format(
                fp=self.filepath,
                ))
            try:
                response = user_input.strip().lower()[0]
            except IndexError:
                pass
        if response == 'r':
            return self.open()
        elif response == 'a':
            sys.exit('aborting')

    def open(self):
        try:
            return open(self.filepath, self.mode)
        except PermissionError:
            return self.retry_dialog()

    def close(self):
        if self.handle is not None:
            self.handle.close()

    def __enter__(self):
        self.handle = self.open()
        return self.handle

    def __exit__(self, type, value, traceback):
        self.close()
        self.handle = None

def find_bro_xml_undeclared_namespaces(common_ns, xml_required_namespaces=['brocom', 'gml', 'bhrgt', 'bhrgtcom']):
    """
    if namespaces are not properly declared, fall back to these defaults. These may need to be 
    updated as BRO standards evolve
    """
    default_ns = {'bhrgt': 'http://www.broservices.nl/xsd/isbhr-gt/1.0',
                  'brocom': 'http://www.broservices.nl/xsd/brocommon/3.0',
                  'gml': 'http://www.opengis.net/gml/3.2',
                  'bhrgtcom': 'http://www.broservices.nl/xsd/bhrgtcommon/1.0'}

    for ns in xml_required_namespaces:
        n = common_ns.get(ns) or None
        if n is None:
            common_ns[ns] = default_ns[ns]
    
    return common_ns       

def find_bro_xml_namespaces(ns):
    common_ns = {}
    for key, value in ns.items():
        if 'brocommon' in value:
            common_ns['brocom'] = value
        elif 'opengis.net/gml' in value:
            common_ns['gml'] = value
        elif 'isbhr-gt' in value or 'dsbhr-gt' in value:
            common_ns['bhrgt'] = value
        elif 'bhrgtcommon' in value:
            common_ns['bhrgtcom'] = value
        else:
            common_ns[key] = value
    
    common_ns = find_bro_xml_undeclared_namespaces(common_ns)

    # Optional keys that are less common, but e.g. Fugro has them in their exported files
    # set_common = set(common_ns.keys())
    # set_ns = set(ns.keys())
    # ns_diff = set_ns.difference(set_common)

    # for nsd in ns_diff:
    #     common_ns[nsd] = ns[nsd]

    return common_ns


# Temporary solutions to translate BRO XML data (newer NEN14688) to DINO XML (old NEN5104)
# Should probably go to a config file later (edit TODO: use already defined bins of the SandmedianClassifier!)
def sandmedian_to_5104(median, type='int'):
    if type == 'int':
        if 62 < median <= 105:
            return 'ZUF'
        elif 105 < median <= 150:
            return 'ZZF'
        elif 150 < median <= 210:
            return 'ZMF'
        elif 210 < median <= 300:
            return 'ZMG'
        elif 300 < median <= 420:
            return 'ZZG'
        elif 420 < median:
            return 'ZUG'
    elif type == 'str':
        if median.lower() == 'fijn':
            return 'ZMF'
        elif median.lower() == 'middelgrof':
            return 'ZMG'

def is_valid_lithoclass(lithoclass):
    return main_lithoclass in ('')

# Mag officieel niet vertaald worden door andere grenzen textuurdriehoek
find_alphanum = re.compile(r'\w+')
find_capital = re.compile(r'[A-Z]+')

def lithoclass_14688_to_5104(lithoclass_14688):
    if lithoclass_14688 == 'zandMetKeitjes':
        return('Z', None, None)
    capitals = find_capital.findall(lithoclass_14688) or None
    main_lithoclass = None
    admix_intensity = None
    admix_type = None

    # so if an admixture is given
    if capitals is not None:
        starts = []
        for capital in capitals:
            find = re.compile(f'{capital}+')
            starts.append(find.search(lithoclass_14688).start())
        if len(capitals) == 1:
            admix_intensity = ''
            admix_type = lithoclass_14688[:starts[0]]
            main_lithoclass = lithoclass_14688[starts[0]:][0]
        elif len(capitals) == 2:
            admix_intensity = lithoclass_14688[:starts[0]]
            admix_type = lithoclass_14688[starts[0]:starts[1]]
            main_lithoclass = lithoclass_14688[starts[1]:][0]
        elif len(capitals) == 3:
            admix_intensity = lithoclass_14688[:starts[0]]
            admix_type = lithoclass_14688[starts[0]:starts[1]]
            main_lithoclass = lithoclass_14688[starts[0]:starts[1]][0]
        elif len(capitals) == 4:
            admix_intensity = lithoclass_14688[:starts[0]]
            admix_type = lithoclass_14688[starts[0]:starts[1]]
            main_lithoclass = lithoclass_14688[starts[1]:starts[2]][0]
        else:
            print('Warning: NEN14688 admixtures not understood')

    else:
        main_lithoclass = find_alphanum.match(lithoclass_14688).group()[0].upper()

    # 14688 kent geen 'leem' maar 'silt'
    if main_lithoclass == 'S':
        main_lithoclass = 'L'

    return(main_lithoclass, admix_type, admix_intensity)


