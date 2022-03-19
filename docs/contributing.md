# Contributor Guide

*Based on the [octoprint plugin quickstart guide](https://docs.octoprint.org/en/master/plugins/gettingstarted.html)*

## 1. Install octoprint from source

Install octoprint locally:

```shell
git clone https://github.com/OctoPrint/OctoPrint
cd OctoPrint
virtualenv venv
source venv/bin/activate
pip install -e .
```

## 2. Install and start the continuous print plugin in local dev mode

In the same terminal as the one where you activated the environment, Install the plugin in dev mode and launch the server:

```shell
git clone https://github.com/smartin015/continuousprint.git
cd continuousprint
octoprint dev plugin:install
pre-commit install  # Cleans up files when you commit them - see https://pre-commit.com/. Note that venv must be activated or else flake8 raises improper errors
octoprint serve
```

You should see "Successfully installed continuousprint" when running the install command, and you can view the page at [http://localhost:5000](http://localhost:5000).

## 3. Run unit tests to verify changes

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

## 4. Install a dev version on OctoPi

Users of [OctoPi](https://octoprint.org/download/) can install a development version directly on their pi to test their changes on actual hardware.

!!! warning

    Editing code - especially unfamiliar code - can lead to unpredictable behavior. You're controlling a robot that can pinch fingers and melt plastic, so be careful and consider using the [built-in virtual printer](https://docs.octoprint.org/en/master/development/virtual_printer.html) before a physical test.

1. `ssh pi@<your octopi hostname>` and provide your password (the default is `raspberry`, but for security reasons you should change it with `passwd` when you can)
1. `git clone https://github.com/smartin015/continuousprint.git`
1. Uninstall any existing continuous print installations (see `Settings` -> `Plugin Manager` in the browser)
1. `cd continuousprint && ~/oprint/bin/python3 setup.py install`

Note that we're using the bundled version of python3 that comes with octoprint, **NOT** the system installed python3. If you try the latter, it'll give an error that sounds like octoprint isn't installed.

## Tips and Tricks

This is a collection of random tidbits intended to help you get your bearings. If you're new to this plugin (and/or plugin development in general), please take a look!

* The backend (`__init__.py` and dependencies) stores a flattened representation of the print queue and
  iterates through it from beginning to end. Each item is loaded as a QueueItem (see `print_queue.py`).
* The frontend talks to the backend with the flattened queue, but operates on an inmemory structured version:
    * Each flattened queue item is loaded as a `CPQueueItem` (see continuousprint/static/js/continuousprint_queueitem.js)
    * Sets of the same queue item are aggregated into a `CPQueueSet` (see continuousprint/static/js/continuousprint_queueset.js)
    * Multiple queuesets are grouped together and run one or more times as a `CPJob` (see continuousprint/static/js/continuousprint_job.js)
    * For simplicity, each level only understands the level below it - e.g. a Job doesn't care about QueueItems.
* Octoprint currently uses https://fontawesome.com/v5.15/icons/ for icons.
* Drag-and-drop functionality uses SortableJS wrapped with Knockout-SortableJS, both of which are heavily customized. For more details on changes see:
    * Applied fix from https://github.com/SortableJS/knockout-sortablejs/pull/13
    * Applied fix from https://github.com/SortableJS/knockout-sortablejs/issues/14
    * Discussion at https://github.com/smartin015/continuousprint/issues/14 (conflict with a different `knockout-sortable` library)

