// Import must happen after declaring constants
const VM = require('./continuousprint_settings_queues');

function mocks() {
  return {
    AUTOMATION: 'automation',
    QUEUES: 'queues',
    get: jest.fn((_, cb) => cb([])),
    edit: jest.fn(),
  };
}

test('load queues on settings view shown', () => {
  m = mocks();
  m.get = function (typ, cb) {
    if (typ === m.QUEUES) {
      cb([
        {name: "archive"},
        {name: "local", addr: "", strategy:"IN_ORDER"},
        {name: "LAN", addr: "a:1", strategy:"IN_ORDER"},
      ]);
    }
  };
  let v = new VM.CPSettingsQueuesViewModel(m);
  v.onSettingsShown();
  expect(v.queues().length).toBe(2); // Archive excluded
});
test('dirty exit commits queues', () => {
  let m = mocks();
  m.get = function (typ, cb) {
    if (typ === m.QUEUES) {
      cb([]);
    }
  };
  let v = new VM.CPSettingsQueuesViewModel(m);
  v.onSettingsShown();
  v.queues.push({name: 'asdf', addr: ''});
  v.onSettingsBeforeSave();
  expect(v.api.edit).toHaveBeenCalledWith(m.QUEUES, expect.anything(), expect.anything());
});
test('non-dirty exit does not commit queues', () => {
  let m = mocks();
  m.get = function (typ, cb) {
    if (typ === m.QUEUES) {
      cb([]);
    }
  };
  let v = new VM.CPSettingsQueuesViewModel(m);
  v.onSettingsShown();
  v.onSettingsBeforeSave();
  expect(v.api.edit).not.toHaveBeenCalled();
});
