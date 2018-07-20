#!/usr/bin/env python
# -*- coding: us-ascii -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab

import copy
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


SKIP_TIME_TIME_CHECK = False

# NOTE currently tests are hard coded for 3 files
# fixtures need to contain 3 until test is more dynamic
test_fixtures_us_ascii = {
    'test1.txt': (1345316082.71875, b'1'),
    'test2.txt': (1345316082.71875 - 12, b'2'),
    'test3.txt': (1345316082.71875 - 72, b'3'),
}

test_fixtures_us_ascii_unicode_filenames = {
    u'test1.txt': (1345316082.71875, b'1'),
    u'test2.txt': (1345316082.71875 - 12, b'2'),
    u'test3.txt': (1345316082.71875 - 72, b'3'),
}

# latin1 (i.e. Western European (iso-8559-1, iso-8559-15, and cp1252)
test_fixtures_latin1 = {
    ##u'test\u00DC.txt': (1345316082.71875, b'1'),  # uppercase U-umlaut / U-diaeresis # NOTE case sensitive test
    u'test\u00FC.txt': (1345316082.71875 - 12, b'2'),  # lowercase U-umlaut / U-diaeresis
    u'testB.txt': (1345316082.71875 - 72, b'3'),
    u'testC.txt': (1345316082.71875 - 72, b'4'),
}

# Asia
test_fixtures_asia = {
    u'test\u9152.txt': (1345316082.71875 - 12, b'2'),  # Unicode Han Character 'wine, spirits, liquor, alcoholic beverage
    u'testB.txt': (1345316082.71875 - 72, b'3'),
    u'testC.txt': (1345316082.71875 - 72, b'4'),
}

def safe_rmtree(testdir):
    """Windows fails to delete filenames with characters not in locale
    if directory name was not encoded in Unicode to begin with
    even if directory name is 7 bit clean ASCII!"""
    testdir = sksync.to_unicode(testdir)
    if '*' in testdir:
        raise ValueError('directory name %r appears to contain wildcard' % testdir)
    try:
        shutil.rmtree(testdir)
    except OSError as info:
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


def check_file_contents_and_mtime(pathname, filename, test_fixtures, skip_time_time_check=SKIP_TIME_TIME_CHECK):
    """pathname can be empty string
    """
    canon_mtime, canon_data = test_fixtures[filename]
    filename = os.path.join(pathname, filename)
    x = os.stat(filename)
    f = open(filename, 'rb')
    data = f.read()
    f.close()
    assert canon_data == data, 'for %r; canon %r != results %r' % (filename, canon_data, data)
    if not skip_time_time_check:
        assert abs(canon_mtime - x.st_mtime) <= 1, 'canon_mtime mismatch x.st_mtime: %r' % ((canon_mtime, x.st_mtime),)  # with in 1 second


def create_test_files(test_fixtures, testdir='tmp_testsuitedir', data_override=None):

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
        sksync.set_utime(filename, (mtime, mtime))


def perform_sync(server_dir, client_dir, HOST='127.0.0.1', PORT=get_random_port(), recursive=False, config=None):
    config = config or {}
    config['host'] = HOST
    config['port'] = PORT
    config['require_auth'] = config.get('require_auth', False)
    #config['server_path'] = server_dir
    #config['client_path'] = client_dir
    config['clients'] = config.get('clients', {})
    config['clients']['testing'] = {}
    config['clients']['testing']['server_path'] = server_dir
    config['clients']['testing']['client_path'] = client_dir
    config['clients']['testing']['recursive'] = recursive
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
    def setUp(self, test_fixtures=test_fixtures_us_ascii):
        # NOTE using Python unittest, setUp() is called before EACH and every
        self.test_dir = os.path.join('tmp_testsuitedir', 'walk')
        self.test_fixtures = test_fixtures
        create_test_files(self.test_fixtures, testdir=self.test_dir)
        sub_test_dir = os.path.join(self.test_dir, 'subdir1')
        create_test_files(self.test_fixtures, testdir=sub_test_dir)
    
    def test_non_recursive_dir(self):
        file_list = sksync.get_file_listings(self.test_dir, recursive=False, include_size=True, return_list=True)
        canon = [('test3.txt', 1345316010000, 1), ('test1.txt', 1345316082000, 1), ('test2.txt', 1345316070000, 1)]
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
        canon = [(os.path.join('subdir1', 'test1.txt'), 1345316082000, 1),
                (os.path.join('subdir1', 'test2.txt'), 1345316070000, 1),
                (os.path.join('subdir1', 'test3.txt'), 1345316010000, 1),
                ('test1.txt', 1345316082000, 1),
                ('test2.txt', 1345316070000, 1),
                ('test3.txt', 1345316010000, 1),
                ]
        canon.sort()
        file_list.sort()
        self.assertEqual(canon, file_list)


