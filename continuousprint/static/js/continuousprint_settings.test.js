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
      simulate: jest.fn(),
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

test('invalid model change is ignored', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  v.modelChanged();
  expect(v.settings.settings.plugins.continuousprint.cp_bed_clearing_script).not.toHaveBeenCalled();
  expect(v.settings.settings.plugins.continuousprint.cp_queue_finished_script).not.toHaveBeenCalled();
});

test('load queues and scripts on settings view shown', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS);
  v.queues.onSettingsShown = jest.fn();
  v.automation.onSettingsShown = jest.fn();
  v.onSettingsShown();
  expect(v.queues.onSettingsShown).toHaveBeenCalled();
  expect(v.automation.onSettingsShown).toHaveBeenCalled();
});

test('Get slicers and profiles for dropdowns', () => {
  let op = mock_oprint();
  let cb = null;

  op.slicing.listAllSlicersAndProfiles = () => {
    return {
      done: (c) => cb = c
    };
  };
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS, EVENTS, CP_SIMULATOR_DEFAULT_SYMTABLE, op);
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
