#!/usr/bin/env python
# -*- coding: us-ascii -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
#

import os
import sys
import socket
import SocketServer
import threading
import select
import logging
import glob
import errno
import locale

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


FILENAME_ENCODING = 'UTF-8'
FILENAME_ENCODING = 'cp1252'  # latin1 encoding used by sksync 1
language_name, SYSTEM_ENCODING = locale.getdefaultlocale()
#print language_name, SYSTEM_ENCODING

SKSYNC_DEFAULT_PORT = 23456
#SKSYNC_DEFAULT_PORT = 23456 + 1  # FIXME DEBUG not default!!
#SKSYNC_DEFAULT_PORT = 23456 + 3  # FIXME DEBUG not default!!
SKSYNC_PROTOCOL_01 = 'sksync 1\n'
SKSYNC_PROTOCOL_ESTABLISHED = 'Protocol Established\n'
SKSYNC_PROTOCOL_TYPE_FROM_SERVER_USE_TIME = '2\n'
SKSYNC_PROTOCOL_TYPE_FROM_SERVER_NO_TIME = '5\n'
SKSYNC_PROTOCOL_TYPE_BIDIRECTIONAL_USE_TIME = '0\n'  # NOTE BIDIRECTIONAL needs checksum support
SKSYNC_PROTOCOL_TYPE_BIDIRECTIONAL_NO_TIME = '3\n'
SKSYNC_PROTOCOL_TYPE_TO_SERVER_USE_TIME = '1\n'
SKSYNC_PROTOCOL_TYPE_TO_SERVER_NO_TIME = '4\n'

SKSYNC_PROTOCOL_RECURSIVE = '0\n'
SKSYNC_PROTOCOL_NON_RECURSIVE = '1\n'


class BaseSkSyncException(Exception):
    '''Base SK Sync exception'''

class NotAllowed(BaseSkSyncException):
    '''Requested operation not allowed exception'''


