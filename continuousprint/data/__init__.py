import yaml
import os
from enum import Enum

# Import YAML data
base = os.path.dirname(__file__)
with open(os.path.join(base, "printer_profiles.yaml"), "r") as f:
    PRINTER_PROFILES = dict(
        (d["name"], d) for d in yaml.safe_load(f.read())["PrinterProfile"]
    )
with open(os.path.join(base, "gcode_scripts.yaml"), "r") as f:
    GCODE_SCRIPTS = dict((d["name"], d) for d in yaml.safe_load(f.read())["GScript"])

with open(os.path.join(base, "preprocessors.yaml"), "r") as f:
    PREPROCESSORS = dict(
        (d["name"], d) for d in yaml.safe_load(f.read())["Preprocessors"]
    )


class CustomEvents(Enum):
    ACTIVATE = (
        "continuousprint_activate",
        "Queue Activated",
        "Fires when the queue is started, e.g. via the 'Start Managing' button.",
    )
    PRINT_START = (
        "continuousprint_start_print",
        "Print Start",
        "Fires when a new print is starting from the queue. Unlike OctoPrint events, this does not fire when event scripts are executed.",
    )
    PRINT_SUCCESS = (
        "continuousprint_success",
        "Print Success",
        "Fires when the active print finishes. This will also fire for prints running before the queue was started. The final print will fire QUEUE_FINISH instead of PRINT_SUCCESS.",
    )
    PRINT_CANCEL = (
        "continuousprint_cancel",
        "Print Cancel",
        "Fires when automation or the user has cancelled the active print.",
    )
    COOLDOWN = (
        "continuousprint_cooldown",
        "Bed Cooldown",
        "Fires when bed cooldown is starting. Bed Cooldown is disabled by default - see the settings below.",
    )
    FINISH = (
        "continuousprint_finish",
        "Queue Finished",
        "Fires when there is no work left to do and the plugin goes idle.",
    )
    AWAITING_MATERIAL = (
        "continuousprint_awaiting_material",
        "Awaiting Material",
        "Fires once when the current job requires a different material than what is currently loaded. This requires SpoolManager to be installed (see Integrations).",
    )
    DEACTIVATE = (
        "continuousprint_deactivate",
        "Queue Deactivated",
        "Fires when the queue is no longer actively managed. This script may be skipped if another print is underway when the queue goes inactive.",
    )

    def __init__(self, event, displayName, desc):
        self.event = event
        self.displayName = displayName
        self.desc = desc

    def as_dict(self):
        return dict(event=self.event, display=self.displayName, desc=self.desc)


class Keys(Enum):

    BED_COOLDOWN_SCRIPT_DEPRECATED = (
        "cp_bed_cooldown_script",
        "; Put script to run before bed cools here\n",
    )
    FINISHED_SCRIPT_DEPRECATED = ("cp_queue_finished_script", "Generic Off")
    CLEARING_SCRIPT_DEPRECATED = ("cp_bed_clearing_script", "Pause")
    QUEUE_DEPRECATED = ("cp_queue", None)

    PRINTER_PROFILE = ("cp_printer_profile", "Generic")
    RESTART_MAX_RETRIES = ("cp_restart_on_pause_max_restarts", 3)
    RESTART_ON_PAUSE = ("cp_restart_on_pause_enabled", False)
    RESTART_MAX_TIME = ("cp_restart_on_pause_max_seconds", 60 * 60)
    BED_COOLDOWN_ENABLED = ("bed_cooldown_enabled", False)
    BED_COOLDOWN_THRESHOLD = ("bed_cooldown_threshold", 30)
    BED_COOLDOWN_TIMEOUT = ("bed_cooldown_timeout", 60)
    MATERIAL_SELECTION = ("cp_material_selection_enabled", False)
    NETWORK_NAME = ("cp_network_name", "Generic")
    AUTOMATION_TIMELAPSE_ACTION = (
        "cp_automation_timelapse_action",
        "do_nothing",
    )  # One of "do_nothing", "auto_remove"
    UPLOAD_ACTION = (
        "cp_upload_action",
        "do_nothing",
    )  # One of "do_nothing", "add_draft", "add_printable"
    INFER_PROFILE = ("cp_infer_profile", True)
    AUTO_RECONNECT = ("cp_auto_reconnect", False)
    SKIP_GCODE_COMMANDS = ("cp_skip_gcode_commands", "")

    def __init__(self, setting, default):
        self.setting = setting
        if setting.endswith("_script") and not default.startswith(";"):
            self.default = GCODE_SCRIPTS[default]["gcode"]
        else:
            self.default = default


PRINT_FILE_DIR = "ContinuousPrint"
TEMP_FILE_DIR = PRINT_FILE_DIR + "/tmp"
ASSETS = dict(
    js=[
        "js/cp_modified_sortable.js",
        "js/cp_modified_knockout-sortable.js",
        "js/continuousprint_api.js",
        "js/continuousprint_history_row.js",
        "js/continuousprint_set.js",
        "js/continuousprint_job.js",
        "js/continuousprint_queue.js",
        "js/continuousprint_viewmodel.js",
        "js/continuousprint_settings.js",
        "js/continuousprint.js",
    ],
    css=["css/continuousprint.css"],
)

TEMPLATES = [
    dict(
        type="settings",
        custom_bindings=True,
        template="continuousprint_settings.jinja2",
    ),
    dict(
        type="tab",
        name="Continuous Print",
        custom_bindings=False,
        template="continuousprint_tab.jinja2",
    ),
]


def update_info(plugin_version):
    return dict(
        continuousprint=dict(
            displayName="Continuous Print Plugin",
            displayVersion=plugin_version,
            # version check: github repository
            type="github_release",
            user="smartin015",
            repo="continuousprint",
            current=plugin_version,
            stable_branch=dict(name="Stable", branch="master", comittish=["master"]),
            prerelease_branches=[
                dict(
                    name="Release Candidate",
                    branch="rc",
                    comittish=["rc", "master"],
                )
            ],
            # update method: pip
            pip="https://github.com/smartin015/continuousprint/archive/{target_version}.zip",
        )
    )
