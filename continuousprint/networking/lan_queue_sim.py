# TODO https://github.com/bakwc/PySyncObj
# TODO https://github.com/cr0hn/PyDiscover
from lan_print_queue import LANPrintQueue
from dataclasses import dataclass
import logging

@dataclass
class VolumeConfig:
  width: float
  depth: float
  height: float
  formFactor: str

@dataclass
class PrinterConfig:
  # For these attributes, see
  # https://docs.octoprint.org/en/master/modules/printer.html#module-octoprint.printer.profile
  name: str
  model: str
  volume: [VolumeConfig, dict]
  def __post_init__(self): # allow dict initialization
    self.volume = VolumeConfig(**self.volume)

  # These attributes aren't available in OctoPrint itself and must be provided separately.
  materialsAvailable: list[str]
  selfClearing: bool
  
@dataclass
class PrinterState:
  # State parameters, will change frequently
  current_print: str
  current_octoprint_state: str
  manualEffortCost: int
  materialsReady: list[str]

def main():
    logging.basicConfig(level=logging.DEBUG)
    import sys  
    import yaml
    if len(sys.argv) != 2:
        print('Usage: lan_queue.py [testdata/scenario.yaml]')
        sys.exit(-1)


    with open(sys.argv[1], 'r') as f:
      config = yaml.safe_load(f.read())

    start_port = 6700
    lpqs = []
    # TODO multiple queues
    queue = config['queues'][0]
    def ready_cb(addr):
      logging.info(f"Queue ready yo, TODO send config/state and files for {printer.name}")
    for k, printer_dict in config['printers'].items():
      printer = PrinterConfig(name=k, **printer_dict)
      lpqs.append(AutoDiscoveryLANPrintQueue(queue['namespace'], f"localhost:{start_port}", ready_cb, logging.getLogger(f"lpq:{printer.name}")))
      start_port += 1
      
    while True:
      cmd = input(">> ").split()
      lpq[0].pushJob({"name": cmd[0], "queuesets": [{"name": 'herp.gcode', 'count': 2}], "count": 2})

if __name__ == "__main__":
  main()
