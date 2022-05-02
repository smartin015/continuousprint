/*
 * View model for OctoPrint-Print-Queue
 *
 * Contributors: Michael New, Scott Martin
 * License: AGPLv3
 */

if (typeof CPHistoryRow === "undefined" || CPHistoryRow === null) {
  // In the testing environment, dependencies must be manually imported
  ko = require('knockout');
  CPAPI = require('./continuousprint_api');
  CPHistoryRow = require('./continuousprint_run');
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
  self.title = `${job} - ${set}`;
}

function CPHistoryViewModel(parameters) {
    var self = this;
    self.PLUGIN_ID = "octoprint.plugins.continuousprint";
    self.TAB_ID = "#tab_plugin_continuousprint_2";
    self.log = log.getLogger(self.PLUGIN_ID);
    self.log.info(`[${self.PLUGIN_ID}] History init`);

    self.loading = ko.observable(false);
    self.api = parameters[0] || new CPAPI();
    self.api.init(self.loading);
    self.entries = ko.observableArray();
    self.isDivider = function(data) {
      return data instanceof CPHistoryDivider;
    };

    self._setState = function(data) {
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
      console.log(result);
      self.entries(result);
    };
    self.refresh = function() {
      self.api.history(self._setState);
    };
    self.clearHistory = function() {
      self.api.clearHistory(() => {
        self.entries([]);
      });
    };

    // This also fires on initial load
    self.onTabChange = function(next, current) {
      if (current !== self.TAB_ID && next === self.TAB_ID) {
        self.refresh();
      }
    };

}


try {
module.exports = CPHistoryViewModel;
} catch {}
