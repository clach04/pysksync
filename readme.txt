
Usage

Start server with default settings:

    python sksync.py

This server is compatible with SK Sync Android client when "require_auth"
is set to false (the default for "require_auth" is true)

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

Sample config suitable for use with existing Android SK Sync client that
restricts paths the server will sync with:

    {
        "host": "0.0.0.0", 
        "port": 23456,
        "server_dir_whitelist": ["/tmp/override/path"],
        "server_dir_whitelist_policy": "silent",
        "client": {
            "server_path": "/tmp/server/path",
            "client_path": "/tmp/client/path"
        },
        "require_auth": false,
    }

NOTE the require_auth entry for backwards compatibility with SK Sync.

If "server_dir_whitelist_policy" is not "silent" the server will terminate
the client connection if "server_dir_whitelist" is set.

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
