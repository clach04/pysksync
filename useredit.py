#!/usr/bin/env python
# -*- coding: us-ascii -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
#

import os
import sys
import logging
import binascii

try:
    import getpass
except ImportError:
    class getpass(object):
        def getpass(cls, prompt=None, stream=None):
            if prompt is None:
                prompt = ''
            if stream is None:
                stream = sys.stdout
            prompt = prompt + ' (warning password WILL echo): '
            stream.write(prompt)
            result = raw_input('') # or simply ignore stream??
            return result
        getpass = classmethod(getpass)

import srp

import sksync
from sksync import load_json, dump_json


logging.basicConfig()
logger = logging
logger = logging.getLogger("useredit")
#logger.setLevel(logging.INFO)
#logger.setLevel(logging.DEBUG)


def main(argv=None):
    if argv is None:
        argv = sys.argv

    logger.setLevel(logging.INFO)
    #logger.setLevel(logging.DEBUG)
    try:
        conf_filename = argv[1]
    except IndexError:
        conf_filename = 'sksync.json'
    logger.info('attempting to open config: %r', conf_filename)
    try:
        f = open(conf_filename, 'rb')
        config = load_json(f.read())
        f.close()
    except IOError:
        config = {}

    # defaults
    config['users'] = config.get('users', {})

    username = raw_input('Username: ')
    password = getpass.getpass('"%s" Password: ' % username)
    password2 = None
    while password != password2:
        password2 = getpass.getpass('Confirm password: ')

    salt, vkey = srp.create_salted_verification_key(username, password)
    salt, vkey = binascii.hexlify(salt), binascii.hexlify(vkey)
    config['users'][username] = config['users'].get('username', {})
    config['users'][username]['authsrp'] = salt, vkey

    raw_json = dump_json(config, indent=4)
    logger.info('attempting to open config for write: %r', conf_filename)
    f = open(conf_filename, 'wb')
    f.write(raw_json)
    f.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
