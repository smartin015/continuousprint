# Continuous Print Queue Plugin

Octoprint plugin that allows users to generate a print queue, specify a print bed clearning script and run the queue which will

WARNING: Your printer must have a method of clearing the bed automatically, with correct GCODE instructions set up in this plugin's settings page - damage to your printer may occur if this is not done correctly.

# Setup

## Add the plugin

1. In the OctoPrint UI, go to `Settings` -> `Plugin Manager` -> `Get More`
1. Search for "Continuous Print", and click Install, following any instructions
   * If you can't find the plugin, you can also put https://github.com/Zinc-OS/continuousprint/archive/master.zip into the "...from URL" section of the Get More page.
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
git clone https://github.com/Zinc-OS/continuousprint.git
cd continuousprint
octoprint dev plugin:install
octoprint serve
```

You should see "Successfully installed continuousprint" when running the install command, and you can view the page at http://localhost:5000.

## Installing dev version on OctoPi

Users of [OctoPi](https://octoprint.org/download/) can install a development version directly on their pi as follows:

1. `ssh pi@<your octopi hostname>` and provide your password (the default is `raspberry`, but for security reasons you should change it with `passwd` when you can)
1. `git clone https://github.com/Zinc-OS/continuousprint.git`
1. Uninstall any existing continuous print installations (see `Settings` -> `Plugin Manager` in the browser)
1. `cd continuousprint && ~/oprint/bin/python3 setup.py install`

Note that we're using the bundled version of python3 that comes with octoprint, **NOT** the system installed python3. If you try the latter, it'll give an error that sounds like octoprint isn't installed.

## Developer tips

* Remember, you can enable the virtual printer under `Virtual Printer` in OctoPrint settings.
* Octoprint currently uses https://fontawesome.com/v5.15/icons/ for icons.

