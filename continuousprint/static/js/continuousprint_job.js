/*
 * View model for OctoPrint-Print-Queue
 *
 * Contributors: Michael New, Scott Martin
 * License: AGPLv3
 */

if (typeof ko === "undefined" || ko === null) {
  ko = require('knockout');
}
if (typeof CPSet === "undefined" || CPSet === null) {
  CPSet = require('./continuousprint_set');
}

// jobs and sets are derived from self.queue, but they must be
// observableArrays in order for Sortable to be able to reorder it.
function CPJob(obj, peers, api) {
  if (api === undefined) {
    throw Error("API must be provided when creating CPJob");
  }
  var self = this;
  obj = {...{sets: [], name: "", draft: false, count: 1, remaining: 1, queue: "default", id: -1}, ...obj};
  self.id = ko.observable(obj.id);
  self._name = ko.observable(obj.name || "");

  if (obj.acquired) {
    self.acquiredBy = ko.observable('local');
  } else if (obj.acquired_by_) {
    let peer = peers[obj.acquired_by_];
    if (peer !== undefined) {
      self.acquiredBy = ko.observable(peer.name);
    } else {
      self.acquiredBy = ko.observable(obj.acquired_by_)
    }
  } else {
    self.acquiredBy = ko.observable();
  }
  self.draft = ko.observable(obj.draft);
  self.count = ko.observable(obj.count);
  self.remaining = ko.observable((obj.remaining !== undefined) ? obj.remaining : obj.count);
  self.completed = ko.observable(obj.count - self.remaining());
  self.selected = ko.observable(obj.selected || false);

  self.sets = ko.observableArray([]);
  for (let s of obj.sets) {
    self.sets.push(new CPSet(s, self, api));
  }

  self.as_object = function() {
    let data = {
        name: self._name(),
        count: self.count(),
        remaining: self.remaining(),
        id: self.id(),
        sets: []
    };
    for (let s of self.sets()) {
      data.sets.push(s.as_object());
    }
    return data;
  }

  self.editStart = function() {
    api.edit(api.JOB, {id: self.id(), draft: true}, () => {
      self.draft(true);
    });
  }
  self.onSetModified = function(s) {
    let newqs = new CPSet(s, self, api);
    for (let qs of self.sets()) {
      if (qs.id === s.id) {
        return self.sets.replace(qs, newqs);
      }
    }
    self.sets.push(newqs);
 }
  self.editEnd = function() {
    let data = self.as_object();
    data.draft = false;
    api.edit(api.JOB, data, (result) => {
      self.draft(false);
      self.count(result.count);
      self.remaining(result.remaining); // Adjusted when count is mutated
      self.completed(result.count - result.remaining); // Adjusted when count is mutated
      self.id(result.id); // May change if no id to start with
      self._name(result.name);
      let cpss = [];
      if (result.sets !== undefined) {
        for (let qsd of result.sets) {
          cpss.push(new CPSet(qsd, self, api));
        }
      }
      self.sets(cpss);
    });
  }

  self.length = ko.computed(function() {
    let l = 0;
    let c = self.count();
    for (let qs of self.sets()) {
      l += qs.count()*c;
    }
    return l;
  });
  self.length_completed = ko.computed(function() {
    let r = 0;
    for (let qs of self.sets()) {
      r += qs.length_completed();
    }
    return r;
  });
  self.checkFraction = ko.computed(function() {
    return (self.selected()) ? 1 : 0;
  });
  self.pct_complete = ko.computed(function() {
    return Math.round(100 * self.completed()/self.count()) + '%';
  });
  self.pct_active = ko.computed(function() {
    return Math.round(100 / self.count()) + '%';
  });
  self.onChecked = function() {
    self.selected(!self.selected());
  }
}

try {
  module.exports = CPJob;
} catch {}
