
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
