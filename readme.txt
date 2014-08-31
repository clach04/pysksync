pysksync - a Pure Python implementation of the SK Sync protocol

The can be used with the existing Android SK Sync client and
Java SK Sync server.

For more information see the wiki at
https://bitbucket.org/clach04/pysksync/wiki/Home


Usage

Start server with default settings:

    python sksync.py

Start client, note requires settings file, e.g. `sksync.json`:

    python sksync.py sksync.json client CLIENTNAME

Where CLIENTNAME is specified in the settings file covered later.

Change server settings, provide a file called `sksync.json`

Sample sksync.json contents:

    {
        "sksync1_compat": true,
        "clients": {
            "client": {
                "recursive": false,
                "server_path": "/tmp/server/path",
                "client_path": "/tmp/client/path"
            }
        }
    }

"client" indicates the config for a sync client. I.e. this file
can be used for both client and server.

Sample config that limits the paths that clients can sync with:

    {
        "sksync1_compat": true,
        "host": "0.0.0.0", 
        "port": 23456,
        "server_dir_whitelist": ["/tmp/override/path"],
        "server_dir_whitelist_policy": "silent",
        "ignore_time_errors": false,
        "clients": {
            "client": {
                "recursive": true,
                "server_path": "/tmp/server/path",
                "client_path": "/tmp/client/path"
            }
        }
        "require_auth": false,
    }

NOTE the require_auth entry for backwards compatibility with SK Sync,
this is not needed if sksync1_compat is set to true but can be used
to disable SRP support, e.g. when using SSL and the server is
validating client certificate.

If "server_dir_whitelist_policy" is not "silent" the server will terminate
the client connection if "server_dir_whitelist" is set. This means that the
server will not share all disks and directories.

If "ignore_time_errors" is true, errors relating to setting files
modification times will be ignored. This is useful on a number
of Android devices.

NOTE both the server "host" address and and "port" can be specified in
the "client" section.

sksync1_compat

sksync1_compat limits the filename encoding to a Latin1 encoding (cp1252).
If sksync1_compat is not set UTF-8 is used instead, for full character
preservation support.


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

NOTE "ssl_server_certfile", "ssl_client_certfile", and "ssl_client_keyfile" can
be specified in the "client" section.

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

There is a small overhead with the SSL support (unclear if compression is on
or off with CPython 2.x ssl lib). Performing a loopback test on the same
machine with 1502 files ~7.7Mb takes 0.66 secs without SSL and 0.93 secs with
TLSv1/SSLv3 and AES256-SHA encryption.


Users, authentication, and passwords

This server supports Secure Remote Password protocol (SRP-6a), user verifier
information is stored in the json file (as hex), sample entry for a user
"testuser" with a password of "testpassword".

    {
        "users": {
            "testuser": {
                "authsrp": [
                    "cf78a7a5", 
                    "7443843a24acb936bfb5d5e0d4184a3fd521d4edd8096cf2ac9cdc62eed1a363d9c4a1bd39cb69c8836eb6f77e757e73b77be766af8547eeab4d9b3be17e2860c81afde7d4d8b5b855635ccd22352e2538b27a30518c65e825f7bb29a7037e79aa144726af2dc24ccae76a8e7a2f97fede87aee5ecab1e1ee7e559ce85fc14767ef25314c121b9c093dcf980caab66c60ae7c426a885e04bcbd761b6289b582a6d194a145932180f9b55f58cb1d937659ded8c9eeb59490705c22263241ead65db01ac218a2b76c49947fdaf4f82c5de79c97f17da1101fc1daf14e7f49beb9b8c4496c4a585805a8b858f159ec2c8d423819f84530f496ee5303d2b2eb6a32b"
                ]
            }
        }, 
    }

User information can be created/edited with `useredit.py`.

A client can sync with the following config file:

    {
        "username": "testuser",
        "password": "testpassword",
    
        "client": {
            "server_path": "/tmp/server/path",
            "client_path": "/tmp/client/path"
        },
    }
