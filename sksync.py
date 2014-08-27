#!/usr/bin/env python
# -*- coding: us-ascii -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
#

import os
import sys
import socket
try:
    import ssl
except ImportError:
    ssl = None
import SocketServer
import threading
import select
import logging
import glob
import errno
import binascii
import locale
import zlib

try:
    #raise ImportError ## Debug, pretend we are 2.3 and earlier
    from datetime import timedelta, datetime
except ImportError:
    import time
    datetime=None

try:
    set
except NameError:
    # probably pre Python 2.4
    #from sets import Set as set
    import sets
    set = sets.Set
    frozenset = sets.ImmutableSet

# json support, TODO consider http://pypi.python.org/pypi/omnijson
try:
    # Python 2.6+
    import json
except ImportError:
    try:
        # from http://code.google.com/p/simplejson
        import simplejson as json
    except ImportError:
        json = None

if json is None:
    
    def dump_json(x, indent=None):
        """dumb not safe!
        Works for the purposes of this specific script as quotes never
        appear in data set.
        
        Parameter indent ignored"""
        if indent:
            result = pprint.pformat(x, indent)
        else:
            result = repr(x).replace("'", '"')
        return result
    
    def load_json(x):
        """dumb not safe! Works for the purposes of this specific script"""
        x = x.replace('\r', '')
        return eval(x)
else:
    dump_json = json.dumps
    load_json = json.loads

try:
    import easydialogs
except ImportError:
    try:
        import EasyDialogs as easydialogs
    except ImportError:
        easydialogs = None


def fake_module(name):
    # Fail with a clear message (possibly at an unexpected time in the future)
    class MissingModule(object):
        def __getattr__(self, attr):
            raise ImportError('No module named %s' % name)

        def __nonzero__(self):
            return False

    return MissingModule()

try:
    import srp  # from https://pypi.python.org/pypi/srp
except ImportError:
    srp = fake_module('srp')


PYSKSYNC_FILENAME_ENCODING = 'UTF-8'
FILENAME_ENCODING = 'cp1252'  # latin1 encoding used by sksync 1
language_name, SYSTEM_ENCODING = locale.getdefaultlocale()
# SYSTEM_ENCODING is usually set. If not, default to UTF-8
# (a good default for Unix, Android, Mac.)
SYSTEM_ENCODING = SYSTEM_ENCODING or 'UTF-8'  # TODO could allow config setting override

# SK Sync specific constants
SKSYNC_DEFAULT_PORT = 23456
#SKSYNC_DEFAULT_PORT = 23456 + 1  # FIXME DEBUG not default!!
#SKSYNC_DEFAULT_PORT = 23456 + 3  # FIXME DEBUG not default!!
SKSYNC_PROTOCOL_01 = 'sksync 1\n'
PYSKSYNC_PROTOCOL_01 = 'pysksync 1\n'  # same as SKSYNC_PROTOCOL_01 but using UTF-8 for filenames on wire protocol
SKSYNC_PROTOCOL_ESTABLISHED = 'Protocol Established\n'
SKSYNC_PROTOCOL_TYPE_FROM_SERVER_USE_TIME = '2\n'
SKSYNC_PROTOCOL_TYPE_FROM_SERVER_NO_TIME = '5\n'
SKSYNC_PROTOCOL_TYPE_BIDIRECTIONAL_USE_TIME = '0\n'  # NOTE BIDIRECTIONAL needs checksum support
SKSYNC_PROTOCOL_TYPE_BIDIRECTIONAL_NO_TIME = '3\n'
SKSYNC_PROTOCOL_TYPE_TO_SERVER_USE_TIME = '1\n'
SKSYNC_PROTOCOL_TYPE_TO_SERVER_NO_TIME = '4\n'

SKSYNC_PROTOCOL_RECURSIVE = '0\n'
SKSYNC_PROTOCOL_NON_RECURSIVE = '1\n'

if ssl:
    SSL_VERSION = ssl.PROTOCOL_TLSv1


# PYSKSYNC specific constants
PYSKSYNC_CR_START = 'PYSKSYNC SRP START:'  # Challenge Response start message


class BaseSkSyncException(Exception):
    '''Base SK Sync exception'''

class NotAllowed(BaseSkSyncException):
    '''Requested operation not allowed exception'''

class PAKEFailure(BaseSkSyncException):
    '''Password authenticated key agreement exception
    Either client has wrong password, or server does.'''


logging.basicConfig()
logger = logging.getLogger("sksync")
"""
logging_fmt_str = "%(process)d %(thread)d %(asctime)s - %(name)s %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
ch = logging.StreamHandler()  # use stdio
formatter = logging.Formatter(logging_fmt_str)
ch.setFormatter(formatter)
logger.addHandler(ch)
"""
#logger.setLevel(logging.INFO)
#logger.setLevel(logging.DEBUG)

IGNORE_SET_TIME_ERRORS = False

def set_utime(a, b):
    try:
        os.utime(a, b)
    except OSError, info:
        if IGNORE_SET_TIME_ERRORS:
            # probably Android https://groups.google.com/forum/#!msg/python-for-android/MlOLiTOeK0o/_5m2jtvXsNIJ
            pass
        else:
            raise

