#!/usr/bin/env python
# -*- coding: us-ascii -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab

import os
import sys
import string
import errno
import shutil
import unittest



def safe_mkdir(newdir):
    result_dir = os.path.abspath(newdir)
    try:
        os.makedirs(result_dir)
    except OSError, info:
        if info.errno == errno.EEXIST and os.path.isdir(result_dir):
            pass
        else:
            raise

def create_test_files(testdir='tmp_testsuitedir'):
    
    test_fixtures = [
        ('test1.txt', 1345316082.71875, '1'),
        ('test2.txt', 1345316082.71875 - 12, '2'),
        ('test3.txt', 1345316082.71875 - 72, '3'),
    ]
    
    if '*' in testdir:
        raise ValueError("directory name appears to contain wildcard")
    try:
        shutil.rmtree(testdir)
    except OSError, info:
        if info.errno == errno.ENOENT:
            pass
        else:
            raise
    safe_mkdir(testdir)
    
    for filename, mtime, data in test_fixtures:
        mtime = int(mtime)
        filename = os.path.join(testdir, filename)
        filename = os.path.abspath(filename)  # just in case...
        f = open(filename, 'wb')
        f.write(data)
        f.close()
        os.utime(filename, (mtime, mtime))
        x = os.stat(filename)

class TestSKSync(unittest.TestCase):
    
    def setUp(self):
        # NOTE using Python unittest, setUp() is called before EACH and every
        self.server_dir = os.path.join('tmp_testsuitedir', 'server')
        create_test_files(testdir=self.server_dir)
        pass
    
    def test1(self):
        result = os.path.isdir(self.server_dir)
        result = os.path.isfile(os.path.join(self.server_dir, 'test1.txt'))
        self.assertEqual(True, result)


if __name__ == '__main__':
    unittest.main()
