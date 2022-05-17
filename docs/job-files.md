# Job Files

3D print slicers generate a `*.gcode` file for a particular make and model of 3D printer - running that file on a different printer than the one for which it was sliced would likely damage that printer (or maybe just fail to print properly).\

Similarly, GCODE doesn't allow for quickly changing the number and type of objects which are printed - which is something Continuous Print does as a base feature. Other metadata (like material types and the type of printer supported by the GCODE file) are also non-standard and stored in a slicer-specific way.

For these reasons, it becomes useful to define a new file type:

**`.gjob` files store everything that a printer requires to print a Continuous Print job**.

## Creating a gjob

## Loading a gjob
