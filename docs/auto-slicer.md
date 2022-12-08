# Automatic Slicing

## Use Case

Continuous Print normally prints `.gcode` files. These files are sliced for a specific printer and are not portable across makes/models.

Typically, 3d models are sliced by external slicer programs, and [profiles](/printer-profiles) are assigned in the queue so it only runs on compatible printers. This is especially important for heterogeneous [LAN queues](/lan-queues).

With automatic slicing, **you can add 3D models directly to the queue for printing**. This eliminates some manual effort and sources of error.


## Setup

OctoPrint supports integration with slicers via the [`SlicerPlugin` mixin](https://docs.octoprint.org/en/master/plugins/mixins.html#slicerplugin) - this mixin is inherited by various plugins to allow slicing models in the OctoPrint file manager by clicking a "slice" button next to the file.

Any plugin that uses this mixin should enable automated slicing, but for the sake of awesomeness we will use [PrePrintService](https://github.com/christophschranz/OctoPrint-PrePrintService) which can also automatically orient your model before slicing it to maximize the likelihood of a successful print.

!!! Important

    Until the PrePrintService maintainer [accepts a few changes](https://github.com/ChristophSchranz/Octoprint-PrePrintService/pull/12), the plugin **will not work without edits**. If you're having trouble getting things to work, make sure you followed the installation instructions using the `test_and_fix` branch of the [forked version](https://github.com/smartin015/Octoprint-PrePrintService/tree/test_and_fix).

!!! Warning

    Just because the file automatically slices, doesn't mean it'll slice *correctly*.

    PrePrintService improves the odds with automatic orientation, but this will only work as correctly as it's configured, and may not work at all if your printer is non-cartesian (e.g. a belt printer).

### Requirements

You will need:

* A machine with [Docker](https://www.docker.com/) installed and running - this may be the same as the OctoPrint server, or a different one on the same network.
* Some form of [git](https://git-scm.com/) tool to download the forked PrePrintService repository


### Install PrePrintService

!!! Important

    This is using a **forked** version of PrePrintService; the original will not work until the changes are upstreamed.

First, we'll set up the slicer server. On your OctoPrint machine or another machine accessible over the network, run the following commands (assuming Linux):

```
git clone https://github.com/smartin015/Octoprint-PrePrintService.git --branch test_and_fix --single-branch
cd Octoprint-PrePrintService
docker-compose up --build -d

# To follow the logs:
docker-compose logs -f
```

Now, we need to install the plugin so OctoPrint can communicate with the slicer.

1. Navigate to `Settings > Plugin Manager > + Get More` in the OctoPrint interface.
2. Add the following URL into the `... from URL` box.
3. Click the adjacent `Install` button to install the forked PrePrintService plugin, then restart OctoPrint when prompted.
4. Navigate to `Settings > PrePrintService Plugin`.
5. Set the `PrePrintService URL` text input to point to your slicer server, e.g. `http://pre-print-service:2304/tweak`.
6. Uncheck the `Receive auto-rotated model file` setting to prevent the slicer server from pushing intermediate models into the queue.
7. Import a slic3r profile - you can generate one in [Slic3r](https://slic3r.org/) and export it [like this](https://manual.slic3r.org/configuration-organization/configuration-organization#:~:text=If%20you%20want%20to%20store,not%20just%20the%20selected%20profiles).
8. Click `Save` to save your settings, then restart OctoPrint.

You should be able to click the "magic wand" button next to an STL file in the file manager to slice the file to .gcode - this may take a minute or two if you installed the slicer server on a slow machine (e.g. raspberry pi).

Finally, we need Continuous Print to know what slicer to use when running STL files:

1. Navigate to `Settings > Continuous Print` in the OctoPrint interface, then click the `Behavior` tab to show behavior settings.
2. Select `PrePrintService` under `Slicer for auto-slicing`.
3. Select the profile you uploaded earlier under `Slicer Profile`.
4. Click Save.

After following these instructions, you should have:

* The service container started and running
* PrePrintService plugin installed and pointing to the service
* The Continuous Print plugin installed (of course!)

You'll know you have the correct settings when you see in the logs:

```
Connection to PrePrintService on <...> is ready
```

## Usage

!!! Warning

    Auto-slicing may make weird decisions about how to orient your print, or even incorrect decisions if your printer is not correctly modeled ([e.g. belt printers are not currently supported in Tweaker](https://github.com/ChristophSchranz/Tweaker-3/issues/24)).

    It's strongly recommended to watch your first few print attempts until you're confident in the setup.

    Also, consider setting up [failure recovery](/failure-recovery) so failing prints are more likely to be caught automatically.

With the default slicer configured, it's time to try it out!

1. Upload an `.stl` file you wish to test out.
1. Click the `+` arrow in the file manager to add it to the queue.
`. Click `Start Managing`, and watch as the STL is detected, sliced into `.gcode`, and printed.

Note that you can mix `.gcode` and `.stl` files in your queue, and Continuous Print will handle them accordingly.
