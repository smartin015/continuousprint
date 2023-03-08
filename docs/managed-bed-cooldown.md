# Managed Bed Cooldown

## Use Case

Depending on your printer model the g-code instruction M190 (Wait for Bed Temperature) is not always respected
when the targed temperature is cooling down.
For printers that don't respect the M190 cooldown instruction but depend on the bed cooling to a specified temperature
this feature should be enabled.

## Configure feature

This feature can be configured in the Continuous Print settings panel under `Bed Cooldown Settings`.

**Enable Managed Bed Cooldown Box** enables and disables the feature.

**Bed Cooldown Script** is the  G-Code script that will run once print in queue is finished, but before bed cooldown is run. Useful for triggering events via g-code like activating part cooling fan, or moving print head from above part while it cools.

**Bed Cooldown Threshold** is the temperature in Celsius that once met triggers the bed to clear.
The goal is to pick a temperature at which the part becomes free from the bed. Example temperature range is around 25 to 35 but depends greatly on your bed material. Experiment to find the best threshold for your printer.

**Bed Cooldown Timeout** a timeout in minutes starting from after the bed clear script has run when once exceeded bed will be cleared regardless of bed temperature. Useful for cases where the target bed temperature is not being met, but the part is ready to be cleared anyway. Useful for cases where the part cools faster than the bed, or external environment is too hot so bed is not meeting temperature, but part has already cooled enough.

Once configured the final event flow will look like this

`PRINT FINISHES -> Bed Cooldown Script Runs -> Bed is turned off -> Wait until measured temp meets threshold OR timeout is exceeded -> Bed Clearing Script Runs -> NEXT PRINT BEGINS`
