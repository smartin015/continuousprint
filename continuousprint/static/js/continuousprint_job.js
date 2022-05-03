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

  self.sets = ko.observableArray([]);
  for (let s of obj.sets) {
    self.sets.push(new CPSet(s, api, self));
  }

  self.onSetModified = function(s) {
    let newqs = new CPSet(s, api, self);
    for (let qs of self.sets()) {
      if (qs.id === s.id) {
        return self.sets.replace(qs, newqs);
      }
    }
    self.sets.push(newqs);
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
  self.selected = ko.observable(false);
  self.checkFraction = ko.computed(function() {
    let ss = self.sets();
    let numsel = (self.selected()) ? 0.1 : 0;
    if (ss.length === 0) {
      return numsel;
    }
    for (let qs of ss) {
      if (qs.selected()) {
        numsel++;
      }
    }
    return numsel / ss.length;
  });
  self.pct_complete = ko.computed(function() {
    return Math.round(100 * (self.count() - self.remaining())/(self.count())) + '%';
  });
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
