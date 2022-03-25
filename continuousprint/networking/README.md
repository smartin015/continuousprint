# Network Queue Modules

## Run the server and connect to it

```
# Start the main server from the root of this repository.
# Include --debug to allow for connecting cmd.py.
python3 -m networking.server networking/testdata/headless1 --debug

# Start a command prompt to interact with the server.
# Pass the same data directory to pick up the debug socket settings.
python3 -m networking.cmd networking/testdata/headless1

# Type 'help' to see available commands (defined in `server.py`).
>> help
```

## Test UDP broadcast discovery code

```
python3 -m networking.discovery ns1 asdfasdfasd

# In another terminal
python3 -m networking.discovery ns1 asdfasdf
```

The last argument *should* be an address and port, but can be whatever if you're just testing discovery capability.

## Test LAN queue data syncing

```
python3 -m networking.lan_queue ns1 localhost:6700

# In another terminal
python3 -m networking.lan_queue ns1 localhost:6701
```

This also tests discovery - the RAFT consensus stuff runs with the ports given. 