def safe_mkdir(newdir):
    result_dir = os.path.abspath(newdir)
    try:
        os.makedirs(result_dir)
    except OSError, info:
        if info.errno == errno.EEXIST and os.path.isdir(result_dir):
            pass
        else:
            raise

def gettime():
    # orig
    if datetime:
        return datetime.now()
    else:
        return time.time()
    
    # supposed to have better granularity for sub second
    """
    # choose timer to use
    if sys.platform.startswith('win'):
        default_timer = time.clock
    else:
        default_timer = time.time

    return default_timer()
    """

class SimpleTimer(object):
    def __init__(self):
        self._start = None
        self._stop = None
        self.timediff = None
        self.num_secs = None
    
    def start(self):
        self._start = gettime()
    
    def stop(self):
        self._stop = gettime()
        self.timediff = self._stop - self._start
        if datetime:
            timediff = self.timediff
            if isinstance(timediff, timedelta):
                self.num_secs = timediff.days * 3600 * 24 + timediff.seconds + (timediff.microseconds / 1000000.0)
        #print type(self.timediff)
        #print type(self.num_secs)
    
    def __str__(self):
        #return stringify(self.num_secs)
        return '%d secs' % self.num_secs

# norm/unnorm have not been tested....
def norm_mtime(m):
    """traditionally this is float
    BUT there are odd behaviors when float is used under win32"""
    m = int(m)
    return m


def unnorm_mtime(m):
    """normalized to Native
    """
    m = m / 1000  # NOTE still integer
    return m


def parse_file_details(in_str):
    mtime, filename = in_str.split(' ', 1)
    mtime = norm_mtime(mtime)
    assert filename.endswith('\n')
    filename = filename[:-1]
    return (filename, mtime)


BIGBUF = 1024  # FIXME


class SKBufferedSocket(object):
    """buffer reads from an SK Sync Server which uses CR as packet terminators.
    Kinda messed up API as caller can perform recv()'s too.
    basically a helper to make the protocol reading easier.
    """
    def __init__(self, server_sock):
        self.server_sock = server_sock
        self.data = ''
    
    def __iter__(self):
        return self
    
    def recv(self, bytecount):
        data_len = len(self.data)
        while not (bytecount <= data_len):
            logger.debug("about to call server_sock.recv")
            read_length = bytecount - data_len
            logger.debug("read_length %r", (bytecount, data_len, read_length))
            tmp_bytes = self.server_sock.recv(read_length)
            self.data = self.data + tmp_bytes
            data_len = len(self.data)
        data = self.data[:bytecount]
        self.data = self.data[bytecount:]
        return data
    
    def next(self):
        while 1:
            if not self.data or '\n' not in self.data:
                logger.debug("about to call server_sock.recv")
                self.data = self.data + self.server_sock.recv(BIGBUF)
                logger.debug("data from socket = %r", (len(self.data), self.data))
            if self.data:
                newline_pos = self.data.find('\n')
                #if '\n' in data:
                if newline_pos >= 0:
                    data = self.data[:newline_pos + 1]
                    self.data = self.data[newline_pos + 1:]
                    logger.debug("remaining self.data %r", (len(self.data), self.data))
                    return data
            else:
                raise StopIteration


###############################################################

def path_walker(path_to_search, filename_filter=None, abspath=False):
    """Walk directory of files, directory depth first, returns generator
    """
    if abspath:
        path_to_search = os.path.abspath(path_to_search)
    
    def always_true(*args, **kwargs):
        # Use a function rather than Lamda
        return True
    
    if filename_filter is None:
        filename_filter = always_true
    
    path_to_search_len = len(path_to_search) + 1
    
    ## Requires os.walk (python 2.3 and later).
    ## Pure Python versions for earlier versions available from:
    ##  http://osdir.com/ml/lang.jython.user/2006-04/msg00032.html
    ## but lacks "topdown" support, walk class later
    for dirpath, dirnames, filenames in os.walk(path_to_search, topdown=False):
        filenames.sort()
        for temp_filename in filenames:
            if filename_filter(temp_filename):
                temp_filename = os.path.join(dirpath, temp_filename)
                if not abspath:
                    temp_filename = temp_filename[path_to_search_len:]
                yield temp_filename

###############################################################

def get_file_listings(path_of_files, recursive=False, include_size=False, return_list=True, force_unicode=False):
    """return_list=True, if False returns dict
    """
    
    if recursive:
        file_list = list(path_walker(path_of_files))
    current_dir = os.getcwd()  # TODO non-ascii; os.getcwdu()
    os.chdir(path_of_files)  # TODO non-ascii path names

    if not recursive:
        # TODO include file size param
        # Get non-recursive list of files in real_client_path
        # FIXME TODO nasty hack using glob (i.e. not robust)
        file_list = glob.glob('*')
    
    if return_list:
        listings_result = []
    else:
        listings_result = {}
    for filename in file_list:
        if os.path.isfile(filename):
            x = os.stat(filename)
            mtime = x.st_mtime
            # TODO non-ascii path names
            mtime = int(mtime) * 1000  # TODO norm
            if force_unicode:
                if isinstance(filename, str):
                    # This is probably Windows
                    # Assume str, in locale encoding
                    filename = filename.decode(SYSTEM_ENCODING)
            if include_size:
                file_details = (filename, mtime, x.st_size)
            else:
                file_details = (filename, mtime)
            if return_list:
                listings_result.append(file_details)
            else:
                listings_result[filename] = file_details[1:]
        elif os.path.isdir(filename):
            # no need to process directories
            pass
        else:
            # Probably Windows, with a (byte/str) filename containing
            # characters that are NOT in the current locale we can't
            # access it unless we have a Unicode filename
            logger.error('Unable to access and process %r, ignoring', filename)
    os.chdir(current_dir)
    return listings_result


