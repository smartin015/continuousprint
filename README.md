# Continuous Print Queue Plugin

This plugin automates your printing!

* **Add gcode files to the queue and set a number of times to print each.** The plugin will print them in sequence, running "bed clearing" script after each.
* **Group multiple files together into "jobs" and run them multiple times.** Don't make 10 boxes by printing 10 bases, then 10 lids - just define a "box" job and print box/lid combos in sequence.
* **Reduce manual intervention with failure automation.** This plugin optionally integrates with [The Spaghetti Detective](https://www.thespaghettidetective.com/) and can retry prints that fail to adhere to the bed, with configurable limits on how hard to try before giving up.

WARNING: Your printer must have a method of clearing the bed automatically, with correct GCODE instructions set up in this plugin's settings page - damage to your printer may occur if this is not done correctly. If you want to manually remove prints, look in the plugin settings for details on how to use `@pause` so the queue is paused before another print starts.

# Setup

## Add the plugin

1. In the OctoPrint UI, go to `Settings` -> `Plugin Manager` -> `Get More`
1. Search for "Continuous Print", and click Install, following any instructions
   * If you can't find the plugin, you can also put https://github.com/smartin015/continuousprint/archive/master.zip into the "...from URL" section of the Get More page.
1. Restart OctoPrint

That's it! Now let's configure it to work with your printer.

## Configure the plugin

Go to `Settings` -> `Continuous Print` and ensure the bed cleaning and queue finished scripts are correct for your 3D printer.

You can also enable settings here for compatibility with [The Spaghetti Detective](https://www.thespaghettidetective.com/) for automatic retries when the print starts failing.

## Add prints to the queue

1. Navigate to the file you wish to add in the Files dialog on the left of the page.
1. Add it to the print queue by clicking the `+` button to the right of the file name.
   * If you want to print more than one, you can click multiple times to add more copies, or set a specific count in the `Continuous Print` tab.

## Start the queue

The print queue won't start your prints just yet. To run the queue:

1. Click the 'Continuous Print` tab (it may be hidden in the extra tabs fold-out on the right)
1. Double check the order and count of your prints - set the count and order using the buttons and number box to the right of the queued print, and delete with the red `X`.
1. Click `Start Managing`.

The plugin will wait until your printer is ready to start a print, then it'll begin with the top of the queue and proceed until the bottom.

Note that when it's time to clear the print bed or finish up, a temporary `cp_\*.gcode` file will appear in your local files, and disappear when it completes. This is a change from older "gcode injecting" behavior that is necessary to support [at-commands](https://docs.octoprint.org/en/master/features/atcommands.html) in the clearing and finish scripts.

## Inspect queue items

As the print queue is managed and prints complete, you can see the status of individual prints by clicking the small triangle to the left of any individual queue item.

This opens a sub-panel showing individual print stats and results.

## Stop the queue

When all prints are finished, the plugin stops managing the queue and waits for you to start it again.

If you need to stop early, click `Stop Managing` (**Note: any currently running print will continue unless you cancel it**)

## Clean up the queue

Click the triple-dot menu for several convenient queue cleanup options. You can also remove individual queue items with the red `X` next to the item.

# Development

*Based on the instructions at https://docs.octoprint.org/en/master/plugins/gettingstarted.html*

Install octoprint locally:

```shell
git clone https://github.com/OctoPrint/OctoPrint
cd OctoPrint
virtualenv venv
source venv/bin/activate
pip install -e .
```

In the same terminal as the one where you activated the environment, Install the plugin in dev mode and launch the server:

```shell
git clone https://github.com/smartin015/continuousprint.git
cd continuousprint
octoprint dev plugin:install
octoprint serve
```

You should see "Successfully installed continuousprint" when running the install command, and you can view the page at http://localhost:5000.

## Testing

Backend unit tests are currently run manually:
```
python3 continuousprint/print_queue_test.py
python3 continuousprint/driver_test.py
```

Frontend unit tests require some additional setup (make sure [yarn](https://classic.yarnpkg.com/lang/en/docs/install/#debian-stable) and its dependencies are installed):

```
cd .../continuousprint
yarn install
yarn run test
```

This will run all frontend JS test files (`continuousprint/static/js/\*.test.js`). You can also `yarn run watch-test` to set up a test process which re-runs whenever you save a JS test file.

## Installing dev version on OctoPi

Users of [OctoPi](https://octoprint.org/download/) can install a development version directly on their pi as follows:

1. `ssh pi@<your octopi hostname>` and provide your password (the default is `raspberry`, but for security reasons you should change it with `passwd` when you can)
1. `git clone https://github.com/smartin015/continuousprint.git`
1. Uninstall any existing continuous print installations (see `Settings` -> `Plugin Manager` in the browser)
1. `cd continuousprint && ~/oprint/bin/python3 setup.py install`

Note that we're using the bundled version of python3 that comes with octoprint, **NOT** the system installed python3. If you try the latter, it'll give an error that sounds like octoprint isn't installed.

## Developer tips

* The backend (`__init__.py` and dependencies) stores a flattened representation of the print queue and
  iterates through it from beginning to end. Each item is loaded as a QueueItem (see `print_queue.py`).
* The frontend talks to the backend with the flattened queue, but operates on an inmemory structured version:
  * Each flattened queue item is loaded as a `CPQueueItem` (see continuousprint/static/js/continuousprint_queueitem.js)
  * Sets of the same queue item are aggregated into a `CPQueueSet` (see continuousprint/static/js/continuousprint_queueset.js)
  * Multiple queuesets are grouped together and run one or more times as a `CPJob` (see continuousprint/static/js/continuousprint_job.js)
  * For simplicity, each level only understands the level below it - e.g. a Job doesn't care about QueueItems.
* Remember, you can enable the virtual printer under `Virtual Printer` in OctoPrint settings.
* Octoprint currently uses https://fontawesome.com/v5.15/icons/ for icons.
* Drag-and-drop functionality uses SortableJS wrapped with Knockout-SortableJS, customized:
  * https://github.com/SortableJS/knockout-sortablejs/pull/13
  * https://github.com/SortableJS/knockout-sortablejs/issues/14

## QA

Check these before releasing:

* All buttons under the triple-dot menu work as intended
* Jobs and items can be drag-reordered
* Jobs can't be dragged into items, items can't be dragged outside jobs
* Adding a file from the Files dialog works as intended
* Setting the count for jobs and items behaves as expected
* [At-commands](https://docs.octoprint.org/en/master/features/atcommands.html) work in clearing/finish scripts
* Temporary gcode files are cleaned up after use
* Pausing and resuming the print works
* Cancelling restarts the print
* Print queue can be started and stopped; queue items complete in order
* Stylings look good in light and dark themes

## Potential future work

* File integrity checking (resilience to renames/deletions)
* Save/remember and allow re-adding of jobs
* Improved queue history/status with more stats
* Segmented status bars to better indicate run completion
* Client library to support queue management automation
* Bed clearing profiles for specific printers
* Multi-user queue modification with attribution (shows who added which prints, prevents overwriting others' jobs)
