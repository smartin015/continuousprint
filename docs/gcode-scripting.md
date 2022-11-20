# Scripting

**Control what happens in between queued prints by using Events to run Scripts**.

## Events

Events fire at certain points when the queue is being run - when a print completes, for instance. You can see the full list of events by going to `Settings > Continuous Print > Events` or [looking here in the source code](https://github.com/smartin015/continuousprint/blob/master/continuousprint/data/__init__.py).

When an event fires, you can run one or more configured scripts. These events are also visible to other OctoPrint plugins (e.g. [OctoPrint-IFTTT](https://plugins.octoprint.org/plugins/IFTTT/)) and can be used to perform actions in them.

## Scripts

Event scripts, just like 3D print files, are in GCODE. Each script is a series of commands that are sent to the printer that tell it to move, heat up, cool down, etc.

GCODE scripts can be quite complex - it's recommended to load default scripts if you're just getting started, or as examples to modify. If you want to learn to make your own scripts, try reading through [this primer](https://www.simplify3d.com/support/articles/3d-printing-gcode-tutorial/).

## Load Defaults

If your 3D printer is common, you should first check the user-contributed default scripts for your printer.

To load default scripts:

1. Navigate to `Settings > Continuous Print > Profile` and ensure the make and model of your 3D printer is correct.
1. Click on the `Scripts` tab, then click `Load from Profile`. You should see two new scripts ("Bed Clearing" and "Finished") appear matching your printer make and model.
1. Click on the `Events` tab and scroll down to `Print Success`.
1. Replace the Bed Clearing script there with the new one.
1. Scroll down to `Queue Finished` and replace its script with the new script.
1. Click `Save`.

If you want to contribute a change or a new default script, read the [Contributing](#contributing) section below. You can browse through all the scripts [here](https://github.com/smartin015/continuousprint/blob/master/continuousprint/data/gcode_scripts.yaml).

## Custom Scripts

You can also set up your own custom scripts to run when events happen.

To add a new custom script:

1. Navigate to `Settings > Continuous Print > Scripts`, then click `New Script`. A new (unnamed) script will appear in the list.
1. Put your GCODE script in the large text box - as an example, try typing in `@pause` to pause the print and wait for you to resume it.
1. Give the script a name (e.g. "Example Script"), then click the Done button at the bottom of the edit area.

Your script is now created, but it will not run until we assign it to one or more events.

To register the script to an event:

1. Click the `Events` tab and scroll to the desired event. For example, `Queue Deactivated` which runs when you click the `Stop Managing` button.
1. Click the `Add Script` button, then the name of your script. You should now see it listed below the event name.
1. Click `Save` to save your settings.

Now try it out! Whenever your event fires, it should run this new script.

!!! Tip

    You can use the same script for multiple events, e.g. run bed clearing after each print *and* when the last print is finished.

    You can also run multiple scripts in the same event - they are executed from top to bottom, and you can drag to reorder them.

### Optional: Use BedReady to check bed state

[OctoPrint-BedReady](https://plugins.octoprint.org/plugins/bedready/) is a plugin that checks the webcam image of the bed against a refrence image where the bed is clear.

If you install BedReady, you can add an automated check that the bed is clear for the next print by adding `@BEDREADY` onto the end of your bed clearing script.

## Preprocessors

You may discover that you want more complex behavior than just running the same script every time an event happens - maybe you want to revert to manual part removal if the print is too small to remove automatically, or you want to sweep prints off in a different direction depending on their material or file name.

This can be done by adding a **Preprocessor**, which is a little bit of extra code that modifies how your GCODE script is executed.

Preprocessors are optionally added to assigned scripts in the `Events` settings tab. They evaluate based on instantaneous state details, print file metadata, and optional externally provided state.

### Language

Preprocessors are evaluated using [ASTEVAL](https://newville.github.io/asteval/) which is a [Python](https://www.python.org/)-like interpreter. Most simple Python scripts will run just fine.

If you're new to writing Python code and the examples in `Settings > Continuous Print > Scripts` don't have the answers you need, check out [here](https://wiki.python.org/moin/BeginnersGuide) for language resources, or open a new [discussion on GitHub](https://github.com/smartin015/continuousprint/discussions).

### Return Value

The final line of a preprocessor is used to modify the behavior of the GCODE script:

* **If the last line evaluates to `True` or `False`**, then it either runs or supresses the script, respectively.
* **If the last line evaluates to `None`**, then it suppresses the script.
* **If the last line evalutes to a `dict` object**, then the items are injected into the GCODE script (they're treated as keyword arguments in a call to [format()](https://docs.python.org/3/tutorial/inputoutput.html#the-string-format-method))

To clarify that last option, if you have a GCODE script that looks like:

```
G0 X{move_dist}
```

And you have a preprocessor that looks like:

```
dict(move_dist = 10 if current['path'].endswith("_right.gcode") else -10)
```

Then the printer will receive `G0 X10` for files named e.g. `file_right.gcode` and `G0 X-10` for all other files.

For more examples, see the default preprocessors and scripts in `Settings > Continuous Print > Scripts & Preprocessors` within OctoPrint. You can also browse [this YAML file](https://github.com/smartin015/continuousprint/blob/master/continuousprint/data/preprocessors.yaml) which is the source of those entries.

### Available State

When you write a Preprocessor, you will reference external information in your expression in order to return a boolean result. This is done by accessing `State` variables (referred to in [ASTEVAL docs](https://newville.github.io/asteval/) as the "symbol table").

Here's an example of what you can expect for state variables:

```
current: {
    'path': 'testprint.gcode',
    'materials': ['PLA_red_#ff0000'],
    'bed_temp': 23.59,
}
external: {<user provided>}
metadata: {
    'hash': '38eea2d4463053bd79af52c3fadc37deaa7bfff7',
    'analysis': {
        'printingArea': {'maxX': 5.3, 'maxY': 7.65, 'maxZ': 19.7, 'minX': -5.3, 'minY': -8.5608, 'minZ': 0.0},
        'dimensions': {'depth': 16.2108, 'height': 19.7, 'width': 10.6},
        'estimatedPrintTime': 713.6694555778557,
        'filament': {'tool0': {'length': 311.02239999999875, 'volume': 0.0}}
    },
    'continuousprint': {
        'profile': 'Monoprice Mini Delta V2'
    },
    'history': [
        {
          'timestamp': 1660053581.8503253,
          'printTime': 109.47731690102955,
          'success': True,
          'printerProfile': '_default'
        },
    ],
    'statistics': {
        'averagePrintTime': {'_default': 113.51082421375965},
        'lastPrintTime': {'_default': 306.7005050050211}
    }
}
```

Note that `path`, `materials`, and `bed_temp` are all instantaneous variables about the current state, while `metadata` comes from file metadata analysis and is absent if `path` is None or empty.

See also `update_interpreter_symbols` in [driver.py](https://github.com/smartin015/continuousprint/blob/master/continuousprint/driver.py) for how state is constructed and sent to the interpreter.

### External State

The `external` section of the state example above is where you'll find any custom data you inject via POST request to `/automation/external` - see the [API docs](/api/#inject-external-data-into-preprocessor-state) for details.

External data can come from anywhere that can reach your OctoPrint instance on the network - microservices, CRON jobs, IOT and other embedded systems, etc. However, ASTEVAL disables many of the more complex features of Python for security reasons. For this reason, you may want to do heavy processing (e.g. image or video segmentation, object detection, point cloud processing) elsewhere and then push only the information needed to format the event script.

## Contributing

When you come up with a useful script for e.g. clearing the print bed, consider contributing it back to the community!

1. Visit [the repository](https://github.com/smartin015/continuousprint) and click the "Fork" button on the top right to create a fork.
2. Go to [printer_profiles.yaml](https://github.com/smartin015/continuousprint/tree/rc/continuousprint/data/printer_profiles.yaml) and check to see if your printer make and model are present. If they aren't, click the pencil icon on the top right of the file to begin editing.
3. When you're done adding details, save it to a new branch of your fork.
4. Now go to [gcode_scripts.yaml](https://github.com/smartin015/continuousprint/tree/rc/continuousprint/data/gcode_scripts.yaml) and edit it in the same way, adding your gcode and any additional fields.
5. Save your changes - to a new branch if you didn't have to do anything on step 2, otherwise to the same branch you created earlier.
6. Check one last time that the script names match those provided in your printer profiles `defaults` section, then submit a pull request. **Make sure to do a PR against the `rc` branch, NOT the `master` branch.**