class GenericSetup(unittest.TestCase):
    def setUp(self, test_fixtures=test_fixtures_us_ascii, server_dir=os.path.join('tmp_testsuitedir', 'server'), client_dir=os.path.join('tmp_testsuitedir', 'client')):
        # NOTE using Python unittest, setUp() is called before EACH and every
        self.server_dir = server_dir
        self.client_dir = client_dir
        self.test_fixtures = test_fixtures
        create_test_files(self.test_fixtures, testdir=self.server_dir)
        safe_rmtree(self.client_dir)
        safe_mkdir(self.client_dir)
        self.config = {}
        test_filenames = list(self.test_fixtures.keys())
        test_filenames.sort()
        for i in range(len(test_filenames)):
            tmp_filename = 'TEST_FILENAME_%d' % (i + 1,)
            setattr(self, tmp_filename, test_filenames[i])

    def check_file_contents_and_mtime(self, pathname, filename, test_fixtures=None, skip_time_time_check=SKIP_TIME_TIME_CHECK):
        if test_fixtures is None:
            test_fixtures = self.test_fixtures
        check_file_contents_and_mtime(pathname, filename, test_fixtures, skip_time_time_check)


    def perform_sync(self, server_dir, client_dir, HOST='127.0.0.1', PORT=get_random_port(), recursive=False, config=None):
        perform_sync(server_dir, client_dir, HOST=HOST, PORT=PORT, recursive=recursive, config=config)


