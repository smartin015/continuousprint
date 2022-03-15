/*
 * View model for OctoPrint-Print-Queue
 *
 * Contributors: Michael New, Scott Martin
 * License: AGPLv3
 */

if (typeof ko === "undefined" || ko === null) {
  ko = require('knockout');
}
if (typeof CPQueueSet === "undefined" || CPQueueSet === null) {
  CPQueueSet = require('./continuousprint_queueset');
}

// jobs and queuesets are derived from self.queue, but they must be
// observableArrays in order for Sortable to be able to reorder it.
function CPJob(obj) {
  var self = this;
  obj = {...{queuesets: [], name: ""}, ...obj};
  self.name = ko.observable(obj.name);
  self.queuesets = ko.observableArray([]);
  for (let qs of obj.queuesets) {
    self.queuesets.push(new CPQueueSet(qs));
  }
  self._count = function(exclude_qs=null) {
    let maxrun = 0;
    for (let qs of self.queuesets()) {
      if (qs.length() > 0 && qs !== exclude_qs) {
        maxrun = Math.max(maxrun, qs.items()[qs.length()-1].run());
      }
    }
    return maxrun+1; // Runs, not last run idx
  }
  self.count = ko.computed(self._count);
  self.length = ko.computed(function() {
    let l = 0;
    for (let qs of self.queuesets()) {
      l += qs.length();
    }
    return l;
  });
  self.is_configured = function() {
    return (self.name() !== "" || self.count() != 1);
  }
  self.is_complete = function() {
    let cnt = self.count();
    for (let qs of self.queuesets()) {
      if (qs.runs_completed() !== cnt) {
        return false;
      }
    }
    return true;
  }
  self.items_completed = ko.computed(function() {
    let num = 0;
    for (let qs of self.queuesets()) {
      num += qs.items_completed();
    }
    return num;
  })
  self.runs_completed = ko.computed(function() {
    if (self.queuesets().length < 1) {
      return 0;
    }
    let rc = self.count();
    for (let qs of self.queuesets()) {
      rc = Math.min(rc, qs.runs_completed());
    }
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
    let job = self.name();
    for (let run = 0; run < self.count(); run++) {
      for (let i=0; i < qsi.length; i++) {
        let items = qss[i].items();
        while (items.length > qsi[i] && items[qsi[i]].run() <= run) {
          let item = {...items[qsi[i]].as_object(), job, run};
          result.push(item);
          qsi[i]++;
        }
      }
    }
    return result;
  }

  // ==== Mutation methods =====

  self.set_count = function(v) {
    for (let qs of self.queuesets()) {
      qs.set_runs(v);
    }
  }
  self.set_name = function(name) {
    self.name(name);
  }
  self.sort_end = function(item) {
    let cnt = self._count(exclude_qs=item);
    for (let qs of self.queuesets()) {
      qs.set_runs(cnt);
    }
  }
  self.pushQueueItem = function(item) {
    self.queuesets.push(new CPQueueSet([item]));
  }
  self.requeueFailures = function() {
    for (let qs of self.queuesets()) {
      let items = qs.items();
      let modified = false;
      for (let i of items) {
        if (i.result().startsWith("fail")) {
          i.requeue();
          modified = true;
        }
      }
      if (modified) {
        qs.items(items);
      }
    }
  }
}

try {
  module.exports = CPJob;
} catch {}
