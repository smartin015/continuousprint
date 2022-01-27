/*
 * View model for OctoPrint-Print-Queue
 *
 * Contributors: Michael New, Scott Martin
 * License: AGPLv3
 */

$(function() {
    const SELF_TAB_ID = "#tab_plugin_continuousprint";

    const QueueState = {
      UNKNOWN: null,
      QUEUED: "queued",
      PRINTING: "printing",
      
    }

    // Inspired by answers at
		// https://stackoverflow.com/questions/6108819/javascript-timestamp-to-relative-time
		function timeAgo(previous, current=null) {
        var sPerMinute = 60;
				var sPerHour = sPerMinute * 60;
				var sPerDay = sPerHour * 24;
				var sPerMonth = sPerDay * 30;
        if (current === null) {
          current = (new Date()).getTime()/1000;
        }
				var elapsed = current - previous;
				if (elapsed < sPerHour) {
						 return Math.round(elapsed/sPerMinute) + ' minutes';   
				}
				else if (elapsed < sPerDay ) {
						 return Math.round(elapsed/sPerHour) + ' hours';   
				}
				else if (elapsed < sPerMonth) {
						return Math.round(elapsed/sPerDay) + ' days';   
				}
				else {
						return Math.round(elapsed/sPerMonth) + ' months';   
				}
		}

    // see QueueItem in print_queue.py for matching python object
    function QueueItem(data, idx) {
      var self = this;
      self.idx = idx;
      self.name = data.name;
      self.path = data.path;
      self.sd = data.sd;
      self.job = data.job;
      self.run = ko.observable(data.run);
      self.changed = ko.observable(data.changed || false);
      self.retries= ko.observable((data.start_ts !== null) ? data.retries : null);
      self.start_ts = ko.observable(data.start_ts || null);
      self.end_ts = ko.observable(data.end_ts || null);
      self.result = ko.computed(function() {
        if (data.result !== null && data.result !== undefined) {
          return data.result;
        }
        if (self.start_ts() === null) {
          return "pending";
        }
        if (self.start_ts() !== null && self.end_ts() === null) {
          return "started";
        }
      });
      self.duration = ko.computed(function() {
        let start = self.start_ts();
        let end = self.end_ts();
        if (start === null || end === null) {
          return null;
        }
        return timeAgo(start, end);
      });
    }

    function QueueSet(items, idx) {
      var self = this;
      self.idx = idx;
      self._n = items[0].name; // Used for easier inspection in console
      self._len = items.length;
      self.items = ko.observableArray(items);
      self.changed = ko.computed(function() {
        for (let item of self.items()) {
          if (item.changed()) {
            return true;
          }
        }
        return false;
      });
      self.length = ko.computed(function() {return self.items().length;});
      self.name = ko.computed(function() {return self.items()[0].name;});
      self.path = ko.computed(function() {return self.items()[0].path;});
      self.job = ko.computed(function() {return self.items()[0].job;});
      self.count = ko.computed(function() {
        return Math.floor(self.length() / (self.items()[self.length()-1].run()+1));
      });
      self.sd = ko.computed(function() {return self.items()[0].sd;});
      self.start_ts = ko.computed(function() {return self.items()[0].start_ts();});
      self.end_ts = ko.computed(function() {
        for (let item of self.items()) {
          if (item.end_ts !== null) {
            return item.end_ts();
          }
        }
        return null;
      });
      self.result = ko.computed(function() {
        return self.items()[self.items().length-1].result();
      })
      self.num_completed = ko.computed(function() {
        let i = 0;
        for (let item of self.items()) {
          if (item.end_ts() !== null) {
            i++;
          }
        }
        return i;
      });
      self.runs_completed = ko.computed(function() {
        return Math.floor(self.num_completed() / self.count());
      });
      self.progress = ko.computed(function() {
        let progress = [];
        let curNum = 0;
        let curResult = self.items()[0].result();
        let pushProgress = function() {
          progress.push({
            pct: (100 * curNum / self._len).toFixed(0),
            order: {"pending": 2, "success": 1}[curResult] || 0,
            result: curResult,
          });
        }
        for (let item of self.items()) {
          let res = item.result();
          if (res !== curResult) {
            pushProgress();
            curNum = 0;
            curResult = res;
          }
          curNum++;
        }
        pushProgress();
        return progress;
      });
      self.active = ko.computed(function() {
        for (let item of self.items()) {
          if (item.start_ts === null && item.end_ts !== null) {
            return true;
          }
        }
      });
      self.description = ko.computed(function() {
        if (self.start_ts() === null) {
          return "Pending";
        } else if (self.active()) {
          return `First item started ${timeAgo(self.start_ts)} ago`;
        } else if (self.end_ts() !== null) {
					return `${self.result()} (${timeAgo(self.end_ts())} ago; took ${timeAgo(self.start_ts(), self.end_ts())})`;
				} else {
					return self.result();
				}
      });


      self.tmpl = {
        "name": self.name(), 
        "path": self.path(), 
        "sd": self.sd(), 
        "job": self.job(), 
      };
      self.set_count = function(_, e) {
        let v = parseInt(e.target.value, 10);
        if (isNaN(v) || v < 1) {
          return;
        }
        let items = self.items();
        let cnt = self.count();
        let runs = items[items.length-1].run() + 1;
        let diff = v - cnt;
        if (diff > 0) {
          // TODO interleave
          // Splice in `diff` amount of new items at the end of each run
          for (let run = 0; run < runs; run++) {
            let base = run * v + cnt; // Position of next insert
            for (let i = 0; i < diff; i++) {
              items.splice(base, 0, new QueueItem({...self.tmpl, run}));
            }
          }
          self.items(items);
          console.warn("TODO API update");
        } else if (diff < 0) {
          items.splice(v*runs);
          // We must re-specify the runs since we're truncating from the end
          for (let run = 0; run < runs; run++) {
            for (let i = 0; i < v; i++) {
              items[run*v + i].run(run);
            }
          }
          self.items(items);
          console.warn("TODO API update");
          //self.api.remove(cnt.idx + (cnt.length() + diff - 1), -diff, self._setState);
        } 
        // Do nothing if equal
      }
      self.set_runs = function(v) {
        let cnt = self.count();
        let items = self.items();
        let runs = items[items.length-1].run() + 1;
        if (v < runs) {
          items.splice(v*cnt);
          self.items(items);
          console.warn("TODO API update");
        } else if (v > runs) {
          for (let run = runs; run < v; run++) {
            for (let j = 0; j < cnt; j++) {
              items.push(new QueueItem({...self.tmpl, run}));
            }
          }
          self.items(items);
          console.warn("TODO API update");
        }
      }
    }

    // jobs and queuesets are derived from self.queue, but they must be 
    // observableArrays in order for Sortable to be able to reorder it.
    function Job(obj) {
      var self = this;
      obj = obj || {
        queuesets: [], 
        name: "",
        idx: 0, 
      };
      self.prep = {} // map of item names to list of items in the job
      self.push = function(item) {
        if (self.prep[item.name] === undefined) {
          self.prep[item.name] = [];
        }
        self.prep[item.name].push(item);
      }
      self.finalize = function() {
        // TODO convert self.prep into queuesets
        let result = [];
        for (let p of Object.values(self.prep)) {
          result.push(new QueueSet(p, p[0].idx));
        }
        result.sort(function(a,b) {return a.idx > b.idx});
        self.queuesets(result);
        console.log("Finalized job " + self.name, result);
      }
      self.name = ko.observable(obj.name);
      self.queuesets = ko.observableArray(obj.queuesets);
      self.idx = obj.idx;
      self._count = function(exclude_qs=null) {
        let maxrun = 0;
        for (let qs of self.queuesets()) {
          if (qs === exclude_qs) {console.log("skipping dropped queueset");}
          if (qs.length && qs !== exclude_qs) {
            maxrun = Math.max(maxrun, qs.items()[qs.length()-1].run());
          }
        }
        return maxrun+1; // Runs, not last run idx
      }
      self.count = ko.computed(self._count);

      // TODO
      self.runs_completed = ko.computed(function() { 
        let rc = self.count();
        for (let qs of self.queuesets()) {
          rc = Math.min(rc, qs.runs_completed()); 
          console.log(rc);
        }
        console.log("Runs completed:", rc);
        return rc;
      });
      self.progress = ko.computed(function() {
        let result = [];
        for (let qs of self.queuesets()) {
          result.push(qs.progress());
        }
        return result.flat();
      })
      self.as_queue = function() {
        let result = [];
        let qss = self.queuesets();
        let qsi = [];
        for (let i = 0; i < qss.length; i++) {
          qsi.push(0);
        }
        // Round-robin through the queuesets, pushing until we've exhausted each run
        for (let ridx = 0; ridx < self.runs(); ridx++) {
          for (let i=0; i < qsi.length; i++) {
            let items = qss[i].items();
            while (items.length > qsi[i] && items[qsi[i]].run() <= ridx) {
              result.push(items[qsi[i]]);
              qsi[i]++;
            }
          }
        }
        return result;
      }

      self.set_count = function(_, e) {
        let v = parseInt(e.target.value, 10);
        if (isNaN(v) || v < 1) {
          return;
        }
        for (let qs of self.queuesets()) {
          qs.set_runs(v);
        }
      }
      self.set_name = function(name) {
        self.name(name);
        console.log("TODO update from name:", self.name());
      }
      self.sort_end = function(item) {
        let cnt = self._count(exclude_qs=item);
        for (let qs of self.queuesets()) {
          qs.set_runs(cnt);
          console.log("Job ", self.name(), "set runs", cnt, "for", qs.name());
        }
      }
    }

    function ContinuousPrintViewModel(parameters) {
        var self = this;
        self.api = new CPrintAPI();

        // These are used in the jinja template (TODO CONFIRM)
        self.printerState = parameters[0];
        self.loginState = parameters[1];
        self.loading = ko.observable(true);
        self.active = ko.observable(false);
        self.status = ko.observable("Initializing...");
        self.searchtext = ko.observable("");
        self.queue = ko.observableArray([]);
        self.selected = ko.observable(0);

        // Obsevable variable definitions
        self.jobs = ko.observableArray([]);
        self.activeIdx = ko.computed(function() {
          if (!self.printerState.isPrinting() && !self.printerState.isPaused()) {
            return null;
          }
          let q = self.queue(); 
          let printname = self.printerState.filename();
          for (let i = 0; i < q.length; i++) {
            if (q[i].end_ts() === null && q[i].name === printname) {
              return i;
            }
          }
          return null;
        });
        self.activeQueueSet = ko.computed(function() {
          let idx = self.activeIdx();
          if (idx === null) {
            return null;
          }
          for (let j of self.jobs()) {
            for (let qss of j.queuesets()) {
              if (idx >= qss.idx && idx < qss.idx + qss.length()) {
                return qss.idx;
              }
            }
          }
          return null;
        });
        
        self.onBeforeBinding = function() {
            self._loadState();
        }
  
        // Patch the files panel to allow for adding to queue
        self.files = parameters[2];
        self.files.add = function(data) {
            let now = Date.now();
            let jobs = self.jobs();
            let job = jobs[jobs.length-1];
            // We want to add to a job with a single run and no name -
            // otherwise implies adding to something a user has already configured
            if (job.name() !== "" || job.count() !== 1) {
              job = new Job({name: "", idx: now});
              self.jobs.push(job);
            }
  
            let qs = new QueueSet([new QueueItem({
                name: data.name,
                path: data.path,
                sd: (data.origin !== "local"),
                run: 0,
                job: job.name(),
                idx: now, // Prevent selection errors before sync with server
            })], now);
            job.queuesets.push(qs);
            console.warn("TODO update from new item");
            /*
            self.api.add([{
              }], undefined, (state) => {
                // Notify of additions when we aren't able to see the result
                if (window.location.hash.indexOf("continuousprint") === -1) {
                  new PNotify({
                      title: 'Continuous Print',
                      text: "Added " + data.name,
                      type: "success",
                      hide: true,
                      buttons: {closer: true, sticker: false}
                  });
                }
                self._setState(state);
              });
          */
        };

        self._loadState = function(state) {
            self.loading(true);
            self.api.getState(self._setState);
        };    
        self._updateQueueSets = function() {
          let q = self.queue();
          if (q.length === 0) {
            self.jobs([new Job({name: "", idx: 0})]);
            return
          }
          let jobs = {}; // {jobname: {queuesetname: [item1, item2,...]}}
          let cur = [];
          let curName = null;
          let curJob = (q.length) ? q[0].job : null;

          let i = 0;
          let qidx = 0;

          // Convert to intermediate representation
          for (let item of q) {
            item.job = item.job || "";
            if (jobs[item.job] === undefined) {
              jobs[item.job] = new Job({name: item.job, idx: item.idx});
            }
            jobs[item.job].push(item)
          }
          for (let j of Object.values(jobs)) {
            j.finalize();
          }
          let result = Object.values(jobs);
          result.sort(function(a,b) {return a.idx > b.idx;}); // in place
          self.jobs(result);
        }

        self._setState = function(state) {
            self.queue($.map(state.queue, function(q, i) {
              return new QueueItem(q, i);
            }));
            self._updateQueueSets();
            self.active(state.active);
            self.status(state.status);
            self.loading(false);
        }
                        
        // *** ko template methods ***
        self.setActive = function(active) {
            self.api.setActive(active, self._setState);
        }
        self.remove = function(e) {
          if (e.constructor.name === "Job") {
            self.jobs.remove(e);
          } else if (e.constructor.name === "QueueSet") {
            for (let j of self.jobs()) {
              j.queuesets.remove(e);
            }
          }
        }
        self.clearCompleted = function() {
            if (self.loading()) return;
            self.loading(true);
            self.api.clear(self._setState, false, true);
        }
        self.clearSuccessful = function() {
            if (self.loading()) return;
            self.loading(true);
            self.api.clear(self._setState, true, true);
        }
        self.clearAll = function() {
            if (self.loading()) return;
            self.loading(true);
            self.api.clear(self._setState, false, false);
        }
        self.setSelected = function(sel) {
            if (self.loading()) return;
            self.selected((sel.idx === self.selected()) ? null : sel.idx);
        }
        self.refreshQueue = function() {
            if (self.loading()) return;
            self._loadState();
        }
        self.setJobName = function(job, evt) {
            job.set_name(evt.target.value);
            // If we don't have an unnamed job at the bottom of the list, make one
            let jobs = self.jobs();
            if (jobs.length < 1 || jobs[jobs.length-1].name() !== "") {
              self.jobs.push(new Job({name: "", idx: self.queue().length}));
            }
        }

        self.sortStart = function(evt) {
          // Faking server disconnect allows us to disable the default whole-page 
          // file drag and drop behavior.
          self.files.onServerDisconnect();
        }
        self.sortEnd = function(evt, item, dest) {
          // Re-enable default drag and drop behavior
          self.files.onServerConnect();
          console.log(arguments);
          for (let j of self.jobs()) {
            j.sort_end(item);
          }
        }
        self.sortMove = function(evt, itemVM, parentVM) {
          // Like must move to like (e.g. no dragging a queueset out of a job)
          return (evt.from.id === evt.to.id);
        }

        // ***

        // Reload state if we go back to this window from somewhere else
        // TODO disable when drag-drop
        //window.addEventListener('focus', function() {
        //  self._loadState();
        //});

        self.onTabChange = function(next, current) {
          if (current === SELF_TAB_ID && next !== SELF_TAB_ID) {
            // Navigating away - clear hellow highlights
            for (let i = 0; i < self.queue.length; i++) {
              if (self.queue[i].changed()) {
                self.queue[i].changed(false);
              }
            }
          } else if (current !== SELF_TAB_ID && next === SELF_TAB_ID) {
            // Reload in case other things added
            self._loadState();
          }
        }

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
        }
    }
    /**/

    $(document).ready(function(){
        /*
         * This adds a "Q" button to the left file panel for quick access
         * Adapted from OctoPrint-PrusaSlicerThumbnails
         * https://github.com/jneilliii/OctoPrint-PrusaSlicerThumbnails/blob/master/octoprint_prusaslicerthumbnails/static/js/prusaslicerthumbnails.js
         */
        let regex = /<div class="btn-group action-buttons">([\s\S]*)<.div>/mi;
        let template = '<div class="btn btn-mini bold" data-bind="click: function() { if ($root.loginState.isUser()) { $root.add($data) } else { return; } }" title="Add To Continuous Print Queue" ><i class="fas fa-plus"></i></div>';

        $("#files_template_machinecode").text(function () {
            var return_value = $(this).text();
            return_value = return_value.replace(regex, '<div class="btn-group action-buttons">$1    ' + template + '></div>');
            return return_value
        });
    });


    // Add config info to the global var to register our plugin
    OCTOPRINT_VIEWMODELS.push([
        // This is the constructor to call for instantiating the plugin
        ContinuousPrintViewModel,

        // Dependencies (injected in-order)
        [
          "printerStateViewModel", 
          "loginStateViewModel",
          "filesViewModel", 
          "settingsViewModel"
        ],

        // Selectors for all elements binding to this view model
        [SELF_TAB_ID]
    ]);
});
