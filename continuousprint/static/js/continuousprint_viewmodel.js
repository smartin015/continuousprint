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
}

function CPViewModel(parameters) {
    var self = this;

    self.TAB_ID = "#tab_plugin_continuousprint";
    self.printerState = parameters[0];
    self.loginState = parameters[1];
    self.files = parameters[2];
    self.settings = parameters[3]; // (smartin015@) IDK why this is a dependency
    self.api = parameters[4] || new CPAPI();

    // These are used in the jinja template
    self.loading = ko.observable(true);
    self.active = ko.observable(false);
    self.status = ko.observable("Initializing...");
    self.jobs = ko.observableArray([]);
    self.selected = ko.observable(null);

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

    self.isActiveItem = function(j=null, q=null, i=null) {
      j = self._resolve(j);
      q = self._resolve(q);
      i = self._resolve(i);
      return ko.computed(function() {
        let a = self.activeItem();
        if (a === null) {
          return false;
        }
        return (j === null || j === a[0]) && (q === null || q === a[1]) && (i === null || i === a[2]);
      });
    };
    self.activeItem = ko.computed(function() {
      if (!self.printerState.isPrinting() && !self.printerState.isPaused()) {
        return null;
      }
      let printname = self.printerState.filename();
      for (let j = 0; j < self.jobs().length; j++) {
        let job = self.jobs()[j];
        for (let q = 0; q < job.queuesets().length; q++) {
          let qs = job.queuesets()[q];
          for (let i = 0; i < qs.items().length; i++) {
            let item = qs.items()[i];
            if (item.path === printname && item.start_ts() !== null && item.end_ts() === null) {
              return [j,q,i];
            }
          }
        }
      }
      return null;
    });

    // Patch the files panel to allow for adding to queue
    self.files.add = function(data) {
        if (self.loading()) {return;}
        let now = Date.now();
        let jobs = self.jobs();
        let job = jobs[jobs.length-1];
        // We want to add to a job with a single run and no name -
        // otherwise implies adding to something a user has already configured
        if (job.is_configured()) {
          job = new CPJob();
          self.jobs.push(job);
        }
        job.pushQueueItem({
            name: data.name,
            path: data.path,
            sd: (data.origin !== "local"),
            run: 0,
            job: job.name(),
        });
        self._updateQueue();
    };


    // Call this after every mutation
    self._updateQueue = function() {
      let q = [];
      for (let j of self.jobs()) {
        q = q.concat(j.as_queue());
      }
      self.api.assign(q, self._setState);
    };

    self._loadState = function(state) {
        self.loading(true);
        self.api.getState(self._setState);
    };

    self._updateJobs = function(q) {
      if (q.length === 0) {
        self.jobs([new CPJob({name: "", idx: 0})]);
        return
      }
      let curName = null;
      let curJob = null;

      // Convert to nested representation
      let rep = [];
      for (let item of q) {
        // Compatibility for older version data
        if (item.job === null || item.job === undefined) {
          item.job = "";
        }
        if (item.job !== curJob) {
          rep.push([[]]);
        } else if (item.name !== curName) {
          rep[rep.length-1].push([]);
        }
        curJob = item.job;
        curName = item.name;
        let qsl = rep[rep.length-1].length;
        rep[rep.length-1][qsl-1].push(item);
      }
      let jobs = [];
      // In-place merge alike queuesets
      for (let i = 0; i < rep.length; i++) {
        let r = rep[i];
        for (let j = 0; j < r.length; j++) {
          for (let k = r.length-1; k > j; k--) {
            if (r[k][0].name === r[j][0].name) {
              r[j] = r[j].concat(r[k]);
              r.splice(k,1);
            }
          }
        }
        jobs.push(new CPJob({name: rep[i][0][0].job || "", queuesets: r}));
      }
      // Push an extra empty job on the end if the last job is configured
      if (jobs.length < 1 || jobs[jobs.length-1].is_configured()) {
        jobs.push(new CPJob());
      }
      self.jobs(jobs);
    };

    self._setState = function(state) {
        self._updateJobs(state.queue);
        self.active(state.active);
        self.status(state.status);
        self.loading(false);
    };

    // *** ko template methods ***
    self.setActive = function(active) {
        if (self.loading()) return;
        self.api.setActive(active, self._setState);
    };

    self.remove = function(e) {
        if (self.loading()) return;
        if (e.constructor.name === "CPJob") {
            self.jobs.remove(e);
        } else if (e.constructor.name === "CPQueueSet") {
            for (let j of self.jobs()) {
                j.queuesets.remove(e);
            }
        }
        self._updateQueue();
    };

    self.requeueFailures = function() {
        if (self.loading()) return;
        self.loading(true);
        for (let j of self.jobs()) {
          j.requeueFailures();
        }
        self._updateQueue();
    };

    self.clearCompleted = function() {
        if (self.loading()) return;
        self.loading(true);
        self.jobs(self.jobs().filter((j) => !j.is_complete()));
        self._updateQueue();
    };

    self.clearAll = function() {
        if (self.loading()) return;
        self.loading(true);
        self.jobs([]);
        self._updateQueue();
    };

    self._resolve = function(observable) {
      if (typeof(observable) === 'undefined') {
        return null;
      } else if (typeof(observable) === 'function') {
        return observable();
      }
      return observable;
    };

    self.setSelected = function(job, queueset) {
        job = self._resolve(job);
        queueset = self._resolve(queueset);
        if (self.loading()) return;
        let s = self.selected();
        if (s !== null && s[0] == job && s[1] == queueset) {
          self.selected(null);
        } else {
          self.selected([job, queueset]);
        }
    };

    self.refreshQueue = function() {
        if (self.loading()) return;
        self._loadState();
    };

    self.setJobName = function(job, evt) {
        if (self.loading()) return;
        job.set_name(evt.target.value);
        self._updateQueue();
    };

    self.setCount = function(vm, e) {
      if (self.loading()) return;
      let v = parseInt(e.target.value, 10);
      if (isNaN(v) || v < 1) {
        return;
      }
      vm.set_count(v);
      self._updateQueue();
    };

    self.sortStart = function(evt) {
      // Faking server disconnect allows us to disable the default whole-page
      // file drag and drop behavior.
      self.files.onServerDisconnect();
    };

    self.sortEnd = function(_, item) {
      if (self.loading()) return;
      // Re-enable default drag and drop behavior
      self.files.onServerConnect();
      for (let j of self.jobs()) {
        j.sort_end(item);
      }
      self._updateQueue();
    };

    self.sortMove = function(evt) {
      // Like must move to like (e.g. no dragging a queueset out of a job)
      return (evt.from.id === evt.to.id);
    };

    // This also fires on initial load
    self.onTabChange = function(next, current) {
      if (current === self.TAB_ID && next !== self.TAB_ID) {
        // Navigating away - TODO clear hellow highlights
      } else if (current !== self.TAB_ID && next === self.TAB_ID) {
        // Reload in case other things added
        self._loadState();
      }
    };

    self.onDataUpdaterPluginMessage = function(plugin, data) {
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
    };
}


try {
module.exports = CPViewModel;
} catch {}
