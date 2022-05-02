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
function CPJob(obj, api) {
  if (api === undefined) {
    throw Error("API must be provided when creating CPJob");
  }
  var self = this;
  obj = {...{sets: [], name: "", count: 1, remaining: 1, queue: "default", id: -1}, ...obj};
  self.id = ko.observable(obj.id);
  self.name = ko.observable(obj.name);
  self.count = ko.observable(obj.count);
  self.countInput = ko.observable(obj.count);
  self.remaining = ko.observable(obj.remaining);

  self.queuesets = ko.observableArray([]);
  for (let s of obj.sets) {
    self.queuesets.push(new CPQueueSet(s, api, self));
  }

  self.onSetModified = function(s) {
    let newqs = new CPQueueSet(s, api, self);
    for (let qs of self.queuesets()) {
      if (qs.id === s.id) {
        return self.queuesets.replace(qs, newqs);
      }
    }
    self.queuesets.push(newqs);
  }

  self.length = ko.computed(function() {
    let l = 0;
    let c = self.count();
    for (let qs of self.queuesets()) {
      l += qs.count()*c;
    }
    return l;
  });
  self.length_completed = ko.computed(function() {
    let r = 0;
    for (let qs of self.queuesets()) {
      r += qs.length_completed();
    }
    return r;
  });
  self.selected = ko.observable(false);
  self.checkFraction = ko.computed(function() {
    let qss = self.queuesets();
    let numsel = (self.selected()) ? 0.1 : 0;
    if (qss.length === 0) {
      return numsel;
    }
    for (let qs of qss) {
      if (qs.selected()) {
        numsel++;
      }
    }
    return numsel / qss.length;
  });
  self.is_configured = function() {
    return (self.name() !== "" || self.count() != 1);
  }
  self.is_complete = function() {
    return self.remaining() >= self.count();
  };
  self.pct_complete = ko.computed(function() {
    return Math.round(100 * (self.count() - self.remaining())/(self.count())) + '%';
  });
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
  self.onChecked = function() {
    self.selected(!self.selected());
  }

  // ==== Mutation methods =====

  self.set_count = function(count) {
    api.update(api.JOB, {id: self.id, count}, (result) => {
      self.count(result.count);
      self.countInput(result.count);
      self.remaining(result.remaining); // Adjusted when count is mutated
      self.id(result.id); // May change if no id to start with
    });
  }
  self.set_name = function(name) {
    api.update(api.JOB, {id: obj.id, name}, (result) => {
      self.name(result.name);
      self.id(result.id); // May change if no id to start with
    });
  }
}

try {
  module.exports = CPJob;
} catch {}
