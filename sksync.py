#!/usr/bin/env python
# -*- coding: us-ascii -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
#

import os
import sys
import socket
import logging
import glob


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
            logger.debug("bytecount - data_len %r", (bytecount, data_len, bytecount - data_len))
            tmp_bytes = self.server_sock.recv(bytecount - data_len)
            self.data = self.data + tmp_bytes
            data_len = len(self.data)
        data = self.data[:bytecount]
        self.data = self.data[bytecount:]
        return data
    
    def next(self):
        while 1:
            logger.debug("about to call server_sock.recv")
            self.data = self.data + self.server_sock.recv(BIGBUF)
            logger.debug("data from socket = %r", (len(self.data), self.data))
            if self.data:
                newline_pos = self.data.find('\n')
                #if '\n' in data:
                if newline_pos >= 0:
                    data = self.data[:newline_pos + 1]
                    self.data = self.data[newline_pos + 1:]
                    return data
            else:
                raise StopIteration


def empty_client_paths(ip, port, server_path, client_path):
    """client dir is assumed to be empty but handle all files
    that the server (chooses to) sends back.
    """
    real_client_path = os.path.abspath(client_path)
    file_list_str = ''
    
    # Get non-recursive list of files in real_client_path
    # FIXME TODO nasty hack using glob (i.e. not robust)
    os.chdir(real_client_path)  # TODO non-ascii path names
    file_list = glob.glob('*')
    file_list_info = []
    for filename in file_list:
        if os.path.isfile(filename):
            x = os.stat(filename)
            mtime = x.st_mtime
            # TODO non-ascii path names
            mtime = int(mtime) * 1000
            file_details = '%d %s' % (mtime, filename)
            file_list_info.append(file_details)
    file_list_str = '\n'.join(file_list_info)
    
    # Connect to the server
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((ip, port))
    
    message = 'sksync 1\n'
    len_sent = s.send(message)
    logger.debug('sent: len %d %r' % (len_sent, message, ))
    
    reader = SKBufferedSocket(s)
    # Receive a response
    response = reader.next()
    logger.debug('Received: "%r"' % response)
    assert response == 'Protocol Established\n'

    # type of sync?
    message = '2\n'
    len_sent = s.send(message)
    logger.debug('sent: len %d %r' % (len_sent, message, ))

    # type of sync? and folders to sync (server path, client path)
    # example: '0\n/tmp/skmemos\n/sdcard/skmemos\n\n'
    if file_list_str:
        # FIXME this could be refactored....
        message = '0\n' + server_path + '\n' + client_path + '\n' + file_list_str +'\n\n'
    else:
        message = '0\n' + server_path + '\n' + client_path + '\n\n'
    len_sent = s.send(message)
    logger.debug('sent: len %d %r' % (len_sent, message, ))

    # Receive a response
    response = reader.next()
    logger.debug('Received: "%r"' % response)
    assert response == '\n'

    # if get CR end of session, otherwise get files
    response = reader.next()
    logger.debug('Received: "%r"' % response)
    while response != '\n':
        filename = response[:-1]  # loose trailing \n
        logger.debug('filename: "%r"' % filename)
        mtime = reader.next()
        logger.debug('mtime: "%r"' % mtime)
        mtime = norm_mtime(mtime)
        mtime = unnorm_mtime(mtime)
        logger.debug('mtime: "%r"' % mtime)
        filesize = reader.next()
        logger.debug('filesize: "%r"' % filesize)
        filesize = int(filesize)
        logger.debug('filesize: "%r"' % filesize)
        logger.info('processing "%r"' % ((filename, filesize, mtime),))
        
        # now read filesize bytes....
        filecontents = reader.recv(filesize)
        logger.debug('filecontents: "%r"' % filecontents)
        
        full_filename = os.path.join(real_client_path, filename)
        f = open(full_filename, 'wb')
        f.write(filecontents)
        f.close()
        os.utime(full_filename, (mtime, mtime))
        
        # any more files?
        response = reader.next()
        logger.debug('Received: "%r"' % response)

    # Clean up
    s.close()


## for server probably should be using SocketServer / SocketServer.TCPServer ....
def doit():
    host, port = 'localhost', 23457
    #host, port = 'localhost', 23456
    server_path, client_path = '/tmp/skmemos', '/tmp/skmemos_client'
    print host, port, server_path, client_path
    empty_client_paths(host, port, server_path, client_path)



def main(argv=None):
    if argv is None:
        argv = sys.argv
    
    doit()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
