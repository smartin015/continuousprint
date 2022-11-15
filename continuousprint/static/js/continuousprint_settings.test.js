// Import must happen after declaring constants
const VM = require('./continuousprint_settings');

const PROFILES = [
  {
    name: 'Generic',
    make: 'Generic',
    model: 'Generic',
    defaults: {
      clearBed: 'script1',
      finished: 'script2',
    },
  },
  {
    name: 'TestPrinter',
    make: 'Test',
    model: 'Printer',
    defaults: {
      clearBed: 'script1',
      finished: 'script2',
    },
  },
]

const SCRIPTS = [
  {
    name: 'script1',
    gcode: 'test1',
  },
  {
    name: 'script2',
    gcode: 'test2',
  },
];


function mocks() {
  return [
    {
      settings: {
        plugins: {
          continuousprint: {
            cp_bed_clearing_script: jest.fn(),
            cp_queue_finished_script: jest.fn(),
            cp_printer_profile: jest.fn(),
          },
        },
      },
      exchanging: () => false,
    },
    {
      onServerDisconnect: jest.fn(),
      onServerConnect: jest.fn(),
    },
    {
      SCRIPTS: 'scripts',
      QUEUES: 'queues',
      init: jest.fn(),
      get: jest.fn((_, cb) => cb([])),
      edit: jest.fn(),
    },
  ];
}

test('makes are populated', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS);
  expect(v.printer_makes().length).toBeGreaterThan(1); // Not just "Select one"
});

test('models are populated based on selected_make', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS);
  v.selected_make("Test");
  expect(v.printer_models()).toEqual(["-", "Printer"]);
});

test('valid model change updates settings scripts', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS);
  v.selected_make("Test");
  v.selected_model("Printer");
  v.modelChanged();
  expect(v.settings.settings.plugins.continuousprint.cp_bed_clearing_script).toHaveBeenCalledWith("test1");
  expect(v.settings.settings.plugins.continuousprint.cp_queue_finished_script).toHaveBeenCalledWith("test2");
});

test('"auto" address allows submit', () =>{
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS);
  v.queues.push({name: 'asdf', addr: 'auto'});
  v.onSettingsBeforeSave();
  expect(v.settings.exchanging()).toEqual(false);
});

test('invalid address blocks submit', () =>{
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS);
  v.queues.push({name: 'asdf', addr: 'something_invalid'});
  v.onSettingsBeforeSave();
  expect(v.settings.exchanging()).toEqual(true);
});

test('valid address allows submit', () =>{
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS);
  v.queues.push({name: 'asdf', addr: '192.168.1.69:13337'});
  v.onSettingsBeforeSave();
  expect(v.settings.exchanging()).toEqual(false);
});

test('invalid model change is ignored', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS);
  v.modelChanged();
  expect(v.settings.settings.plugins.continuousprint.cp_bed_clearing_script).not.toHaveBeenCalled();
  expect(v.settings.settings.plugins.continuousprint.cp_queue_finished_script).not.toHaveBeenCalled();
});

test('load queues and scripts on settings view shown', () => {
  m = mocks();
  m[2].get = function (typ, cb) {
    console.log(typ);
    if (typ === m[2].QUEUES) {
      cb([
        {name: "archive"},
        {name: "local", addr: "", strategy:"IN_ORDER"},
        {name: "LAN", addr: "a:1", strategy:"IN_ORDER"},
      ]);
    } else if (typ === m[2].SCRIPTS) {
      cb({
        scripts: {a: 'g1', b: 'g2'},
        events: {e1: ['a']},
        allEvents: ['e1', 'e2'],
      });
    }
  };
  let v = new VM.CPSettingsViewModel(m, PROFILES, SCRIPTS);
  v.onSettingsShown();
  expect(v.queues().length).toBe(2); // Archive excluded
});
test.only('dirty exit commits queues', () => {
  let m = mocks();
  let v = new VM.CPSettingsViewModel(m, PROFILES, SCRIPTS);
  v.queues.push({name: 'asdf', addr: ''});
  v.onSettingsBeforeSave();
  expect(v.api.edit).toHaveBeenCalledWith(m[2].QUEUES, expect.any());
});
test('non-dirty exit does not call commitQueues', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS);
  v.onSettingsBeforeSave();
  expect(v.api.edit).not.toHaveBeenCalled();
});
test.todo('add script button');
test.todo('add action handling');
