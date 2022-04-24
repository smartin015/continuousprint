if (typeof log === "undefined" || log === null) {
  // In the testing environment, dependencies must be manually imported
  ko = require('knockout');
  log = {
    "getLogger": () => {return console;}
  };
  CP_PRINTER_PROFILES = [];
  CP_GCODE_SCRIPTS = [];
}

function CPSettingsViewModel(parameters, profiles=CP_PRINTER_PROFILES, scripts=CP_GCODE_SCRIPTS) {
    var self = this;
    self.PLUGIN_ID = "octoprint.plugins.continuousprint";
    self.log = log.getLogger(self.PLUGIN_ID);
    self.settings = parameters[0];

    // Constants defined in continuousprint_settings.jinja2, passed from the plugin (see `get_template_vars()` in __init__.py)
    self.profiles = {};
    for (let prof of profiles) {
      if (self.profiles[prof.make] === undefined) {
        self.profiles[prof.make] = {};
      }
      self.profiles[prof.make][prof.model] = prof;
    }
    self.scripts = {};
    for (let s of scripts) {
      self.scripts[s.name] = s.gcode;
    }

    self.selected_make = ko.observable();
    let makes = Object.keys(self.profiles);
    makes.unshift("Select one");
    self.printer_makes = ko.observable(makes);
    self.selected_model = ko.observable();
    self.printer_models = ko.computed(function() {
      let models = self.profiles[self.selected_make()];
      if (models === undefined) {
        return ["-"];
      }
      let result = Object.keys(models);
      result.unshift("-");
      return result;
    });

    self.modelChanged = function() {
      let profile = (self.profiles[self.selected_make()] || {})[self.selected_model()];
      if (profile === undefined) {
        return;
      }
      let cpset = self.settings.settings.plugins.continuousprint;
      cpset.cp_bed_clearing_script(self.scripts[profile.defaults.clearBed]);
      cpset.cp_queue_finished_script(self.scripts[profile.defaults.finished]);
    }
}


try {
module.exports = {
  CPSettingsViewModel,
  CP_PRINTER_PROFILES,
  CP_GCODE_SCRIPTS,
};
} catch {}
