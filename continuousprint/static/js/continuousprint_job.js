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
function CPJob(obj, peers, api, profile) {
  if (api === undefined) {
    throw Error("API must be provided when creating CPJob");
  }
  var self = this;

  obj = {...{sets: [], name: "", draft: false, count: 1, id: -1}, ...obj};
  if (obj.remaining === undefined) {
    obj.remaining = obj.count;
  }
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
  self.active = ko.observable(obj.active || false);
  self.remaining = ko.observable((obj.remaining !== undefined) ? obj.remaining : obj.count);
  self.completed = ko.observable(obj.count - self.remaining());
  self.selected = ko.observable(obj.selected || false);

  self.sets = ko.observableArray([]);
  for (let s of obj.sets) {
    self.sets.push(new CPSet(s, self, api, profile));
  }

  self._update = function(result) {
    self.draft(result.draft);
    self.count(result.count); // Adjusted when remaining is mutated
    self.remaining(result.remaining);
    self.completed(result.count - result.remaining); // Adjusted when remaining is mutated
    self.id(result.id); // May change if no id to start with
    self._name(result.name);
    let cpss = [];
    if (result.sets !== undefined) {
      for (let qsd of result.sets) {
        cpss.push(new CPSet(qsd, self, api, profile));
      }
    }
    self.sets(cpss);
  };

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
    api.edit(api.JOB, {queue: obj.queue, id: self.id(), draft: true}, () => {
      self.draft(true);
    });
  }
  self.onSetModified = function(s) {
    let newqs = new CPSet(s, self, api, profile);
    for (let qs of self.sets()) {
      if (qs.id === s.id) {
        return self.sets.replace(qs, newqs);
      }
    }
    self.sets.push(newqs);
 }
  self.editCancel = function() {
    api.edit(api.JOB, {queue: obj.queue, id: self.id(), draft: false}, self._update);
  }
  self.onBlur = function(vm, e) {
    let cl = e.target.classList;
    let v = parseInt(e.target.value, 10);
    if (isNaN(v)) {
      return;
    }
    vm.count(vm.completed() + v);
  }
  self.editEnd = function() {
    let data = self.as_object();
    data.draft = false;
    data.queue = obj.queue;
    api.edit(api.JOB, data, self._update);
  }

  self._safeParse = function(v) {
    v = parseInt(v, 10);
    if (isNaN(v)) {
      return 0;
    }
    return v;
  }

  self.totals = ko.computed(function() {
    let r = {count: 0, completed: 0, remaining: 0, total: 0};
    for (let qs of self.sets()) {
      r.remaining += self._safeParse(qs.remaining());
      r.total += self._safeParse(qs.length_remaining());
      r.count += self._safeParse(qs.count());
      r.completed += self._safeParse(qs.completed());
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
  self.onChecked = function(sel) {
    if (self.draft() || self.acquiredBy()) {
      return;
    }
    if (sel !== undefined) {
      self.selected(sel);
    } else {
      self.selected(!self.selected());
    }
  }
  self.onEnter = function(d, e) {
    e.keyCode === 13 && self.editEnd();
    return true;
  }
}

try {
  module.exports = CPJob;
} catch {}
