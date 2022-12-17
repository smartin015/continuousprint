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

function mock_oprint() {
  return {
    slicing: {
      listAllSlicersAndProfiles: jest.fn(),
    },
  };
}

function mocks() {
  return [
    {
      settings: {
        plugins: {
          continuousprint: {
            cp_bed_clearing_script: jest.fn(),
            cp_queue_finished_script: jest.fn(),
            cp_printer_profile: jest.fn(),
            cp_slicer: jest.fn(),
            cp_slicer_profile: jest.fn(),
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
    if (typ === m[2].QUEUES) {
      cb([
        {name: "archive"},
        {name: "local", addr: "", strategy:"IN_ORDER"},
        {name: "LAN", addr: "a:1", strategy:"IN_ORDER"},
      ]);
    } else if (typ === m[2].AUTOMATION) {
      cb({
        scripts: {a: 'g1', b: 'g2'},
        preprocessors: {c: 'p1'},
        events: {e1: [{script: 'a', preprocessor: 'c'}]},
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
    if (typ === m[2].QUEUES) {
      cb([]);
    } else if (typ === m[2].AUTOMATION) {
      cb({
        scripts: {},
        preprocessors: {},
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
    if (typ === m[2].QUEUES) {
      cb([]);
    } else if (typ === m[2].AUTOMATION) {
      cb({
        scripts: {},
        preprocessors: {},
        events: {},
      });
    }
  };
  let v = new VM.CPSettingsViewModel(m, PROFILES, SCRIPTS, EVENTS);
  v.onSettingsShown();
  v.onSettingsBeforeSave();
  expect(v.api.edit).not.toHaveBeenCalled();
});

test('addPreprocessor, rmPreprocessor', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  let p = v.addPreprocessor();
  expect(v.preprocessors().length).toEqual(1);

  // rmPreprocessor also removes from any events, without deleting the action
  v.events([{
    actions: ko.observableArray([
      {script: {name: ko.observable('testscript')}, preprocessor: ko.observable(p)},
    ])
  }]);
  v.rmPreprocessor(p);
  expect(v.preprocessors().length).toEqual(0);
  expect(v.events()[0].actions()[0].preprocessor()).toEqual(null);

});

test('addScript, rmScript', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  v.addScript();
  expect(v.scripts().length).toEqual(1);

  // rmScript also removes the script from any events
  v.events([{
    actions: ko.observableArray([
      {script: v.scripts()[0], preprocessor: ko.observable(null)},
    ])
  }]);
  v.rmScript(v.scripts()[0]);
  expect(v.scripts().length).toEqual(0);
  expect(v.events()[0].actions().length).toEqual(0);
});

test('addAction, rmAction', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  let e = {"actions": ko.observableArray([])};
  let a = {script:"foo"};
  v.addAction(e, a);
  expect(e.actions()[0].script).toEqual(a);
  v.rmAction(e, e.actions()[0]);
  expect(e.actions().length).toEqual(0);
});

test('script or preprocessor naming collision blocks submit', () =>{
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  v.addScript();
  v.addScript();
  expect(v.settings.exchanging()).toEqual(true);
});

test('registrations of script / preprocessor are tracked', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  let s = v.addScript();
  expect(s.registrations()).toEqual([]);
  v.events([{
    display: "testevent",
    actions: ko.observableArray([
      {script: s, preprocessor: ko.observable(null)},
    ])
  }]);
  expect(s.registrations()).toEqual(["testevent"]);
});
test('loadScriptFromFile, loadPreprocessorFromFile', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  v.loadFromFile = (file, cb) => cb("name", "result", false);
  // No file argument needed since using fake loadFromFile
  v.loadScriptFromFile();
  let s = v.scripts()[0];
  expect(s.body()).toEqual("result");
  expect(s.name()).toEqual("name");
  v.loadPreprocessorFromFile();
  let p = v.preprocessors()[0];
  expect(p.body()).toEqual("result");
  expect(p.name()).toEqual("name");
});
test('downloadScript, downloadPreprocessor', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  v.downloadFile = jest.fn()

  v.downloadScript({name: ko.observable('foo'), body: ko.observable('bar')});
  expect(v.downloadFile).toHaveBeenCalledWith("foo.gcode", "bar");

  v.downloadPreprocessor({name: ko.observable('foo'), body: ko.observable('bar')});
  expect(v.downloadFile).toHaveBeenCalledWith("foo.py", "bar");
});
test('add new preprocessor from Events tab', () =>{
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  v.gotoTab = jest.fn()
  let s = v.addScript();
  v.events([{
    display: "testevent",
    actions: ko.observableArray([
      {script: s, preprocessor: ko.observable(null)},
    ])
  }]);
  let a = v.events()[0].actions()[0]
  a.preprocessor(null);
  v.actionPreprocessorChanged(a);
  expect(v.preprocessors().length).toBe(0);
  expect(a.preprocessor()).toBe(null);
  expect(v.gotoTab).not.toHaveBeenCalled();

  a.preprocessor('ADDNEW');
  v.actionPreprocessorChanged(a);
  expect(v.preprocessors().length).toBe(1);
  expect(a.preprocessor()).not.toBe(null);
  expect(v.gotoTab).toHaveBeenCalled();

});

test('Get slicers and profiles for dropdowns', () => {
  let op = mock_oprint();
  let cb = null;

  op.slicing.listAllSlicersAndProfiles = () => {
    return {
      done: (c) => cb = c
    };
  };
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS, op);
  cb({"preprintservice":{
    "configured":false,
    "default":false,
    "displayName":"PrePrintService",
    "extensions":{
      "destination":["gco","gcode","g"],
      "source":["stl"]
    },
    "key":"preprintservice",
    "profiles":{
      "profile_015mm_brim":{
        "default":true,
        "description":"Imported ...",
        "displayName":"profile_015mm_brim\n",
        "key":"profile_015mm_brim",
        "resource":"http://localhost:5000/api/slicing/preprintservice/profiles/profile_015mm_brim"
      }
    },
    "sameDevice":false
  }});
  expect(v.slicers()).toEqual({
    "preprintservice": {
      "key": "preprintservice",
      "name": "PrePrintService",
      "profiles": ["profile_015mm_brim"],
    },
  });
});

test('Set slicer & profile before save', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  v.slicers({slicername: {key: "slicername", name: "Slicer", profiles: ["profile1", "profile2"]}});

  v.slicer("slicername");
  expect(v.slicerProfiles()).toEqual(["profile1", "profile2"]);
  v.slicer_profile("profile2");

  v.onSettingsBeforeSave();
  expect(v.settings.settings.plugins.continuousprint.cp_slicer).toHaveBeenCalledWith("slicername");
  expect(v.settings.settings.plugins.continuousprint.cp_slicer_profile).toHaveBeenCalledWith("profile2");
});
