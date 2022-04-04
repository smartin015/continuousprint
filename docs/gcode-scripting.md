# GCODE Scripting Exapmles

GCODE scripts can be quite complex - if you want to learn the basics, try reading through [this primer](https://www.simplify3d.com/support/articles/3d-printing-gcode-tutorial/).

## Bed cleaing scripts

When Continuous Print is managing the queue, this script is run after every print completes - **including prints started before queue managing begins**. 

Your cleaning script should remove all 3D print material from the build area to make way for the next print.

### Gantry Sweep

This script example assumes a box style printer with a vertical Z axis and a `200mm x 235mm` XY build area. It uses the printer's extruder to
push the part off the build plate.

```
M17 ;enable steppers
G91 ; Set relative for lift
G0 Z10 ; lift z by 10
G90 ;back to absolute positioning
M190 R25 ; set bed to 25 and wait for cooldown
G0 X200 Y235 ;move to back corner
G0 X110 Y235 ;move to mid bed aft
G0 Z1 ;come down to 1MM from bed
G0 Y0 ;wipe forward
G0 Y235 ;wipe aft
G28 ; home
```

### Advance Belt

This script works with a belt printer (specifically, a [Creality CR-30](https://www.creality.com/goods-detail/creality-3dprintmill-3d-printer)). The belt is advanced to move the print out of the way before starting another print.

```
M17 ; enable steppers
G91 ; Set relative for lift
G21 ; Set units to mm
G0 Z10 ; advance bed (Z) by 10mm
G90 ; back to absolute positioning
M104 S0; Set Hot-end to 0C (off)
M140 S0; Set bed to 0C (off)
```

### Wait for Input

Use this script if you want to remove the print yourself but use the queue to keep track of your prints. It uses an [`@ Command`](https://docs.octoprint.org/en/master/features/atcommands.html) to tell OctoPrint to pause the print. The printer will stay paused until you press "Resume" on the OctoPrint UI.

```
M18 ; disable steppers
M104 T0 S0 ; extruder heater off
M140 S0 ; heated bed heater off
@pause ; wait for user input
```

## Queue finished scripts

This script is run after all prints in the queue have been printed. Use this script to put the machine in a safe resting state. Note that the last print will have already been cleared by the bed cleaning script (above).

### Generic

This is a generic "heaters and motors off" script which should be compatible with most printers.

```
M18 ; disable steppers
M104 T0 S0 ; extruder heater off
M140 S0 ; heated bed heater off
M300 S880 P300 ; beep to show its finished
```

### Advance Belt

This matches the "Advance Belt" script above.

```
M17 ; enable steppers
G91 ; Set relative for lift
G21 ; Set units to mm
G0 Z300 ; advance bed (Z) to roll off all parts
M18 ; Disable steppers
G90 ; back to absolute positioning
M104 S0; Set Hot-end to 0C (off)
M140 S0; Set bed to 0C (off)
```
