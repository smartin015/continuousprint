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
  log = {
    "getLogger": () => {return console;}
  };
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

function CPQueue(data, api) {
    var self = this;
    self.api = api;
    self.name = data.name;
    self.strategy = data.strategy;
    self.addr = data.addr;
    self.jobs = ko.observableArray([]);
    for (let j of data.jobs) {
      self.jobs.push(new CPJob(j, api));
    }
    self.details = ko.observable("");
    self.active_set = ko.observable(data.active_set);
    self.fullDetails = ko.observable("");
    if (self.addr !== null && data.peers !== undefined) {
      let pkeys = Object.keys(data.peers);
      if (pkeys.length === 0) {
        self.details(`(connecting...)`);
      } else {
        self.details(`(${pkeys.length-1} peers)`);
      }
      let fd = '';
      for (let p of pkeys) {
        fd += `\n${p}: ${data.peers[p].status}`;
      }
      self.fullDetails(fd);
    }

    self.batchSelectBase = function(mode) {
      switch (mode) {
        case "All":
          for (let j of self.jobs()) {
            j.selected(true);
          }
          break;
        case "None":
          for (let j of self.jobs()) {
            j.selected(false);
          }
          break;
        case "Empty Jobs":
          for (let j of self.jobs()) {
            j.selected(j.sets().length === 0);
          }
          break;
        case "Unstarted Jobs":
          for (let j of self.jobs()) {
            j.selected(j.sets().length !== 0 && j.length_completed() === 0);
          }
          break;
        case "Incomplete Jobs":
          for (let j of self.jobs()) {
            let lc = j.length_completed();
            j.selected(lc > 0 && lc < j.length());
          }
          break;
        case "Completed Jobs":
          for (let j of self.jobs()) {
            j.selected(j.sets().length !== 0 && j.length_completed() >= j.length());
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
      return 0;
    });
    self.onChecked = function(v, e) {
      let c = self.checkFraction();
      self.batchSelectBase((c == 0) ? "All" : "None");
      e.cancelBubble = true;
      if (e.stopPropagation) {
        e.stopPropagation();
      }

    }

    // *** ko template methods ***
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
      }
      return {jobs, job_ids};
    }

    self.deleteSelected = _ecatch("remove", function(e) {
      let d = self._getSelections();
      self.api.rm(self.api.JOB, {job_ids: d.job_ids}, () => {
          for (let j of d.jobs) {
            self.jobs.remove(j);
          }
      });
    });

    self.resetSelected = _ecatch("resetSelected", function() {
      let d = self._getSelections();
      self.api.reset(self.api.JOB, {job_ids: d.job_ids}, () => {
        for (let j of d.jobs) {
          j.remaining(j.count());
          for (let s of j.sets()) {
            s.remaining(s.count());
          }
        }
      });
    });

    self.exportSelected = _ecatch("exportSelected", function() {
      let d = self._getSelections();
      self.api.export(self.api.JOB, {job_ids: d.job_ids}, (result) => {
          new PNotify({
              title: 'Continuous Print',
              text: `Exported jobs to 'files' panel: \n - ${result.join('\n - ')}`,
              type: 'success',
              hide: true,
              buttons: {closer: true, sticker: false}
          });
      });
    });

    self.newEmptyJob = _ecatch("newEmptyJob", function() {
        self.api.add(self.api.JOB, {}, (result) => {
          self.jobs.push(new CPJob(result, self.api));
        });
    });

    self.importJob = function(path) {
      self.api.import(self.api.JOB, {path, queue: self.name}, (result) => {
        console.log("TODO", result);
      });
    }

    self.addFile = _ecatch("addFile", function(data) {
        if (data.path.endsWith('.gjob')) {
          // .gjob import has a different API path
          return self.importJob(data.path);
        }

        let now = Date.now();
        let jobs = self.jobs();
        let job = null;
        for (let j of self.jobs()) {
          if (j.draft()) {
            job = j.id();
            break;
          }
        }
        self.api.add(self.api.SET, {
            name: data.name,
            path: data.path,
            sd: (data.origin !== "local"),
            count: 1,
            job,
        }, (response) => {
          // Take the updated job ID and set and merge it into the nested arrays
          for (let j of self.jobs()) {
            if (j.id() === response.job_id) {
              return j.onSetModified(response.set_);
            }
          }
          return self.jobs.push(new CPJob({id: response.job_id, name: job, count: 1, sets: [response.set_]}, self.api));
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
    });
}

try {
module.exports = CPQueue;
} catch {}
