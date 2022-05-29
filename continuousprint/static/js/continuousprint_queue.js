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

function CPQueue(data, api, files, profile) {
    var self = this;
    self.api = api;
    self.files = files;
    self.name = data.name;
    self.strategy = data.strategy;
    self.addr = data.addr;
    self.jobs = ko.observableArray([]);
    for (let j of data.jobs) {
      self.jobs.push(new CPJob(j, data.peers, self.api, profile));
    }
    self.shiftsel = ko.observable(-1);
    self.details = ko.observable("");
    self.active_set = ko.observable(data.active_set);
    self.fullDetails = ko.observable("");
    if (self.addr !== null && data.peers !== undefined) {
      let pkeys = Object.keys(data.peers);
      if (pkeys.length === 0) {
        self.details(`(connecting...)`);
      } else {
        self.details(`(${pkeys.length-1} peer${(pkeys.length != 2) ? 's' : ''})`);
      }
      let fd = '';
      for (let p of pkeys) {
        fd += `\n${data.peers[p].name} (${p}): ${data.peers[p].status}`;
      }
      self.fullDetails(fd);
    }

    self.batchSelectBase = function(mode) {
      switch (mode) {
        case "All":
          for (let j of self.jobs()) {
            j.onChecked(true);
          }
          break;
        case "None":
          for (let j of self.jobs()) {
            j.onChecked(false);
          }
          break;
        case "Empty Jobs":
          for (let j of self.jobs()) {
            j.onChecked(j.sets().length === 0);
          }
          break;
        case "Unstarted Jobs":
          for (let j of self.jobs()) {
            j.onChecked(j.sets().length !== 0 && j.length_completed() === 0);
          }
          break;
        case "Incomplete Jobs":
          for (let j of self.jobs()) {
            let lc = j.length_completed();
            j.onChecked(lc > 0 && lc < j.length());
          }
          break;
        case "Completed Jobs":
          for (let j of self.jobs()) {
            j.onChecked(j.sets().length !== 0 && j.length_completed() >= j.length());
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
    self.onChecked = function(vm, e) {
      if (vm === self) {
        let c = self.checkFraction();
        self.batchSelectBase((c == 0) ? "All" : "None");
        e.cancelBubble = true;
        if (e.stopPropagation) {
          e.stopPropagation();
        }
        return;
      }

      let idx = self.shiftsel()
      if (e.shiftKey && idx !== -1) {
        console.log(vm, e);
        let target_idx = self.jobs.indexOf(vm);
        let sel = !vm.selected();
        let start = Math.min(idx, target_idx);
        let end = Math.max(idx, target_idx);
        let jobs = self.jobs();
        for (let i = start; i <= end; i++) {
          jobs[i].onChecked(sel);
        }
        self.shiftsel(target_idx);
      } else {
        vm.onChecked();
        self.shiftsel(self.jobs.indexOf(vm));
      }
      e.preventDefault();
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

    self.deleteSelected = function(e) {
      let d = self._getSelections();
      self.api.rm(self.api.JOB, {queue: self.name, job_ids: d.job_ids}, () => {
          for (let j of d.jobs) {
            self.jobs.remove(j);
          }
      });
    };

    self.resetSelected = function() {
      let d = self._getSelections();
      self.api.reset(self.api.JOB, {queue: self.name, job_ids: d.job_ids}, () => {
        for (let j of d.jobs) {
          j.remaining(j.count());
          j.completed(0);
          for (let s of j.sets()) {
            s.remaining(s.count());
            s.completed(0);
          }
        }
      });
    };

    self.exportSelected = function() {
      let d = self._getSelections();
      self.api.export(self.api.JOB, {job_ids: d.job_ids}, (result) => {
          new PNotify({
              title: 'Continuous Print',
              text: `Exported jobs to 'files' panel: \n - ${result.join('\n - ')}`,
              type: 'success',
              hide: true,
              buttons: {closer: true, sticker: false}
          });
          // Reload the file panel to show the new file
          self.files.requestData({force: true});
      });
    };

    self.newEmptyJob = function() {
        self.api.add(self.api.JOB, {}, (result) => {
          self.jobs.push(new CPJob(result, data.peers, self.api, profile));
        });
    };

    self.importJob = function(path) {
      self.api.import(self.api.JOB, {path, queue: self.name}, (result) => {
        self.jobs.push(new CPJob(result, data.peers, self.api, profile));
      });
    }

    self.addFile = function(data) {
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
          return self.jobs.push(new CPJob({id: response.job_id, name: job, count: 1, sets: [response.set_]}, data.peers, self.api, profile));
        });
    };

    self._resolve = function(observable) {
      if (typeof(observable) === 'undefined') {
        return null;
      } else if (typeof(observable) === 'function') {
        return observable();
      }
      return observable;
    };

    self.setJobName = function(job, evt) {
      job.set_name(evt.target.value);
    };

    self.setCount = function(vm, e) {
      let v = parseInt(e.target.value, 10);
      if (isNaN(v) || v < 1) {
        return;
      }
      vm.set_count(v);
    };
}

try {
module.exports = CPQueue;
} catch {}
