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
  CPStats = require('./continuousprint_stats');
  CP_STATS_DIMENSIONS={
    completed: null,
    count: null,
    remaining: null,
    total: null,
  };
  log = {
    "getLogger": () => {return console;}
  };
}

function CPQueue(data, api, files, profile, materials, stats_dimensions=CP_STATS_DIMENSIONS) {
    var self = this;
    self.api = api;
    self.files = files;
    self.name = data.name;
    self.strategy = data.strategy;
    self.addr = data.addr;
    self.jobs = ko.observableArray([]);
    self._pushJob = function(jdata) {
      self.jobs.push(new CPJob(jdata, data.peers, self.api, profile, materials, stats_dimensions));
    };
    for (let j of data.jobs) {
      self._pushJob(j);
    }
    self.shiftsel = ko.observable(-1);
    self.details = ko.observable("");
    self.fullDetails = ko.observable("");
    self.showStats = ko.observable(true);
    if (self.addr !== null && data.peers !== undefined) {
      try {
        let pstr = [];
        let actives = [];
        for (let peer of data.peers) {
          for (let printer of peer.clients) {
            let prof = JSON.parse(printer.profile);
            let loc = "location unknown";
            if (printer.location.Latitude && printer.location.Longitude) {
              let loc = `${printer.location.Latitude.toFixed(2)}lat, ${printer.location.Longitude.toFixed(2)}lon`;
            }
            pstr.push(`${printer.name} (${prof.name}, ${loc}): ${printer.status}`);
            if (printer.activeUnit) {
              actives.push(printer.activeUnit);
            }
          }
        }
        if (pstr.length === 0) {
          self.details(`(1 printer)`);
          self.fullDetails('This printer is the only one on the network - go to Settings > PeerPrint for troubleshooting tips');
        } else {
          self.details(`(${pstr.length} printer${(pstr.length != 1) ? 's' : ''})`);
          self.fullDetails(`Connected Printers:\n${pstr.join('\n')}\nGo to Settings > PeerPrint for more details`);
        }
        self.active_sets = ko.observableArray(actives);
      } catch (err) {
        console.error(err);
        self.active_sets = ko.observableArray([]);
      }
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
          if (actives.has(s.id.toString())) {
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
            let t = j.totals().values()[0];
            j.onChecked(j.sets().length !== 0 && t.completed === 0 && j.completed() === 0);
          }
          break;
        case "Incomplete Jobs":
          for (let j of self.jobs()) {
            let t = j.totals().values()[0];
            j.onChecked(j.remaining() > 0 && (j.completed() > 0 || t.completed > 0));
          }
          break;
        case "Completed Jobs":
          for (let j of self.jobs()) {
            j.onChecked(j.sets().length !== 0 && j.remaining() === 0);
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

    self.totals = ko.computed(function() {
      return new CPStats(self.jobs, stats_dimensions);
    });

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
          if (result.errors.length > 0) {
            new PNotify({
                title: 'Continuous Print',
                text: `Error(s) during export: \n - ${result.errors.join('\n - ')}`,
                type: 'error',
                hide: false,
                buttons: {closer: true, sticker: false}
            });
          }
          if (result.paths.length > 0) {
            new PNotify({
                title: 'Continuous Print',
                text: `Exported jobs to 'files' panel: \n - ${result.paths.join('\n - ')}`,
                type: 'success',
                hide: true,
                buttons: {closer: true, sticker: false}
            });
          }
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

    self.hasDraftJobs = function() {
      for (let j of self.jobs()) {
        if (j.draft()) {
          return true;
        }
      }
      return false;
    }

    self._extractMetadata = function(path) {
      let meta = {estimatedPrintTime: null, filamentLengths: []};

      let f = self.files.elementByPath(path);
      if (f !== null && f !== undefined) {
        meta.estimatedPrintTime = (f.gcodeAnalysis || {}).estimatedPrintTime;

        let fila = (f.gcodeAnalysis || {}).filament || {};
        for (let tool of Object.values(fila)) {
          meta.filamentLengths.push(tool.length);
        }
      }
      return JSON.stringify(meta);
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
            metadata: self._extractMetadata(data.path),
            count: 1,
        };

        if (infer_profile) {
          // See CPQProfileAnalysisQueue for metadata path key constants
          let prof = (data.continuousprint || {}).profile;
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
          return self._pushJob({queue: self.name, id: response.job_id, name: set_data['jobName'], draft: true, count: 1, sets: [response.set_]});
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