logging.basicConfig()
logger = logging
logger = logging.getLogger("sksync")
#logger.setLevel(logging.INFO)
#logger.setLevel(logging.DEBUG)


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
        else:
            # Probably Windows, with a (byte/str) filename containing
            # characters that are NOT in the current locale we can't
            # access it unless we have a Unicode filename
            logger.error('Unable to access and process %r, ignoring"', filename)
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
        logger.info('Client %r connected' % (self.request.getpeername(),))
        config = getattr(self.server, 'sksync_config', {})
        config['server_dir_whitelist'] = config.get('server_dir_whitelist', [])

        sync_timer = SimpleTimer()
        sync_timer.start()
        
        # self.request is the TCP socket connected to the client
        reader = SKBufferedSocket(self.request)
        response = reader.next()
        logger.debug('Received: %r' % response)
        assert response == SKSYNC_PROTOCOL_01

        message = SKSYNC_PROTOCOL_ESTABLISHED
        len_sent = self.request.send(message)
        logger.debug('sent: len %d %r' % (len_sent, message, ))

        response = reader.next()
        logger.debug('Received: %r' % response)
        assert response in (SKSYNC_PROTOCOL_TYPE_FROM_SERVER_USE_TIME, ), repr(response)  # type of sync
        # FROM SERVER appears to use the same protocol, the difference is in the server logic for working out which files to send to the client

        response = reader.next()
        logger.debug('Received: %r' % response)
        assert response in (SKSYNC_PROTOCOL_NON_RECURSIVE, SKSYNC_PROTOCOL_RECURSIVE)  # start of path (+file) info
        
        if response == SKSYNC_PROTOCOL_NON_RECURSIVE:
            recursive = False
        else:
            # SKSYNC_PROTOCOL_RECURSIVE
            recursive = True
        
        server_path = reader.next()
        logger.debug('server_path: %r' % server_path)
        server_path = server_path[:-1]  # loose trailing \n
        server_path = os.path.abspath(server_path)
        logger.debug('server_path abs: %r' % server_path)
        if config['server_dir_whitelist']:
            if server_path not in config['server_dir_whitelist']:
                if config.get('server_dir_whitelist_policy', "deny") == 'silent':
                    # silently ignore client's path request, use first white listed dir
                    server_path = config['server_dir_whitelist'][0]
                    logger.info('OVERRIDE server_path: %r', server_path)
                else:
                    logger.error('client requested path %r which is not in "server_dir_whitelist"', server_path)
                    raise NotAllowed('access to path %r' % server_path)

        client_path = reader.next()
        logger.debug('client_path: %r' % client_path)

        # possible first file details
        response = reader.next()
        logger.debug('Received: %r' % response)
        client_files = {}
        while response != '\n':
            # TODO start counting and other stats
            # read all file details
            filename, mtime = parse_file_details(response)
            logger.debug('Received meta data for: %r' % ((filename, mtime),))
            filename = filename.decode(FILENAME_ENCODING)
            if os.path.sep == '\\':
                # Windows
                filename = filename.replace('/', '\\')  # Unix path conversion to Windows
            client_files[filename] = mtime
            response = reader.next()
            logger.debug('Received: %r' % response)
        
        # we're done receiving data from client now
        self.request.send('\n')
        
        # TODO start counting and other stats
        # TODO output count and other stats
        logger.info('Number of files on client %r ' % (len(client_files),))
        server_files = get_file_listings(server_path, recursive=recursive, include_size=True, return_list=False, force_unicode=True)
        logger.info('Number of files on server %r ' % (len(server_files),))
        
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
        logger.info('Number of files for server to send %r out of %r ' % (len(missing_from_client), len(server_files)))
        # TODO consider a progress bar/percent base on number of missing files (not byte count)
        current_dir = os.getcwd()  # TODO non-ascii; os.getcwdu()
        os.chdir(server_path)
        sent_count = 0
        try:
            for filename in missing_from_client:
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
                    send_filename = send_filename.encode(FILENAME_ENCODING)

                file_details = '%s\n%d\n%d\n' % (send_filename, mtime, data_len)
                logger.debug('file_details: %r', file_details)
                f = open(filename, 'rb')
                data = f.read()
                f.close()
                self.request.send(file_details)
                self.request.send(data)
                sent_count += 1

            # Tell client there are no files to send back
            self.request.sendall('\n')
        finally:
            os.chdir(current_dir)
        sync_timer.stop()
        logger.info('Successfully checked %r, set sent %r files in %s', len(server_files), sent_count, sync_timer)
        logger.info('Client %r disconnected' % (self.request.getpeername(),))


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

    host, port = config['host'], config['port']

    logger.info('starting server: %r', (host, port))

    # Create the server, binding to localhost on port 9999
    server = MyTCPServer((host, port), MyTCPHandler)
    server.sksync_config = config

    # Activate the server; this will keep running until you
    # interrupt the program with Ctrl-C
    server.serve_forever()


