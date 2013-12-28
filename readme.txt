
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
            "recursive": false,
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
            "recursive": true,
            "server_path": "/tmp/server/path",
            "client_path": "/tmp/client/path"
        }
    }

If "server_dir_whitelist_policy" is not "silent" the server will terminate
the client connection if "server_dir_whitelist" is set.
