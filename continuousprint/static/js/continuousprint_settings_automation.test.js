// Import must happen after declaring constants
const VM = require('./continuousprint_settings_automation');

const SYMTABLE = () => {return {}};

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
  return {
    AUTOMATION: 'automation',
    QUEUES: 'queues',
    init: jest.fn(),
    get: jest.fn((_, cb) => cb([])),
    edit: jest.fn(),
    simulate: jest.fn(),
  };
}

test('loadScriptsFromProfile', () => {
  let v = new VM.CPSettingsAutomationViewModel(mocks(), SCRIPTS, EVENTS, SYMTABLE);
  v.loadScriptsFromProfile({
    name: 'TestPrinter',
    make: 'Test',
    model: 'Printer',
    defaults: {
      clearBed: 'script1',
      finished: 'script2',
    },
  });
  expect(v.scripts()[0].name()).toMatch(/^Clear Bed.*/);
  expect(v.scripts()[1].name()).toMatch(/^Finish.*/);
});

test('load scripts, preprocessors, events on settings view shown', () => {
  m = mocks();
  m.get = function (typ, cb) {
    if (typ === m.AUTOMATION) {
      cb({
        scripts: {a: 'g1', b: 'g2'},
        preprocessors: {c: 'p1'},
        events: {e1: [{script: 'a', preprocessor: 'c'}]},
      });
    }
  };
  let v = new VM.CPSettingsAutomationViewModel(m, SCRIPTS, EVENTS, SYMTABLE);
  v.onSettingsShown();
  expect(v.events().length).toBe(1);
  expect(v.scripts().length).toBe(2);
  expect(v.preprocessors().length).toBe(1);
});

test('addPreprocessor, rmPreprocessor', () => {
  let v = new VM.CPSettingsAutomationViewModel(mocks(), SCRIPTS, EVENTS, SYMTABLE);
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
  let v = new VM.CPSettingsAutomationViewModel(mocks(), SCRIPTS, EVENTS, SYMTABLE);
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
  let v = new VM.CPSettingsAutomationViewModel(mocks(), SCRIPTS, EVENTS, SYMTABLE);
  let e = {"actions": ko.observableArray([])};
  let a = {script:"foo"};
  v.addAction(e, a);
  expect(e.actions()[0].script).toEqual(a);
  v.rmAction(e, e.actions()[0]);
  expect(e.actions().length).toEqual(0);
});

test('allUniqueScriptNames', () =>{
  let v = new VM.CPSettingsAutomationViewModel(mocks(), SCRIPTS, EVENTS, SYMTABLE);
  expect(v.allUniqueScriptNames()).toEqual(true);
  v.addScript();
  expect(v.allUniqueScriptNames()).toEqual(true);
  v.addScript();
  expect(v.allUniqueScriptNames()).toEqual(false);
});

test('allUniquePreprocessorNames', () =>{
  let v = new VM.CPSettingsAutomationViewModel(mocks(), SCRIPTS, EVENTS, SYMTABLE);
  expect(v.allUniquePreprocessorNames()).toEqual(true);
  v.addPreprocessor();
  expect(v.allUniquePreprocessorNames()).toEqual(true);
  v.addPreprocessor();
  expect(v.allUniquePreprocessorNames()).toEqual(false);
});

test('registrations of script / preprocessor are tracked', () => {
  let v = new VM.CPSettingsAutomationViewModel(mocks(), SCRIPTS, EVENTS, SYMTABLE);
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
  let v = new VM.CPSettingsAutomationViewModel(mocks(), SCRIPTS, EVENTS, SYMTABLE);
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
  let v = new VM.CPSettingsAutomationViewModel(mocks(), SCRIPTS, EVENTS, SYMTABLE);
  v.downloadFile = jest.fn()

  v.downloadScript({name: ko.observable('foo'), body: ko.observable('bar')});
  expect(v.downloadFile).toHaveBeenCalledWith("foo.gcode", "bar");

  v.downloadPreprocessor({name: ko.observable('foo'), body: ko.observable('bar')});
  expect(v.downloadFile).toHaveBeenCalledWith("foo.py", "bar");
});

test('add new preprocessor from Events tab', () =>{
  let v = new VM.CPSettingsAutomationViewModel(mocks(), SCRIPTS, EVENTS, SYMTABLE);
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
