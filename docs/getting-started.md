# Getting Started

## Install the plugin

1. In the OctoPrint UI, go to `Settings` -> `Plugin Manager` -> `Get More`
1. Search for "Continuous Print", and click Install, following any instructions
   * If you can't find the plugin, you can also put https://github.com/smartin015/continuousprint/archive/master.zip into the "...from URL" section of the Get More page.
1. Restart OctoPrint

That's it! Now let's configure it to work with your printer.

!!! tip "Want cool features?"

    There's [much more automation on the way](github.com/smartin015/continuousprint/issues)! 

    To help speed up development and get features early (and if you don't mind the odd bug here and there), turn on `Release Candidates` under `Settings -> Software Update` (more info [here](https://community.octoprint.org/t/how-to-use-the-release-channels-to-help-test-release-candidates/402))

## Configure the plugin

Go to `Settings` -> `Continuous Print` and ensure the bed cleaning and queue finished scripts are correct for your 3D printer.

You can also enable settings here for compatibility with [The Spaghetti Detective](https://www.thespaghettidetective.com/) for automatic retries when the print starts failing.

## Add prints to the queue

1. Navigate to the file you wish to add in the Files dialog on the left of the page.
1. Add it to the print queue by clicking the `+` button to the right of the file name.
   * If you want to print more than one, you can click multiple times to add more copies, or set a specific count in the `Continuous Print` tab.

### Use Jobs to group your print files

The queue is actually made up of two levels: sets and jobs.

**Sets** are a single print file, printed one or more times. You created a set by following the "Add prints to the queue" step above.

**Jobs** are a collection of sets, printed one or more times. 

By default, every print file you add (as a set) is appended to a default, unnamed job at the end of the queue. If you give this job a name (by clicking the title box, typing a name, then hitting enter or clicking away) it will stop collecting new prints and a new default job will be created 

**Example 1: Batched**

Let's consider an empty queue. If you add `A.gcode` with 5 copies and `B.gcode` with 5 copies, the print order will be:

`A A A A A B B B B B`

This is great if you want all of your `A` files to print before all your `B` files, e.g. if you're working on a project that uses `A` but plan use `B` for something later. 

**Example 2: Interleaved**

Let's start again with an empty queue, but now suppose we add `A.gcode` with 1 copy, `B.gcode` with 1 copy, then set the job count to `5`. The print order will now be:

`A B A B A B A B A B`

This is exactly the pattern you would want if you were, for example, printing a box with `A.gcode` as the base and `B.gcode` as the lid. Each box would be completed in order, so you can use the first box without waiting for all the bases to print, then for the first lid to print.

You can mix and match 

## Start the queue

!!! warning "Safety check!"

    If you glossed over "Configure the plugin" above, read it now. Seriously.

    You can permanently damage your printer if you don't set up the correct GCODE instructions to a
    clear the bed and finish the queue. 

    Supporting specific printer profiles is [on the to-do list](https://github.com/smartin015/continuousprint/issues/21), but not yet available, so you'll have to do this on your own for now.

The print queue won't start your prints just yet. To run the queue:

1. Click the 'Continuous Print` tab (it may be hidden in the extra tabs fold-out on the right)
1. Double check the order and count of your prints - set the count and order using the buttons and number box to the right of the queued print, and delete with the red `X`.
1. Click `Start Managing`.

The plugin will wait until your printer is ready to start a print, then it'll begin with the top of the queue and proceed until the bottom.

Note that when it's time to clear the print bed or finish up, a temporary `cp\_\*.gcode` file will appear in your local files, and disappear when it completes. This is a change from older "gcode injecting" behavior that is necessary to support [at-commands](https://docs.octoprint.org/en/master/features/atcommands.html) in the clearing and finish scripts.

## Inspect queue items

As the print queue is managed and prints complete, you can see the status of individual prints by clicking the small triangle to the left of any individual queue item.

This opens a sub-panel showing individual print stats and results.

## Stop the queue

When all prints are finished, the plugin stops managing the queue and waits for you to start it again.

If you need to stop early, click `Stop Managing`.

!!! important 
    
    The queue may not be managed any more, but **any currently running print will continue printing**  unless you cancel it with the `Cancel` button.

## Clean up the queue

Click the triple-dot menu in the top right corner of the plugin tab for several convenient queue cleanup options. You can also remove individual queue items with the red `X` next to the item.

## Troubleshooting

If at any point you're stuck or see unexpected behavior or bugs, please file a [bug report](https://github.com/smartin015/continuousprint/issues/new?assignees=&labels=bug&template=bug_report.md&title=). 

**Be sure to include system info and browser logs** so the problem can be quickly diagnosed and fixed.



