# LAN Queues (Early Alpha Feature)

**A LAN queue is a local network queue that multiple 3D printers can print from.**

It's not unusual to have multiple 3D printers - in home workshops, in the prototyping industry, and even for 3D printing services (e.g. Shapeways) and manufacturers that manage hundreds/thousands of them.

Continuous Print provides a single, local queue by default - managed by a single printer with a single instance of OctoPrint. But by adding LAN queues, multiple printers can coordinate together over the network to print jobs from the same queue(s).

!!! Important

    This feature is not yet proven. If you encounter problems, please read this guide thoroughly before [creating an issue](https://github.com/smartin015/continuousprint/issues/new/choose) if you're unable to resolve them.

!!! Danger

    LAN queues are intended for trusted, local (LAN) networks only - not for cross-network (WAN) use cases. Using LAN queues across networks is insecure and strongly discouraged.

## Behavior

### LAN Queues manage Jobs, not Sets/Files

Queues operate at the level of a Job (see [Sets and Jobs](/advanced-queuing/#sets-and-jobs) for disambiguation). All work described by the job will be completed by the printer which acquires it. In other words, **the work within a job will not be distributed across printers**. This is to ensure compatability with future work to support WAN / decentralized network printing, ensuring that all prints of any job are guaranteed to end up in the same place.

### Queue Strategies

When a printer is done with its job, it will choose the next one based on whichever strategy is configured for the queue it's printing from (configurable in "Setup" below):

*  **In-Order** prints linearly down the queue from top to bottom, one job at a time.
*  **Least Manual** (not yet implemented) selects a printing order which avoids excessive filament changes and other manual actions.

The overall strategy *between* queues is currently in-order, i.e. all prints in the topmost queue will be executed before moving onto the next queue, and so on. This will eventually change to allow a top-level strategy which dictates which queue to print from.

### GCODE Limitations

3D print slicers generate a `*.gcode` file for a particular make and model of 3D printer - running that file on a different printer than the one for which it was sliced would likely damage that printer (or maybe just fail to print properly).

The current LAN queue implementation is bound by this limitation - **your LAN queue must only have the same make and model of printer as members**. [Design work is underway](https://github.com/smartin015/continuousprint/issues/54) to allow for multiple printer types to pull from the same queue, but that work is secondary to providing a stable first implementation that works for the simpler case where all printers in the queue are identical.

## Setup

By default, no LAN queues are configured and all prints are local to the specific instance of Octoprint.

**You will need a working instance of OctoPrint (with the Continuous Print plugin installed) for every (identical) printer you wish to have join the queue.**

## Add a LAN queue

1. Open OctoPrint's settings page
2. Click through to Continuous Print
3. Click the Queues button to go to the queue settings page.
4. Click the "Add Queue" button to add a new LAN queue.
5. Fill in the inputs, but keep in mind:
    * Each queue must have a unique name (which cannot be `local` and `archive` - these are reserved)
    * Hostname:Port must be of the form `hostname:port` (e.g. `0.0.0.0:6789`, `localhost:5001`, `myhostname:9007`)
        * A hostname of `localhost` will only connect to other OctoPrint instances on the same host. If you're unsure what to specify here, try `0.0.0.0` which [binds to all IP addresses on the host](https://en.wikipedia.org/wiki/0.0.0.0).
    * Access control may be a factor if you're using a port number below 1024 (see [privileged ports](https://www.w3.org/Daemon/User/Installation/PrivilegedPorts.html))
    * You may experience silent failures if you specify a port that's already in use by another process.
    * All LAN queues are only visible to other devices on the same network, unless you've taken steps to expose ports (NOT recommended).
6. When you've finished configuring your queues, click `Save`.

If everything is working properly, you'll see the changes reflected in the queues on the Continuous Print tab with the queue(s) you added. It will show no other peers connected to it, but that's because we still have to set them up. Complete steps 1-6 for all remaining printers, and you should see them as peers when you look at the header of the queue.

## Submit a job

1. Click the checkbox next to the job to select it.
2. Click the paper airplane icon, then the name of the queue you want to send the job to.

The job will disappear from the local queue and show up on the LAN queue.

!!! Tip
    You can also bulk add queue items by selecting multiple (via the checkbox) and following the same steps.

## Cancel a job

1. Click the checkbox next to the job in your LAN queue.
1. Click the trash can icon that appears, or the up-arrow icon to move it back to the local queue.

The job will disappear from the LAN queue (arriving back in the local queue if you clicked the arrow).
