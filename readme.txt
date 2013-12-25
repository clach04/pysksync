
Usage

Start server with default settings:

    python sksync.py

This server is compatible with SK Sync Android client.

Change server settings, provide a file called `sksync.json`

Sample sksync.json contents:

    {
        "host": "0.0.0.0", 
        "port": 23456,
        "client": {
            "server_path": "/tmp/server/path",
            "client_path": "/tmp/client/path"
        }
    }

"client" indicates the config for a sync client.

Sample config that sets path that the server limits sync'ing to:

    {
        "host": "0.0.0.0", 
        "port": 23456,
        "server_dir_whitelist": ["/tmp/override/path"],
        "server_dir_whitelist_policy": "silent",
        "client": {
            "server_path": "/tmp/server/path",
            "client_path": "/tmp/client/path"
        }
    }

If "server_dir_whitelist_policy" is not "silent" the server will terminate
the client connection if "server_dir_whitelist" is set.


Enabling SSL support

How to generate an SSL certificate suitable for protecting traffic.

This will generate a certificate that is good for 1 year.

    #!/bin/sh
    
    rm server.key server.csr key.pem cert.pem
    
    openssl genrsa -des3 -out server.key 1024
    openssl req -new -key server.key -out server.csr
    openssl rsa -in server.key -out key.pem  # remove passphrase
    openssl x509 -req -days 365 -in server.csr -signkey key.pem -out cert.pem

Then set config to enable ssl support and use the certificate/key generated
above:

    {
        "use_ssl": true,
        "ssl_server_certfile": "cert.pem",
        "ssl_server_keyfile": "key.pem",
    }

If the client config sets "ssl_server_certfile", the server certificate will be
checked and the connection will be encrypted. If "ssl_server_certfile" is not set
client side, the connection will be encrypted but the certificate will not
be checked.

The server needs both the certificate and key file. Note if the key file is
protected by a pass phrase the server process will prompt on the console!
For convenience, consider removing the pass phrase from the key file.

Also the server can verify the client certificate too:

    {
        "use_ssl": true,
        "ssl_server_certfile": "cert.pem",
        "ssl_server_keyfile": "key.pem",
        
        "ssl_client_certfile": "cert.pem",
        "ssl_client_keyfile": "key.pem",
    }

NOTE this example is using the same cert (and key) for both client and server.