class MyTCPHandler(SocketServer.BaseRequestHandler):
    """
    The RequestHandler class for our server.

    It is instantiated once per connection to the server, and must
    override the handle() method to implement communication to the
    client.
    """

    def handle(self):
        logger.info('Client %r connected', (self.request.getpeername(),))
        config = getattr(self.server, 'sksync_config', {})
        config['server_dir_whitelist'] = config.get('server_dir_whitelist', [])
        raise_errors = config.get('raise_errors', True)
        config['users'] = config.get('users', {})
        config['require_auth'] = config.get('require_auth', True)

        sync_timer = SimpleTimer()
        sync_timer.start()

        # self.request is the TCP socket connected to the client
        if config.get('use_ssl'):
            try:
                logger.info('Attempting SSL session')
                ssl_server_certfile = config.get('ssl_server_certfile')
                ssl_server_keyfile = config.get('ssl_server_keyfile')
                logger.info('using SSL certificate file  %r', ssl_server_certfile)
                logger.info('using SSL key file  %r', ssl_server_keyfile)

                if config.get('ssl_client_certfile'):
                    self.request = ssl.wrap_socket(self.request,
                                    server_side=True,
                                    certfile=ssl_server_certfile,
                                    keyfile=ssl_server_keyfile,
                                    ca_certs=config['ssl_client_certfile'],  # verify client
                                    cert_reqs=ssl.CERT_REQUIRED,
                                    ssl_version=SSL_VERSION)
                else:
                    self.request = ssl.wrap_socket(self.request,
                                    server_side=True,
                                    certfile=ssl_server_certfile,
                                    keyfile=ssl_server_keyfile,
                                    ssl_version=SSL_VERSION)
                logger.info('SSL connected using %r', self.request.cipher())
            except ssl.SSLError, info:
                if raise_errors:
                    raise
                logger.error('Error starting SSL, check certificate and key are valid. %r', info)
                # could be a bad client....
                return
        reader = SKBufferedSocket(self.request)
        response = reader.next()
        logger.debug('Received: %r' % response)

        # Start of PYSKSYNC challenge/response
        if config['require_auth'] or response.startswith(PYSKSYNC_CR_START):
            try:
                if not response.startswith(PYSKSYNC_CR_START):
                    # client is not starting PAKE session
                    raise PAKEFailure()

                # SRP 6a
                # As per spec, errors result in an abort, PAKEFailure is raised.
                # Nothing helpful is sent to the peer.
                logger.info('authenticated connection requested')
                try:
                    I_hex, A_hex = response[len(PYSKSYNC_CR_START):].split()
                except ValueError:
                    # bad user/verifier
                    raise PAKEFailure()
                I, A = binascii.unhexlify(I_hex), binascii.unhexlify(A_hex)
                logger.info('attempting authentication for user %s' % I)

                #salt, vkey = config['users'][I]['authsrp']
                authsrp = config['users'].get(I, {}).get('authsrp')
                if not authsrp:
                    # User does not exist
                    raise PAKEFailure()
                try:
                    salt, vkey = authsrp
                except ValueError:
                    # bad user/verifier entry
                    raise PAKEFailure()
                salt, vkey = binascii.unhexlify(salt), binascii.unhexlify(vkey)
                svr = srp.Verifier(I, salt, vkey, A)
                s, B = svr.get_challenge()
                if s is None or B is None:
                    raise PAKEFailure()
                message = '%s %s\n' % (binascii.hexlify(s), binascii.hexlify(B))
                logger.debug('sending: len %d %r' % (len(message), message, ))
                len_sent = self.request.send(message)
                logger.debug('sent: len %d' % (len_sent, ))

                response = reader.next()
                logger.debug('Received: %r' % response)
                M = binascii.unhexlify(response.strip())
                HAMK = svr.verify_session(M)
                if HAMK is None:
                    raise PAKEFailure()
                message = '%s\n' % (binascii.hexlify(HAMK),)
                logger.debug('sending: len %d %r' % (len(message), message, ))
                len_sent = self.request.send(message)
                logger.debug('sent: len %d' % (len_sent, ))
                if not svr.authenticated():
                    raise PAKEFailure()
                # svr.K is now a shared key available to use

                # Resume SKSYNC PROTOCOL
                response = reader.next()
                logger.debug('Received: %r' % response)
            except PAKEFailure:
                logger.error('SRP PAKEFailure server side, missing auth or client auth does not match server.')
                message = '\n'  # Empty message so that client should also raise a PAKEFailure
                logger.debug('sending: len %d %r' % (len(message), message, ))
                len_sent = self.request.send(message)
                logger.debug('sent: len %d' % (len_sent, ))
                if raise_errors:
                    raise
                else:
                    return

        # Start of SKSYNC PROTOCOL 01
        assert response in (SKSYNC_PROTOCOL_01, PYSKSYNC_PROTOCOL_01), 'unexpected protocol, %r' % (response,)
        # PYSKSYNC_PROTOCOL_01 is the same as SKSYNC_PROTOCOL_01 but using UTF-8 for filenames
        if response == SKSYNC_PROTOCOL_01:
            filename_encoding = FILENAME_ENCODING
        elif response == PYSKSYNC_PROTOCOL_01:
            filename_encoding = PYSKSYNC_FILENAME_ENCODING
        logger.info('filename_encoding %r', filename_encoding)

        message = SKSYNC_PROTOCOL_ESTABLISHED
        len_sent = self.request.send(message)
        logger.debug('sent: len %d %r', len_sent, message)

        response = reader.next()
        logger.debug('Received: %r', response)
        assert response in (SKSYNC_PROTOCOL_TYPE_FROM_SERVER_USE_TIME, ), repr(response)  # type of sync
        # FROM SERVER appears to use the same protocol, the difference is in the server logic for working out which files to send to the client

        response = reader.next()
        logger.debug('Received: %r', response)
        assert response in (SKSYNC_PROTOCOL_NON_RECURSIVE, SKSYNC_PROTOCOL_RECURSIVE)  # start of path (+file) info
        
        if response == SKSYNC_PROTOCOL_NON_RECURSIVE:
            recursive = False
        else:
            # SKSYNC_PROTOCOL_RECURSIVE
            recursive = True
        
        server_path = reader.next()
        logger.debug('server_path: %r', server_path)
        server_path = server_path[:-1]  # loose trailing \n
        server_path = os.path.abspath(server_path)
        logger.debug('server_path abs: %r', server_path)
        server_dir_whitelist = []
        if config['server_dir_whitelist']:
            server_dir_whitelist = []
            for tmp_path in config['server_dir_whitelist']:
                # clean path so we can use string comparisons for dir equality check
                tmp_path = os.path.abspath(tmp_path)
                server_dir_whitelist.append(tmp_path)
            if server_path not in server_dir_whitelist:
                if config.get('server_dir_whitelist_policy', "deny") == 'silent':
                    # silently ignore client's path request, use first white listed dir
                    server_path = server_dir_whitelist[0]
                    logger.info('OVERRIDE server_path: %r', server_path)
                else:
                    logger.error('client requested path %r which is not in "server_dir_whitelist"', server_path)
                    raise NotAllowed('access to path %r' % server_path)

        client_path = reader.next()
        logger.debug('client_path: %r', client_path)

        # possible first file details
        response = reader.next()
        logger.debug('Received: %r', response)
        client_files = {}
        while response != '\n':
            # TODO start counting and other stats
            # read all file details
            filename, mtime = parse_file_details(response)
            logger.debug('Received meta data for: %r', ((filename, mtime),))
            filename = filename.decode(filename_encoding)
            if os.path.sep == '\\':
                # Windows
                filename = filename.replace('/', '\\')  # Unix path conversion to Windows
            client_files[filename] = mtime
            response = reader.next()
            logger.debug('Received: %r', response)
        
        # we're done receiving data from client now
        self.request.send('\n')
        
        # TODO start counting and other stats
        # TODO output count and other stats
        logger.info('Number of files on client %r ', (len(client_files),))
        # NOTE if sync type is SKSYNC_PROTOCOL_TYPE_FROM_SERVER_* and
        # server_path does not exist, SK Sync simply returns 0 files
        server_files = get_file_listings(server_path, recursive=recursive, include_size=True, return_list=False, force_unicode=True)
        logger.info('Number of files on server %r ', (len(server_files),))
        
        server_files_set = set(server_files)
        client_files_set = set(client_files)

        # if SKSYNC_PROTOCOL_TYPE_BIDIRECTIONAL_* or SKSYNC_PROTOCOL_TYPE_FROM_SERVER_
        # files that are not on client
        missing_from_client = server_files_set.difference(client_files_set)

        common = server_files_set.intersection(client_files_set)
        # Now find out if any common files are newer
        fuzz_factor = 1  # one second
        for filename in common:
            server_mtime = server_files[filename][0]
            client_mtime = client_files[filename]
            mtime_diff = server_mtime - client_mtime
            if mtime_diff >= fuzz_factor:
                # if SKSYNC_PROTOCOL_TYPE_BIDIRECTIONAL_* or SKSYNC_PROTOCOL_TYPE_FROM_SERVER_
                # 'server ahead'
                missing_from_client.add(filename)
            """
            elif mtime_diff < -fuzz_factor:
                print 'client ahead'
            else:
                # files same timestamp on client and server, do nothing
                print 'client sever same'
            """
        
        # if SKSYNC_PROTOCOL_TYPE_BIDIRECTIONAL_* or SKSYNC_PROTOCOL_TYPE_TO_SERVER_*
        #missing_from_server = client_files_set.difference(server_files_set)
        
        # send new files to the client
        # TODO deal with incoming files from client
        logger.info('Number of files for server to send %r out of %r ', len(missing_from_client), len(server_files))
        # TODO consider a progress bar/percent base on number of missing files (not byte count)
        current_dir = os.getcwd()  # TODO non-ascii; os.getcwdu()
        os.chdir(server_path)
        sent_count = 0
        skip_count = 0
        byte_count_sent = 0
        try:
            for filename in missing_from_client:
                try:
                    logger.debug('File to send: %r', filename)
                    mtime, data_len = server_files[filename]
                    if os.path.sep == '\\':
                        # Windows path conversion to Unix/protocol
                        send_filename = filename.replace('\\', '/')
                    else:
                        send_filename = filename
                    if isinstance(send_filename, str):
                        # Assume str, in locale encoding
                        send_filename = send_filename.decode(SYSTEM_ENCODING)
                    if isinstance(send_filename, unicode):
                        # Need to send binary/byte across wire
                        send_filename = send_filename.encode(filename_encoding)

                    f = open(filename, 'rb')
                    data = f.read()
                    f.close()
                    assert data_len == len(data)
                    compression_type = 'gz'
                    #compression_type = None
                    # TODO compress black list (e.g. don't attempt to compress; .zip, .png, .jpg, .mp3, ....
                    if compression_type:
                        # TODO handle different compression types...
                        data = zlib.compress(data)  # TODO compression level
                        data_len = len(data)
                        # TODO if compressed length is longer use original...

                    if compression_type:
                        data_len_str = '%s %d' % (compression_type, data_len,)
                    else:
                        data_len_str = '%d' % (data_len,)
                    file_details = '%s\n%d\n%s\n' % (send_filename, mtime, data_len_str)
                    logger.debug('file_details: %r', file_details)
                    self.request.send(file_details)
                    self.request.send(data)
                    sent_count += 1
                    byte_count_sent += len(data)
                except UnicodeEncodeError:
                    # Skip this file
                    logger.error('Encoding error - unable to access and process %r, ignoring', filename)
                    skip_count += 1
                    continue

            # Tell client there are no files to send back
            self.request.sendall('\n')
        finally:
            os.chdir(current_dir)
        sync_timer.stop()
        if skip_count:
            skip_count_str = ', skipped %d' % skip_count
        else:
            skip_count_str = ''
        logger.info('Successfully checked %r, sent %r bytes in %r%s files in %s', len(server_files), byte_count_sent, sent_count, skip_count_str, sync_timer)
        logger.info('Client %r disconnected', self.request.getpeername())