def client_start_sync(ip, port, server_path, client_path, sync_type=SKSYNC_PROTOCOL_TYPE_FROM_SERVER_USE_TIME, recursive=False):
    """Implements SK Client, currently only supports:
       * direction =  "from server (use time)" ONLY
    """
    logger.info('client connecting to server %s:%d', ip, port)
    logger.info('server_path %r', server_path)
    logger.info('client_path %r', client_path)
    real_client_path = os.path.abspath(client_path)
    file_list_str = ''
    
    logger.info('determine client files')
    file_list = get_file_listings(real_client_path, recursive=recursive)
    file_list_info = []
    for filename, mtime in file_list:
        if isinstance(filename, str):
            # Assume str, in locale encoding
            filename = filename.decode(SYSTEM_ENCODING)
        if isinstance(filename, unicode):
            # Need to send binary/byte across wire
            filename = filename.encode(FILENAME_ENCODING)
        file_details = '%d %s' % (mtime, filename)
        file_list_info.append(file_details)
    logger.info('Number of files on client %d', len(file_list_info))
    file_list_str = '\n'.join(file_list_info)

    # Connect to the server
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((ip, port))
    logger.info('connected')

    message = SKSYNC_PROTOCOL_01
    len_sent = s.send(message)
    logger.debug('sent: len %d %r' % (len_sent, message, ))
    
    reader = SKBufferedSocket(s)
    # Receive a response
    response = reader.next()
    logger.debug('Received: %r' % response)
    assert response == SKSYNC_PROTOCOL_ESTABLISHED

    # type of sync
    message = sync_type
    len_sent = s.send(message)
    logger.debug('sent: len %d %r' % (len_sent, message, ))
    
    recursive_type = SKSYNC_PROTOCOL_NON_RECURSIVE
    if recursive:
        recursive_type = SKSYNC_PROTOCOL_RECURSIVE
    
    # type of sync? and folders to sync (server path, client path)
    # example: '0\n/tmp/skmemos\n/sdcard/skmemos\n\n'
    if isinstance(server_path, unicode):
        # Need to send binary/byte across wire
        server_path = server_path.encode(FILENAME_ENCODING)
    if isinstance(client_path, unicode):
        # Need to send binary/byte across wire
        client_path = client_path.encode(FILENAME_ENCODING)

    if file_list_str:
        # FIXME this could be refactored....
        message = recursive_type + server_path + '\n' + client_path + '\n' + file_list_str + '\n\n'
    else:
        message = recursive_type + server_path + '\n' + client_path + '\n\n'
    len_sent = s.send(message)
    logger.debug('sent: len %d %r' % (len_sent, message, ))

    # Receive a response
    response = reader.next()
    logger.debug('Received: %r' % response)
    assert response == '\n'

    # if get CR end of session, otherwise get files
    response = reader.next()
    logger.debug('Received: %r' % response)
    received_file_count = 0
    while response != '\n':
        filename = response[:-1]  # loose trailing \n
        logger.debug('filename: %r' % filename)
        filename = filename.decode(FILENAME_ENCODING)
        mtime = reader.next()
        logger.debug('mtime: %r' % mtime)
        mtime = norm_mtime(mtime)
        mtime = unnorm_mtime(mtime)
        logger.debug('mtime: %r' % mtime)
        filesize = reader.next()
        logger.debug('filesize: %r' % filesize)
        filesize = int(filesize)
        logger.debug('filesize: %r' % filesize)
        logger.info('processing %r' % ((filename, filesize, mtime),))
        
        # now read filesize bytes....
        filecontents = reader.recv(filesize)
        logger.debug('filecontents: %r' % filecontents)
        
        full_filename = os.path.join(real_client_path, filename)
        full_filename_dir = os.path.dirname(full_filename)
        #if not exists full_filename_dir
        safe_mkdir(full_filename_dir)
        f = open(full_filename, 'wb')
        f.write(filecontents)
        f.close()
        os.utime(full_filename, (mtime, mtime))
        received_file_count += 1

        # any more files?
        response = reader.next()
        logger.debug('Received: %r' % response)

    # Clean up
    s.close()
    logger.info('Number of files sent by server %d', received_file_count)
    logger.info('disconnected')


def run_client(config, config_name='client'):
    host, port = config['host'], config['port']
    if host == '0.0.0.0':
        host = 'localhost'

    client_config = config[config_name]
    server_path, client_path = client_config['server_path'], client_config['client_path']
    recursive = client_config.get('recursive')
    client_start_sync(host, port, server_path, client_path, recursive=recursive)


def main(argv=None):
    if argv is None:
        argv = sys.argv

    # TODO proper argument parsing
    logger.setLevel(logging.INFO)
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
    config['host'] = config.get('host', '0.0.0.0')
    config['port'] = config.get('port', SKSYNC_DEFAULT_PORT)

    if 'client' in argv:
        run_client(config)
    else:
        run_server(config)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
