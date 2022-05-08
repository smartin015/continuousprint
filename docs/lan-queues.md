# LAN Queues (Early Alpha Feature)

It's perfectly reasonable for people to have multiple 3D printers at home and in the prototyping industry. There are even 3D printing services (e.g. Shapeways) and manufacturers managing hundreds/thousands of printers.

While Continuous Print provides a local queue for a single instance of octoprint (and thus a single printer), you can also create shared queues that can be accessed by all 3D printers on the network that are so configured. In this way, many queues can be managed by many printers.

!!! Important

    This feature is not yet proven. Networking is hard, and peer-to-peer networking is even more so. If you encounter problems, please read this guide thoroughly and [create an issue](https://github.com/smartin015/continuousprint/issues/new/choose) if you're unable to resolve them.

## Setup

By default, no LAN queues are configured. Open OctoPrint's settings page, click through to Continuous Print, then click the Queues button.

On this page, you can click the "Add Queue" button to add network queues. Fill in the inputs, but bear in mind:

* Each queue must have a unique name (`default` and `archive` are reserved)
* Hostname:Port must be of the form `hostname:port` (e.g. `0.0.0.0:6789`, `localhost:5001`, `mydomain:9007`)
* Access control may be a factor if you're using a port number below 1024 (see [privileged ports](https://www.w3.org/Daemon/User/Installation/PrivilegedPorts.html))
* You may experience silent failures if you sepcify a port that's already in use.
* A hostname of `localhost` will only connect to other octoprint instances on the same host. If you're unsure what to specify here, try `0.0.0.0` which [binds to all IP addresses on the host](https://en.wikipedia.org/wiki/0.0.0.0).
* All network queues are only visible to other devices on the same network, unless you've taken steps to expose ports (NOT recommended).

When you've finished configuring your queues, click `Save`. You'll see the changes reflected in the queues on the Continuous Print tab.

To add and remove jobs from the network queues, simply drag them from the local queue down to the queue of choice. You can also bulk add/remove queue items by selecting multiple (via the checkbox) and clicking the appropriate arrow button.

## Queue Strategies

Each queue you add is bound by a particular strategy:

*  **In-Order** prints linearly down the queue from top to bottom, one job / set at a time.
*  **Least Manual** avoids excessive filament changes and other manual actions.

Note that the overall strategy *between* queues is in-order, i.e. all prints in the topmost queue will be executed before moving onto the next queue, and so on.