class StoppableTCPServer(SocketServer.ThreadingTCPServer):
   def __init__(self, address_tuple, handler):
      SocketServer.ThreadingTCPServer.__init__(self, address_tuple, handler)
      self.__is_shut_down = threading.Event()
      self.__shutdown_request = False
 
   def serve_forever(self, poll_interval=0.5):
      """Handle one request at a time until shutdown.
 
         Polls for shutdown every poll_interval seconds. Ignores
         self.timeout. If you need to do periodic tasks, do them in
         another thread.
      """
      self.__is_shut_down.clear()
      try:
         while not self.__shutdown_request:
            r, w, e = select.select([self], [], [], poll_interval)
            if self in r:
               self._handle_request_noblock()
      finally:
         self.__shutdown_request = False
         self.__is_shut_down.set()
 
   def shutdown(self):
      """Stops the serve_forever loop.
 
         Blocks until the loop has finished. This must be called while
         serve_forever() is running in another thread, or it will
         deadlock.
      """
      self.__shutdown_request = True
      self.__is_shut_down.wait()
 
   def _handle_request_noblock(self):
      """Handle one request, without blocking.
 
         I assume that select.select has returned that the socket is
         readable before this function was called, so there should be
         no risk of blocking in get_request().
      """
      try:
         request, client_address = self.get_request()
      except socket.error:
         return
      if self.verify_request(request, client_address):
         try:
            self.process_request(request, client_address)
         except:
            self.handle_error(request, client_address)
            self.close_request(request)

