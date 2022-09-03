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
  cphr = require('./continuousprint_history_row');
  CP_PRINTER_PROFILES = [];
  CPHistoryRow = cphr.CPHistoryRow;
  CPHistoryDivider = cphr.CPHistoryDivider;
  log = {
    "getLogger": () => {return console;}
  };
  $ = function() { return null; };
}

function CPViewModel(parameters) {
    var self = this;
    self.PLUGIN_ID = "octoprint.plugins.continuousprint";
    self.log = log.getLogger(self.PLUGIN_ID);
    self.TAB_ID = "#tab_plugin_continuousprint";
    self.printerState = parameters[0];
    self.loginState = parameters[1];
    self.files = parameters[2];
    self.printerProfiles = parameters[3];
    self.settings = parameters[4];
    self.cpPrinterProfiles = CP_PRINTER_PROFILES;
    self.extruders = ko.computed(function() { return self.printerProfiles.currentProfileData().extruder.count(); });
    self.status = ko.observable("Initializing...");
    self.statusType = ko.observable("INIT");
    self.active = ko.observable(false);
    self.active_set = ko.observable(null);
    self.loading = ko.observable(false);
    self.materials = ko.observable([]);
    self.queues = ko.observableArray([]);
    self.defaultQueue = null;
    self.expanded = ko.observable(null);
    self.profile = ko.observable('');
    self.showStats = ko.observable(false);

    self.api = parameters[5] || new CPAPI();


    self.api.init(self.loading,
      function(code, reason) {
        console.error("API Error", code, reason);
        new PNotify({
            title: `Continuous Print API (Error ${code})`,
            text: reason,
            type: 'error',
            hide: true,
            buttons: {closer: true, sticker: false},
        });
      });

    self.setActive = function(active) {
        self.api.setActive(active, () => {
          self.active(active);
        });
    };

    // Patch the files panel to allow for adding to queue
    self.files.add = function(data) {
      // We first look for any queues with draft jobs - add the file here if so
      // Otherwise it goes into the default queue.
      let fq = self.defaultQueue;
      for (let q of self.queues()) {
        if (q.hasDraftJobs()) {
          fq = q;
          break;
        }
      }
      fq.addFile(data, self.settings.settings.plugins.continuousprint.cp_infer_profile() || false);
    };
    // Also patch file deletion, to show a modal if the file is in the queue
    let oldRemove = self.files.removeFile;
    let remove_cb = null;
    self.files.removeFile = function(data, evt) {
      for (let j of self.defaultQueue.jobs()) {
        for (let s of j.sets()) {
          if (s.path() === data.path) {
            remove_cb = () => oldRemove(data, evt);
            return self.showRemoveConfirmModal()
          }
        }
      }
      return oldRemove(data, evt);
    };
		self.rmDialog = $("#cpq_removeConfirmDialog");
    self.showRemoveConfirmModal = function() {
			self.rmDialog.modal({}).css({
					width: 'auto',
					'margin-left': function() { return -($(this).width() /2); }
			});
    };
    self.hideRemoveConfirmModal = function() {
			self.rmDialog.modal('hide');
    };
    self.removeConfirm = function() {
      remove_cb();
      remove_cb = null;
      self._loadState(); // Refresh to get new "file missing" states
      self.hideRemoveConfirmModal();
    };

    // Patch the files panel to prevent selecting/printing .gjob files
    let oldEnableSelect = self.files.enableSelect;
    self.files.enableSelect = function(data) {
      if (data['path'].endsWith('.gjob')) {
        return false;
      }
      return oldEnableSelect(data);
    }
    let oldEnableSelectAndPrint = self.files.enableSelectAndPrint;
    self.files.enableSelectAndPrint = function(data) {
      if (data['path'].endsWith('.gjob')) {
        return false;
      }
      return oldEnableSelectAndPrint(data);
    }

    // Patch the printer state view model to display current status
    self.printerState.continuousPrintStateString = ko.observable("");
    self.printerState.continuousPrintStateStatus = ko.observable("");
    self.printerState.continuousPrintStateIcon = ko.computed(function() {
      switch(self.printerState.continuousPrintStateStatus()) {
        case "NEEDS_ACTION":
          return "fas fa-hand-paper";
        case "ERROR":
          return "far fa-exclamation-triangle";
        default:
          return "";
      }
    });

    self._loadState = function(state) {
        self.log.info(`[${self.PLUGIN_ID}] loading state...`);
        self.api.get(self.api.STATE, self._setState);
    };

    self._updateQueues = function(queues) {
      let result = [];

      // Preserve selections and expansions by traversing all queues before
      // replacing them
      let selections = {};
      let expansions = {};
      let drafts = {}
      for (let q of self.queues()) {
        for (let j of q.jobs()) {
          if (j.draft()) {
            drafts[j.id().toString()] = j;
          }
          if (j.selected()) {
            selections[j.id().toString()] = true;
          }
          for (let s of j.sets()) {
            if (s.expanded()) {
              expansions[s.id.toString()] = true;
            }
          }
        }
      }
      for (let q of queues) {
        for (let j of q.jobs) {
          j.selected = selections[j.id.toString()];
          for (let s of j.sets) {
            s.expanded = expansions[s.id.toString()];
          }
        }
        let cpq = new CPQueue(q, self.api, self.files, self.profile);

        // Replace draft entries
        let cpqj = cpq.jobs();
        for (let i = 0; i < q.jobs.length; i++) {
          let draft = drafts[cpqj[i].id()];
          if (draft !== undefined) {
            cpq.jobs.splice(i, 1, draft);
          }
        }
        result.push(cpq);
        if (cpq.name === 'local') {
          self.defaultQueue = cpq;
        }
      }
      self.queues(result);
    };

    self._setState = function(state) {
        //self.log.info(`[${self.PLUGIN_ID}] updating queues (len ${state.queues.length})`);
        self._updateQueues(state.queues);
        self.active(state.active);
        self.active_set(state.active_set);
        self.status(state.status);
        self.statusType(state.statusType);
        self.profile(state.profile);
        self.printerState.continuousPrintStateString(state.status);
        self.printerState.continuousPrintStateStatus(state.statusType);
        //self.log.info(`[${self.PLUGIN_ID}] new state loaded`);
    };

    self.newEmptyJob = function() {
      self.defaultQueue.newEmptyJob();
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

    self.draggingSet = ko.observable();
    self.draggingJob = ko.observable();
    self.sortStart = function(evt, vm) {
      // Faking server disconnect allows us to disable the default whole-page
      // file drag and drop behavior.
      self.files.onServerDisconnect();
      self.draggingSet(vm.constructor.name === "CPSet");
      self.draggingJob(vm.constructor.name === "CPJob");
    };

    self.sortEnd = function(evt, vm, src, dataFor=ko.dataFor) {
      // Re-enable default drag and drop behavior
      self.files.onServerConnect();
      self.draggingSet(false);
      self.draggingJob(false);

      // Sadly there's no "destination job" information, so we have to
      // infer the index of the job based on the rendered HTML given by evt.to
      if (vm.constructor.name === "CPJob") {
        let jobs = self.defaultQueue.jobs();
        let destq = dataFor(evt.to);
        let dest_idx = destq.jobs().indexOf(vm);

        let ids = []
        for (let j of jobs) {
          ids.push(j.id());
        }
        self.api.mv(self.api.JOB, {
            src_queue: src.name,
            dest_queue: destq.name,
            id: vm.id(),
            after_id: (dest_idx > 0) ? destq.jobs()[dest_idx-1].id() : null
        }, (result) => {
          if (result.error) {
            self.onDataUpdaterPluginMessage("continuousprint", {type: "error", msg: result.error});
          }
        });
      }
    };

    self.sortMove = function(evt) {
      // Like must move to like (e.g. no dragging a set out of a job)
      if (evt.from.id !== evt.to.id) {
        return false;
      }
      // Sets must only be dragged among draft jobs
      if (evt.from.id === "queue_sets" && !evt.to.classList.contains("draft")) {
        return false;
      }
      // No dragging items in non-ready queues
      if (evt.to.classList.contains("loading")) {
        return false;
      }
      return true;
    };

    // This also fires on initial load
    self.onTabChange = function(next, current) {
      self.log.info(`[${self.PLUGIN_ID}] onTabChange - ${self.TAB_ID} == ${current} vs ${next}`);
      if (current === self.TAB_ID && next !== self.TAB_ID) {
        // Navigating away - TODO clear hellow highlights
      } else if (current !== self.TAB_ID && next === self.TAB_ID) {
        // Reload in case other things added
        self._loadState();
        self.refreshHistory();
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
            case "setstate":
                data = JSON.parse(data["state"]);
                console.log("got setstate", data);
                return self._setState(data);
            case "sethistory":
                data = JSON.parse(data["history"]);
                console.log("got sethistory", data);
                return self._setHistory(data);
            default:
                theme = "info";
                break;
        }

        if (data.msg != "") {
            new PNotify({
                title: 'Continuous Print',
                text: data.msg,
                type: theme,
                hide: (theme !== 'danger'),
                buttons: {closer: true, sticker: false}
            });
        }
    };

    self.hasSpoolManager = ko.observable(false);
    self.badMaterialCount = ko.observable(0);
    self.api.getSpoolManagerState(function(resp) {
      let result = {};
      let nbad = 0;
      for (let spool of resp.allSpools) {
        if (spool.material === null) {
          nbad++;
          continue;
        }
        let k = `${spool.material}_${spool.colorName}_#${spool.color.substring(1)}`;
        result[k] = {value: k, text: `${spool.material} (${spool.colorName})`};
      }
      self.materials(Object.values(result));
      self.badMaterialCount(nbad);
      self.hasSpoolManager(true);
    }, function(statusCode, errText) {
      self.hasSpoolManager(statusCode !== 404);
    });

    self.humanize = function(num) {
      // Humanizes numbers by condensing and adding units
      if (num < 1000) {
        return num.toString()
      } else if (num < 100000) {
        let k = (num/1000);
        return ((k % 1 === 0) ? k : k.toFixed(1)) + 'k';
      } else {
        let m = (num/1000000);
        return ((m % 1 === 0) ? m : m.toFixed(1)) + 'm';
      }
    };

    self.hasDraftJob = ko.computed(function() {
      for (let q of self.queues()) {
        for (let j of q.jobs()) {
          if (j.draft()) {
            return true;
          }
        }
      }
      return false;
    });

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
          result.push(new CPHistoryDivider(r.queue_name, r.job_name, r.set_path));
          job = r.job_name;
          set = r.set_path;
        }
        result.push(new CPHistoryRow(r));
      }
      self.history(result);
    };
    self.refreshHistory = function() {
      self.api.get(self.api.HISTORY, self._setHistory);
    };
    self.clearHistory = function() {
      self.api.reset(self.api.HISTORY, null, () => {
        self.entries([]);
      });
    };
}


try {
module.exports = CPViewModel;
} catch {}
