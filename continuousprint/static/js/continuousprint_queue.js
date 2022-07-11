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
    self._pushJob = function(jdata) {
      self.jobs.push(new CPJob(jdata, data.peers, self.api, profile));
    };
    for (let j of data.jobs) {
      self._pushJob(j);
    }
    self.shiftsel = ko.observable(-1);
    self.details = ko.observable("");
    self.fullDetails = ko.observable("");
    if (self.addr !== null && data.peers !== undefined) {
      let pkeys = Object.keys(data.peers);
      if (pkeys.length === 0) {
        self.details(`(connecting...)`);
        self.fullDetails('Searching for other printers with this queue\non the local network - this could take up to a minute');
      } else {
        self.details(`(${pkeys.length} printer${(pkeys.length != 1) ? 's' : ''})`);
        let fd = 'Connected printers:';
        for (let p of pkeys) {
          let pd = data.peers[p];
          fd += `\n${pd.name} (${pd.profile.name}, ${p}): ${pd.status}`;
        }
        self.fullDetails(fd);
      }

      let actives = [];
      for (let pd of Object.values(data.peers)) {
        if (pd.active_set !== null) {
          actives.push(pd.active_set);
        }
      }
      self.active_sets = ko.observableArray(actives);
    } else {
      self.active_sets = ko.observableArray([data.active_set]);
    }
    self.local_active_set = ko.observable(data.active_set);

    self.active_jobs = ko.computed(function() {
      let actives = new Set(self.active_sets());
      let result = [];
      for (let j of self.jobs()) {
        if (j.acquiredBy() === undefined) {
          continue;
        }
        for (let s of j.sets()) {
          if (actives.has(s.id)) {
            result.push(j.id());
            break;
          }
        }
      }
      return result;
    });

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
          j.selected(false);
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

          for (let j of d.jobs) {
            j.selected(false);
          }
      });
    };

    self._uniqueJobName = function() {
      let names = new Set();
      for (let j of self.jobs()) {
        names.add(j._name());
      }
      let i = 0;
      let result;
      do {
        i++;
        result = "Job " + i;
      } while (i < 100 && names.has(result));
      return result;
    };

    self.newEmptyJob = function() {
        self.api.add(self.api.JOB, {name: self._uniqueJobName()}, (result) => {
          self._pushJob(result);
        });
    };

    self.importJob = function(path) {
      self.api.import(self.api.JOB, {path, queue: self.name}, (result) => {
        self._pushJob(result);
      });
    }

    self.addFile = function(data, infer_profile=false) {
        if (data.path.endsWith('.gjob')) {
          // .gjob import has a different API path
          return self.importJob(data.path);
        }

        let now = Date.now();
        let jobs = self.jobs();
        let job = null;
        for (let j of self.jobs()) {
          if (j.draft()) {
            job = j;
            break;
          }
        }

        let set_data = {
            name: data.name,
            path: data.path,
            sd: (data.origin !== "local"),
            count: 1,
        };

        if (infer_profile) {
          let prof = (data.gcodeAnalysis || {}).continuousprint_profile;
          if (prof) {
            set_data.profiles = [prof];
          }
        }

        // Adding to a draft job does not invoke the API
        if (job !== null) {
          return job.onSetModified(set_data);
        }
        set_data['jobName'] = self._uniqueJobName();
        set_data['job'] = null;
        // Invoking API causes a new job to be created
        self.api.add(self.api.SET, set_data, (response) => {
          return self._pushJob({id: response.job_id, name: set_data['jobName'], draft: true, count: 1, sets: [response.set_]});
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
