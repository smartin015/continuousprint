# Printer Profiles

**Printer Profiles restrict the make/model of printer that's allowed to print certain files.**

## Why have profiles?

3D print slicers generate a `*.gcode` file for a particular make and model of 3D printer - running that file on a different printer than the one for which it was sliced would likely damage that printer (or maybe just fail to print properly).

In the case of a single printer running a single OctoPrint instance, this doesn't usually matter - typically only compatible GCODE files will end up in the Files list. But with [LAN Queues](/lan-queues), multiple kinds of printers may be vying for the same print Job and compatibility becomes a problem.

## Setting your printer's profile

In `Settings > Plugins > Continuous Print`, in the `Scripts > Printer Profile` section, select the manufacturer and model of your printer. If your printer is not present in the list, follow [these directions](https://smartin015.github.io/continuousprint/gcode-scripting/#contributing) to add it.

When you click `Save`, this profile will be associated with your printer.

## Automatic profile assignment

Starting with version `2.1.0`, Continuous Print will attempt to automatically infer the correct printer profile for gcode files added to the queue. This currently only works the following slicers:

* [Kiri:Moto slicer](https://grid.space/kiri/)
* [PrusaSlicer](https://www.prusa3d.com/page/prusaslicer_424/)
* TODO [Ultimaker Cura](https://ultimaker.com/software/ultimaker-cura)
* TODO [Simplify3D](https://www.simplify3d.com/)

If you want your slicer to be supported, [open a Feature Request](https://github.com/smartin015/continuousprint/issues/new?assignees=&labels=&template=feature_request.md) and include an example gcode script that you've sliced as an example.

## Assigning and removing printer profiles to/from Sets

1. Click the edit (pencil) button on a Job in your queue to enter edit mode.
2. Expand your desired Set by clicking the triangle next to its name.
3. Next to `Profiles:` you will see a drop-down. Click this and select a matching profile for your printer.
4. A new label should appear with the profile name. You can add additional profiles if your Set can be printed by other printers.
5. Remove any unwanted profiles by clicking the `X` next to them.
6. Click the "Save" button at the bottom of the Job to save your changes.

## Behavior

**If a Set has no associated profiles, any printer will attempt to print it.** This is fine if you have all the same type of printer, but becomes a hazard if you have multiple incompatible printers sharing the same LAN queue (e.g. a continuous belt printer and a small delta printer).

**If a Set has one or more associated profiles, your printer will only print it if the printer's profile is present**. For instance: a printer with the `Generic` profile will not print a Set with only a `Creality CR30` profile.

**All sets within jobs in [LAN queues](/lan-queues) MUST have an assigned profile**, or else you will not be able to submit them. This is to ensure that gcode files areprinted only by the correct printer.