class TestSKSync(GenericSetup):
    def setUp(self, test_fixtures=test_fixtures_us_ascii, server_dir=os.path.join('tmp_testsuitedir', 'server'), client_dir=os.path.join('tmp_testsuitedir', 'client')):
        GenericSetup.setUp(self, test_fixtures, server_dir=server_dir, client_dir=client_dir)

    def test_sync_from_server_with_times_to_empty_client_directory(self):
        #import pdb ; pdb.set_trace()
        safe_rmtree(self.client_dir)
        safe_mkdir(self.client_dir)
        result = os.path.isdir(self.server_dir)
        
        # for easy of reading - explictly document/check each file
        # rather than looping through fixtures
        self.assertTrue(os.path.isfile(os.path.join(self.server_dir, self.TEST_FILENAME_1)))
        self.assertTrue(os.path.isfile(os.path.join(self.server_dir, self.TEST_FILENAME_2)))
        self.assertTrue(os.path.isfile(os.path.join(self.server_dir, self.TEST_FILENAME_3)))
        
        self.assertFalse(os.path.isfile(os.path.join(self.client_dir, self.TEST_FILENAME_1)))
        self.assertFalse(os.path.isfile(os.path.join(self.client_dir, self.TEST_FILENAME_2)))
        self.assertFalse(os.path.isfile(os.path.join(self.client_dir, self.TEST_FILENAME_3)))

        self.check_file_contents_and_mtime(self.server_dir, self.TEST_FILENAME_1)
        self.check_file_contents_and_mtime(self.server_dir, self.TEST_FILENAME_2)
        self.check_file_contents_and_mtime(self.server_dir, self.TEST_FILENAME_3)

        # do sync
        self.perform_sync(self.server_dir, self.client_dir, config=self.config)
        
        # check files exist
        self.assertTrue(os.path.isfile(os.path.join(self.client_dir, self.TEST_FILENAME_1)))
        self.assertTrue(os.path.isfile(os.path.join(self.client_dir, self.TEST_FILENAME_2)))
        self.assertTrue(os.path.isfile(os.path.join(self.client_dir, self.TEST_FILENAME_3)))
        
        # No need to check if files compare with server versions as we compared server dir with fixture contents
        
        # check file contents
        # check mtimes
        self.check_file_contents_and_mtime(self.client_dir, self.TEST_FILENAME_1)
        self.check_file_contents_and_mtime(self.client_dir, self.TEST_FILENAME_2)
        self.check_file_contents_and_mtime(self.client_dir, self.TEST_FILENAME_3)
        # TODO check no other files exist in self.client_dir

    def test_sync_from_server_with_times_to_empty_client_directory_dynamic(self):
        safe_rmtree(self.client_dir)
        safe_mkdir(self.client_dir)
        result = os.path.isdir(self.server_dir)
        
        # basically a duplicate of
        # test_sync_from_server_with_times_to_empty_client_directory()
        # but refactored to reduce code by looping through fixtures
        for filename in self.test_fixtures:
            self.assertTrue(os.path.isfile(os.path.join(self.server_dir, filename)))
        
            self.assertFalse(os.path.isfile(os.path.join(self.client_dir, filename)))

            self.check_file_contents_and_mtime(self.server_dir, filename)

        # do sync
        self.perform_sync(self.server_dir, self.client_dir, config=self.config)
        
        # check files exist
        for filename in self.test_fixtures:
            self.assertTrue(os.path.isfile(os.path.join(self.client_dir, filename)))
            # No need to check if files compare with server versions as we compared server dir with fixture contents
        
            # check file contents
            # check mtimes
            self.check_file_contents_and_mtime(self.client_dir, filename)
        # TODO check no other files exist in self.client_dir

    def test_sync_from_server_with_times_to_nonempty_client_directory_client_newer(self):
        safe_rmtree(self.client_dir)
        safe_mkdir(self.client_dir)
        result = os.path.isdir(self.server_dir)
        
        # Ensure server sends no files if the client already has files of same name that are ahead of the server files
        test_string = b'NEVER_INCLUDE_THIS_STRING_IN_TESTS'
        for filename in self.test_fixtures:
            self.assertTrue(os.path.isfile(os.path.join(self.server_dir, filename)))
            tmp_client_file = os.path.join(self.client_dir, filename)
            f = open(tmp_client_file, 'wb')
            f.write(test_string)
            f.close()  # assume mtime is ahead of fixtures mtimes
            self.assertTrue(os.path.isfile(tmp_client_file))

            self.check_file_contents_and_mtime(self.server_dir, filename)

        # do sync
        self.perform_sync(self.server_dir, self.client_dir, config=self.config)
        
        # check files exist
        for filename in self.test_fixtures:
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
            self.check_file_contents_and_mtime(self.server_dir, filename)
            #self.check_file_contents_and_mtime(self.client_dir, filename)
        # TODO check no other files exist in self.client_dir
        #import pdb ; pdb.set_trace()  # DEBUG

    def test_sync_from_server_with_times_to_nonempty_client_directory_client_same_timestamps(self):
        test_string = b'NEVER_INCLUDE_THIS_STRING_IN_TESTS'
        # Ensure server sends no files if the client already has files of same name that are the same time as the server files
        create_test_files(self.test_fixtures, testdir=self.client_dir, data_override=test_string)
        result = os.path.isdir(self.server_dir)
        
        for filename in self.test_fixtures:
            self.assertTrue(os.path.isfile(os.path.join(self.server_dir, filename)))
            self.assertTrue(os.path.isfile(os.path.join(self.client_dir, filename)))

            self.check_file_contents_and_mtime(self.server_dir, filename)

        # do sync
        self.perform_sync(self.server_dir, self.client_dir, config=self.config)
        
        # check files exist
        for filename in self.test_fixtures:
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
        create_test_files(self.test_fixtures, testdir=server_sub_test_dir)

        result = os.path.isdir(self.server_dir)
        
        # for easy of reading - explictly document/check each file
        # rather than looping through fixtures
        self.assertTrue(os.path.isfile(os.path.join(self.server_dir, self.TEST_FILENAME_1)))
        self.assertTrue(os.path.isfile(os.path.join(self.server_dir, self.TEST_FILENAME_2)))
        self.assertTrue(os.path.isfile(os.path.join(self.server_dir, self.TEST_FILENAME_3)))
        
        self.assertFalse(os.path.isfile(os.path.join(self.client_dir, self.TEST_FILENAME_1)))
        self.assertFalse(os.path.isfile(os.path.join(self.client_dir, self.TEST_FILENAME_2)))
        self.assertFalse(os.path.isfile(os.path.join(self.client_dir, self.TEST_FILENAME_3)))

        self.check_file_contents_and_mtime(self.server_dir, self.TEST_FILENAME_1)
        self.check_file_contents_and_mtime(self.server_dir, self.TEST_FILENAME_2)
        self.check_file_contents_and_mtime(self.server_dir, self.TEST_FILENAME_3)

        # do sync
        self.perform_sync(self.server_dir, self.client_dir, recursive=True)
        #x = raw_input('paused')
        
        # check files exist
        self.assertTrue(os.path.isfile(os.path.join(self.client_dir, self.TEST_FILENAME_1)))
        self.assertTrue(os.path.isfile(os.path.join(self.client_dir, self.TEST_FILENAME_2)))
        self.assertTrue(os.path.isfile(os.path.join(self.client_dir, self.TEST_FILENAME_3)))
        self.assertTrue(os.path.isfile(os.path.join(sub_test_dir, self.TEST_FILENAME_1)))
        self.assertTrue(os.path.isfile(os.path.join(sub_test_dir, self.TEST_FILENAME_2)))
        self.assertTrue(os.path.isfile(os.path.join(sub_test_dir, self.TEST_FILENAME_3)))
        
        # No need to check if files compare with server versions as we compared server dir with fixture contents
        
        # check file contents
        # check mtimes
        self.check_file_contents_and_mtime(self.client_dir, self.TEST_FILENAME_1)
        self.check_file_contents_and_mtime(self.client_dir, self.TEST_FILENAME_2)
        self.check_file_contents_and_mtime(self.client_dir, self.TEST_FILENAME_3)
        self.check_file_contents_and_mtime(sub_test_dir, self.TEST_FILENAME_1)
        self.check_file_contents_and_mtime(sub_test_dir, self.TEST_FILENAME_2)
        self.check_file_contents_and_mtime(sub_test_dir, self.TEST_FILENAME_3)
        # TODO check no other files exist in self.client_dir

    def test_sync_from_server_with_times_to_nonempty_client_directory_client_newer_and_server_newer(self):
        # based on TestSKSync.test_sync_from_server_with_times_to_nonempty_client_directory_client_newer()
        # Update both client and server and ensure correct sync happens

        # setup client dir and server dir with same files
        create_test_files(self.test_fixtures, testdir=self.client_dir)
        local_client_test_fixtures = copy.deepcopy(self.test_fixtures)
        local_server_test_fixtures = copy.deepcopy(local_client_test_fixtures)
        canon_filenames = list(local_client_test_fixtures.keys())
        canon_filenames.sort()
        #import pdb ; pdb.set_trace()

        # update single client file
        test_string = b'client updated'
        filename = canon_filenames[0]  # 'test1.txt'
        local_client_test_fixtures[filename] = (local_client_test_fixtures[filename][0], test_string)
        self.assertTrue(os.path.isfile(os.path.join(self.server_dir, filename)))
        tmp_client_file = os.path.join(self.client_dir, filename)
        f = open(tmp_client_file, 'wb')
        f.write(test_string)
        f.close()  # assume mtime is ahead of fixtures mtimes
        self.assertTrue(os.path.isfile(tmp_client_file))
        self.check_file_contents_and_mtime(self.server_dir, filename)

        # update single server file
        test_string = b'server updated'
        filename = canon_filenames[1]  # 'test2.txt'
        local_server_test_fixtures[filename] = (local_server_test_fixtures[filename][0], test_string)
        local_client_test_fixtures[filename] = local_server_test_fixtures[filename]
        self.assertTrue(os.path.isfile(os.path.join(self.client_dir, filename)))
        tmp_client_file = os.path.join(self.server_dir, filename)
        f = open(tmp_client_file, 'wb')
        f.write(test_string)
        f.close()  # assume mtime is ahead of fixtures mtimes
        self.assertTrue(os.path.isfile(tmp_client_file))
        self.check_file_contents_and_mtime(self.client_dir, filename)

        # do sync
        self.perform_sync(self.server_dir, self.client_dir, config=self.config)

        # check files exist and match
        for filename in local_server_test_fixtures:
            # NOTE assumes local_server_test_fixtures and local_client_test_fixtures have same filenames
            self.assertTrue(os.path.isfile(os.path.join(self.server_dir, filename)))
            self.assertTrue(os.path.isfile(os.path.join(self.client_dir, filename)))
            self.check_file_contents_and_mtime(self.server_dir, filename, test_fixtures=local_server_test_fixtures, skip_time_time_check=True)
            self.check_file_contents_and_mtime(self.client_dir, filename, test_fixtures=local_client_test_fixtures, skip_time_time_check=True)
        # TODO check no other files exist in self.client_dir and self.server_dir
        #import pdb ; pdb.set_trace()  # DEBUG


