#!/usr/bin/env python
# -*- coding: us-ascii -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab

import os
import sys
import string
import errno
import shutil
import threading
import unittest


import sksync


HOST, PORT = '127.0.0.1', sksync.SKSYNC_DEFAULT_PORT  # local only consider using a random port (or at least non-default)

test_fixtures = {
    'test1.txt': (1345316082.71875, '1'),
    'test2.txt': (1345316082.71875 - 12, '2'),
    'test3.txt': (1345316082.71875 - 72, '3'),
}


def safe_mkdir(newdir):
    result_dir = os.path.abspath(newdir)
    try:
        os.makedirs(result_dir)
    except OSError, info:
        if info.errno == errno.EEXIST and os.path.isdir(result_dir):
            pass
        else:
            raise


def safe_rmtree(testdir):
    if '*' in testdir:
        raise ValueError('directory name %r appears to contain wildcard' % testdir)
    try:
        shutil.rmtree(testdir)
    except OSError, info:
        if info.errno == errno.ENOENT:
            pass
        else:
            raise


def check_file_contents_and_mtime(pathname, filename):
    """pathname can be empty string
    """
    canon_mtime, canon_data = test_fixtures[filename]
    filename = os.path.join(pathname, filename)
    x = os.stat(filename)
    f = open(filename)
    data = f.read()
    f.close()
    assert canon_data == data
    assert abs(canon_mtime - x.st_mtime) <= 1, 'canon_mtime mismatch x.st_mtime: %r' % ((canon_mtime, x.st_mtime),)  # with in 1 second


def create_test_files(testdir='tmp_testsuitedir'):
    
    safe_rmtree(testdir)
    safe_mkdir(testdir)
    
    for filename in test_fixtures:
        mtime, data = test_fixtures[filename]
        mtime = int(mtime)
        filename = os.path.join(testdir, filename)
        filename = os.path.abspath(filename)  # just in case...
        f = open(filename, 'wb')
        f.write(data)
        f.close()
        os.utime(filename, (mtime, mtime))


class TestSKSync(unittest.TestCase):
    
    def setUp(self):
        # NOTE using Python unittest, setUp() is called before EACH and every
        self.server_dir = os.path.join('tmp_testsuitedir', 'server')
        self.client_dir = os.path.join('tmp_testsuitedir', 'client')
        create_test_files(testdir=self.server_dir)
        pass
    
    def test_sync_from_server_with_times_to_empty_client_directory(self):
        safe_rmtree(self.client_dir)
        safe_mkdir(self.client_dir)
        result = os.path.isdir(self.server_dir)
        
        # for easy of reading - explictly document/check each file
        # rather than looping through fixtures
        self.assertTrue(os.path.isfile(os.path.join(self.server_dir, 'test1.txt')))
        self.assertTrue(os.path.isfile(os.path.join(self.server_dir, 'test2.txt')))
        self.assertTrue(os.path.isfile(os.path.join(self.server_dir, 'test3.txt')))
        
        self.assertFalse(os.path.isfile(os.path.join(self.client_dir, 'test1.txt')))
        self.assertFalse(os.path.isfile(os.path.join(self.client_dir, 'test2.txt')))
        self.assertFalse(os.path.isfile(os.path.join(self.client_dir, 'test3.txt')))

        check_file_contents_and_mtime(self.server_dir, 'test1.txt')
        check_file_contents_and_mtime(self.server_dir, 'test2.txt')
        check_file_contents_and_mtime(self.server_dir, 'test3.txt')

        # Start sync server in thread
        
        server = sksync.MyThreadedTCPServer((HOST, PORT), sksync.MyTCPHandler)
        host, port = server.server_address
        
        # Start a thread with the server, in turn that thread will then start additional threads
        # One additional thread for each client request/connection
        server_thread = threading.Thread(target=server.serve_forever)
        # Exit the server thread when the main thread terminates
        server_thread.daemon = True
        server_thread.start()
        #print "Server loop running in thread:", server_thread.name
        
        # do sync
        sksync.empty_client_paths(host, port, self.server_dir, self.client_dir)  # FIXME rename this function it is mis-named
        server.shutdown()
        
        # check files exist
        self.assertTrue(os.path.isfile(os.path.join(self.client_dir, 'test1.txt')))
        self.assertTrue(os.path.isfile(os.path.join(self.client_dir, 'test2.txt')))
        self.assertTrue(os.path.isfile(os.path.join(self.client_dir, 'test3.txt')))
        
        # No need to check if files compare with server versions as we compared server dir with fixture contents
        
        # check file contents
        # check mtimes
        check_file_contents_and_mtime(self.client_dir, 'test1.txt')
        check_file_contents_and_mtime(self.client_dir, 'test2.txt')
        check_file_contents_and_mtime(self.client_dir, 'test3.txt')


if __name__ == '__main__':
    unittest.main()
