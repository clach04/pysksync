#!/usr/bin/env python
# -*- coding: us-ascii -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab

import os
import sys
import string
import errno
import shutil
import socket
import threading
import unittest


import sksync
safe_mkdir = sksync.safe_mkdir

test_fixtures = {
    'test1.txt': (1345316082.71875, '1'),
    'test2.txt': (1345316082.71875 - 12, '2'),
    'test3.txt': (1345316082.71875 - 72, '3'),
}


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


def get_random_port():
    """Determine a port number suitable for listening on"""
    x = socket.socket()
    x.bind(('', 0))
    hostname, host_port = x.getsockname()
    x.close()
    return host_port


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


def perform_sync(server_dir, client_dir, HOST='127.0.0.1', PORT=get_random_port(), recursive=False, config=None):
    config = config or {}
    config['host'] = HOST
    config['port'] = PORT
    config['require_auth'] = config.get('require_auth', False)
    #config['server_path'] = server_dir
    #config['client_path'] = client_dir
    config['testing'] = {}
    config['testing']['server_path'] = server_dir
    config['testing']['client_path'] = client_dir
    config['testing']['recursive'] = recursive
    config = sksync.set_default_config(config)

    # Start sync server in thread
    server = sksync.MyThreadedTCPServer((HOST, PORT), sksync.MyTCPHandler)
    try:
        host, port = server.server_address
        server.sksync_config = config

        # Start a thread with the server, in turn that thread will then start additional threads
        # One additional thread for each client request/connection
        server_thread = threading.Thread(target=server.serve_forever)
        # Exit the server thread when the main thread terminates
        server_thread.daemon = True
        server_thread.start()
        #print "Server loop running in thread:", server_thread.name
        
        # do sync
        sksync.run_client(config, config_name='testing')
    finally:
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
        canon.sort()
        file_list.sort()
        self.assertEqual(canon, file_list)
    
    def test_recursive_dir1(self):
        file_list = list(sksync.path_walker(self.test_dir))
        canon = [os.path.join('subdir1', 'test1.txt'),
                os.path.join('subdir1', 'test2.txt'),
                os.path.join('subdir1', 'test3.txt'),
                os.path.join('test1.txt'),
                os.path.join('test2.txt'),
                os.path.join('test3.txt'),
                ]
        canon.sort()
        file_list.sort()
        self.assertEqual(canon, file_list)
    
    def test_recursive_dir2(self):
        file_list = sksync.get_file_listings(self.test_dir, recursive=True, include_size=True, return_list=True)
        canon = [(os.path.join('subdir1', 'test1.txt'), 1345316082000L, 1L),
                (os.path.join('subdir1', 'test2.txt'), 1345316070000L, 1L),
                (os.path.join('subdir1', 'test3.txt'), 1345316010000L, 1L),
                ('test1.txt', 1345316082000L, 1L),
                ('test2.txt', 1345316070000L, 1L),
                ('test3.txt', 1345316010000L, 1L),
                ]
        canon.sort()
        file_list.sort()
        self.assertEqual(canon, file_list)


class GenericSetup(unittest.TestCase):
    def setUp(self):
        # NOTE using Python unittest, setUp() is called before EACH and every
        self.server_dir = os.path.join('tmp_testsuitedir', 'server')
        self.client_dir = os.path.join('tmp_testsuitedir', 'client')
        create_test_files(testdir=self.server_dir)
        safe_rmtree(self.client_dir)
        safe_mkdir(self.client_dir)
        self.config = {}


class TestSKSync(GenericSetup):

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
        perform_sync(self.server_dir, self.client_dir, config=self.config)
        
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
        perform_sync(self.server_dir, self.client_dir, config=self.config)
        
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
        perform_sync(self.server_dir, self.client_dir, config=self.config)
        
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
        perform_sync(self.server_dir, self.client_dir, config=self.config)
        
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

    def test_sync_from_server_with_times_to_empty_client_directory_recursive(self):
        safe_rmtree(self.client_dir)
        safe_mkdir(self.client_dir)
        server_sub_test_dir = os.path.join(self.server_dir, 'subdir1')
        sub_test_dir = os.path.join(self.client_dir, 'subdir1')
        create_test_files(testdir=server_sub_test_dir)

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
        perform_sync(self.server_dir, self.client_dir, recursive=True)
        #x = raw_input('pausned')
        
        # check files exist
        self.assertTrue(os.path.isfile(os.path.join(self.client_dir, 'test1.txt')))
        self.assertTrue(os.path.isfile(os.path.join(self.client_dir, 'test2.txt')))
        self.assertTrue(os.path.isfile(os.path.join(self.client_dir, 'test3.txt')))
        self.assertTrue(os.path.isfile(os.path.join(sub_test_dir, 'test1.txt')))
        self.assertTrue(os.path.isfile(os.path.join(sub_test_dir, 'test2.txt')))
        self.assertTrue(os.path.isfile(os.path.join(sub_test_dir, 'test3.txt')))
        
        # No need to check if files compare with server versions as we compared server dir with fixture contents
        
        # check file contents
        # check mtimes
        check_file_contents_and_mtime(self.client_dir, 'test1.txt')
        check_file_contents_and_mtime(self.client_dir, 'test2.txt')
        check_file_contents_and_mtime(self.client_dir, 'test3.txt')
        check_file_contents_and_mtime(sub_test_dir, 'test1.txt')
        check_file_contents_and_mtime(sub_test_dir, 'test2.txt')
        check_file_contents_and_mtime(sub_test_dir, 'test3.txt')
        # TODO check no other files exist in self.client_dir


