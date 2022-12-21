# Job Files

**`.gjob` files store everything that a printer needs to print a Continuous Print job**.

!!! info "Why create a new file type?"

    3D print slicers generate a `*.gcode` file for a particular make and model of 3D printer - running that file on a different printer than the one for which it was sliced would likely damage that printer (or maybe just fail to print properly).

    Similarly, GCODE doesn't allow for quickly changing the number and type of objects which are printed - which is something Continuous Print does as a base feature.

    Other metadata (like [material types](/material-selection) and [printer profile](/printer-profiles) supported by the GCODE file) are also non-standard and stored in a slicer-specific way, if at all.

    For these reasons, it becomes useful to define the `.gjob` file type.


## Creating a .gjob file

1. Click the check box next to one or more Jobs in the Queues tab to select them.
2. Click the save (floppy disk) icon that appears at the top of the queue to save to `.gjob`.

All saved `.gjob` files will appear in the Files panel on the left.

## Loading a .gjob file

To load a `.gjob` file, click the `+` button next to a `.gjob` file in the Files panel.

The job will be inserted at the bottom of the queue in an edit mode - make any desired changes, then hit Save.

## Technical Details

Under the hood, a `.gjob` is really just a `.zip` file containing the various `.gcode` files, plus a `manifest.json` file which describes how to print them.

If you're interested in learning more about how these jobs are built, see the [PeerPrint implementation](https://github.com/smartin015/peerprint/blob/main/peerprint/filesharing.py)
