# Failure Recovery

Sometimes, printers don't do what they're told.

Follow the steps in this guide to help Continuous Print recover from unexpected printing behavior.

## Spaghetti Detection and Recovery

By default, the print queue doesn't know whether your print is proceeding fine or spraying filament everywhere ("spaghettification").

Follow [The Spaghetti Detective installation instructions](https://www.thespaghettidetective.com/docs/octoprint-plugin-setup/) on your octoprint installation, then restart OctoPrint. Continuous Print will automatically detect that TSD is installed and will enable queue recovery when spaghetti is detected (TSD plugin must be `v1.8.11` or higher).

When TSD thinks the print is failing:

1. Continuous Print checks how long the current print has been running. If the failure was detected late into the print, the queue will pause and wait for user input.
2. Otherwise, it looks to see how many time this specific print has been attempted. If it's been tried too many times, the queue pauses and waits for user input.
3. Otherwise, run the failure clearing script and try the print again.

In the case of #1, TSD can cause false-positives, so this saves print time and filament even if it's a bit more manual.

For #2, either the printer isn't adhesive enough or the print itself is at fault. [Further development](https://github.com/smartin015/continuousprint/issues/37) may improve behavior here, e.g. attempting the next print in the queue before giving up in case the print itself is at fault.

### Configuration

By going to Settings -> Continuous Print and scrolling down to "Failure Recovery", you can adjust:

* The amount of time a print can run before Continuous Print pauses the qeueue on failure
* The number of allowed retries before stopping the queue
