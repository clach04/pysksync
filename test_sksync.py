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


def create_test_files(testdir='tmp_testsuitedir', data_override=None):
    
    safe_rmtree(testdir)
    safe_mkdir(testdir)
    
    for filename in test_fixtures:
        mtime, data = test_fixtures[filename]
        if data_override:
            data = data_override
        mtime = int(mtime)
        filename = os.path.join(testdir, filename)
        filename = os.path.abspath(filename)  # just in case...
        f = open(filename, 'wb')
        f.write(data)
        f.close()
        os.utime(filename, (mtime, mtime))


def perform_sync(server_dir, client_dir, HOST='127.0.0.1', PORT=sksync.SKSYNC_DEFAULT_PORT):
    
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
    sksync.client_start_sync(host, port, server_dir, client_dir)
    server.shutdown()


class TestFileWalk(unittest.TestCase):
    def setUp(self):
        # NOTE using Python unittest, setUp() is called before EACH and every
        self.test_dir = os.path.join('tmp_testsuitedir', 'walk')
        create_test_files(testdir=self.test_dir)
        sub_test_dir = os.path.join(self.test_dir, 'subdir1')
        create_test_files(testdir=sub_test_dir)
    
    def test_non_recursive_dir(self):
        file_list = sksync.get_file_listings(self.test_dir, recursive=False, include_size=True, return_list=True)
        canon = [('test3.txt', 1345316010000L, 1L), ('test1.txt', 1345316082000L, 1L), ('test2.txt', 1345316070000L, 1L)]
        self.assertEqual(canon, file_list)

    def test_recursive_dir(self):
        file_list = sksync.get_file_listings(self.test_dir, recursive=True, include_size=True, return_list=True)
        canon = []  # TODO
        self.assertEqual(canon, file_list)


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

        # do sync
        perform_sync(self.server_dir, self.client_dir)
        
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
        # TODO check no other files exist in self.client_dir

    def test_sync_from_server_with_times_to_empty_client_directory_dynamic(self):
        safe_rmtree(self.client_dir)
        safe_mkdir(self.client_dir)
        result = os.path.isdir(self.server_dir)
        
        # basically a duplicate of
        # test_sync_from_server_with_times_to_empty_client_directory()
        # but refactored to reduce code by looping through fixtures
        for filename in test_fixtures:
            self.assertTrue(os.path.isfile(os.path.join(self.server_dir, filename)))
        
            self.assertFalse(os.path.isfile(os.path.join(self.client_dir, filename)))

            check_file_contents_and_mtime(self.server_dir, filename)

        # do sync
        perform_sync(self.server_dir, self.client_dir)
        
        # check files exist
        for filename in test_fixtures:
            self.assertTrue(os.path.isfile(os.path.join(self.client_dir, filename)))
            # No need to check if files compare with server versions as we compared server dir with fixture contents
        
            # check file contents
            # check mtimes
            check_file_contents_and_mtime(self.client_dir, filename)
        # TODO check no other files exist in self.client_dir

    def test_sync_from_server_with_times_to_nonempty_client_directory_client_newer(self):
        safe_rmtree(self.client_dir)
        safe_mkdir(self.client_dir)
        result = os.path.isdir(self.server_dir)
        
        # Ensure server sends no files if the client already has files of same name that are ahead of the server files
        test_string = 'NEVER_INCLUDE_THIS_STRING_IN_TESTS'
        for filename in test_fixtures:
            self.assertTrue(os.path.isfile(os.path.join(self.server_dir, filename)))
            tmp_client_file = os.path.join(self.client_dir, filename)
            f = open(tmp_client_file, 'wb')
            f.write(test_string)
            f.close()  # assume mtime is ahead of fixtures mtimes
            self.assertTrue(os.path.isfile(tmp_client_file))

            check_file_contents_and_mtime(self.server_dir, filename)

        # do sync
        perform_sync(self.server_dir, self.client_dir)
        
        # check files exist
        for filename in test_fixtures:
            self.assertTrue(os.path.isfile(os.path.join(self.client_dir, filename)))
            # No need to check if files compare with server versions as we compared server dir with fixture contents
        
            # check file contents are not the server contents
            # do not check mtimes
            tmp_client_file = os.path.join(self.client_dir, filename)
            f = open(tmp_client_file, 'rb')
            data = f.read()
            f.close()
            assert test_string 
            self.assertEqual(test_string, data, 'server clobbered client file %r' % filename)
        # TODO check no other files exist in self.client_dir

    def test_sync_from_server_with_times_to_nonempty_client_directory_client_same_timestamps(self):
        test_string = 'NEVER_INCLUDE_THIS_STRING_IN_TESTS'
        # Ensure server sends no files if the client already has files of same name that are the same time as the server files
        create_test_files(testdir=self.client_dir, data_override=test_string)
        result = os.path.isdir(self.server_dir)
        
        for filename in test_fixtures:
            self.assertTrue(os.path.isfile(os.path.join(self.server_dir, filename)))
            self.assertTrue(os.path.isfile(os.path.join(self.client_dir, filename)))

            check_file_contents_and_mtime(self.server_dir, filename)

        # do sync
        perform_sync(self.server_dir, self.client_dir)
        
        # check files exist
        for filename in test_fixtures:
            self.assertTrue(os.path.isfile(os.path.join(self.client_dir, filename)))
            # No need to check if files compare with server versions as we compared server dir with fixture contents
        
            # check file contents are not the server contents
            # do not check mtimes
            tmp_client_file = os.path.join(self.client_dir, filename)
            f = open(tmp_client_file, 'rb')
            data = f.read()
            f.close()
            assert test_string 
            self.assertEqual(test_string, data, 'server clobbered client file %r' % filename)
        # TODO check no other files exist in self.client_dir

try:
    TestSKSync.assertTrue
except AttributeError:
    # wow, old unittest
    TestSKSync.assertTrue = TestSKSync.assert_
    TestSKSync.assertFalse = TestSKSync.failIf

if __name__ == '__main__':
    unittest.main()
