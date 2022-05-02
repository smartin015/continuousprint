/*
 * View model for OctoPrint-Print-Queue
 *
 * Contributors: Michael New, Scott Martin
 * License: AGPLv3
 */

if (typeof ko === "undefined" || ko === null) {
  ko = require('knockout');
}

// QueueSets are a sequence of the same queue item repated a number of times.
// This is an abstraction on top of the actual queue maintained by the server.
function CPQueueSet(data, api, job) {
  var self = this;
  self.id = data.id;
  self.job = job;

  self.sd = ko.observable(data.sd);
  self.name = ko.observable(data.path);
  self.count = ko.observable(data.count);
  self.countInput = ko.observable(data.count);
  self.length = ko.computed(function() {
    return job.count() * self.count();
  });
  self.remaining = ko.observable(data.remaining);
  self.length_completed = ko.computed(function() {
    let c = self.count()
    let job_completed = (job.count() - job.remaining());
    console.log(c, job_completed, self.remaining());
    if (self.remaining() == 0) {
      return c*job_completed;
    }
    return c*job_completed + (c - self.remaining());
  });
  self.selected = ko.observable(false);
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
    for (let i of data.materials) {
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
    return Math.max(1, Math.round(100 * (self.count() - self.remaining())/(self.count()))) + '%';
  });
  self.pct_active = ko.computed(function() {
    return Math.max(1, Math.round(100 / self.count())) + '%';
  });

  // ==== Mutation methods ====

  self.set_count = function(count) {
    api.update(api.SET, {id: self.id, count}, (result) => {
      self.count(result.count);
      self.countInput(result.count);
      self.remaining(result.remaining); // Adjusted when count is mutated
      self.job.remaining(result.job_remaining);
    });
  }
  self.set_material = function(t, v) {
    throw Error("TODO");
    /*
    const items = self.items();
    for (let i of items) {
      let mats = i.materials();
      while (t >= mats.length) {
        mats.push(null);
      }
      mats[t] = v;
      i.materials(mats);
    }
    self.items(items);
    */
  }
}

try {
  module.exports = CPQueueSet;
} catch {}
