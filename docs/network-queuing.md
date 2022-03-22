# Network Queues (ALPHA)

Traditionally, owning multiple printers requires managing each printer individually. 

With Network Queues, Continuous Print now lets you set up a [many-to-many](https://en.wikipedia.org/wiki/Many-to-many_(data_model)) system of queues and printers - each queue can distribute work to many printers, and each printer can be working on many queues!

!!! warning

    **This feature is currently in an ALPHA state** - please install and try it, but expect bugs. 

    You can help make this feature more stable by [filing a bug report](https://github.com/smartin015/continuousprint/issues/new?assignees=&labels=bug&template=bug_report.md&title=) when you find them.

## Behavior

Currently, network queues operate only for OctoPrint instances on the same local area network (LAN) - if your OctoPrint hosts are connected to the same router/switch or the same WiFi network, they should be discoverable to each other. This may change in the future (see [discussion](https://github.com/smartin015/continuousprint/issues/35)).

When you enable Network Queues, you will specify a "namespace" that uniquely identifies it. This could be `default`, `my-awesome-queue`, `specific_project_queue` - whatever you like that describes what the queue will be doing. The same namespace must be provided to every OctoPrint instance you wish to have working on the queue.

Now, the queues configured for each OctoPrint instance will show up below the local queue. When you add jobs to these queues, they will be synced to all other connected printers.

When you enable the queue, printers will begin to accept jobs that they are able to print - the process for which job goes to which printer is complicated, and described in the [technical notes](https://smartin015.github.io/continuousprint/network-technical/), but it aims to maximize the amount of printing you can do with minimal time and manual effort.

When a printer claims a job, it must then print one whole copy of the job - including all copies of the items within - before it can move on to another job in the same or another queue. With many printers tackling many queues, the queued jobs may end up printing out of order. However, increasing priority is given to older, uncompleted jobs - so they should be assigned eventually!

## Configuration

TODO

## Usage

TODO

## Troubleshooting

### My OctoPrint instances aren't connecting to one another!

* Check that your instances are on the same LAN - are they plugged into the same router / connected to the same wifi network?

* Check that the namespace you provided for the print queue matches on each instance. Namespaces are case-sensitive.
