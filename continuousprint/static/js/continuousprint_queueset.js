/*
 * View model for OctoPrint-Print-Queue
 *
 * Contributors: Michael New, Scott Martin
 * License: AGPLv3
 */

if (typeof ko === "undefined" || ko === null) {
  ko = require('knockout');
}
if (typeof CPQueueItem === "undefined" || CPQueueItem === null) {
  CPQueueItem = require('./continuousprint_queueitem');
}

// QueueSets are a sequence of the same queue item repated a number of times.
// This is an abstraction on top of the actual queue maintained by the server.
function CPQueueSet(data, api, job) {
  var self = this;
  self.id = data.id;
  self.job = job;

  let runs = [];
  for (let r of data.runs) {
    runs.push(new CPQueueItem(r));
  }
  self.sd = ko.observable(data.sd);
  self.runs = ko.observable(runs);
  self.name = ko.observable(data.path);
  self.length = ko.observable(data.count);
  self.count = ko.observable(data.count);
  self.selected = ko.observable(false);
  self.runs_completed = ko.computed(function() {
    let n = 0;
    for (let r of self.runs()) {
      if (r.status == 'success') {
        n++;
      }
    }
    return n/self.count();
  });

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
  self.progress = ko.computed(function() {
    /*
    let progress = [];
    let curNum = 0;
    let curResult = self.items()[0].result();
    let pushProgress = function() {
      progress.push({
        pct: Math.round(100 * curNum / self._len),
        order: {"pending": 3, "success": 1}[curResult] || 2,
        result: curResult,
      });
    }
    for (let item of self.items()) {
      let res = item.result();
      if (res !== curResult) {
        pushProgress();
        curNum = 0;
        curResult = res;
      }
      curNum++;
    }
    pushProgress();
    return progress;
    */
    return [];
  });
  self.active = ko.computed(function() {
    /*
    for (let item of self.items()) {
      if (item.start_ts === null && item.end_ts !== null) {
        return true;
      }
    }
    */
    return false;
  });

  // ==== Mutation methods ====

  self.set_count = function(count) {
    api.update(api.SET, {id: self.id, count}, (result) => {
      self.count(result.count);
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