class TestSKSyncUnicodeType7bitFilenames(TestSKSync):
    # Uses 7 bit ascii filenames, but we use unicode in the fixture
    # mostly a no-op test
    def setUp(self, test_fixtures=test_fixtures_us_ascii_unicode_filenames):
        GenericSetup.setUp(self, test_fixtures)

"""
class TestSKSyncWhitelistFail(TestSKSync):
    def setUp(self, test_fixtures=test_fixtures_us_ascii_unicode_filenames):
        GenericSetup.setUp(self, test_fixtures)
        self.config['server_dir_whitelist'] = ['/must/not/exist/for/this/test']
        # TODO run all tests with assertRaises NotAllowed for server
"""


class TestSKSyncLatin1Files(TestSKSync):
    def setUp(self, test_fixtures=test_fixtures_latin1):
        GenericSetup.setUp(self, test_fixtures)


class TestSKSyncAsiaFiles(TestSKSync):
    def setUp(self, test_fixtures=test_fixtures_asia):
        GenericSetup.setUp(self, test_fixtures)


# document client to server (SKSYNC_PROTOCOL_TYPE_TO_SERVER_USE_TIME) - currently this test is the only documentation
# TODO test bi-directional (SKSYNC_PROTOCOL_TYPE_BIDIRECTIONAL_USE_TIME) sync
class TestSKSyncClientPush(TestSKSync):
    #def setUp(self, test_fixtures=test_fixtures_us_ascii, server_dir=os.path.join('tmp_testsuitedir', 'server'), client_dir=os.path.join('tmp_testsuitedir', 'client')):
    def setUp(self, test_fixtures=test_fixtures_us_ascii, server_dir=os.path.join('tmp_testsuitedir', 'client'), client_dir=os.path.join('tmp_testsuitedir', 'server')):
        # NOTE switch client and server directory
        GenericSetup.setUp(self, test_fixtures, server_dir=server_dir, client_dir=client_dir)

    def perform_sync(self, server_dir, client_dir, HOST='127.0.0.1', PORT=get_random_port(), recursive=False, config=None):
        config = config or {}
        config['host'] = HOST
        config['port'] = PORT
        config['require_auth'] = config.get('require_auth', False)
        #config['server_path'] = server_dir
        #config['client_path'] = client_dir
        config['clients'] = config.get('clients', {})
        config['clients']['testing'] = {}
        config['clients']['testing']['server_path'] = client_dir  # NOTE switch client/server directory
        config['clients']['testing']['client_path'] = server_dir  # NOTE switch client/server directory
        config['clients']['testing']['recursive'] = recursive
        config['clients']['testing']['sync_type'] = sksync.SKSYNC_PROTOCOL_TYPE_TO_SERVER_USE_TIME
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


