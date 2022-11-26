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
function CPJob(obj, peers, api, profile, materials) {
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

  if (obj.acquired_by_) {
    let peer = peers[obj.acquired_by_];
    if (peer !== undefined) {
      self.acquiredBy = ko.observable(`${peer.name} (${peer.profile.name})`);
    } else {
      self.acquiredBy = ko.observable(obj.acquired_by_)
    }
  } else if (obj.acquired) {
    self.acquiredBy = ko.observable('local');
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


  self.humanize = function(num, unit="") {
    // Humanizes numbers by condensing and adding units
    let v = '';
    if (num < 1000) {
      v = (num % 1 === 0) ? num : num.toFixed(1);
    } else if (num < 100000) {
      let k = (num/1000);
      v = ((k % 1 === 0) ? k : k.toFixed(1)) + 'k';
    }
    return v + unit;
  };

  self.humanTime = function(s) {
    // Humanizes time values; parameter is seconds
    if (s < 60) {
      return Math.round(s) + 's';
    } else if (s < 3600) {
      return Math.round(s/60) + 'm';
    } else if (s < 86400) {
      let h = s/3600;
      return ((h % 1 === 0) ? h : h.toFixed(1)) + 'h';
    } else {
      let d = s/86400;
      return ((d % 1 === 0) ? d : d.toFixed(1)) + 'd';
    }
  };

  self.getMaterialLinearMasses = ko.computed(function() {
    let result = [];
    for (let m of materials()) {
      // Convert density from g/cm^3 to g/mm^3, then multiply by
      // filament cross-sectional area (mm^2) to get grams per linear mm
      result.push(
        (m.density / 1000) *
        ((m.diameter / 2)*(m.diameter / 2)*Math.PI)
      );
    }

    // Values are in g/mm
    // TODO fetch from profiles and printer nozzle dia
    let g_per_mm3 = (1.25)/1000;
    let filament_mm2 = (1.75/2)*(1.75/2)*3.14159;
    return [g_per_mm3 *  filament_mm2];
  });

  self.totals = ko.computed(function() {
    let r = [
      {legend: 'Total items printed', title: ""},
      {legend: 'Total time', title: "Uses Octoprint's file analysis estimate; may be inaccurate"},
      {legend: 'Total mass', title: "Mass is calculated using active spool(s) in SpoolManager"},
    ];
    for (let t of r) {
      t.count = 0;
      t.completed = 0;
      t.remaining = 0;
      t.total = 0;
      t.error = 0;
    }

    let linmasses = self.getMaterialLinearMasses();

    for (let qs of self.sets()) {
      if (!qs.profile_matches) {
        continue;
      }

      let rem = self._safeParse(qs.remaining())
      let tot = self._safeParse(qs.length_remaining());
      let count = self._safeParse(qs.count());
      let cplt = self._safeParse(qs.completed());

      let meta = qs.metadata;
      let ept = meta && meta.estimatedPrintTime
      let len = meta && meta.filamentLengths;

      // Update print count totals
      r[0].remaining += rem;
      r[0].total += tot;
      r[0].count += count;
      r[0].completed += cplt;

      if (ept === null || ept === undefined) {
        r[1].error += 1;
      } else {
        r[1].remaining += rem * ept;
        r[1].total += tot * ept
        r[1].count += count * ept;
        r[1].completed += cplt * ept;
      }

      if (len === null || len === undefined || len.length === 0) {
        r[2].error += 1;
      } else {
        let mass = 0;
        for (let i = 0; i < len.length; i++) {
          mass += linmasses[i] * len[i];
        }

        if (!isNaN(mass)) {
          r[2].remaining += rem * mass;
          r[2].total += tot * mass;
          r[2].count += count * mass;
          r[2].completed += cplt * mass;
        } else {
          r[2].error += 1;
        }
      }

    }
    // Assign error texts
    r[0].error = '';
    r[1].error = (r[1].error > 0) ? `${r[1].error} sets missing time estimates` : '';
    r[2].error = (r[2].error > 0) ? `${r[1].error} errors calculating mass` : '';

    for (let k of ['remaining', 'total', 'count', 'completed']) {
      r[0][k] = self.humanize(r[0][k]);
      r[1][k] = self.humanTime(r[1][k]);
      r[2][k] = self.humanize(r[2][k], 'g');
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
