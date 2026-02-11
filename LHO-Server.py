#!/usr/bin/env python3

import subprocess
import sys
import os


def main():
    """
    THIS PROGRAM JUST CALLS THE EPICS SERVER V2 AND IT IS
    STRUCTURED THIS WAY FOR BACKWARDS COMPATIBILITY
    """

    print("starting lho picket fence server")
    prefix = 'H1:SEI-USGS_'
    path = "Picket_fence_EPICS_server_v2.py"
    os.execv('/usr/bin/python3', ['/usr/bin/python3', path, prefix])
    print(f"picket fence closed with return code {result.return_code}")
    sys.exit(0)


if __name__ == '__main__':
    main()
