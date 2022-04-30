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
  self.start = ko.observable((data.start !== null) ? timeAgo(data.start) + " ago" : null);
  self.end = ko.observable(data.end || null);
  self._result = ko.observable(data.result || null);
  self.result = ko.computed(function() {
    let result = self._result();
    if (result !== null && result !== undefined) {
      return result;
    }
    return "started";
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
    let start = self.start();
    let end = self.end();
    if (start === null || end === null) {
      return null;
    }
    return timeAgo(start, end);
  });
}

try {
  module.exports = CPQueueItem;
} catch {}