class TestSKSyncBiDirectionalUseTime(TestSKSync):
    def setUp(self, test_fixtures=test_fixtures_us_ascii, server_dir=os.path.join('tmp_testsuitedir', 'server'), client_dir=os.path.join('tmp_testsuitedir', 'client')):
        #def setUp(self, test_fixtures=test_fixtures_us_ascii, server_dir=os.path.join('tmp_testsuitedir', 'client'), client_dir=os.path.join('tmp_testsuitedir', 'server')):
        # NOTE switch client and server directory
        GenericSetup.setUp(self, test_fixtures, server_dir=server_dir, client_dir=client_dir)

    def perform_sync(self, server_dir, client_dir, HOST='127.0.0.1', PORT=get_random_port(), recursive=False, config=None):
        config = config or {}
        config['host'] = HOST
        config['port'] = PORT
        config['require_auth'] = config.get('require_auth', False)
        #config['server_path'] = server_dir
        #config['client_path'] = client_dir
        config['clients'] = config.get('clients', {})
        config['clients']['testing'] = {}

        #config['clients']['testing']['server_path'] = client_dir  # NOTE switch client/server directory
        #config['clients']['testing']['client_path'] = server_dir  # NOTE switch client/server directory
        config['clients']['testing']['server_path'] = server_dir
        config['clients']['testing']['client_path'] = client_dir

        config['clients']['testing']['recursive'] = recursive
        config['clients']['testing']['sync_type'] = sksync.SKSYNC_PROTOCOL_TYPE_BIDIRECTIONAL_USE_TIME
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

    def test_sync_from_server_with_times_to_nonempty_client_directory_client_newer_and_server_newer(self):
        pass  # See test_sync_from_server_with_times_to_nonempty_client_directory_client_newer
        # BiDirectional sync will update both client and server which TestSKSync.test_sync_from_server_with_times_to_nonempty_client_directory_client_newer_and_server_newer() is not expecting.

    def test_sync_from_server_with_times_to_nonempty_client_directory_client_newer(self):
        # based on TestSKSync.test_sync_from_server_with_times_to_nonempty_client_directory_client_newer()
        # Update both client and server and ensure sync happens both ways

        # setup client dir and server dir with same files
        create_test_files(self.test_fixtures, testdir=self.client_dir)
        local_test_fixtures = copy.deepcopy(self.test_fixtures)
        #import pdb ; pdb.set_trace()

        # update single client file
        test_string = b'client updated'
        filename = 'test1.txt'
        local_test_fixtures[filename] = (local_test_fixtures[filename][0], test_string)
        self.assertTrue(os.path.isfile(os.path.join(self.server_dir, filename)))
        tmp_client_file = os.path.join(self.client_dir, filename)
        f = open(tmp_client_file, 'wb')
        f.write(test_string)
        f.close()  # assume mtime is ahead of fixtures mtimes
        self.assertTrue(os.path.isfile(tmp_client_file))
        self.check_file_contents_and_mtime(self.server_dir, filename)

        # update single server file
        test_string = b'server updated'
        filename = 'test2.txt'
        local_test_fixtures[filename] = (local_test_fixtures[filename][0], test_string)
        self.assertTrue(os.path.isfile(os.path.join(self.client_dir, filename)))
        tmp_client_file = os.path.join(self.server_dir, filename)
        f = open(tmp_client_file, 'wb')
        f.write(test_string)
        f.close()  # assume mtime is ahead of fixtures mtimes
        self.assertTrue(os.path.isfile(tmp_client_file))
        self.check_file_contents_and_mtime(self.client_dir, filename)

        # do sync
        self.perform_sync(self.server_dir, self.client_dir, config=self.config)

        # check files exist and match
        for filename in local_test_fixtures:
            self.assertTrue(os.path.isfile(os.path.join(self.server_dir, filename)))
            self.assertTrue(os.path.isfile(os.path.join(self.client_dir, filename)))
            self.check_file_contents_and_mtime(self.server_dir, filename, test_fixtures=local_test_fixtures, skip_time_time_check=True)
            self.check_file_contents_and_mtime(self.client_dir, filename, test_fixtures=local_test_fixtures, skip_time_time_check=True)
        # TODO check no other files exist in self.client_dir and self.server_dir
        #import pdb ; pdb.set_trace()  # DEBUG


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

        # clone of self.perform_sync(server_dir, client_dir, 
        HOST = '127.0.0.1'
        PORT = get_random_port()
        config = self.config
        server_dir, client_dir = self.server_dir, self.client_dir
        recursive = True

        config['host'] = HOST
        config['port'] = PORT
        #config['server_path'] = server_dir
        #config['client_path'] = client_dir
        config['clients'] = config.get('clients', {})
        config['clients']['testing'] = {}
        config['clients']['testing']['server_path'] = server_dir
        config['clients']['testing']['client_path'] = client_dir
        config['clients']['testing']['recursive'] = recursive
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
        self.config['username'] = 'testuser'  # valid username for below
        self.config['password'] = 'testpassword'  # valid password for testuser below
        self.config['users'] = {
            'testuser': {
                'authsrp': [
                    'cf78a7a5', 
                    '7443843a24acb936bfb5d5e0d4184a3fd521d4edd8096cf2ac9cdc62eed1a363d9c4a1bd39cb69c8836eb6f77e757e73b77be766af8547eeab4d9b3be17e2860c81afde7d4d8b5b855635ccd22352e2538b27a30518c65e825f7bb29a7037e79aa144726af2dc24ccae76a8e7a2f97fede87aee5ecab1e1ee7e559ce85fc14767ef25314c121b9c093dcf980caab66c60ae7c426a885e04bcbd761b6289b582a6d194a145932180f9b55f58cb1d937659ded8c9eeb59490705c22263241ead65db01ac218a2b76c49947fdaf4f82c5de79c97f17da1101fc1daf14e7f49beb9b8c4496c4a585805a8b858f159ec2c8d423819f84530f496ee5303d2b2eb6a32b'
                ]
            }
        }


