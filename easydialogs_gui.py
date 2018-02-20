#!/usr/bin/env python
# -*- coding: us-ascii -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
#

import os
import sys
import logging

import sksync

def main(argv=None):
    if argv is None:
        argv = sys.argv

    logging.basicConfig()
    logger = logging.getLogger("sksync_edgui")

    # TODO proper argument parsing
    logger.setLevel(logging.INFO)
    sksync.logger.setLevel(logging.INFO)
    try:
        conf_filename = argv[1]
    except IndexError:
        conf_filename = 'sksync.json'
        # try and locate it
        if not os.path.isfile(conf_filename):
            # Under android current directory doesn't work
            conf_filename = os.path.join(os.path.dirname(__file__), conf_filename)
    logger.info('attempting to open config: %r', conf_filename)
    try:
        f = open(conf_filename, 'rb')
        config = sksync.load_json(f.read())
        f.close()
    except IOError:
        print('config file not found, defaulting config')
        config = {}

    # defaults
    config = sksync.set_default_config(config)

    sksync.easydialogs_gui(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
