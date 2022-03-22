from dataclasses import dataclass

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
  nextAvailable: int # timestamp
  manualEffortCost: int
  materialsReady: list[str]


class QueueJob:
  name: str
  materials: list[str]
  createdAt: int