if hasattr(SocketServer.TCPServer, 'shutdown'):
    MyBaseTCPServer = SocketServer.TCPServer
else:
    # CPython 2.5 or older
    MyBaseTCPServer = StoppableTCPServer

class MyTCPServer(MyBaseTCPServer):
    """Ensure CTRL-C followed by restart works without:
             socket.error: [Errno 98] Address already in use
    """
    def __init__(self, *args, **kwargs):
        self.allow_reuse_address = 1
        MyBaseTCPServer.__init__(self, *args, **kwargs)


class MyThreadedTCPServer(SocketServer.ThreadingMixIn, MyTCPServer):
    pass


def run_server(config):
    """Implements SK Server, currently only supports:
       * direction =  "from server (use time)" ONLY
       * TODO add option for server to filter/restrict server path
         (this is not a normal SK Sync option)
    """

    config = set_default_config(config)
    if config.get('sksync1_compat') and (config.get('use_ssl') or config.get('require_auth', True)):
        logger.error('Support for SK Sync v1 is incompatible with use_ssl/require_auth options.')
        raise NotAllowed('Support for SK Sync v1 is incompatible with use_ssl/require_auth options.')

    host, port = config['host'], config['port']

    logger.info('starting server: %r', (host, port))

    # Create the server, binding to localhost on port 9999
    server = MyTCPServer((host, port), MyTCPHandler)
    server.sksync_config = config

    # Activate the server; this will keep running until you
    # interrupt the program with Ctrl-C
    server.serve_forever()


