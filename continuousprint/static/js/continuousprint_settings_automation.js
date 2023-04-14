if (typeof log === "undefined" || log === null) {
  // In the testing environment, dependencies must be manually imported
  ko = require('knockout');
  CP_GCODE_SCRIPTS = [];
  CP_CUSTOM_EVENTS = [];
  CP_SIMULATOR_DEFAULT_SYMTABLE = function() {return {};};
  CPSettingsEvent = require('./continuousprint_settings_event');
}

function CPSettingsAutomationViewModel(api, default_scripts=CP_GCODE_SCRIPTS, custom_events=CP_CUSTOM_EVENTS, default_symtable=CP_SIMULATOR_DEFAULT_SYMTABLE) {
  var self = this;
  self.api = api;
  self.default_scripts = {};
  for (let s of default_scripts) {
    self.default_scripts[s.name] = s.gcode;
  }
  self.scripts = ko.observableArray([]);
  self.preprocessors = ko.observableArray([]);
  self.events = ko.observableArray([]);
  self.scripts_fingerprint = null;

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
            if (ppname && ppname.name) {
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

  self.onSettingsShown = function() {
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

  self.onSettingsBeforeSave = function() {
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
}


try {
module.exports = {
  CPSettingsAutomationViewModel,
  CP_GCODE_SCRIPTS,
};
} catch {}
