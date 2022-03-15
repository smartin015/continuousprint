/*
 * View model for OctoPrint-Print-Queue
 *
 * Contributors: Michael New, Scott Martin
 * License: AGPLv3
 */

if (typeof ko === "undefined" || ko === null) {
  ko = require('knockout');
}

// see QueueItem in print_queue.py for matching python object
function CPQueueItem(data) {
  var self = this;
  self.name = data.name;
  self.path = data.path;
  self.sd = data.sd;
  self.job = ko.observable(data.job);
  self.run = ko.observable(data.run);
  self.changed = ko.observable(data.changed || false);
  self.start_ts = ko.observable(data.start_ts || null);
  self.end_ts = ko.observable(data.end_ts || null);
  self._retries = ko.observable(data.retries);
  self.retries = ko.computed(() => ((self.start_ts() !== null) ? self._retries() : null));
  self._result = ko.observable(data.result || null);
  self.result = ko.computed(function() {
    let result = self._result();
    if (result !== null && result !== undefined) {
      return result;
    }
    if (self.start_ts() === null) {
      return "pending";
    }
    if (self.start_ts() !== null && self.end_ts() === null) {
      return "started";
    }
  });

  // Inspired by answers at
  // https://stackoverflow.com/questions/6108819/javascript-timestamp-to-relative-time
  function timeAgo(previous, current=null) {
      var sPerMinute = 60;
      var sPerHour = sPerMinute * 60;
      var sPerDay = sPerHour * 24;
      var sPerMonth = sPerDay * 30;
      if (current === null) {
        current = (new Date()).getTime()/1000;
      }
      var elapsed = current - previous;
      if (elapsed < sPerHour) {
           return Math.round(elapsed/sPerMinute) + ' minutes';
      }
      else if (elapsed < sPerDay ) {
           return Math.round(elapsed/sPerHour) + ' hours';
      }
      else if (elapsed < sPerMonth) {
          return Math.round(elapsed/sPerDay) + ' days';
      }
      else {
          return Math.round(elapsed/sPerMonth) + ' months';
      }
  }

  self.duration = ko.computed(function() {
    let start = self.start_ts();
    let end = self.end_ts();
    if (start === null || end === null) {
      return null;
    }
    return timeAgo(start, end);
  });
  self.requeue = function() {
    self._result(null);
    self.start_ts(null);
    self.end_ts(null);
    self._retries(0);
  }
  self.as_object = function() {
    return {
      name: self.name,
      path: self.path,
      sd: self.sd,
      job: self.job(),
      run: self.run(),
      start_ts: self.start_ts(),
      end_ts: self.end_ts(),
      result: self._result(), // Don't propagate default strings
      retries: self._retries(), // ditto
    };
  }
}

try {
  module.exports = CPQueueItem;
} catch {}