def client_start_sync(ip, port, server_path, client_path, sync_type=SKSYNC_PROTOCOL_TYPE_FROM_SERVER_USE_TIME, recursive=False, use_ssl=None, ssl_server_certfile=None, ssl_client_certfile=None, ssl_client_keyfile=None, sksync1_compat=False, raise_errors=True, username=None, password=None):
    """Implements SK Client, currently only supports:
       * direction =  "from server (use time)" ONLY
    """
    logger.info('server_path %r', server_path)
    logger.info('client_path %r', client_path)
    real_client_path = os.path.abspath(client_path)
    file_list_str = ''

    username = username or ''
    password = password or ''

    if sksync1_compat and (use_ssl or (username or password)):
        logger.error('Support for SK Sync v1 is incompatible with SSL/SRP options.')
        raise NotAllowed('Support for SK Sync v1 is incompatible with SSL/SRP options.')

    sync_timer = SimpleTimer()
    sync_timer.start()

    if sksync1_compat:
        filename_encoding = FILENAME_ENCODING
        sync_protocol = SKSYNC_PROTOCOL_01
    else:
        filename_encoding = PYSKSYNC_FILENAME_ENCODING
        sync_protocol = PYSKSYNC_PROTOCOL_01

    logger.info('server_path %r', server_path)
    logger.info('client_path %r', client_path)
    # Make filenames/paths Unicode
    client_path = client_path.encode(SYSTEM_ENCODING)
    real_client_path = os.path.abspath(client_path)
    file_list_str = ''

    logger.info('filename_encoding %r', filename_encoding)
    logger.info('determining client files for %r', real_client_path)
    file_list = get_file_listings(real_client_path, recursive=recursive)
    file_list_info = []
    for filename, mtime in file_list:
        try:
            if isinstance(filename, str):
                # Assume str, in locale encoding
                filename = filename.decode(SYSTEM_ENCODING)
            if isinstance(filename, unicode):
                # Need to send binary/byte across wire
                filename = filename.encode(filename_encoding)
            file_details = '%d %s' % (mtime, filename)
            file_list_info.append(file_details)
        except UnicodeEncodeError:
            # Skip this file
            logger.error('Encoding error - unable to access and process %r, ignoring', filename)
            # TODO log summary of skipped files at end
            continue
    logger.info('Number of files on client %d', len(file_list))
    logger.info('Number of files to process on client %d', len(file_list_info))
    delta = len(file_list) - len(file_list_info)
    if delta != 0:
        logger.info('Skiping %d', delta)
    file_list_str = '\n'.join(file_list_info)

    # Connect to the server
    logger.info('client connecting to server %s:%d', ip, port)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    if use_ssl:
        try:
            logger.info('Attempting SSL session')
            if ssl_server_certfile:
                logger.info('using SSL certificate file  %r', ssl_server_certfile)
                if ssl_client_certfile:
                    s = ssl.wrap_socket(s,
                               ca_certs=ssl_server_certfile,
                               cert_reqs=ssl.CERT_REQUIRED,
                               certfile=ssl_client_certfile,
                               keyfile=ssl_client_keyfile,
                               ssl_version=SSL_VERSION)
                else:
                    # assume that if server is checking client cert, client will be checking server cert
                    s = ssl.wrap_socket(s,
                               ca_certs=ssl_server_certfile,
                               cert_reqs=ssl.CERT_REQUIRED,
                               ssl_version=SSL_VERSION)
            else:
                logger.info('ignoring SSL certificate')
                s = ssl.wrap_socket(s,
                               cert_reqs=ssl.CERT_NONE,
                               ssl_version=SSL_VERSION)
            s.connect((ip, port))
            logger.info('SSL connected using %r', s.cipher())
        except ssl.SSLError, info:
            if raise_errors:
                raise
            logger.error('Error starting SSL connection, check SSL is enabled on server and certificate and key are valid. %r', info)
            return
    else:
        s.connect((ip, port))
    logger.info('connected')
    reader = SKBufferedSocket(s)

    if username or password:
        # SRP-6a - Secure Remote Password protocol
        """http://srp.stanford.edu/design.html

          N    A large safe prime (N = 2q+1, where q is prime)
               All arithmetic is done modulo N.
          g    A generator modulo N
          k    Multiplier parameter (k = H(N, g) in SRP-6a, k = 3 for legacy SRP-6)
          s    User's salt
          I    Username
          p    Cleartext Password
          H()  One-way hash function
          ^    (Modular) Exponentiation
          u    Random scrambling parameter
          a,b  Secret ephemeral values
          A,B  Public ephemeral values
          x    Private key (derived from p and s)
          v    Password verifier

        The host stores passwords using the following formula:

          x = H(s, p)               (s is chosen randomly)
          v = g^x                   (computes password verifier)

        The host then keeps {I, s, v} in its password database.
        The authentication protocol itself goes as follows:

        User -> Host:  I, A = g^a                  (identifies self, a = random number)
        Host -> User:  s, B = kv + g^b             (sends salt, b = random number)

                Both:  u = H(A, B)

                User:  x = H(s, p)                 (user enters password)
                User:  S = (B - kg^x) ^ (a + ux)   (computes session key)
                User:  K = H(S)

                Host:  S = (Av^u) ^ b              (computes session key)
                Host:  K = H(S)

        Now the two parties have a shared, strong session key K. To complete
        authentication, they need to prove to each other that their keys
        match. One possible way:

        User -> Host:  M = H(H(N) xor H(g), H(I), s, A, B, K)
        Host -> User:  H(A, M, K)

        The two parties also employ the following safeguards:

            The user will abort if he receives B == 0 (mod N) or u == 0.
            The host will abort if it detects that A == 0 (mod N).
            The user must show his proof of K first. If the server detects that
                the user's proof is incorrect, it must abort without showing its
                own proof of K. 
        """
        logger.info('attempting authentication for user %s' % username)
        usr = srp.User(username, password)
        I, A = usr.start_authentication()

        message = '%s%s %s\n' % (PYSKSYNC_CR_START, binascii.hexlify(I), binascii.hexlify(A))
        logger.debug('sending: len %d %r' % (len(message), message, ))
        len_sent = s.send(message)
        logger.debug('sent: len %d' % (len_sent, ))

        response = reader.next()
        logger.debug('Received: %r' % response)
        try:
            s_hex, B_hex = response.split()
        except ValueError:
            # split failed, probably got sent back an empty string which is
            # what the server does when it hits a PAKEFailure
            raise PAKEFailure()
        _s, B = binascii.unhexlify(s_hex), binascii.unhexlify(B_hex)

        if s is None or B is None:
            raise PAKEFailure()

        M = usr.process_challenge(_s, B)
        if M is None:
            raise PAKEFailure()
        message = '%s\n' % (binascii.hexlify(M),)
        logger.debug('sending: len %d %r' % (len(message), message, ))
        len_sent = s.send(message)
        logger.debug('sent: len %d' % (len_sent, ))

        response = reader.next()
        logger.debug('Received: %r' % response)
        HAMK = binascii.unhexlify(response.strip())
        # if HAMK == '', we have a failure, this will be detected in verify_session()

        usr.verify_session(HAMK)
        if not usr.authenticated():
            raise PAKEFailure()
        # usr.K is now a shared key available to use

    message = sync_protocol
    len_sent = s.send(message)
    logger.debug('sent: len %d %r', len_sent, message)
    
    # Receive a response
    response = reader.next()
    logger.debug('Received: %r', response)
    assert response == SKSYNC_PROTOCOL_ESTABLISHED

    # type of sync
    message = sync_type
    len_sent = s.send(message)
    logger.debug('sent: len %d %r', len_sent, message)
    
    recursive_type = SKSYNC_PROTOCOL_NON_RECURSIVE
    if recursive:
        recursive_type = SKSYNC_PROTOCOL_RECURSIVE
    
    # type of sync? and folders to sync (server path, client path)
    # example: '0\n/tmp/skmemos\n/sdcard/skmemos\n\n'
    if isinstance(server_path, unicode):
        # Need to send binary/byte across wire
        server_path = server_path.encode(filename_encoding)
    if isinstance(client_path, unicode):
        # Need to send binary/byte across wire
        client_path = client_path.encode(filename_encoding)

    if file_list_str:
        # FIXME this could be refactored....
        message = recursive_type + server_path + '\n' + client_path + '\n' + file_list_str + '\n\n'
    else:
        message = recursive_type + server_path + '\n' + client_path + '\n\n'
    len_sent = s.send(message)
    logger.debug('sent: len %d %r', len_sent, message)

    # Receive a response
    response = reader.next()
    logger.debug('Received: %r', response)
    assert response == '\n'

    # if get CR end of session, otherwise get files
    response = reader.next()
    logger.debug('Received: %r', response)
    received_file_count = 0
    byte_count_recv = 0
    while response != '\n':
        filename = response[:-1]  # loose trailing \n
        logger.debug('filename: %r', filename)
        filename = filename.decode(filename_encoding)
        mtime = reader.next()
        logger.debug('mtime: %r', mtime)
        mtime = norm_mtime(mtime)
        mtime = unnorm_mtime(mtime)
        logger.debug('mtime: %r', mtime)
        filesize = reader.next()
        logger.debug('filesize: %r', filesize)
        filesize_split = filesize.split()
        if len(filesize_split) == 2:
            compression_type, filesize = filesize_split
        else:
            compression_type = None
        filesize = int(filesize)
        logger.debug('filesize: %r', filesize)
        logger.info('processing %r', ((filename, filesize, mtime),))  # TODO add option to supress this?
        
        # now read filesize bytes....
        filecontents = reader.recv(filesize)
        logger.debug('filecontents: %r', filecontents)
        if compression_type:
            # TODO handle different compression types...
            filecontents = zlib.decompress(filecontents)

        full_filename = os.path.join(real_client_path, filename)
        full_filename_dir = os.path.dirname(full_filename)
        # Not all platforms support Unicode file names (e.g. Python android)
        full_filename = full_filename.encode(SYSTEM_ENCODING)
        full_filename_dir = full_filename_dir.encode(SYSTEM_ENCODING)

        #if not exists full_filename_dir
        safe_mkdir(full_filename_dir)
        f = open(full_filename, 'wb')
        f.write(filecontents)
        f.close()
        set_utime(full_filename, (mtime, mtime))
        received_file_count += 1
        byte_count_recv += len(filecontents)

        # any more files?
        response = reader.next()
        logger.debug('Received: %r', response)

    # Clean up
    s.close()
    sync_timer.stop()
    logger.info('%r bytes in %d files sent by server in %s', byte_count_recv, received_file_count, sync_timer)
    if delta != 0:
        logger.info('Skipped %d', delta)
    logger.info('disconnected')


