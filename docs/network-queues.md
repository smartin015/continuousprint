# Network Queues

**A Network Queue is a queue that multiple 3D printers print from via the local or world internet.**

It's not unusual to have multiple 3D printers - in home workshops, in the prototyping industry, and even for 3D printing services (e.g. Shapeways) and manufacturers that manage hundreds/thousands of them.

In addition to providing a local queue by default, Continuous Print also configures a default LAN queue that will automatically link any other printers on your local network. Printers can then coordinate together over the network to print jobs from the same queue.

!!! Warning

    Network Queues are intended for **trusted networks** only. Guard your security keys closely and don't share them publicly, or else anyone can print anything on your printer network!

!!! Info

    **If you upgraded from v2.0.0 or earlier**, the default LAN Queue will not be added (a compatibility measure). If you don't see the default LAN Queue, please read and follow [Additional Network Queues](#additional-network-queues) for instructions on how to set up your own.

## Setup

To use network queues, you must first install [PeerPrint](https://github.com/smartin015/peerprint) and enable the default LAN queue that comes with installation:

1. Go to `Settings > Plugin Manager > Get More`, search for `PeerPrint` and click the `Install` button.
2. Wait for the dialog to complete, then restart OctoPrint.
3. Once OctoPrint has restarted, go to `Settings > Continuous Print > Queues`. You should see a new queue labeled `LAN`. Click the checkbox under `Enabled`, then click `Save`.

You should now see the new LAN queue below the usual (now labeled "local") queue.

**You will need a working instance of OctoPrint (with the Continuous Print plugin installed) for every printer you wish to have join the queue.** Go ahead and repeat the above process for each printer you wish to set up.

See what printers are connected to the queue by hovering your mouse over the queue name:

![Hover Example](/hover_viz.png)

If printers are missing from this list, make sure they have the same versions of OctoPrint and Continous Print installed and enabled, and that they are on networks  that can reach each other. This means:

* same LAN for local PeerPrint networks
* both WAN-connected for global networks
* sharing at least one in-common [network driver](https://docs.docker.com/network/) if containerized (Docker, podman, etc.)

See [Additional Network Queues](#additional-network-queues) below if you need more advanced Network Queue configuration.

## Submit a job

Submitting a job is as simple as dragging it from the "local" queue to your Network Queue. After a brief pause to transfer data, the job will be moved out of the local queue and into the Network Queue.

## Undo job submission

Submission can be undone simply by dragging the job back to the "local" queue. This can be done by any printer in the Network Queue, but of course it will be moved to that printer's local queue only (local queues aren't shared).

!!! Info

    The printer receiving the local job may not have the local `.gcode` files initially, so the files are fetched and copied to `ContinuousPrint/imports/<job name>/` and the Set paths are auto-updated accordingly.

## Edit a Network Queue job

You can edit jobs in Network Queues just as in Local queues - see [Queuing Basics](advanced-queuing.md) for more details.

## Cancel a Network Queue job

1. Click the checkbox next to the job in your Network Queue.
1. Click the trash can icon that appears.

The job will disappear from the Network Queue and no longer be printed. Note that a job cannot be deleted if a printer is actively printing it.

## Details

### Network Queues manage Jobs, not Sets/Files

Queues operate at the level of a Job (see [Sets and Jobs](/advanced-queuing/#sets-and-jobs) for disambiguation). All work described by the job will be completed by the printer which acquires it. In other words, **the work within a job will not be distributed across printers**. This is to ensure compatability with future work to support WAN / decentralized network printing, ensuring that all prints of any job are guaranteed to end up in the same physical location.

### Queue Strategies

When a printer is done with its job, it will choose the next one based on whichever strategy is configured for the queue it's printing from.

There is currently only one strategy:

*  **In-Order** prints linearly down the queue from top to bottom, one job at a time.

In the future, you will be able to customize how your printer works on the queue, e.g. choosing jobs in a way which avoids excessive filament changes and other manual actions.

The overall strategy *between* queues is currently in-order, i.e. all prints in the topmost queue will be executed before moving onto the next queue, and so on. This will eventually change to allow a top-level strategy which dictates which queue to print from.

### GCODE Limitations

3D print slicers generate a `*.gcode` file for a particular make and model of 3D printer - running that file on a different printer than the one for which it was sliced would likely damage that printer (or maybe just fail to print properly).

This can be mitigated in several ways:

1. Use exactly the same make and model of printer for all members of the Network Queue
2. Configure the correct [profiles](/printer-profiles) for all Sets so that each type of printer has its own compatible `*.gcode` files to fully print the job.
3. Create jobs using `STL` model files instead of `*.gcode`. This requires [Automatic Slicing](/auto-slicer) to be correctly configured, but ensures that only trusted GCODE will run on your printer.

!!! Info

    For users of [Kiri:Moto slicer](https://grid.space/kiri/), the second mitigation is automatic: gcode files are automatically analyzed and the printer profile applied when they are added to the queue. See the [Printer Profiles](/printer-profiles) page for more details.

### Additional Network Queues

You can add additional Network Queues, or remove/modify the default Network Queue if desired:

1. Open OctoPrint's settings page
2. Click through to PeerPrint
3.
3. Click the Queues button to go to the queue settings page.
4. Click the "Add Queue" button to add a new Network Queue.
5. Fill in the inputs, but keep in mind:
    * Each queue must have a unique name (which cannot be `local` and `archive` - these are reserved)
    * Address:Port must be either set to `auto` or have the form of `ip_address:port` (e.g. `192.168.1.43:6789`)
        * A hostname of `localhost` will only connect to other OctoPrint instances on the same host. If you're unsure what to specify here, try `0.0.0.0` which [binds to all IP addresses on the host](https://en.wikipedia.org/wiki/0.0.0.0).
        * If `auto` is used, an IP address and port will be selected automatically - this will probably work, but may not be correct for more complicated network setups.
    * Access control may be a factor if you're using a port number below 1024 (see [privileged ports](https://www.w3.org/Daemon/User/Installation/PrivilegedPorts.html))
    * You may experience silent failures if you specify a port that's already in use by another process.
    * All Network Queues are only visible to other devices on the same network, unless you've taken steps to expose ports (NOT recommended).
6. When you've finished configuring your queues, click `Save`.

If everything is working properly, you'll see the changes reflected in the queues on the Continuous Print tab with the queue(s) you added. It will show no other peers connected to it, but that's because we still have to set them up. Complete steps 1-6 for all remaining printers, and you should see them as peers when you look at the header of the queue.
