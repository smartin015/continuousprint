# Action Commands

If you interact with your 3D printer using its display (touchscreen, LCD, or similar), you may be interested in action commands.

**Action Commands are messages sent by the printer to OctoPrint when a user performs an action on the printer's display.**

## Standard Action Commands

OctoPrint supports several actions out of the box - see [here](https://docs.octoprint.org/en/master/features/action_commands.html) for more details.

Proper handling of these commands by Continuous Print is [still under development](https://github.com/smartin015/continuousprint/issues/95).

**Your printer firmware must also support action commands** for this to work (see [Firmware Support for Action Commands](#firmware-support-for-action-commands) below).

## Custom actions for Continuous Print

Currently, the Continuous Print plugin supports a single custom action command:

```
// action:queuego
```

When received from the printer, this message instructs the Continuous Print plugin to start managing the queue - equivalent to clicking "Start Managing" on the UI.

**This command is non-standard and requires additions to firmware** - in particular, a custom menu entry must be added in [CUSTOM_MENU_MAIN of Configuration_adv.h for Marlin firmware](https://github.com/MarlinFirmware/Marlin/blob/2.0.x/Marlin/Configuration_adv.h#L3900) which issues a `M118 //action:queuego` command.

## Firmware support for Action Commands

Not all printers support Action Commands - it depends on the firmware they're running. The easiest way to know if your printer supports action commands is to watch the Terminal tab in OctoPrint for occurrences of `// action:<command>`. If these appear e.g. when a print is cancelled from the printer's interface, then it's supported.

Adding support for action commands for your printer involves updating the printer's firmware, which is a device-specific process. Check for user-contributed firmwares which include this support - for Marlin-based firmwares for instance, you want to ensure `HOST_ACTION_COMMANDS` is defined in the firmware (see [here](https://github.com/MarlinFirmware/Marlin/blob/2.0.x/Marlin/Configuration_adv.h#L4004)).
