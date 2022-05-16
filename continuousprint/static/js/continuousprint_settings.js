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
    self.files = parameters[1]
    self.api = parameters[2] || new CPAPI();
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
    self.queue_fingerprint = null;
    self.api.queues((result) => {
      let queues = []
      for (let r of result) {
        if (r.name === "archive") {
          continue; // Archive is hidden
        }
        queues.push(r);
      }
      self.queues(queues);
      self.queue_fingerprint = JSON.stringify(queues);
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
      let queues = JSON.stringify(self.queues());
      if (queues === self.queue_fingerprint) {
        return; // Don't call out to API if we haven't changed anything
      }
      // Sadly it appears flask doesn't have good parsing of nested POST structures,
      // So we pass it a JSON string instead.
      self.api.commitQueues({queues}, () => {
        console.log("Queues committed");
      });
    }

    self.sortStart = function() {
      // Faking server disconnect allows us to disable the default whole-page
      // file drag and drop behavior.
      self.files.onServerDisconnect();
    };
    self.sortEnd = function() {
      // Re-enable default drag and drop behavior
      self.files.onServerConnect();
    };
}


try {
module.exports = {
  CPSettingsViewModel,
  CP_PRINTER_PROFILES,
  CP_GCODE_SCRIPTS,
};
} catch {}
