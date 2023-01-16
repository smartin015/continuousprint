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

function CPSettingsEvent(evt, actions, api) {
    var self = this;
    self.api = api;
    self.name = evt.name;
    self.display = evt.display;
    self.desc = evt.desc;

    // Construct symtable used for simulating output
    let sym = CP_SIMULATOR_DEFAULT_SYMTABLE();
    sym.current.state = evt.sym_state;
    self.symtable = ko.observable(sym);

    // actions is an array of {script, preprocessor (observable)}
    self.actions = ko.observableArray(actions);

    self.timeout = null;
    self.running = ko.observable(false);
    self.simulation = ko.observable(null);
    self.updater = ko.computed(function() {
      // Computed function doesn't return anything itself, but does
      // update the simulation observable abovself.
      // We operate after a timeout so as not to send unnecessary load
      // to the server.
      self.running(true);
      if (self.timeout !== null) {
        clearTimeout(self.timeout);
      }
      self.timeout = setTimeout(function() {
        automation = [];
        for (let a of self.actions()) {
          let pp = a.preprocessor();
          automation.push([
            a.script.body(),
            (pp && pp.body())
          ]);
        }
        console.log("simUpdater", self.name, automation, self.symtable());
        self.api.simulate(automation, self.symtable(), (result) => {
          self.simulation(result);
          self.timeout = null;
          self.running(false);
        }, (err) => {
          console.error(err);
          self.simulation(err);
          self.timeout = null;
          self.running(false);
        });
      }, 1000);
    });

    self.prep_for_submit = function() {
      let ks = [];
      for (let a of self.actions()) {
        let pp = a.preprocessor();
        if (pp !== null) {
          pp = pp.name();
        }
        ks.push({
          script: a.script.name(),
          preprocessor: pp,
        });
      }
      if (ks.length !== 0) {
        events[self.event] = ks;
      }
    };
}

try {
module.exports = {
  CPSettingsEvent,
};
} catch {}
