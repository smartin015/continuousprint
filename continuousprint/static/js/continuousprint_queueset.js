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
function CPQueueSet(items) {
  var self = this;
  self._n = items[0].name; // Used for easier inspection in console
  self._len = items.length;

  self.items = ko.observableArray([]);
  for (let i of items) {
    self.items.push(new CPQueueItem(i));
  }
  self.changed = ko.computed(function() {
    for (let item of self.items()) {
      if (item.changed()) {
        return true;
      }
    }
    return false;
  });
  
  self._textColorFromBackground = function(rrggbb) {
    // https://stackoverflow.com/a/12043228
    var rgb = parseInt(rrggbb, 16);   // convert rrggbb to decimal
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
    let mats = self.items()[0];
    if (mats !== undefined) {
      mats = mats.materials()
    }
    for (let i of mats) {
      let split = i.split("_");
      let bg = split[1];
      result.push({
        shortName: self._materialShortName(split[0]),
        color: self._textColorFromBackground(bg), 
        bgColor: "#" + bg,
        key: i,
      });
    }
    return result;
  });
  self.length = ko.computed(function() {return self.items().length;});
  self.name = ko.computed(function() {return self.items()[0].name;});
  self.count = ko.computed(function() {
    let len = self.length();
    let nruns = (len > 0) ? (self.items()[len-1].run() || 0) : 0;
    return Math.floor(self.length() / (nruns+1));
  });
  self.items_completed = ko.computed(function() {
    let i = 0;
    for (let item of self.items()) {
      if (item.end_ts() !== null) {
        i++;
      }
    }
    return i;
  });
  self.runs_completed = ko.computed(function() {
    return Math.floor(self.items_completed() / (self.count() || 1));
  });
  self.progress = ko.computed(function() {
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
  });
  self.active = ko.computed(function() {
    for (let item of self.items()) {
      if (item.start_ts === null && item.end_ts !== null) {
        return true;
      }
    }
    return false;
  });

  self._tmpl = {...self.items()[0].as_object(), start_ts: null, end_ts: null, result: null, retries: 0};
  self.set_count = function(v) {
    let items = self.items();
    let cnt = self.count();
    let runs = items[items.length-1].run() + 1;
    let diff = v - cnt;
    if (diff > 0) {
      // Splice in `diff` amount of new items at the end of each run
      for (let run = 0; run < runs; run++) {
        let base = run * v + cnt; // Position of next insert
        for (let i = 0; i < diff; i++) {
          items.splice(base, 0, new CPQueueItem({...self._tmpl, run}));
        }
      }
      self.items(items);
    } else if (diff < 0) {
      items.splice(v*runs);
      // We must re-specify the runs since we're truncating from the end
      for (let run = 0; run < runs; run++) {
        for (let i = 0; i < v; i++) {
          items[run*v + i].run(run);
        }
      }
      self.items(items);
    }
    // Do nothing if equal
  }
  self.set_runs = function(v) {
    let cnt = self.count();
    let items = self.items();
    let runs = items[items.length-1].run() + 1;
    if (v < runs) {
      items.splice(v*cnt);
      self.items(items);
    } else if (v > runs) {
      for (let run = runs; run < v; run++) {
        for (let j = 0; j < cnt; j++) {
          items.push(new CPQueueItem({...self._tmpl, run}));
        }
      }
      self.items(items);
    }
  }
  self.set_material = function(t, v) {
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
  }
}

try {
  module.exports = CPQueueSet;
} catch {}
