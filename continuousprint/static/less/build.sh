#!/bin/bash
for file in *.less; do lessc --strict-imports $file ../css/`basename $file`.css ; done
