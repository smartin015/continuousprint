# Network Queues: Decentralized, Distributed 3D Printing 

## Audience

This document assumes a basic understanding of networking and peer-to-peer communications.

## Abstract

Continuous Print's Network Queues makes distributed 3D printing available to everyone, not just large companies investing heavily in technical infrastructure. 

UDP multicast service discovery supports easy onboarding into a distributed cluster of 3D printers which can tackle multiple shared job queues. 

Namespacing of print queues allows many-to-many association of queues to printers; individual printers can thus contribute to multiple projects/disciplines which maximizes productive time even with variable project load.

Printers coordinate via RAFT consensus (provided by [PySyncObj](https://github.com/bakwc/PySyncObj)) to synchronize the state of the queue, printer statuses, and assigned jobs. 

The work assignment strategy can vary per queue - an initial implementation using [PuLP](https://coin-or.github.io/pulp/) for linear optimization factors in printer busyness, added manual effort, and job age in order to maximize throughput while also limiting queue starvation and human busywork.

The implementation is currently suitable for groups of trusted devices on local networks - further development can enable WAN and even anonymous queueing driven by [Ethereum Smart Contracts](https://ethereum.org/en/smart-contracts/)

## Problems

### Fleet Management

It's not so unreasonable for people to have multiple 3D printers at home, or in the prototyping industry. Even more extreme are 3D printing services (e.g. Shapeways) managing hundreds/thousands of printers.

The continuous print queue is a plugin for a single instance of octoprint, and guides like [this one](https://all3dp.com/2/octoprint-multiple-printers/) suggest the easiest way to manage multiple printers is with multiple instances of octoprint. This means also multiple instances of the plugin, with independent queues.

Providing a single queue that can feed many printers would reduce the mental effort required to keep the fleet of 3D printers busy.

### Multi-disciplinary Contributions

3D printing has been used to manufacture parts for many different purposes across many disciplines. Whole communities have emerged (e.g. [Thingiverse](http://thingiverse.com)) that collect, refine, and distribute 3D printed solutions to problems.

3D printers themselves - at least those not part of a 3D printing service like Shapeways - often experience periods of extended downtime when the purpose they're being used for does not require much printing. 

Assigning multiple queues to the same printer expands the pool of doable work. This reduces the amount of time spent idle, and can also reduce the number of printers needed to do the work.

### Network configuration

With 3D printing reaching the consumer market, most users of 3D printers today have a limited knowledge of networking. Network management is also unrelated to turning STLs into 3D printed parts, so efforts there should be minimized.

## Solution

Continuous Prints' Network Queues combine several technologies to provide distributed, peer-to-peer job queues which 3D printers can join to receive work. Emphasis is placed on ease of onboarding, to allow for users with limited networking knowledge to quickly set up a shared queue that feeds multiple printers.

Continuous Print is itself a plugin to OctoPrint, which runs on a dedicated device (typically a raspberry pi) and hosts a web view of the printer state.

### Service discovery

When Network Queueing is enabled, a brief service discovery period begins. At this time, the host begins sending UDP broadcast packets containing the address and port where the specific queue is served (see "Queue state synchronization" below).

All other hosts on the network listen for UDP broadcast packets, filtering down to ones matching the namespaces for which they're configured.

When the service discovery period ends (nominally ~5 seconds after the queue is enabled), the queue itself is initialized with the list of peers it saw during the discovery period. 

### Queue state synchronization

Queue initialization invokes [PySyncObj](https://github.com/bakwc/PySyncObj), a python implementation of the RAFT protocol for leader election and log replication. When a host intitializes the queue, the RAFT leader plays back the state of the queue. This synchronizes the host so it has the same state, specifically:

* Jobs present in the queue, when they were added, STL files they are composed of, and counts of each file to print
* 3D printer members of the queue and their current states - including time until idle, expected cost of triggering manual effort, and other constraints which would prevent them from printing certain jobs.
* Assignments of jobs to printers

Permissions are as follows:

* Any printer can modify the job list by adding, removing, or updating jobs, except for jobs which are currently assigned to a printer.
* A printer can modify the membership list only for its own entry
* A printer can only modify its own job assignment

### Network resilience

When new nodes wish to join the queue, the "Service discovery" steps are followed and UDP broadcast packets sent. Members of an active queue see these packets and a command to add this host to the RAFT consensus is executed.

When nodes disappear from the network, a brief TTL period is observed, then the membership in the RAFT consensus group is removed.

Nodes can join and leave the queue as much as they want, and the state of the queue will be replayed each time they join.

### Work assignment strategy

When a printer becomes idle and ready to print something new, it begins work assignment.

This process sets up a linear optimization problem and runs it through PuLP. The assignment code can be seen in `continuousprint/scheduler.py`.

TODO describe optimization problem

### File sharing

Each printer instance has its own local filesystem. Before a printer starts a job, it first ensures that it has all the print files required for the job available locally. This is done by consulting a RAFT-synchronized file registry, then fetching the file from whichever host has it.

To ensure that naming conflicts do not exist, the MD5 hash of the file contents is the registry key. This requires computing the hash of print files upon addition to the queue - irrelevant other print files should be omitted.

## Simulation & Testing

### Discovery

Run these scripts in different terminals to see service discovery in action. Changing `ns1` changes the namespace.

```
python3 -m networking.discovery ns1 service1
python3 -m networking.discovery ns1 service2
python3 -m networking.discovery ns1 service3
```

### LAN queue onboarding

Verify queues can auto-discover and connect to each other by running these commands in separate terminals:

```
python3 -m networking.lan_print_queue ns1 localhost:6700
python3 -m networking.lan_print_queue ns1 localhost:6701
```

Typing a string and hitting "enter" adds a new fake job onto the queue.

### Basic queue assignment testing

Run any of the `schedule*.yaml` files in `testdata/` through the scheduler to see what schedule it picks:

```
python3 -m networking.scheduler testdata/schedule1.yaml
```

### Network queue simulation

## Results

TODO show results of optimizer runs

## Caveats

TODO describe limitiations for optimizer

## Future

* Blockchain enabled distributed anonymous queues (smart contracts)
* More sophisticated selection policy
* Time-sensitive queueing behavior

## Conclusion

TODO
