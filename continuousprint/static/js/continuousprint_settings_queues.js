if (typeof log === "undefined" || log === null) {
  // In the testing environment, dependencies must be manually imported
  ko = require('knockout');
}

function CPSettingsQueuesViewModel(api) {
  var self = this;
  self.api = api;
  self.queues = ko.observableArray([]);
  self.queues_fingerprint = null;
  self.rmQueue = function(q) {
    self.queues.remove(q);
  }
  self.queueChanged = function() {
    self.queues.valueHasMutated();
  }
  self.onSettingsShown = function() {
    self.loadQueues();
  };

  // Called automatically by SettingsViewModel
  self.onSettingsBeforeSave = function() {
    let queues = self.queues();
    if (JSON.stringify(queues) !== self.queue_fingerprint) {
      // Sadly it appears flask doesn't have good parsing of nested POST structures,
      // So we pass it a JSON string instead.
      self.api.edit(self.api.QUEUES, queues, () => {
        // Editing queues causes a UI refresh to the main viewmodel
      });
    }
  };

  self.loadQueues = function() {
    self.api.get(self.api.QUEUES, (data) => {
      self.queues(data);
    });
  };
}


try {
module.exports = {
  CPSettingsQueuesViewModel,
};
} catch {}
