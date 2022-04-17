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
          },
        },
      },
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

test('invalid model change is ignored', () => {
  let v = new VM.CPSettingsViewModel(mocks(), PROFILES, SCRIPTS);
  v.modelChanged();
  expect(v.settings.settings.plugins.continuousprint.cp_bed_clearing_script).not.toHaveBeenCalled();
  expect(v.settings.settings.plugins.continuousprint.cp_queue_finished_script).not.toHaveBeenCalled();
});
