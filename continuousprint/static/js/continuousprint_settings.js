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
  console.log(octoprint);
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
    self.default_scripts = {};
    for (let s of default_scripts) {
      self.default_scripts[s.name] = s.gcode;
    }

    // Patch the settings viewmodel to allow for us to block saving when validation has failed.
    // As of 2022-05-31, 'exchanging()' is only used for display and not for logic.
    self.settings.exchanging_orig = self.settings.exchanging;
    self.settings.exchanging = ko.pureComputed(function () {
        return self.settings.exchanging_orig() ||
          !self.allValidQueueNames() || !self.allValidQueueAddr() ||
          !self.allUniqueScriptNames() || !self.allUniquePreprocessorNames();
    });

    self.queues = ko.observableArray();
    self.queue_fingerprint = null;
    self.scripts = ko.observableArray([]);
    self.preprocessors = ko.observableArray([]);
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

    self.preprocessorSelectOptions = ko.computed(function() {
      let result = [{name: '', value: null}, {name: 'Add new...', value: 'ADDNEW'}];
      for (let p of self.preprocessors()) {
        result.push({name: p.name(), value: p});
      }
      return result;
    });

    function mkScript(name, body, expanded) {
      let b = ko.observable(body || "");
      let n = ko.observable(name || "");
      return {
        name: n,
        body: b,
        expanded: ko.observable((expanded === undefined) ? true : expanded),
        preview: ko.computed(function() {
          let flat = b().replace('\n', ' ');
          return (flat.length > 32) ? flat.slice(0, 29) + "..." : flat;
        }),
        registrations: ko.computed(function() {
          let nn = n();
          let result = [];
          for (let e of self.events()) {
            for (let a of e.actions()) {
              let ppname = a.preprocessor();
              if (ppname !== null && ppname.name) {
                ppname = ppname.name();
              }
              if (a.script.name() === nn || ppname === nn) {
                result.push(e.display);
              }
            }
          }
          return result;
        }),
      };
    }

    self.loadScriptsFromProfile = function() {
      let profile = (self.profiles[self.selected_make()] || {})[self.selected_model()];
      if (profile === undefined) {
        return;
      }
      self.addScript(`Clear Bed (${profile.name})`,
        self.default_scripts[profile.defaults.clearBed], true);
      self.addScript(`Finish (${profile.name})`,
        self.default_scripts[profile.defaults.finished], true);
    }

    self.loadFromFile = function(file, cb) {
      // Inspired by https://stackoverflow.com/a/14155586
      if(!window.FileReader) return;
      var reader = new FileReader();
      reader.onload = function(evt) {
          if(evt.target.readyState != 2) return;
          if(evt.target.error) {
              alert('Error while reading file');
              return;
          }
          cb(file.name, evt.target.result, false);
      };
      reader.readAsText(file);
    };
    self.loadScriptFromFile = (f) => self.loadFromFile(f, self.addScript);
    self.loadPreprocessorFromFile = (f) => self.loadFromFile(f, self.addPreprocessor);

   self.downloadFile = function(filename, body) {
     // https://stackoverflow.com/a/45831357
     var blob = new Blob([body], {type: 'text/plain'});
     if (window.navigator && window.navigator.msSaveOrOpenBlob) {
       window.navigator.msSaveOrOpenBlob(blob, filename);
     } else {
       var e = document.createEvent('MouseEvents'),
       a = document.createElement('a');
       a.download = filename;
       a.href = window.URL.createObjectURL(blob);
       a.dataset.downloadurl = ['text/plain', a.download, a.href].join(':');
       e.initEvent('click', true, false, window, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
       a.dispatchEvent(e);
     }
    }
    self.downloadScript = function(s) {
      let n = s.name()
      if (!n.endsWith(".gcode")) {
        n += ".gcode";
      }
      self.downloadFile(n, s.body());
    };

    self.downloadPreprocessor = function(p) {
      let n = p.name()
      if (!n.endsWith(".py")) {
        n += ".py";
      }
      self.downloadFile(n, p.body());
    };

    self.actionPreprocessorChanged = function(vm) {
      if (vm.preprocessor() === "ADDNEW") {
        p = self.addPreprocessor("", "", true);
        vm.preprocessor(p);
        self.gotoTab("scripts");
      }
    };

    self.addScript = function(name, body, expanded) {
      let s = mkScript(name, body, expanded);
      self.scripts.push(s);
      return s;
    };

    self.addPreprocessor = function(name, body, expanded) {
      let p = mkScript(name, body, expanded);
      self.preprocessors.push(p);
      return p;
    };

    self.rmScript = function(s) {
      for (let e of self.events()) {
        for (let a of e.actions()) {
          if (a.script == s) {
            e.actions.remove(a);
          }
        }
      }
      self.scripts.remove(s);
    }
    self.rmPreprocessor = function(p) {
      for (let e of self.events()) {
        for (let a of e.actions()) {
          if (a.preprocessor() == p) {
            a.preprocessor(null);
          }
        }
      }
      self.preprocessors.remove(p);
    }
    self.gotoScript = function(s) {
      s.expanded(true);
      self.gotoTab("scripts");
    }
    self.gotoTab = function(suffix) {
      $(`#settings_continuousprint_tabs a[href="#settings_continuousprint_${suffix}"]`).tab('show');
    }

    self.addAction = function(e, s) {
      if (s === null) {
        s = self.addScript();
        self.gotoScript(s);
      }
      e.actions.push({
        script: s,
        preprocessor: ko.observable(null),
      });
    };
    self.rmAction = function(e, a) {
      e.actions.remove(a);
    }
    self.allUniqueScriptNames = ko.computed(function() {
      let names = new Set();
      for (let s of self.scripts()) {
        let n = s.name();
        if (names.has(n)) {
          return false;
        }
        names.add(n);
      }
      return true;
    });
    self.allUniquePreprocessorNames = ko.computed(function() {
      let names = new Set();
      for (let p of self.preprocessors()) {
        let n = p.name();
        if (names.has(n)) {
          return false;
        }
        names.add(n);
      }
      return true;
    });

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
        self.slicer(self.settings.settings.plugins.continuousprint.cp_slicer());
        self.slicer_profile(self.settings.settings.plugins.continuousprint.cp_slicer_profile());
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
        let scripts = {};
        for (let k of Object.keys(result.scripts)) {
          scripts[k] = mkScript(k, result.scripts[k], false);
        }
        self.scripts(Object.values(scripts));

        let preprocessors = {};
        for (let k of Object.keys(result.preprocessors)) {
          preprocessors[k] = mkScript(k, result.preprocessors[k], false);
        }
        self.preprocessors(Object.values(preprocessors));

        let events = []
        for (let k of custom_events) {
          let actions = [];
          for (let a of result.events[k.event] || []) {
            actions.push({
              script: scripts[a.script],
              preprocessor: ko.observable(preprocessors[a.preprocessor]),
            });
          }
          events.push(new CPSettingsEvent(k, actions, self.api, default_symtable()));
        }
        events.sort((a, b) => a.display < b.display);
        self.events(events);
        self.scripts_fingerprint = JSON.stringify(result);
      });
    };

    // Called automatically by SettingsViewModel
    self.onSettingsBeforeSave = function() {
      let cpset = self.settings.settings.plugins.continuousprint;
      cpset.cp_slicer(self.slicer());
      cpset.cp_slicer_profile(self.slicer_profile());

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
      let preprocessors = {}
      for (let p of self.preprocessors()) {
        preprocessors[p.name()] = p.body();
      }
      let events = {};
      for (let e of self.events()) {
        let e2 = e.pack();
        if (e2) {
          events[e.event] = e2;
        }
      }
      let data = {scripts, preprocessors, events};
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
