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

const EVENTS = [
  {event: 'e1'},
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
      AUTOMATION: 'automation',
      QUEUES: 'queues',
      init: jest.fn(),
      get: jest.fn((_, cb) => cb([])),
      edit: jest.fn(),
    },
  ];
}

test('makes are populated', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  expect(v.printer_makes().length).toBeGreaterThan(1); // Not just "Select one"
});

test('models are populated based on selected_make', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  v.selected_make("Test");
  expect(v.printer_models()).toEqual(["-", "Printer"]);
});

test('valid model change updates profile in settings', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  v.selected_make("Test");
  v.selected_model("Printer");
  v.modelChanged();
  expect(v.settings.settings.plugins.continuousprint.cp_printer_profile).toHaveBeenCalledWith("TestPrinter");
});

test('loadScriptsFromProfile', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  v.selected_make("Test");
  v.selected_model("Printer");
  v.loadScriptsFromProfile();
  expect(v.scripts()[0].name()).toMatch(/^Clear Bed.*/);
  expect(v.scripts()[1].name()).toMatch(/^Finish.*/);
});

test('"auto" address allows submit', () =>{
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  v.queues.push({name: 'asdf', addr: 'auto'});
  v.onSettingsBeforeSave();
  expect(v.settings.exchanging()).toEqual(false);
});

test('invalid address blocks submit', () =>{
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  v.queues.push({name: 'asdf', addr: 'something_invalid'});
  v.onSettingsBeforeSave();
  expect(v.settings.exchanging()).toEqual(true);
});

test('valid address allows submit', () =>{
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  v.queues.push({name: 'asdf', addr: '192.168.1.69:13337'});
  v.onSettingsBeforeSave();
  expect(v.settings.exchanging()).toEqual(false);
});

test('invalid model change is ignored', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
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
    } else if (typ === m[2].AUTOMATION) {
      cb({
        scripts: {a: 'g1', b: 'g2'},
        events: {e1: ['a']},
      });
    }
  };
  let v = new VM.CPSettingsViewModel(m, PROFILES, SCRIPTS, EVENTS);
  v.onSettingsShown();
  expect(v.queues().length).toBe(2); // Archive excluded
});
test('dirty exit commits queues', () => {
  let m = mocks();
  m[2].get = function (typ, cb) {
    console.log(typ);
    if (typ === m[2].QUEUES) {
      cb([]);
    } else if (typ === m[2].AUTOMATION) {
      cb({
        scripts: {},
        events: {},
      });
    }
  };
  let v = new VM.CPSettingsViewModel(m, PROFILES, SCRIPTS, EVENTS);
  v.onSettingsShown();
  v.queues.push({name: 'asdf', addr: ''});
  v.onSettingsBeforeSave();
  expect(v.api.edit).toHaveBeenCalledWith(m[2].QUEUES, expect.anything(), expect.anything());
});
test('non-dirty exit does not call commitQueues', () => {
  let m = mocks();
  m[2].get = function (typ, cb) {
    console.log(typ);
    if (typ === m[2].QUEUES) {
      cb([]);
    } else if (typ === m[2].AUTOMATION) {
      cb({
        scripts: {},
        events: {},
      });
    }
  };
  let v = new VM.CPSettingsViewModel(m, PROFILES, SCRIPTS, EVENTS);
  v.onSettingsShown();
  v.onSettingsBeforeSave();
  expect(v.api.edit).not.toHaveBeenCalled();
});
test('addScript, rmScript', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  v.newScript();
  expect(v.scripts().length).toEqual(1);

  // rmScript also removes the script from any events
  v.events([{actions: ko.observableArray([v.scripts()[0]])}]);
  v.rmScript(v.scripts()[0]);
  expect(v.scripts().length).toEqual(0);
  expect(v.events()[0].actions().length).toEqual(0);
});
test('addAction, rmAction', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  let e = {"actions": ko.observableArray([])};
  let a = "foo";
  v.addAction(e, a);
  expect(e.actions()[0]).toEqual(a);
  v.rmAction(e, a);
  expect(e.actions().length).toEqual(0);
});
