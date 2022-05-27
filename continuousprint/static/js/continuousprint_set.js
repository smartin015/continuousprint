/*
 * View model for OctoPrint-Print-Queue
 *
 * Contributors: Michael New, Scott Martin
 * License: AGPLv3
 */

if (typeof ko === "undefined" || ko === null) {
  ko = require('knockout');
}

// Sets are a sequence of the same queue item repated a number of times.
// This is an abstraction on top of the actual queue maintained by the server.
function CPSet(data, job, api) {
  var self = this;
  self.id = data.id;
  self.job = job;

  self.sd = ko.observable(data.sd);
  self.path = ko.observable(data.path);
  self.shortName = ko.computed(() => {
    return self.path().split(/[\\/]/).pop();
  });
  self.count = ko.observable(data.count);
  self.remaining = ko.observable((data.remaining !== undefined) ? data.remaining : data.count);
  self.completed = ko.observable(data.count - self.remaining()); // Not computed to allow for edits without changing
  self.mats = ko.observable(data.materials || []);
  self.profiles = ko.observableArray(data.profiles || []);

  self.addProfile = function(_, e) {
    let v = e.target.value;
    if (self.profiles.indexOf(v) === -1) {
      self.profiles.push(v);
    }
    e.target.value = ''; // Reset to empty since user has chosen
  };
  self.rmProfile = function(v, e) {
    self.profiles.remove(v);
  };

  self.as_object = function() {
    return {
      id: self.id,
      sd: self.sd(),
      path: self.path(),
      count: self.count(),
      remaining: self.remaining(),
      materials: self.mats(),
      profiles: self.profiles(),
    };
  }
  self.length = ko.computed(function() {
    return self.job.count() * self.count();
  });
  self.length_completed = ko.computed(function() {
    let job_completed = self.job.completed();
    if (job_completed === self.job.count()) {
      job_completed -= 1; // Prevent double-counting the end of the job
    }
    return self.completed() + self.count()*job_completed;
    return result;
  });
  self.remove = function() {
    api.rm(self.api.SET, {set_ids: [self.id]}, () =>{
      job.sets.remove(self);
    });
  }
  self.expanded = ko.observable(false);
  self._textColorFromBackground = function(rrggbb) {
    // https://stackoverflow.com/a/12043228
    var rgb = parseInt(rrggbb.substr(1), 16);   // convert rrggbb to decimal
    var r = (rgb >> 16) & 0xff;  // extract red
    var g = (rgb >>  8) & 0xff;  // extract green
    var b = (rgb >>  0) & 0xff;  // extract blue
    var luma = 0.2126 * r + 0.7152 * g + 0.0722 * b; // per ITU-R BT.709
    return (luma >= 128) ? "#000000" : "#FFFFFF";
  }
  self._materialShortName = function(m) {
    m = m.trim().toUpperCase();
    if (m === "PETG") {
      return "G";
    }
    return m[0];
  }
  self.materials = ko.computed(function() {
    let result = [];
    for (let i of self.mats()) {
      if (i === null || i === "") {
        result.push({
          title: "any",
          shortName: " ",
          color: "transparent",
          bgColor: "transparent",
          key: i,
        });
        continue;
      }
      let split = i.split("_");
      let bg = split[2] || "";
      result.push({
        title: i.replaceAll("_", " "),
        shortName: self._materialShortName(split[0]),
        color: self._textColorFromBackground(bg),
        bgColor: bg,
        key: i,
      });
    }
    return result;
  });
  self.pct_complete = ko.computed(function() {
    return Math.max(1, Math.round(100 * self.completed()/self.count())) + '%';
  });
  self.pct_active = ko.computed(function() {
    return Math.max(1, Math.round(100 / self.count())) + '%';
  });

  // ==== Mutation methods ====

  self.set_material = function(t, v) {
    let mats = self.mats();
    while (t >= mats.length) {
      mats.push('');
    }
    mats[t] = v;
    self.mats(mats);
  }
}

try {
  module.exports = CPSet;
} catch {}