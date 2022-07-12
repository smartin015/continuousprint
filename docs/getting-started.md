# Getting Started

## Install the plugin

1. In the OctoPrint UI, go to `Settings` -> `Plugin Manager` -> `Get More`
1. Search for "Continuous Print", and click Install, following any instructions
   * If you can't find the plugin, you can also put https://github.com/smartin015/continuousprint/archive/master.zip into the "...from URL" section of the Get More page.
1. Restart OctoPrint

That's it! Now let's configure it to work with your printer.

!!! tip "Want cool features?"

    There's [much more automation on the way](https://github.com/smartin015/continuousprint/labels/enhancement)!

    To help speed up development and get features early (and if you don't mind the odd bug here and there), turn on `Release Candidates` under `Settings -> Software Update` (more info [here](https://community.octoprint.org/t/how-to-use-the-release-channels-to-help-test-release-candidates/402))

## Configure the plugin

Go to `Settings` -> `Continuous Print` and ensure the bed cleaning and queue finished scripts are correct for your 3D printer.

**If you select your printer's make and model from the settings drop down, default scripts will be automatically configured.** If you don't see your printer in the listand want to add it, see the [GCODE Scripting contributing section](/gcode-scripting#contributing)

## Add prints to the queue

1. Navigate to the file you wish to add in the Files dialog on the left of the page.
1. Add it to the print queue by clicking the `+` button to the right of the file name.
   * If you want to print more than one, you can click multiple times to add more copies, or set a specific count in the `Continuous Print` tab.
1. Push "Save" to save your print job and make it available for printing.

!!! Tip

    See [Queueing Basics](/advanced-queuing) to learn more about how to group your prints into sets and jobs.

## Start the queue

The print queue won't start your prints just yet. To run the queue:

1. Click the 'Continuous Print` tab (it may be hidden in the extra tabs fold-out on the right)
1. Double check the order and count of your prints - set the count and order using the buttons and number box to the right of the queued print, and delete with the red `X`.
1. Click `Start Managing`.

The plugin will wait until your printer is ready to start a print, then it'll begin with the top of the queue and proceed until the bottom.

Note that the default behavior is to pause after every print to wait for you to remove the printed part - to keep printing, just press the "Resume" button on the OctoPrint UI. You can learn more about how to configure the gcode scripts [here](/gcode-scripting) if you want to further automate your printing.

## Inspect finished prints

As the print queue is managed and prints complete, you can see the status of individual prints by clicking on the "History" tab in the plugin tab window. The progress bar on particular prints and jobs will also fill in as prints complete.

## Stop the queue

When all prints are finished, the plugin stops managing the queue and waits for you to start it again.

If you need to stop early, click `Stop Managing`.

!!! important

    The queue may not be managed any more, but **any currently running print will continue printing**  unless you cancel it with the `Cancel` button.

## Clean up the queue

You can delete completed print jobs by selecting them (using the check box on the left) and pressing the trash can icon.

## Troubleshooting

If at any point you're stuck or see unexpected behavior or bugs, please file a [bug report](https://github.com/smartin015/continuousprint/issues/new?assignees=&labels=bug&template=bug_report.md&title=).

**Be sure to include system info and browser logs** so the problem can be quickly diagnosed and fixed.