class TestSKSyncWithInvalidAuthPassword(GenericSetup):

    def setUp(self):
        GenericSetup.setUp(self)
        self.config['raise_errors'] = False  # Do not raise PAKEFailure on server, see SSL note below
        self.config['require_auth'] = True
        self.config['username'] = 'testuser'  # valid username
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
    # TODO once TestSKSyncWithSSL() checks server SSL error, apply same approach here
    def test_sync_from_server_with_times_to_empty_client_directory(self):
        safe_rmtree(self.client_dir)
        safe_mkdir(self.client_dir)
        result = os.path.isdir(self.server_dir)

        # do sync
        def doit():
            self.perform_sync(self.server_dir, self.client_dir, config=self.config)
        self.assertRaises(sksync.PAKEFailure, doit)
        # Both a server and client failure is expected


class TestSKSyncWithInvalidAuthMissingUser(GenericSetup):

    def setUp(self):
        GenericSetup.setUp(self)
        self.config['raise_errors'] = False  # Do not raise PAKEFailure on server, see SSL note below
        self.config['require_auth'] = True
        self.config['username'] = 'missing_user'  # user that does NOT exist below
        self.config['password'] = 'testpassword'  # valid password for testuser below
        self.config['users'] = {
            'testuser': {
                'authsrp': [
                    'cf78a7a5', 
                    '7443843a24acb936bfb5d5e0d4184a3fd521d4edd8096cf2ac9cdc62eed1a363d9c4a1bd39cb69c8836eb6f77e757e73b77be766af8547eeab4d9b3be17e2860c81afde7d4d8b5b855635ccd22352e2538b27a30518c65e825f7bb29a7037e79aa144726af2dc24ccae76a8e7a2f97fede87aee5ecab1e1ee7e559ce85fc14767ef25314c121b9c093dcf980caab66c60ae7c426a885e04bcbd761b6289b582a6d194a145932180f9b55f58cb1d937659ded8c9eeb59490705c22263241ead65db01ac218a2b76c49947fdaf4f82c5de79c97f17da1101fc1daf14e7f49beb9b8c4496c4a585805a8b858f159ec2c8d423819f84530f496ee5303d2b2eb6a32b'
                ]
            }
        }

    # Cut down and modified version of TestSKSync.test_sync_from_server_with_times_to_empty_client_directory()
    # TODO once TestSKSyncWithSSL() checks server SSL error, apply same approach here
    def test_sync_from_server_with_times_to_empty_client_directory(self):
        safe_rmtree(self.client_dir)
        safe_mkdir(self.client_dir)
        result = os.path.isdir(self.server_dir)

        # do sync
        def doit():
            self.perform_sync(self.server_dir, self.client_dir, config=self.config)
        self.assertRaises(sksync.PAKEFailure, doit)
        # Both a server and client failure is expected


try:
    TestSKSync.assertTrue
except AttributeError:
    # wow, old unittest
    TestSKSync.assertTrue = TestSKSync.assert_
    TestSKSync.assertFalse = TestSKSync.failIf

if __name__ == '__main__':
    print('Python %s on %s' % (sys.version, sys.platform))
    #log.debug('Python %s on %s', sys.version, sys.platform)  # TODO make this info?  in main lib?
    #sksync.logger.setLevel(sksync.logging.INFO)  # Debug
    #sksync.logger.setLevel(sksync.logging.DEBUG)  # Debug
    sksync.logging.disable(sksync.logging.ERROR)  # ugh!
    unittest.main()
