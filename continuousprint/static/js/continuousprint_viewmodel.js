/*
 * View model for OctoPrint-Print-Queue
 *
 * Contributors: Michael New, Scott Martin
 * License: AGPLv3
 */

if (typeof CPJob === "undefined" || CPJob === null) {
  // In the testing environment, dependencies must be manually imported
  ko = require('knockout');
  CPJob = require('./continuousprint_job');
  CPQueue = require('./continuousprint_queue');
  CPAPI = require('./continuousprint_api');
  CPHistoryRow = require('./continuousprint_history_row');
  log = {
    "getLogger": () => {return console;}
  };
}

function CPHistoryDivider(job, set) {
  var self = this;
  self.divider = true;
  if (job === '') {
    job = 'untitled job';
  }
  self.job = job;
  self.set = set;
}


// Due to minification, it's very difficult to find and fix errors reported by users
// due to bugs/issues with JS code. Wrapping functions in _ecatch allows us to retain the
// function name and args, and prints the error to the console with hopefully enough info
// to properly debug.
var _ecatch = function(name, fn) {
  if (typeof(name) !== 'string') {
    throw Error("_ecatch not passed string as first argument (did you forget the function name?)");
  }
  return function() {
    try {
      var args = [];
      for (var i = 0; i < arguments.length; i++) {
        args.push(arguments[i]);
      }
      fn.apply(undefined, args);
    } catch(err) {
      let args_json = "<not json-able>";
      try {
        let args_json = JSON.stringify(arguments);
      } catch(e2) {}
      console.error(`Error when calling ${name} with args ${args_json}: ${err}`);
    }
  };
};

