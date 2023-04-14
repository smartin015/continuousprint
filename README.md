# Continuous Print Queue for Octoprint

![build status](https://img.shields.io/travis/smartin015/continuousprint/master?style=plastic)
[![Coverage Status](https://coveralls.io/repos/github/smartin015/continuousprint/badge.svg?branch=master)](https://coveralls.io/github/smartin015/continuousprint?branch=master)

This plugin automates your 3D printing!

[![v2.3.0 demo thumbnail](https://user-images.githubusercontent.com/607666/210150942-d323ed1c-6d07-41eb-aecc-e504ed9e7705.png)](https://www.youtube.com/watch?v=07XfCi9YR_k&list=PLBLlNoYKuCw3dnUcdPQk6Tc_GmNsfYAr7&index=1)

* **Add gcode files to the queue and set a number of times to print each.** The plugin will print them in sequence, running "bed clearing" script after each.
* **Group multiple files together into "jobs" and run them multiple times.** Don't make 10 boxes by printing 10 bases, then 10 lids - just define a "box" job and print box/lid combos in sequence.
* **Reduce manual intervention with failure automation.** This plugin optionally integrates with [The Spaghetti Detective](https://www.thespaghettidetective.com/) and can retry prints that fail to adhere to the bed, with configurable limits on how hard to try before giving up.
* **Print with multiple 3D printers over the local network**. LAN queues can parallelize your printing efforts, while still providing a single queue to print from.
* **Automatically slice STL files before printing**. Integrates with [PrePrintService](https://plugins.octoprint.org/plugins/preprintservice/) and other OctoPrint slicer implementations so you can add STLs to the queue and slice them on-the-fly.

# Documentation

See https://smartin015.github.io/continuousprint/ for all documentation on installation, setup, queueing strategies, and development.

See also [here](https://octo-plugin-stats2.vercel.app/) for adoption stats.
