import yaml
import json
import glob
import sys
import os

if len(sys.argv) != 1:
    sys.stderr.write('Usage: parse.py ".../src/kiri-dev/fdm/*"\n')

result = []

paths = glob.glob(sys.argv[1])
sys.stderr.write(f"Parsing {len(paths)} paths...\n")

for p in paths:
    try:
        with open(p, "r") as f:
            data = json.loads(f.read())
    except Exception:
        sys.stderr.write(f"Failed to parse path {p}\n")
        continue

    if data.get("mode") is None:
        if data.get("settings", dict).get("bed_width") is None:
            sys.stderr.write(f"Skipping generic printer {p}\n")
            continue
        sys.stderr.write(f"Normalizing new version config for {p}\n")
        data = dict(
            mode="FDM",
            deviceName=os.path.basename(p).replace(".", " "),
            bedWidth=data["settings"]["bed_width"],
            bedDepth=data["settings"]["bed_depth"],
            maxHeight=data["settings"]["build_height"],
            bedBelt=data["settings"].get("bed_belt", False),
            bedRound=False,  # TODO
        )

    if data.get("mode") != "FDM":
        sys.stderr.write(f"Skipping {data.get('mode')} printer at path {p} (non-FDM)\n")
        continue

    result.append(
        dict(
            name=data["deviceName"],
            make=data["deviceName"].split()[0],
            model=" ".join(data["deviceName"].split()[1:]),
            width=data["bedWidth"],
            depth=data["bedDepth"],
            height=data["maxHeight"],
            formFactor="circular" if data["bedRound"] else "rectangular",
            selfClearing=data["bedBelt"],
            defaults=dict(clearBed="Pause", finished="Generic Off"),
            extra_tags=[],
        )
    )

sys.stderr.write("Parsing finished, results:\n")
print(yaml.dump(result))