function CPViewModel(parameters) {
    var self = this;
    self.PLUGIN_ID = "octoprint.plugins.continuousprint";
    self.log = log.getLogger(self.PLUGIN_ID);
    self.TAB_ID = "#tab_plugin_continuousprint";
    self.printerState = parameters[0];
    self.loginState = parameters[1];
    self.files = parameters[2];
    self.printerProfiles = parameters[3];
    self.extruders = ko.computed(function() { return self.printerProfiles.currentProfileData().extruder.count(); });
    self.status = ko.observable("Initializing...");
    self.active = ko.observable(false);
    self.active_set = ko.observable(null);
    self.loading = ko.observable(false);
    self.materials = ko.observable([]);
    self.queues = ko.observableArray([]);
    self.defaultQueue = null;
    self.expanded = ko.observable(null);

    self.api = parameters[4] || new CPAPI();
    self.api.init(self.loading);

    self.setActive = _ecatch("setActive", function(active) {
        self.api.setActive(active, () => {
          self.active(active);
        });
    });

    // Patch the files panel to allow for adding to queue
    self.files.add = _ecatch("files.add", function(data) {
      self.defaultQueue.addFile(data);
    });

    self._loadState = _ecatch("_loadState", function(state) {
        self.log.info(`[${self.PLUGIN_ID}] loading state...`);
        self.api.getState(self._setState);
    });

    self._updateQueues = _ecatch("_updateQueues", function(queues) {
      let result = [];
      for (let q of queues) {
        let cpq = new CPQueue(q, self.api);
        console.log(cpq.name);
        result.push(cpq);
        if (cpq.name === 'local') {
          self.defaultQueue = cpq;
        }
      }
      self.queues(result);
    });

    self._setState = function(state) {
        //self.log.info(`[${self.PLUGIN_ID}] updating queues (len ${state.queues.length})`);
        self._updateQueues(state.queues);
        self.active(state.active);
        self.active_set(state.active_set);
        self.status(state.status);
        //self.log.info(`[${self.PLUGIN_ID}] new state loaded`);
    };

    self._setPeerState = function(state) {
      console.log("TODO PeerState", state);
    }

    self.expand = function(vm) {
      if (self.expanded() === vm) {
        vm.expanded(false);
        self.expanded(null);
      } else {
        vm.expanded(true);
        self.expanded(vm);
      }
    };

    self.sortStart = _ecatch("sortStart", function(evt) {
      // Faking server disconnect allows us to disable the default whole-page
      // file drag and drop behavior.
      self.files.onServerDisconnect();
    });

    self.sortEnd = _ecatch("sortEnd", function(evt, e) {
      // Re-enable default drag and drop behavior
      self.files.onServerConnect();
      // Sadly there's no "destination job" information, so we have to
      // infer the index of the job based on the rendered HTML given by evt.to
      if (e.constructor.name === "CPJob") {
        let jobs = self.defaultQueue.jobs();
        let dest_idx = jobs.indexOf(e);
        self.api.mv(self.api.JOB, {
            id: e.id,
            after_id: (dest_idx > 0) ? jobs[dest_idx-1].id() : -1
        }, (result) => {
          console.log(result);
        });
      }
    });

    self.sortMove = function(evt) {
      // Like must move to like (e.g. no dragging a set out of a job)
      if (evt.from.id !== evt.to.id) {
        return false;
      }
      // Sets must only be dragged among draft jobs
      if (evt.from.id === "queue_sets" && !evt.to.classList.contains("draft")) {
        return false;
      }
      // Draft jobs can only be dragged within the local queue
      if (evt.from.classList.contains("local") && !evt.to.classList.contains("local")) {
        return false;
      }

      return true;
    };

    // This also fires on initial load
    self.onTabChange = _ecatch("onTabChange", function(next, current) {
      self.log.info(`[${self.PLUGIN_ID}] onTabChange - ${self.TAB_ID} == ${current} vs ${next}`);
      if (current === self.TAB_ID && next !== self.TAB_ID) {
        // Navigating away - TODO clear hellow highlights
      } else if (current !== self.TAB_ID && next === self.TAB_ID) {
        // Reload in case other things added
        self._loadState();
        self.refreshHistory();
      }
    });

    self.onDataUpdaterPluginMessage = _ecatch("onDataUpdaterPluginMessage", function(plugin, data) {
        if (plugin != "continuousprint") return;
        var theme;
        switch(data["type"]) {
            case "popup":
                theme = "info";
                break;
            case "error":
                theme = 'danger';
                self._loadState();
                break;
            case "complete":
                theme = 'success';
                self._loadState();
                break;
            case "setstate":
                console.log("got setstate", data);
                return self._setState(JSON.parse(data["state"]));
            default:
                theme = "info";
                break;
        }

        if (data.msg != "") {
            new PNotify({
                title: 'Continuous Print',
                text: data.msg,
                type: theme,
                hide: true,
                buttons: {closer: true, sticker: false}
            });
        }
    });

    self.api.getSpoolManagerState(function(resp) {
      let result = {};
      for (let spool of resp.allSpools) {
        let k = `${spool.material}_${spool.colorName}_#${spool.color.substring(1)}`;
        result[k] = {value: k, text: `${spool.material} (${spool.colorName})`};
      }
      self.materials(Object.values(result));
    });

    self.submitJob = function(vm) {
      for (let id of self.defaultQueue._getSelections().job_ids) {
        self.api.submitJob({id, queue: vm.name}, self._setState);
      }
    }


    /* ===== History Tab ===== */
    self.history = ko.observableArray();
    self.isDivider = function(data) {
      return data instanceof CPHistoryDivider;
    };

    self._setHistory = function(data) {
      let result = [];
      let job = null;
      let set = null;
      for (let r of data) {
        if (job !== r.job_name || set !== r.set_path) {
          result.push(new CPHistoryDivider(r.job_name, r.set_path));
          job = r.job_name;
          set = r.set_path;
        }
        result.push(new CPHistoryRow(r));
      }
      self.history(result);
    };
    self.refreshHistory = function() {
      self.api.history(self._setHistory);
    };
    self.clearHistory = function() {
      self.api.clearHistory(() => {
        self.entries([]);
      });
    };
}


try {
module.exports = CPViewModel;
} catch {}
