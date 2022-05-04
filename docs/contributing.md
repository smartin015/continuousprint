# Contributor Guide

Follow these steps if you'd like to set up a development environment for contributing changes back to Continuous Print.

If you just want to run the plugin, see [Getting Started](/getting-started/).

*This guide is based on the [octoprint plugin quickstart guide](https://docs.octoprint.org/en/master/plugins/gettingstarted.html)*

## 1. Install octoprint from source

Install octoprint locally:

```shell
git clone https://github.com/OctoPrint/OctoPrint
cd OctoPrint
virtualenv venv
source venv/bin/activate
pip install -e .
```

## 2. Install dev tools

!!! important

    Perform this step **in a different terminal** - NOT using the venv we set up for OctoPrint. The
    dev dependencies are known to conflict with OctoPrint's dependencies and can break your OctoPrint installation.

It is recommended to [fork](https://docs.github.com/en/get-started/quickstart/fork-a-repo) this repository so that it's easier to submit your changes back to the main repo later (see "Submit a pull request" below).

```
git clone https://github.com/smartin015/continuousprint.git
cd continuousprint
pip install -r dev-dependencies.txt
pre-commit install
```

You can verify good installation by running `pre-commit run --all-files`. If everything passes, you're good to go.

## 2. Install and start the continuous print plugin in local dev mode

In the same terminal as the one where you activated the environment (see step 1), install the plugin in dev mode and launch the server:

```shell
cd ../continuousprint
octoprint dev plugin:install
octoprint serve
```

You should see "Successfully installed continuousprint" when running the install command, and you can view the page at [http://localhost:5000](http://localhost:5000).

### Editing docs

Continuous Print uses [mkdocs](https://www.mkdocs.org/) to generate web documentation. All documentation lives in `docs/`.

```shell
pip install mkdocs mkdocs-material
```

if you installed the dev tools (step 2) you can run `mkdocs serve` from the root of the repository to see doc edits live at [http://localhost:8000](http://localhost:8000).

## 3. Run unit tests to verify changes

When you've made your changes, it's important to test for regressions.

Run python tests with this command:

```
python3 -m unittest *_test.py
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

## 5. Submit a pull request

When you've made and tested your changes, follow the remaining instructions for [contributing to projects](https://docs.github.com/en/get-started/quickstart/contributing-to-projects) to create a pull request.

!!! important

    New pull requests must be submitted to the `rc` branch, **not to the `master` branch**.

    Additonally, the [plugin version line](https://github.com/smartin015/continuousprint/blob/rc/setup.py#L17) in `setup.py` **must have an incremented `rc` number** (e.g. `1.5.0rc2` -> `1.5.0rc3`, `1.6.1` -> `1.6.2rc1`).

    This allows users to test the "release candidate" and shake out any bugs before everyone receives the change.

You should receive a review within a day or so - if you haven't heard back in a week or more, [email the plugin author](https://github.com/smartin015/continuousprint/blob/master/setup.py#L27).

## Tips and Tricks

This is a collection of random tidbits intended to help you get your bearings.

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
