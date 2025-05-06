#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jul 12 16:53:05 2022

@author: controls
"""

from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from Picket_fence_code_v2 import PicketFence, picketFenceArguments
import logging


def main():
    parser = ArgumentParser(prog='Picket_Fence',
                            description='Plot seedlink seismic data for LIGO',
                            formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('-v', '--verbose', default=False,
                        action="store_true", dest="verbose",
                        help='show verbose debugging output')
    parser.add_argument('--epics', default=False, action="store_true",
                        dest="epics", help="set EPICS variables in IOC")

    # parse the arguments
    runtimeArgs = parser.parse_args()

    #copy arguments over the default
    args=picketFenceArguments()
    args.verbose=runtimeArgs.verbose
    args.send_epics=runtimeArgs.epics
    
    if args.verbose:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.CRITICAL
    logging.basicConfig(level=loglevel)
    
	#select the picket stations from the curated list of allowed stations - ELB 09/26/2023
    pickets= ["LRAL", "MIAR", "TGUH", "HKT", "DWPF","KVTX"]
    
    #specify the data for the observatory we want to monitor:
    observatory={
                "LLO":{
                    "Latitude": 30.5630,
                    "Longitude":-90.7742,
                    "EPICS_prefix":"L1:SEI-USGS_",
                    },
                }
                    
    #initialize a picket fence instance
    pf=PicketFence(picket_list=pickets,myargs=args,epics_prefix=observatory["LLO"]["EPICS_prefix"], observatory_info=observatory) #TODO: change this backwards compatible call
    pf.run()

if __name__ == '__main__':
    main()
