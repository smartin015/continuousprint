if (typeof log === "undefined" || log === null) {
  // In the testing environment, dependencies must be manually imported
  ko = require('knockout');
  log = {
    "getLogger": () => {return console;}
  };
  CP_PRINTER_PROFILES = [];
  CP_GCODE_SCRIPTS = [];
  CPAPI = require('./continuousprint_api');
}

function CPSettingsViewModel(parameters, profiles=CP_PRINTER_PROFILES, scripts=CP_GCODE_SCRIPTS) {
    var self = this;
    self.PLUGIN_ID = "octoprint.plugins.continuousprint";
    self.log = log.getLogger(self.PLUGIN_ID);
    self.settings = parameters[0];
    self.api = parameters[1] || new CPAPI();
    self.loading = ko.observable(false);
    self.api.init(self.loading);

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

    // Queues are stored in the DB; we must fetch them.
    self.queues = ko.observableArray();
    self.api.queues((result) => {
      let queues = []
      for (let r of result) {
        if (r.name === "default" || r.name === "archive") {
          continue;
        }
        queues.push(r);
      }
      self.queues(queues);
    });

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
    };

    self.newBlankQueue = function() {
      self.queues.push({name: "", addr: "", strategy: ""});
    };
    self.rmQueue = function(q) {
      self.queues.remove(q);
    }

    // Called automatically by SettingsViewModel
    self.onSettingsBeforeSave = function() {
      // Sadly it appears flask doesn't have good parsing of nested POST structures,
      // So we pass it a JSON string instead.
      self.api.commitQueues({queues: JSON.stringify(self.queues())}, () => {
        console.log("Queues committed");
      });
    }
}


try {
module.exports = {
  CPSettingsViewModel,
  CP_PRINTER_PROFILES,
  CP_GCODE_SCRIPTS,
};
} catch {}
