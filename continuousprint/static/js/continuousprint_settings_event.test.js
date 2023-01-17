const CPSettingsEvent = require('./continuousprint_settings_event');

function testAction(n, gcode, py) {
  return {
    script: {name: ko.observable('s' + n), body: ko.observable(gcode)},
    preprocessor: ko.observable({name: ko.observable('p' + n), body: ko.observable(py)}),
  }
}

function testEvent() {
  return new CPSettingsEvent(
    {name: 'name', event: 'event', display: 'display', desc: 'desc', sym_state: 'evt_state'},
    [testAction(0, "g1", "p1"), testAction(1, "g2", "p2")],
    {simulate: jest.fn()},
    {defaultsym: 'asdf'}
  );
}

describe('visible text computed vars', () => {
  test('sim running', () => {
    let vm = testEvent();
    vm.running(true);

    expect(vm.simGcodeOutput()).toEqual("...");
    expect(vm.combinedSimOutput()).toEqual("...");
    expect(vm.simSymtable()).toEqual([]);
    expect(vm.simSummary()).toEqual("running simulation...");
  });
  test('sim successful', () => {
    // TODO simGcodeOutput, combinedSimOutput, simSymtable, simSummary
    let vm = testEvent();
    vm.simulation({
      gcode: "gcode",
      stdout: "stdout",
      stderr: "",
      symtable_diff: {a: 'foo'},
    });
    vm.running(false);

    expect(vm.simGcodeOutput()).toEqual("gcode");
    expect(vm.combinedSimOutput()).toEqual("stdout\n");
    expect(vm.simSymtable()).toEqual([{key: 'a', value: 'foo'}]);
    expect(vm.simSummary()).toEqual("Simulation OK: 1 line, 1 notification");
  });
  test('sim error', () => {
    // TODO simGcodeOutput, combinedSimOutput, simSymtable, simSummary
    let vm = testEvent();
    vm.simulation({
      gcode: "gcode ignored",
      stdout: "stdout",
      stderr: "stderr",
      symtable_diff: {a: 'foo'},
    });
    vm.running(false);

    expect(vm.simGcodeOutput()).toEqual("@PAUSE; Preprocessor error");
    expect(vm.combinedSimOutput()).toEqual("stdout\nstderr");
    expect(vm.simSymtable()).toEqual([{key: 'a', value: 'foo'}]);
    expect(vm.simSummary()).toEqual("Simulation: execution error!");
  });
});

describe('symtableEdit', () => {
  test('updates symtable when symtableEdit edited successfully', () => {
    let vm = testEvent();
    vm.symtableEdit("123");
    expect(vm.symtable()).toEqual(123);
  });
  test('updates symtableEditError when JSON parse fails', () => {
    let vm = testEvent();
    vm.symtableEdit("not parseable");
    expect(vm.symtableEditError()).toMatch(/^SyntaxError.*/);
  });
});

describe('updater', () => {
  test('updates simulation values exactly once', () => {
    jest.useFakeTimers();
    let vm = testEvent();
    let want = {symtable_diff: [], gcode: "result", stdout: "", stderr: ""};
    vm.api.simulate = jest.fn((auto, sym, cb, errcb) => {
      cb(want);
    });
    vm.actions(vm.actions()); // Set dirty bit
    vm.updater();
    expect(vm.timer).not.toEqual(null);
    expect(vm.running()).toEqual(true);

    // Trigger updater a couple more times for good measure
    for (let i = 0; i < 10; i++) {
      vm.actions(vm.actions()); // Set dirty bit
      vm.updater();
    }

    jest.runAllTimers();
    expect(vm.api.simulate).toHaveBeenCalledTimes(1);

    expect(vm.running()).toEqual(false);
    expect(vm.simulation()).toEqual(want);
  });
  test('handles server error', () => {
    jest.useFakeTimers();
    let vm = testEvent();
    let want = {symtable_diff: [], gcode: "result", stdout: "", stderr: ""};
    vm.api.simulate = jest.fn((auto, sym, cb, errcb) => {
      errcb(123, "test");
    });
    vm.actions(vm.actions()); // Set dirty bit
    vm.updater();
    jest.runAllTimers();
    expect(vm.running()).toEqual(false);
    expect(vm.simulation().stderr).toEqual('Server error (123): test');
  });
});

test('pack', () => {
  let vm = testEvent();
  expect(vm.pack()).toEqual([
    {"preprocessor": "p0", "script": "s0"},
    {"preprocessor": "p1", "script": "s1"}
  ]);
});