def run_client(config, config_name='client'):
    logger.info('Using config_name %r', config_name)
    config = set_default_config(config)
    host, port = config['host'], config['port']
    if host == '0.0.0.0':
        host = 'localhost'

    sksync1_compat = config.get('sksync1_compat')
    client_config = config['clients'][config_name]
    server_path, client_path = client_config['server_path'], client_config['client_path']
    host, port = client_config.get('host', host), client_config.get('port', port)
    recursive = client_config.get('recursive')

    username, password = config.get('username'), config.get('password')

    use_ssl = config.get('use_ssl')
    ssl_server_certfile = config.get('ssl_server_certfile')
    ssl_server_certfile = client_config.get('ssl_server_certfile', ssl_server_certfile)

    ssl_client_certfile = config.get('ssl_client_certfile')
    ssl_client_keyfile = config.get('ssl_client_keyfile')
    ssl_client_keyfile = client_config.get('ssl_client_keyfile', ssl_client_keyfile)
    ssl_client_certfile = client_config.get('ssl_client_certfile', ssl_client_keyfile)
    client_start_sync(host, port, server_path, client_path, recursive=recursive, use_ssl=use_ssl, ssl_server_certfile=ssl_server_certfile, ssl_client_certfile=ssl_client_certfile, ssl_client_keyfile=ssl_client_keyfile, sksync1_compat=sksync1_compat, username=username, password=password)


