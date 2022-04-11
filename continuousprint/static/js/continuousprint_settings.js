function CPSettingsViewModel(parameters) {
    var self = this;
    self.PLUGIN_ID = "octoprint.plugins.continuousprint";
    self.log = log.getLogger(self.PLUGIN_ID);
    self.settings = parameters[0];

    // Constants defined in continuousprint_settings.jinja2, passed from the plugin (see `get_template_vars()` in __init__.py)
    try {
    self.profiles = {};
    for (let prof of CP_PRINTER_PROFILES) {
      if (self.profiles[prof.make] === undefined) {
        self.profiles[prof.make] = {};
      }
      self.profiles[prof.make][prof.model] = prof;
    }
    self.scripts = {};
    for (let s of CP_GCODE_SCRIPTS) {
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

    self.modelChanged = function(e) {
      let profile = self.profiles[self.selected_make()][self.selected_model()];
      if (profile === undefined) {
        return;
      }
      let cpset = self.settings.settings.plugins.continuousprint;
      cpset.cp_bed_clearing_script(self.scripts[profile.defaults.clearBed]);
      cpset.cp_queue_finished_script(self.scripts[profile.defaults.finished]);
    }
    } catch(e) {
    console.error(e);
    }
}


try {
module.exports = CPSettingsViewModel;
} catch {}
