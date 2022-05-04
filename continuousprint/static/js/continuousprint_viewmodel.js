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
    self.api = parameters[4] || new CPAPI();

    // These are used in the jinja template
    self.loading = ko.observable(true);
    self.active = ko.observable(false);
    self.status = ko.observable("Initializing...");
    self.jobs = ko.observableArray([]);
    self.selected = ko.observable(null);

    self.materials = ko.observable([]);
    self.api.getSpoolManagerState(function(resp) {
      let result = {};
      for (let spool of resp.allSpools) {
        let k = `${spool.material}_${spool.colorName}_#${spool.color.substring(1)}`;
        result[k] = {value: k, text: `${spool.material} (${spool.colorName})`};
      }
      self.materials(Object.values(result));
    });

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
    self.files.add = _ecatch("files.add", function(data) {
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
    });


    // Call this after every mutation
    self._updateQueue = _ecatch("_updateQueue", function() {
      let q = [];
      for (let j of self.jobs()) {
        q = q.concat(j.as_queue());
      }
      console.log(q);
      self.api.assign(q, self._setState);
    });

    self._loadState = _ecatch("_loadState", function(state) {
        self.log.info(`[${self.PLUGIN_ID}] loading state...`);
        self.loading(true);
        self.api.getState(self._setState);
    });

    self._updateJobs = _ecatch("_updateJobs", function(q) {
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
    });

    self._setState = function(state) {
        self.log.info(`[${self.PLUGIN_ID}] updating jobs (len ${state.queue.length})`);
        self._updateJobs(state.queue);
        self.active(state.active);
        self.status(state.status);
        self.loading(false);
        self.log.info(`[${self.PLUGIN_ID}] new state loaded`);
    };

    // *** ko template methods ***

    self.setActive = _ecatch("setActive", function(active) {
        if (self.loading()) return;
        self.api.setActive(active, self._setState);
    });

    self.remove = _ecatch("remove", function(e) {
        if (self.loading()) return;
        if (e.constructor.name === "CPJob") {
            self.jobs.remove(e);
        } else if (e.constructor.name === "CPQueueSet") {
            for (let j of self.jobs()) {
                j.queuesets.remove(e);
            }
        }
        self._updateQueue();
    });

    self.requeueFailures = _ecatch("requeueFailures", function() {
        if (self.loading()) return;
        self.loading(true);
        for (let j of self.jobs()) {
          j.requeueFailures();
        }
        self._updateQueue();
    });

    self.clearCompleted = _ecatch("clearCompleted", function() {
        if (self.loading()) return;
        self.loading(true);
        self.jobs(self.jobs().filter((j) => !j.is_complete()));
        self._updateQueue();
    });

    self.clearAll = _ecatch("clearAll", function() {
        if (self.loading()) return;
        self.loading(true);
        self.jobs([]);
        self._updateQueue();
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
        if (self.loading()) return;
        self._loadState();
    });

    self.setJobName = _ecatch("setJobName", function(job, evt) {
        if (self.loading()) return;
        job.set_name(evt.target.value);
        self._updateQueue();
    });

    self.setCount = _ecatch("setCount", function(vm, e) {
      if (self.loading()) return;
      let v = parseInt(e.target.value, 10);
      if (isNaN(v) || v < 1) {
        return;
      }
      vm.set_count(v);
      self._updateQueue();
    });

    self.setMaterial = _ecatch("setMaterial", function(vm, idx, mat) {
      vm.set_material(idx, mat);
      self._updateQueue();
    });

    self.sortStart = _ecatch("sortStart", function(evt) {
      // Faking server disconnect allows us to disable the default whole-page
      // file drag and drop behavior.
      self.files.onServerDisconnect();
    });

    self.sortEnd = _ecatch("sortEnd", function(_, item) {
      if (self.loading()) return;
      // Re-enable default drag and drop behavior
      self.files.onServerConnect();
      for (let j of self.jobs()) {
        j.sort_end(item);
      }
      self._updateQueue();
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
}


try {
module.exports = CPViewModel;
} catch {}
