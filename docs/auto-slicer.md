# Automatic Slicing

## Use Case

By default, Continuous Print requires `.gcode` files to be provided to the queue to print. These files are sliced specifically for a printer make/model and are not portable.

As a result, manual effort is needed to slice 3d models via external slicers and to [assign profiles](/printer-profiles) the .gcode file in such a way that it only runs on compatible printers (especially important for heterogeneous [LAN queues](/lan-queues)).

To eliminate manual effort and human error, we can optionally set up automatic slicing, which allows us to add 3D models directly to the queue and print them without first hand-generating a `.gcode` file. These can be added interchangeably with customized `.gcode` files in the queue.

## Setup

OctoPrint supports integration with slicers via the [`SlicerPlugin` mixin](https://docs.octoprint.org/en/master/plugins/mixins.html#slicerplugin) - this mixin is inherited by various plugins to allow slicing models in the OctoPrint file manager by clicking a "slice" button next to the file.

Any plugin that uses this mixin should enable automated slicing, but for the sake of awesomeness we will use [PrePrintService](https://github.com/christophschranz/OctoPrint-PrePrintService) which can also automatically orient your model before slicing it to maximize the likelihood of a successful print.

!!! Warning

    Just because the file automatically slices, doesn't mean it'll slice *correctly*.

    PrePrintService improves the odds with automatic orientation, but this will only work as correctly as it's configured, and may not work at all if your printer is non-cartesian (e.g. a belt printer).

### Install PrePrintService

First, follow the [Setup instructions](https://github.com/christophschranz/OctoPrint-PrePrintService#setup) for PrePrintService.

After following the instructions, you should have:

1. The service container started and running
2. PrePrintService plugin installed and pointing to the service
3. The Continuous Print plugin installed (of course!)

### Configure default slicer

OctoPrint doesn't have an easy way to assign a default slicer via the UI, so it's provided in CPQ's settings instead.

Go to `Settings > Continuous Print > Behavior`, and select your PrePrintService slicer from the "Default Slicer" dropdown. Note that this will set the default system-wide.

## Usage

!!! Warning

    Auto-slicing may make weird decisions about how to orient your print, or even incorrect decisions if your printer is not correctly modeled ([e.g. belt printers are not currently supported in Tweaker](https://github.com/ChristophSchranz/Tweaker-3/issues/24)).

    It's strongly recommended to watch your first few print attempts until you're confident in the setup.

    Also, consider setting up [failure recovery](/failure-recovery) so failing prints are more likely to be caught automatically.

With the default slicer configured, it's time to try it out!

1. Upload an `.stl` file you wish to test out.
1. Click the `+` arrow in the file manager to add it to the queue.
`. Click `Start Managing`, and watch as the STL is detected, sliced into `.gcode`, and printed.