def set_default_config(config):
    # defaults
    config['host'] = config.get('host', '0.0.0.0')
    config['port'] = config.get('port', SKSYNC_DEFAULT_PORT)
    config['sksync1_compat'] = config.get('sksync1_compat', False)
    config['ignore_time_errors'] = config.get('ignore_time_errors', False)
    global IGNORE_SET_TIME_ERRORS
    IGNORE_SET_TIME_ERRORS = config['ignore_time_errors']
    config['use_ssl'] = config.get('use_ssl', False)
    if config['sksync1_compat']:
        config['require_auth'] = config.get('require_auth', False)
    else:
        config['require_auth'] = config.get('require_auth', True)
    return config


def easydialogs_gui(config):
    """Easydialogs does not support menus or list of items.
    It does support YesNoCancel so this can be subverted to allow two options
    and quit, (ab)use this to allow server or client to be started.
    For client, allow picking out of only two client settings to be selected.
    """
    easydialogs_yes = 1
    easydialogs_no = 0
    easydialogs_cancel = -1

    # NOTE GTK easydialogs.AskYesNoCancel() default param does NOT work
    #result = easydialogs.AskYesNoCancel('sksync', default=-1, yes='Server', no='Client', cancel='Quit')
    result = easydialogs.AskYesNoCancel('sksync', yes='Server', no='Client', cancel='Quit')

    if result == easydialogs_yes:
        run_server(config)
    elif result == easydialogs_no:
        # Show Client menu
        client_names = list(config.get('clients', {}).keys())
        print client_names
        if 'client_1' not in client_names:
            client_names.append('client_1')
        if 'client_2' not in client_names:
            client_names.append('client_2')
        print client_names
        # just pick first, don't pop()
        client_1 = client_names[0]
        client_2 = client_names[1]
        # Hack for gtk easydialogs, which does NOT accept Unicode type strings but does accept utf-8 Unicode encoding byte strings
        client_1 = client_1.encode('utf-8')
        client_2 = client_2.encode('utf-8')

        client_result = easydialogs_yes
        while client_result != easydialogs_cancel:
            client_result = easydialogs.AskYesNoCancel('Client', yes=client_1, no=client_2, cancel='Quit')
            if client_result == easydialogs_yes:
                config_name = client_1
            elif client_result == easydialogs_no:
                config_name = client_2
            run_client(config, config_name=config_name)


def main(argv=None):
    if argv is None:
        argv = sys.argv

    # TODO proper argument parsing
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
    config = set_default_config(config)
    #print dump_json(config, indent=4)

    if 'gui' in argv:
        easydialogs_gui(config)
    elif 'client' in argv:
        config_name = argv[-1]
        run_client(config, config_name=config_name)
    else:
        run_server(config)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
