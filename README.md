# Continuous Print Queue Plugin

![build status](https://img.shields.io/travis/smartin015/continuousprint/master?style=plastic)
![code coverage](https://img.shields.io/codecov/c/github/smartin015/continuousprint/master)

This plugin automates your printing!

* **Add gcode files to the queue and set a number of times to print each.** The plugin will print them in sequence, running "bed clearing" script after each.
* **Group multiple files together into "jobs" and run them multiple times.** Don't make 10 boxes by printing 10 bases, then 10 lids - just define a "box" job and print box/lid combos in sequence.
* **Reduce manual intervention with failure automation.** This plugin optionally integrates with [The Spaghetti Detective](https://www.thespaghettidetective.com/) and can retry prints that fail to adhere to the bed, with configurable limits on how hard to try before giving up.

WARNING: Your printer must have a method of clearing the bed automatically, with correct GCODE instructions set up in this plugin's settings page - damage to your printer may occur if this is not done correctly. If you want to manually remove prints, look in the plugin settings for details on how to use `@pause` so the queue is paused before another print starts.


# Documentation

See https://smartin015.github.io/continuousprint/ for all documentation on installation, setup, queueing strategies, and development.

