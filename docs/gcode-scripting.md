# GCODE Scripting

GCODE scripts can be quite complex - if you want to learn the basics, try reading through [this primer](https://www.simplify3d.com/support/articles/3d-printing-gcode-tutorial/).

## Bed clearing scripts

When Continuous Print is managing the queue, this script is run after every print completes - **including prints started before queue managing begins**.

Your cleaning script should remove all 3D print material from the build area to make way for the next print.

## Queue finished scripts

This script is run after all prints in the queue have been printed. Use this script to put the machine in a safe resting state. Note that the last print will have already been cleared by the bed cleaning script (above).

## Contributing

When you come up with a useful script for e.g. clearing the print bed, consider contributing it back to the community!

1. Visit [the repository](https://github.com/smartin015/continuousprint) and click the "Fork" button on the top right to create a fork.
2. Go to [printer_profiles.yaml](https://github.com/smartin015/continuousprint/tree/rc/continuousprint/data/printer_profiles.yaml) and check to see if your printer make and model are present. If they aren't, click the pencil icon on the top right of the file to begin editing.
3. When you're done adding details, save it to a new branch of your fork.
4. Now go to [gcode_scripts.yaml](https://github.com/smartin015/continuousprint/tree/rc/continuousprint/data/gcode_scripts.yaml) and edit it in the same way, adding your gcode and any additional fields.
5. Save this print to the same branch (or create a new one if a matching printer profile already exists).
6. Check one last time that the script names match those provided in your printer profiles `defaults` section, then submit a pull request. **Make sure to do a PR against the `rc` branch, NOT the `master` branch.**
