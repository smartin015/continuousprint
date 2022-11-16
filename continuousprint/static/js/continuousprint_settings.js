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
}

function CPSettingsViewModel(parameters, profiles=CP_PRINTER_PROFILES, default_scripts=CP_GCODE_SCRIPTS, custom_events=CP_CUSTOM_EVENTS) {
    var self = this;
    self.PLUGIN_ID = "octoprint.plugins.continuousprint";
    self.log = log.getLogger(self.PLUGIN_ID);
    self.settings = parameters[0];
    self.files = parameters[1]
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
    self.local_ip = ko.observable(CP_LOCAL_IP || '');

    // Constants defined in continuousprint_settings.jinja2, passed from the plugin (see `get_template_vars()` in __init__.py)
    self.profiles = {};
    for (let prof of profiles) {
      if (self.profiles[prof.make] === undefined) {
        self.profiles[prof.make] = {};
      }
      self.profiles[prof.make][prof.model] = prof;
    }
    self.default_scripts = {};
    for (let s of default_scripts) {
      self.default_scripts[s.name] = s.gcode;
    }

    // Patch the settings viewmodel to allow for us to block saving when validation has failed.
    // As of 2022-05-31, 'exchanging()' is only used for display and not for logic.
    self.settings.exchanging_orig = self.settings.exchanging;
    self.settings.exchanging = ko.pureComputed(function () {
        return self.settings.exchanging_orig() || !self.allValidQueueNames() || !self.allValidQueueAddr();
    });

    self.queues = ko.observableArray();
    self.queue_fingerprint = null;
    self.scripts = ko.observableArray([]);
    self.events = ko.observableArray([]);
    self.scripts_fingerprint = null;

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

    self.loadScriptsFromProfile = function() {
      let profile = (self.profiles[self.selected_make()] || {})[self.selected_model()];
      if (profile === undefined) {
        return;
      }
      self.scripts.push({
        name: ko.observable(`Clear Bed (${profile.name})`),
        body: ko.observable(self.default_scripts[profile.defaults.clearBed]),
        expanded: ko.observable(true),
      });
      self.scripts.push({
        name: ko.observable(`Finish (${profile.name})`),
        body: ko.observable(self.default_scripts[profile.defaults.finished]),
        expanded: ko.observable(true),
      });
    }

    self.newScript = function() {
      self.scripts.push({
        name: ko.observable(""),
        body: ko.observable(""),
        expanded: ko.observable(true),
      });
    }
    self.rmScript = function(s) {
      for (let e of self.events()) {
        for (let a of e.actions()) {
          if (a.name() == s.name()) {
            e.actions.remove(a);
          }
        }
      }
      self.scripts.remove(s);
    }
    self.addAction = function(e, s) {
      e.actions.push({...s, condition: ko.observable("")});
    };
    self.rmAction = function(e, a) {
      e.actions.remove(a);
    }

    self.newBlankQueue = function() {
      self.queues.push({name: "", addr: "", strategy: ""});
    };
    self.rmQueue = function(q) {
      self.queues.remove(q);
    }
    self.queueChanged = function() {
      self.queues.valueHasMutated();
    }
    self.allValidQueueAddr = ko.computed(function() {
      for (let q of self.queues()) {
        if (q.name === 'local' || q.addr.toLowerCase() === "auto") {
          continue;
        }
        let sp = q.addr.split(':');
        if (sp.length !== 2) {
          return false;
        }
        let port = parseInt(sp[1]);
        if (isNaN(port) || port < 5000) {
          return false;
        }
      }
      return true;
    });
    self.allValidQueueNames = ko.computed(function() {
      for (let q of self.queues()) {
        if (q.name.trim() === '') {
          return false;
        }
      }
      return true;
    });

    // Called automatically by SettingsViewModel
    self.onSettingsShown = function() {
      for (let prof of profiles) {
        if (self.settings.settings.plugins.continuousprint.cp_printer_profile() === prof.name) {
          self.selected_make(prof.make);
          self.selected_model(prof.model);
          break;
        }
      }
      // Queues and scripts are stored in the DB; we must fetch them whenever
      // the settings page is loaded
      self.api.get(self.api.QUEUES, (result) => {
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
      self.api.get(self.api.AUTOMATION, (result) => {
        let scripts = []
        for (let k of Object.keys(result.scripts)) {
          scripts.push({
            name: ko.observable(k),
            body: ko.observable(result.scripts[k]),
            expanded: ko.observable(true),
          });
        }
        self.scripts(scripts);

        let events = []
        for (let k of custom_events) {
          let actions = [];
          for (let a of result.events[k.event] || []) {
            for (let s of scripts) {
              if (s.name() === a.script) {
                actions.push({...s, condition: ko.observable(a.condition)});
                break;
              }
            }
          }
          events.push({
            ...k,
            actions: ko.observableArray(actions),
          });
        }
        events.sort((a, b) => a.display < b.display);
        self.events(events);

        self.scripts_fingerprint = JSON.stringify({
          scripts: result.scripts,
          events: result.events,
        });
      });
    };

    // Called automatically by SettingsViewModel
    self.onSettingsBeforeSave = function() {
      let queues = self.queues();
      if (JSON.stringify(queues) !== self.queue_fingerprint) {
        // Sadly it appears flask doesn't have good parsing of nested POST structures,
        // So we pass it a JSON string instead.
        self.api.edit(self.api.QUEUES, queues, () => {
          // Editing queues causes a UI refresh to the main viewmodel; no work is needed here
        });
      }

      let scripts = {}
      for (let s of self.scripts()) {
        scripts[s.name()] = s.body();
      }
      let events = {};
      for (let e of self.events()) {
        let ks = [];
        for (let a of e.actions()) {
          ks.push({script: a.name(), condition: a.condition()});
        }
        if (ks.length !== 0) {
          events[e.event] = ks;
        }
      }
      let data = {scripts, events};
      if (JSON.stringify(data) !== self.scripts_fingerprint) {
        self.api.edit(self.api.AUTOMATION, data, () => {});
      }
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
