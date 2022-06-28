/*
 * View model for OctoPrint-Print-Queue
 *
 * Contributors: Michael New, Scott Martin
 * License: AGPLv3
 */

if (typeof ko === "undefined" || ko === null) {
  ko = require('knockout');
}

function CPHistoryDivider(queue, job, set) {
    var self = this;
    self.divider = true;
    if (job === '') {
          job = 'untitled job';
        }
    self.queue_name = queue;
    self.job_name = job;
    if (self.job_name.length > 24) {
      self.job_name = self.job_name.substr(0, 13) + '..';
    }
    self.set_path = set.split("/").pop();
    if (self.set_path.length > 36) {
      self.set_path = self.set_path.substr(0, 13) + '..';
    }
}

// see QueueItem in print_queue.py for matching python object
function CPHistoryRow(data) {
  var self = this;
  self.start = ko.observable(data.start || null);
  self.end = ko.observable(data.end || null);
  self._result = ko.observable(data.result || null);
  self.result = ko.computed(function() {
    let result = self._result();
    if (result !== null && result !== undefined) {
      return result;
    }
    return "in progress";
  });

  if (data.movie_path && data.thumb_path) {
    let movie_base = data.movie_path.split("/").pop();
    let thumb_base = data.thumb_path.split("/").pop();
    self.movieURL = ko.observable("/downloads/timelapse/" + encodeURIComponent(movie_base));
    self.thumbURL = ko.observable("/downloads/timelapse/" + encodeURIComponent(thumb_base));
  } else {
    self.movieURL = ko.observable();
    self.thumbURL = ko.observable();
  }

  self.icon_class = ko.computed(function() {
    let r = self.result();
    switch (r) {
      case "in progress":
        return "fas fa-cube";
      case "aborted":
        return "fa fa-exclamation-triangle";
      case "success":
        return "fas fa-check";
      default:
        return "";
    }
  });

  self.showTimelapse = function() {
    // Hook into the exiting TimelapseViewModel so we don't have to write our own preview code.
    ko.dataFor($("#timelapse").get(0)).showTimelapsePreview({url: self.movieURL()});
  }

  function pluralize(num, unit) {
    num = Math.round(num);
    if (num === 1) {
      return `${num} ${unit}`;
    }
    return `${num} ${unit}s`;
  }
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
           return pluralize(elapsed/sPerMinute, 'minute');
      }
      else if (elapsed < sPerDay) {
           return pluralize(elapsed/sPerHour, 'hour');
      }
      else if (elapsed < sPerMonth) {
          return pluralize(elapsed/sPerDay, 'day');
      }
      else {
          return pluralize(elapsed/sPerMonth, 'month');
      }
  }
  self.startedDate = ko.computed(function() {
    let start = self.start();
    if (start === null) {
      return null;
    }
    return (new Date(start*1000)).toLocaleDateString('sv');
  })
  self.startedTime = ko.computed(function() {
    let start = self.start();
    if (start === null) {
      return null;
    }
    return (new Date(start*1000)).toLocaleTimeString();
  })
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
  module.exports = {CPHistoryRow, CPHistoryDivider};
} catch {}
