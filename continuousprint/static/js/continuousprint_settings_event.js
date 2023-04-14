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

function CPSettingsEvent(evt, actions, api, default_symtable) {
    var self = this;
    self.api = api;
    self.name = evt.name;
    self.event = evt.event;
    self.display = evt.display;
    self.desc = evt.desc;

    // Construct symtable used for simulating output
    let sym = default_symtable;
    if (sym.current) {
      sym.current.state = evt.sym_state;
    }
    self.symtable = ko.observable(sym);
    self.symtableEdit = ko.observable(JSON.stringify(sym, null, 2));
    self.symtableEditError = ko.observable(null);
    self.symtableEdit.subscribe(function(newValue) {
      try {
        let v = JSON.parse(newValue);
        self.symtableEditError(null);
        self.symtable(v);
      } catch(e) {
        self.symtableEditError(e.toString());
      }
    });

    // actions is an array of {script, preprocessor (observable)}
    self.actions = ko.observableArray(actions);

    self.timeout = null;
    self.running = ko.observable(false);
    self.simulation = ko.observable({
      gcode: "",
      stdout: "",
      stderr: "",
      symtable_diff: {},
    });
    self.simGcodeOutput = ko.computed(function() {
      let s = self.simulation();
      if (self.running()) {
        return "...";
      } else if (s.stderr !== "") {
        return "@PAUSE; Preprocessor error";
      } else {
        return s.gcode;
      }
    });
    self.combinedSimOutput = ko.computed(function() {
      let s = self.simulation();
      if (self.running()) {
        return "...";
      }
      return s.stdout + '\n' + s.stderr;
    });
    self.simSymtable = ko.computed(function() {
      let s = self.simulation();
      if (self.running()) {
        return [];
      }
      let r = [];
      for (let k of Object.keys(s.symtable_diff)) {
        r.push({key: k, value: s.symtable_diff[k]});
      }
      return r;
    });
    self.apply = function() {
      // This is called by the sortable code for some reason, no idea why
      // but otherwise it raises an exception.
    };
    let numlines = function(text) {
      if (text === "") {
        return 0;
      }
      let m = text.match(/\n/g);
      if (m === null) {
        return 1;
      } else if (text[text.length-1] == "\n") {
        return m.length;
      }
      return m.length + 1;
    }
    self.simSummary = ko.computed(function() {
      let s = self.simulation();
      if (self.running()) {
        return "running simulation...";
      } else if (s.stderr !== "") {
        return "Simulation: execution error!";
      }
      let r = "Simulation OK: ";
      let gline = numlines(s.gcode);
      r += (gline === 1) ? '1 line' : `${gline} lines`;
      let nline = numlines(s.stdout);
      if (nline > 0) {
        r += (nline === 1) ? ', 1 notification' : `, ${nline} notifications`;
      }
      return r;
    });
    self.simExpanded = ko.observable(true);
    self.symtableExpanded = ko.observable(true);
    self.updater = ko.computed(function() {
      // Computed function doesn't return anything itself, but does
      // update the simulation observable above. It does need to be
      // referenced from the HTML though.
      // We operate after a timeout so as not to send unnecessary load
      // to the server.
      self.running(true);

      // This must run on *every* call to the updater, so that the
      // correct listeners are applied
      let automation = [];
      let sym = self.symtable();
      for (let a of self.actions()) {
        let pp = a.preprocessor();
        automation.push([
          a.script.body(),
          (pp && pp.body())
        ]);
      }

      if (self.timeout !== null) {
        clearTimeout(self.timeout);
      }
      self.timeout = setTimeout(function() {
        self.api.simulate(automation, sym, (result) => {
          self.simulation(result);
          self.timeout = null;
          self.running(false);
        }, (code, reason) => {
          let msg = `Server error (${code}): ${reason}`;
          console.error(msg);
          self.simulation({
            gcode: '',
            stdout: '',
            stderr: msg,
            symtable_diff: [],
          });
          self.timeout = null;
          self.running(false);
        });
      }, 1000);
    });

    self.pack = function() {
      let ks = [];
      for (let a of self.actions()) {
        let pp = a.preprocessor();
        if (pp !== null && pp !== undefined) {
          pp = pp.name();
        }
        ks.push({
          script: a.script.name(),
          preprocessor: pp,
        });
      }
      if (ks.length !== 0) {
        return ks;
      }
    };
}

try {
module.exports = CPSettingsEvent;
} catch {}
