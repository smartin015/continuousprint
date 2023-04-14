if (typeof log === "undefined" || log === null) {
  // In the testing environment, dependencies must be manually imported
  ko = require('knockout');
  log = {
    "getLogger": () => {return console;}
  };
  CP_PRINTER_PROFILES = [];
  CP_GCODE_SCRIPTS = [];
  CP_CUSTOM_EVENTS = [];
  CP_LOCAL_IP = '';
  CPAPI = require('./continuousprint_api');
  CP_SIMULATOR_DEFAULT_SYMTABLE = function() {return {};};
  CPSettingsEvent = require('./continuousprint_settings_event');
  OctoPrint = undefined;
}

function CPSettingsViewModel(parameters, profiles=CP_PRINTER_PROFILES, default_scripts=CP_GCODE_SCRIPTS, custom_events=CP_CUSTOM_EVENTS, default_symtable=CP_SIMULATOR_DEFAULT_SYMTABLE, octoprint=OctoPrint) {
  var self = this;
  self.PLUGIN_ID = "octoprint.plugins.continuousprint";
  self.log = log.getLogger(self.PLUGIN_ID);
  self.settings = parameters[0];
  self.files = parameters[1];
  self.api = parameters[2] || new CPAPI();
  self.loading = ko.observable(false);
  self.api.init(self.loading, function(code, reason) {
    console.log("API Error", code, reason);
    new PNotify({
      title: `Continuous Print Settings (Error ${code})`,
      text: reason,
      type: 'error',
      hide: true,
      buttons: {closer: true, sticker: false},
    });
  });

  self.automation = new CPSettingsAutomationViewModel(self.api, default_scripts, custom_events, default_symtable);
  self.queues = new CPSettingsQueuesViewModel(self.api);

  self.local_ip = ko.observable(CP_LOCAL_IP || '');

  // We have to use the global slicer data retriever instead of
  // slicingViewModel because the latter does not make its profiles
  // available without modifying the slicing modal.
  self.slicers = ko.observable({});
  self.slicer = ko.observable();
  self.slicer_profile = ko.observable();
  if (octoprint !== undefined) {
    octoprint.slicing.listAllSlicersAndProfiles().done(function (data) {
      let result = {};
      for (let d of Object.values(data)) {
        let profiles = [];
        let default_profile = null;
        for (let p of Object.keys(d.profiles)) {
          if (d.profiles[p].default) {
            default_profile = p;
            continue;
          }
          profiles.push(p);
        }
        if (default_profile) {
          profiles.unshift(default_profile);
        }
        result[d.key] = {
          name: d.displayName,
          key: d.key,
          profiles,
        };
      }
      self.slicers(result);
    });
  }
  self.slicerProfiles = ko.computed(function() {
    return (self.slicers()[self.slicer()] || {}).profiles;
  });
  // Constants defined in continuousprint_settings.jinja2, passed from the plugin (see `get_template_vars()` in __init__.py)
  self.profiles = {};
  for (let prof of profiles) {
    if (self.profiles[prof.make] === undefined) {
      self.profiles[prof.make] = {};
    }
    self.profiles[prof.make][prof.model] = prof;
  }

  // Patch the settings viewmodel to allow for us to block saving when validation has failed.
  // As of 2022-05-31, 'exchanging()' is only used for display and not for logic.
  self.settings.exchanging_orig = self.settings.exchanging;
  self.settings.exchanging = ko.pureComputed(function () {
      return self.settings.exchanging_orig() ||
        !self.automation.allUniqueScriptNames() ||
        !self.automation.allUniquePreprocessorNames();
  });

  self.selected_make = ko.observable();
  self.selected_model = ko.observable();
  let makes = Object.keys(self.profiles);
  self.printer_makes = ko.observable(makes);
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
    cpset.cp_printer_profile(profile.name);
  };

  // Called automatically by SettingsViewModel
  self.onSettingsShown = function() {
    self.queues.onSettingsShown();

    for (let prof of profiles) {
      if (self.settings.settings.plugins.continuousprint.cp_printer_profile() === prof.name) {
        self.selected_make(prof.make);
        self.selected_model(prof.model);
        break;
      }
      self.slicer(self.settings.settings.plugins.continuousprint.cp_slicer());
      self.slicer_profile(self.settings.settings.plugins.continuousprint.cp_slicer_profile());
    }
    // Queues and scripts are stored in the DB; we must fetch them whenever
    // the settings page is loaded
    self.api.get(self.api.QUEUES, (result) => {
      let queues = []
      console.log("TODO handle local/global adverts");
      for (let r of result.queues) {
        if (r.name === "archive") {
          continue; // Archive is hidden
        }
        queues.push(self.newLoadout(r));
      }
      self.loadout(queues);
      self.queue_fingerprint = JSON.stringify(queues);
    });

    self.automation.onSettingsShown();
  };

  // Called automatically by SettingsViewModel
  self.onSettingsBeforeSave = function() {
    let cpset = self.settings.settings.plugins.continuousprint;
    cpset.cp_slicer(self.slicer());
    cpset.cp_slicer_profile(self.slicer_profile());

    self.queues.onSettingsBeforeSave();
    self.automation.onSettingsBeforeSave();
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


  self.gotoTab = function(suffix) {
    $(`#settings_continuousprint_tabs a[href="#settings_continuousprint_${suffix}"]`).tab('show');
  }
}


try {
module.exports = {
  CPSettingsViewModel,
  CP_PRINTER_PROFILES,
  CP_GCODE_SCRIPTS,
};
} catch {}