class TestSKSyncWithSSL(GenericSetup):

    def setUp(self):
        GenericSetup.setUp(self)
        self.config['use_ssl'] = True
        # BUT don't set SSL cert/key

    # Cut down and modified version of TestSKSync.test_sync_from_server_with_times_to_empty_client_directory()
    def test_sync_from_server_with_times_to_empty_client_directory(self):
        # Expect SSL errors if SSL requested but no SSL cert/key specified
        safe_rmtree(self.client_dir)
        safe_mkdir(self.client_dir)
        result = os.path.isdir(self.server_dir)

        # clone of perform_sync(server_dir, client_dir, 
        HOST = '127.0.0.1'
        PORT = get_random_port()
        config = self.config
        server_dir, client_dir = self.server_dir, self.client_dir
        recursive = True

        config['host'] = HOST
        config['port'] = PORT
        #config['server_path'] = server_dir
        #config['client_path'] = client_dir
        config['testing'] = {}
        config['testing']['server_path'] = server_dir
        config['testing']['client_path'] = client_dir
        config['testing']['recursive'] = recursive
        config = sksync.set_default_config(config)
        server_config = config.copy()
        # TODO do NOT run server threaded, create thread for client. Then use assertRaises() for server
        server_config['raise_errors'] = False

        # Start sync server in thread
        server = sksync.MyThreadedTCPServer((HOST, PORT), sksync.MyTCPHandler)
        try:
            host, port = server.server_address
            server.sksync_config = server_config

            # Start a thread with the server, in turn that thread will then start additional threads
            # One additional thread for each client request/connection
            server_thread = threading.Thread(target=server.serve_forever)
            # Exit the server thread when the main thread terminates
            server_thread.daemon = True
            server_thread.start()
            
            def local_func_run_client():
                # do sync
                sksync.run_client(config, config_name='testing')
            self.assertRaises(sksync.ssl.SSLError, local_func_run_client)
        finally:
            server.shutdown()

        #local_func()
        #self.assertRaises(sksync.ssl.SSLError, local_func)

class TestSKSyncWithValidAuth(TestSKSync):
    """Repeat tests above but with auth."""

    def setUp(self):
        TestSKSync.setUp(self)
        self.config['require_auth'] = True
        self.config['username'] = 'testuser'
        self.config['password'] = 'testpassword'  # valid password for below
        self.config['users'] = {
            'testuser': {
                'authsrp': [
                    'cf78a7a5', 
                    '7443843a24acb936bfb5d5e0d4184a3fd521d4edd8096cf2ac9cdc62eed1a363d9c4a1bd39cb69c8836eb6f77e757e73b77be766af8547eeab4d9b3be17e2860c81afde7d4d8b5b855635ccd22352e2538b27a30518c65e825f7bb29a7037e79aa144726af2dc24ccae76a8e7a2f97fede87aee5ecab1e1ee7e559ce85fc14767ef25314c121b9c093dcf980caab66c60ae7c426a885e04bcbd761b6289b582a6d194a145932180f9b55f58cb1d937659ded8c9eeb59490705c22263241ead65db01ac218a2b76c49947fdaf4f82c5de79c97f17da1101fc1daf14e7f49beb9b8c4496c4a585805a8b858f159ec2c8d423819f84530f496ee5303d2b2eb6a32b'
                ]
            }
        }


class TestSKSyncWithInvalidAuth(GenericSetup):

    def setUp(self):
        GenericSetup.setUp(self)
        self.config['require_auth'] = True
        self.config['username'] = 'testuser'
        self.config['password'] = 'this is wrong'  # invalid password for below
        self.config['users'] = {
            'testuser': {
                'authsrp': [
                    'cf78a7a5', 
                    '7443843a24acb936bfb5d5e0d4184a3fd521d4edd8096cf2ac9cdc62eed1a363d9c4a1bd39cb69c8836eb6f77e757e73b77be766af8547eeab4d9b3be17e2860c81afde7d4d8b5b855635ccd22352e2538b27a30518c65e825f7bb29a7037e79aa144726af2dc24ccae76a8e7a2f97fede87aee5ecab1e1ee7e559ce85fc14767ef25314c121b9c093dcf980caab66c60ae7c426a885e04bcbd761b6289b582a6d194a145932180f9b55f58cb1d937659ded8c9eeb59490705c22263241ead65db01ac218a2b76c49947fdaf4f82c5de79c97f17da1101fc1daf14e7f49beb9b8c4496c4a585805a8b858f159ec2c8d423819f84530f496ee5303d2b2eb6a32b'
                ]
            }
        }

    # Cut down and modified version of TestSKSync.test_sync_from_server_with_times_to_empty_client_directory()
    def test_sync_from_server_with_times_to_empty_client_directory(self):
        safe_rmtree(self.client_dir)
        safe_mkdir(self.client_dir)
        result = os.path.isdir(self.server_dir)

        # do sync
        perform_sync(self.server_dir, self.client_dir, config=self.config)
        # Both a server and client failure is expected
        # However how they should be reported is not yet specified in the protocol
        # TODO check for failure once failure reporting mechanism is specified


try:
    TestSKSync.assertTrue
except AttributeError:
    # wow, old unittest
    TestSKSync.assertTrue = TestSKSync.assert_
    TestSKSync.assertFalse = TestSKSync.failIf

if __name__ == '__main__':
    #sksync.logger.setLevel(sksync.logging.INFO)  # Debug
    #sksync.logger.setLevel(sksync.logging.DEBUG)  # Debug
    unittest.main()
