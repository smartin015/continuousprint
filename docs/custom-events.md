# Custom Events

**Continuous Print exposes internal events that can be used by other OctoPrint plugins to trigger additional actions.**

## List of Events

See [continuousprint/data/\_\_init\_\_.py CustomEvents class](https://github.com/smartin015/continuousprint/blob/rc/continuousprint/data/__init__.py#L15) for the current list of events and their string identifiers.

**`continuousprint_start_print`**

This event fires whenever a new print is stated from a queue. This event does not fire for bed clearing, finishing, or other event-driven scripts.

**`continuousprint_cooldown`**

This event fires when the [Managed Bed Cooldown](managed-bed-cooldown.md) setting is enabled and the cooldown state is entered. It is not fired if managed bed cooldown is not enabled.

**`continuousprint_clear_bed`**

This event fires when the bed clearing script is executed.

**`continuousprint_finish`**

This event fires when the finishing script is executed.

**`continuousprint_cancel`**

This event is fired when the current print is cancelled by Continuous Print, e.g. when spaghetti has been detected.

## Example: OctoPrint-IFTTT

[OctoPrint-IFTTT](https://plugins.octoprint.org/plugins/IFTTT/) is an example of a plugin that performs actions based on events. Custom events (e.g. `continuousprint_clear_bed`) go in the `Event Name` column of the settings page.
