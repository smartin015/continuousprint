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
  CP_STATS_DIMENSIONS={};
}

// Computes aggregate statistics of time, filament, counts etc.
function CPStats(jobs, stats_dimensions=CP_STATS_DIMENSIONS) {
  var self = this;

  const Stat = {
    COUNT: 0,
    TIME: 1,
    MASS: 2,
  };

  self.header = [
    {legend: 'Total items', title: null},
    {legend: 'Total time', title: "Uses Octoprint's file analysis estimate; may be inaccurate"},
    {legend: 'Total mass', title: "Mass is calculated using active spool(s) in SpoolManager"}
  ];

  self._safeParse = function(v) {
    v = parseInt(v, 10);
    return (isNaN(v)) ? 0 : v;
  };

  self._appendCount = function(r, d) {
    for (let dim of Object.keys(stats_dimensions)) {
      r[Stat.COUNT][dim] += d[dim];
    }
  };

  self._appendTime = function(r, d) {
    if (d.ept === null || d.ept === undefined) {
      r[Stat.TIME].error += 1;
      return;
    }
    for (let dim of Object.keys(stats_dimensions)) {
      r[Stat.COUNT][dim] += d[dim] * d.ept;
    }
  };

  self._appendMass = function(r, d) {
    if (d.len === null || d.len === undefined || d.len.length === 0) {
      r[Stat.MASS].error += 1;
      return;
    }
    let mass = 0;
    for (let i = 0; i < d.len.length; i++) {
      mass += d.linmasses[i] * d.len[i];
    }
    if (isNaN(mass)) {
      r[Stat.MASS].error += 1;
      return;
    }
    for (let dim of Object.keys(stats_dimensions)) {
      r[Stat.MASS][dim] += d[dim] * mass;
    }
  };

  self.values = ko.computed(function() {
    r = Array(Object.keys(Stat).length);
    for (let i = 0; i < Object.keys(Stat).length; i++) {
      r[i] = {error:0};
      for (let d of Object.keys(stats_dimensions)) {
        r[i][d] = 0;
      }
    }
    for (let j of jobs()) {
      let lm = j.getMaterialLinearMasses();
      for (let qs of j.sets()) {
        if (!qs.profile_matches()) {
          continue;
        }
        let meta = qs.metadata;
        let d = {
          remaining: self._safeParse(qs.remaining()),
          total: self._safeParse(qs.length_remaining()),
          count: self._safeParse(qs.count()),
          completed: self._safeParse(qs.completed()),
          ept: meta && meta.estimatedPrintTime,
          len: meta && meta.filamentLengths,
          linmasses: lm,
        };
        self._appendCount(r, d);
        self._appendTime(r, d);
        self._appendMass(r, d);
      }
    }
    return r;
  });

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

  self.values_humanized = ko.computed(function() {
    let r = self.values();
    console.log("values() returned", r);
    for (let i=0; i < r.length; i++) {
      r[i] = { ...self.header[i], ...r[i]};
    }
    for (let k of Object.keys(stats_dimensions)) {
      r[Stat.COUNT][k] = self.humanize(r[0][k]);
      r[Stat.TIME][k] = self.humanTime(r[1][k]);
      r[Stat.MASS][k] = self.humanize(r[2][k], 'g');
    }
    // Assign error texts
    r[Stat.COUNT].error = '';
    r[Stat.TIME].error = (r[1].error > 0) ? `${r[1].error} sets missing time estimates` : '';
    r[Stat.MASS].error = (r[2].error > 0) ? `${r[1].error} errors calculating mass` : '';

    // TODO
    // Hide mass details if linmasses is empty (implies SpoolManager not set up)
    //if (linmasses().length === 0) {
    //  r.splice(2,1);
    //}
    return r;
  });
}

try {
  module.exports = CPStats;
} catch {}
