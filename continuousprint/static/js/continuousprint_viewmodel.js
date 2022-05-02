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
  CPAPI = require('./continuousprint_api');
  log = {
    "getLogger": () => {return console;}
  };
}

function CPViewModel(parameters) {
    var self = this;
    self.PLUGIN_ID = "octoprint.plugins.continuousprint";
    self.log = log.getLogger(self.PLUGIN_ID);
    self.log.info(`[${self.PLUGIN_ID}] Initializing`);
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
          self.log.error(`[${self.PLUGIN_ID}]: error when calling ${name} with args ${args_json}: ${err}`);
        }
      };
    };

    self.TAB_ID = "#tab_plugin_continuousprint";
    self.printerState = parameters[0];
    self.loginState = parameters[1];
    self.files = parameters[2];
    self.printerProfiles = parameters[3];
    self.extruders = ko.computed(function() { return self.printerProfiles.currentProfileData().extruder.count(); });
    // These are used in the jinja template
    self.loading = ko.observable(false);
    self.active = ko.observable(false);
    self.active_set = ko.observable(null);
    self.status = ko.observable("Initializing...");
    self.jobs = ko.observableArray([]);
    self.selected = ko.observable(null);
    self.materials = ko.observable([]);
    self.activeEntities = ko.observable([null, null, null]);

    self.api = parameters[4] || new CPAPI();
    self.api.init(self.loading);

    self.isSelected = function(j=null, q=null) {
      j = self._resolve(j);
      q = self._resolve(q);
      return ko.computed(function() {
        let s = self.selected();
        if (s === null) {
          return false;
        }
        let r =  (j === null || j === s[0]) && (q === null || q === s[1]);
        return r;
      });
    };

    self.batchSelectBase = function(mode) {
      switch (mode) {
        case "All":
          for (let j of self.jobs()) {
            j.selected(true);
            for (let s of j.queuesets()) {
              s.selected(true);
            }
          }
          break;
        case "None":
          for (let j of self.jobs()) {
            j.selected(false);
            for (let s of j.queuesets()) {
              s.selected(false);
            }
          }
          break;
        case "Empty Jobs":
          for (let j of self.jobs()) {
            j.selected(j.queuesets().length === 0);
          }
          break;
        case "Unstarted Jobs":
          for (let j of self.jobs()) {
            j.selected(j.queuesets().length !== 0 && j.length_completed() === 0);
          }
          break;
        case "Incomplete Jobs":
          for (let j of self.jobs()) {
            j.selected(j.length_completed() > 0 && !j.is_complete());
          }
          break;
        case "Completed Jobs":
          for (let j of self.jobs()) {
            j.selected(j.queuesets().length !== 0 && j.is_complete());
          }
          break;
        case "Unstarted Sets":
          for (let j of self.jobs()) {
            j.selected(false);
            for (let s of j.queuesets()) {
              s.selected(s.length_completed() == 0);
            }
          }
          break;
        case "Incomplete Sets":
          for (let j of self.jobs()) {
            j.selected(false);
            for (let s of j.queuesets()) {
              s.selected(s.length_completed() > 0 && s.length_completed() < (s.length() * j.count()));
            }
          }
          break;
        case "Completed Sets":
          for (let j of self.jobs()) {
            j.selected(false);
            for (let s of j.queuesets()) {
              s.selected(s.length_completed() >= (s.length() * j.count()));
            }
          }
          break;
        default:
          console.error("Unknown batch select mode: " + mode);
      }
    }
    self.batchSelect = function(_, e) {
      return self.batchSelectBase(e.target.innerText);
    }

    self.checkFraction = ko.computed(function() {
      let js = self.jobs();
      if (js.length === 0) {
        return 0;
      }
      let numsel = 0;
      for (let j of js) {
        numsel += j.checkFraction();
      }
      return numsel / js.length;
    });
    self.onChecked = function(v, e) {
      let c = self.checkFraction();
      console.log(c);
      self.batchSelectBase((c == 0) ? "All" : "None");
      e.cancelBubble = true;
      if (e.stopPropagation) {
        e.stopPropagation();
      }

    }

    // Patch the files panel to allow for adding to queue
    self.files.add = _ecatch("files.add", function(data) {
        if (self.loading()) {return;}
        let now = Date.now();
        let jobs = self.jobs();
        let job = jobs[jobs.length-1];
        let jobname = (job !== undefined) ? job.name() : "";
        self.api.add(self.api.SET, {
            name: data.name,
            path: data.path,
            sd: (data.origin !== "local"),
            count: 1,
            hash_: "", // TODO
            material: "",
            job: jobname,
        }, (response) => {
          // Take the updated job ID and set and merge it into the nested arrays
          for (let j of self.jobs()) {
            if (j.id() === response.job_id) {
              return j.onSetModified(response.set_);
            }
          }
          return self.jobs.push(new CPJob({id: response.job_id, name: jobname, count: 1, sets: [response.set_]}, self.api));
        });
    });

    self._loadState = _ecatch("_loadState", function(state) {
        self.log.info(`[${self.PLUGIN_ID}] loading state...`);
        self.api.getState(self._setState);
    });

    self._updateJobs = _ecatch("_updateJobs", function(jobs) {
      let result = [];
      for (let j of jobs) {
        result.push(new CPJob(j, self.api)); //{name, count, sets:[...]}));
      }
      self.jobs(result);
    });

    self._setState = function(state) {
        self.log.info(`[${self.PLUGIN_ID}] updating jobs (len ${state.jobs.length})`);
        self._updateJobs(state.jobs);
        self.active(state.active);
        self.active_set(state.active_set);
        self.status(state.status);
        self.log.info(`[${self.PLUGIN_ID}] new state loaded`);
    };

    // *** ko template methods ***
    self.setActive = _ecatch("setActive", function(active) {
        self.api.setActive(active, () => {
          self.active(active);
        });
    });

    self._getSelections = function() {
      let jobs = [];
      let job_ids = [];
      let sets = [];
      let set_ids = [];
      for (let j of self.jobs()) {
        if (j.selected()) {
          jobs.push(j);
          job_ids.push(j.id());
        }
        for (let s of j.queuesets()) {
          if (s.selected()) {
            sets.push(s);
            set_ids.push(s.id);
          }
        }
      }
      return {jobs, job_ids, sets, set_ids};
    }

    self.deleteSelected = _ecatch("remove", function(e) {
      let d = self._getSelections();
      self.api.rm({job_ids: d.job_ids, set_ids: d.set_ids}, () => {
          for (let s of d.sets) {
            s.job.queuesets.remove(s);
          }
          for (let j of d.jobs) {
            self.jobs.remove(j);
          }
      });
    });

    self.resetSelected = _ecatch("resetSelected", function() {
      let d = self._getSelections();
      self.api.reset({job_ids: d.job_ids, set_ids: d.set_ids}, () => {
        for (let j of d.jobs) {
          j.remaining(j.count());
        }
        for (let s of d.sets) {
          s.remaining(s.count());
        }
      });
    });

    self.newEmptyJob = _ecatch("newEmptyJob", function() {
        self.api.add(self.api.JOB, {}, (result) => {
          self.jobs.push(new CPJob(result, self.api));
        });
    });

    self._resolve = function(observable) {
      if (typeof(observable) === 'undefined') {
        return null;
      } else if (typeof(observable) === 'function') {
        return observable();
      }
      return observable;
    };

    self.setSelected = _ecatch("setSelected", function(job, queueset) {
        job = self._resolve(job);
        queueset = self._resolve(queueset);
        if (self.loading()) return;
        let s = self.selected();
        if (s !== null && s[0] == job && s[1] == queueset) {
          self.selected(null);
        } else {
          self.selected([job, queueset]);
        }
    });

    self.refreshQueue = _ecatch("refreshQueue", function() {
      self._loadState();
    });

    self.setJobName = _ecatch("setJobName", function(job, evt) {
      job.set_name(evt.target.value);
    });

    self.setCount = _ecatch("setCount", function(vm, e) {
      let v = parseInt(e.target.value, 10);
      if (isNaN(v) || v < 1) {
        return;
      }
      vm.set_count(v);
    });

    self.setMaterial = _ecatch("setMaterial", function(vm, idx, mat) {
      vm.set_material(idx, mat);
      throw Error("TODO set material");
    });

    self.sortStart = _ecatch("sortStart", function(evt) {
      // Faking server disconnect allows us to disable the default whole-page
      // file drag and drop behavior.
      self.files.onServerDisconnect();
    });

    self.sortEnd = _ecatch("sortEnd", function(_, e, p) {
      // Re-enable default drag and drop behavior
      self.files.onServerConnect();
      console.log(e);
      console.log(p);
      let jobs = self.jobs();
      if (e.constructor.name === "CPJob") {
        let dest_idx = jobs.indexOf(e);
        console.log(dest_idx);
        self.api.mv(self.api.JOB, {
            id: e.id,
            after_id: (dest_idx > 0) ? jobs[dest_idx-1].id : -1
        }, (result) => {
          console.log(result);
        });
      } else if (e.constructor.name === "CPQueueSet") {
        let dest_job = jobs[jobs.indexOf(p)].id;
        let qss = p.queuesets();
        let dest_idx = qss.indexOf(e);
        console.log(dest_job, dest_idx);
        self.api.mv(self.api.SET, {
          id: e.id,
          dest_job,
          after_id: (dest_idx > 0) ? qss[dest_idx-1].id : -1,
        }, (result) => {
          console.log(result);
        });
      }
    });

    self.sortMove = function(evt) {
      // Like must move to like (e.g. no dragging a queueset out of a job)
      return (evt.from.id === evt.to.id);
    };

    // This also fires on initial load
    self.onTabChange = _ecatch("onTabChange", function(next, current) {
      self.log.info(`[${self.PLUGIN_ID}] onTabChange - ${self.TAB_ID} == ${current} vs ${next}`);
      if (current === self.TAB_ID && next !== self.TAB_ID) {
        // Navigating away - TODO clear hellow highlights
      } else if (current !== self.TAB_ID && next === self.TAB_ID) {
        // Reload in case other things added
        self._loadState();
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
            case "reload":
                theme = 'success'
                self._loadState();
                break;
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
}


try {
module.exports = CPViewModel;
} catch {}
