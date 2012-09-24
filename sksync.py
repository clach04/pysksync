#!/usr/bin/env python
# -*- coding: us-ascii -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
#

import os
import sys
import socket
import SocketServer
import logging
import glob


SKSYNC_DEFAULT_PORT = 23456
#SKSYNC_DEFAULT_PORT = 23456 + 1  # FIXME DEBUG not default!!
#SKSYNC_DEFAULT_PORT = 23456 + 3  # FIXME DEBUG not default!!
SKSYNC_PROTOCOL_01 = 'sksync 1\n'
SKSYNC_PROTOCOL_ESTABLISHED = 'Protocol Established\n'

logging.basicConfig()
logger = logging
logger = logging.getLogger("sksync")
logger.setLevel(logging.INFO)
#logger.setLevel(logging.DEBUG)


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


def get_file_list(path_of_files, recursive=False, include_size=False):
    current_dir = os.getcwd()  # TODO non-ascii; os.getcwdu()
    # TODO include file size param
    # TODO recursive param
    # Get non-recursive list of files in real_client_path
    # FIXME TODO nasty hack using glob (i.e. not robust)
    os.chdir(path_of_files)  # TODO non-ascii path names
    file_list = glob.glob('*')
    file_list_info = []
    for filename in file_list:
        if os.path.isfile(filename):
            x = os.stat(filename)
            mtime = x.st_mtime
            # TODO non-ascii path names
            mtime = int(mtime) * 1000  # TODO norm
            if include_size:
                file_details = (filename, mtime, x.st_size)
            else:
                file_details = (filename, mtime)
            file_list_info.append(file_details)
    os.chdir(current_dir)
    return file_list_info


class MyTCPHandler(SocketServer.BaseRequestHandler):
    """
    The RequestHandler class for our server.

    It is instantiated once per connection to the server, and must
    override the handle() method to implement communication to the
    client.
    """

    def handle(self):
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
        assert response == '2\n'  # type of sync?

        response = reader.next()
        logger.debug('Received: %r' % response)
        assert response == '0\n'  # start of path (+file) info

        server_path = reader.next()
        logger.debug('server_path: %r' % server_path)
        server_path = server_path[:-1]  # loose trailing \n
        server_path = os.path.abspath(server_path)
        logger.debug('server_path abs: %r' % server_path)

        client_path = reader.next()
        logger.debug('client_path: %r' % client_path)

        # possible first file details
        response = reader.next()
        logger.debug('Received: %r' % response)
        while response != '\n':
            # TODO start counting and other stats
            # TODO read and ignore all file details....
            response = reader.next()
            logger.debug('Received: %r' % response)
        
        # we're done receiving data from client now
        self.request.send('\n')
        
        # TODO start counting and other stats
        # TODO output count and other stats
        file_list = get_file_list(server_path, include_size=True)
        # FIXME TODO now work out which files in file_list need to be sent to the client (as the client is missing them)
        logger.info('Number of files to send: %r' % len(file_list))
        os.chdir(server_path)
        for filename, mtime, data_len in file_list:
            file_details = '%s\n%d\n%d\n' % (filename, mtime, data_len)  # FIXME non-asci filenames
            f = open(filename, 'rb')
            data = f.read()
            f.close()
            self.request.send(file_details)
            self.request.send(data)

        # Tell client there are no files to send back
        self.request.sendall('\n')


def run_server():
    """Implements SK Server, currently only supports:
       * non-recursive ONLY
       * direction =  "from server (use time)" ONLY
       * TODO add option for server to filter/restrict server path
         (this is not a normal SK Sync option)
    """

    HOST, PORT = '0.0.0.0', SKSYNC_DEFAULT_PORT
    
    print HOST, PORT
    
    # Create the server, binding to localhost on port 9999
    server = SocketServer.TCPServer((HOST, PORT), MyTCPHandler)

    # Activate the server; this will keep running until you
    # interrupt the program with Ctrl-C
    server.serve_forever()


def empty_client_paths(ip, port, server_path, client_path):
    """Implements SK Client, currently only supports:
       * non-recursive ONLY
       * direction =  "from server (use time)" ONLY
    """
    real_client_path = os.path.abspath(client_path)
    file_list_str = ''
    
    # TODO recursion
    file_list = get_file_list(real_client_path)
    file_list_info = []
    for filename, mtime in file_list:
        file_details = '%d %s' % (mtime, filename)
        file_list_info.append(file_details)
    file_list_str = '\n'.join(file_list_info)
    
    # Connect to the server
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((ip, port))
    
    message = SKSYNC_PROTOCOL_01
    len_sent = s.send(message)
    logger.debug('sent: len %d %r' % (len_sent, message, ))
    
    reader = SKBufferedSocket(s)
    # Receive a response
    response = reader.next()
    logger.debug('Received: %r' % response)
    assert response == SKSYNC_PROTOCOL_ESTABLISHED

    # type of sync?
    message = '2\n'
    len_sent = s.send(message)
    logger.debug('sent: len %d %r' % (len_sent, message, ))

    # type of sync? and folders to sync (server path, client path)
    # example: '0\n/tmp/skmemos\n/sdcard/skmemos\n\n'
    if file_list_str:
        # FIXME this could be refactored....
        message = '0\n' + server_path + '\n' + client_path + '\n' + file_list_str + '\n\n'
    else:
        message = '0\n' + server_path + '\n' + client_path + '\n\n'
    len_sent = s.send(message)
    logger.debug('sent: len %d %r' % (len_sent, message, ))

    # Receive a response
    response = reader.next()
    logger.debug('Received: %r' % response)
    assert response == '\n'

    # if get CR end of session, otherwise get files
    response = reader.next()
    logger.debug('Received: %r' % response)
    while response != '\n':
        filename = response[:-1]  # loose trailing \n
        logger.debug('filename: %r' % filename)
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
        f = open(full_filename, 'wb')
        f.write(filecontents)
        f.close()
        os.utime(full_filename, (mtime, mtime))
        
        # any more files?
        response = reader.next()
        logger.debug('Received: %r' % response)

    # Clean up
    s.close()


def run_client():
    host, port = 'localhost', SKSYNC_DEFAULT_PORT
    server_path, client_path = '/tmp/skmemos', '/tmp/skmemos_client'
    print host, port, server_path, client_path
    empty_client_paths(host, port, server_path, client_path)


def main(argv=None):
    if argv is None:
        argv = sys.argv
    
    if 'server' in argv:
        run_server()
    else:
        run_client()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
