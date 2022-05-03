const VM = require('./continuousprint_viewmodel');

function mocks(filename="test.gcode") {
  return [
    {
      isPrinting: jest.fn(() => true),
      isPaused: jest.fn(() => false),
      filename: jest.fn(() => filename)
    },
    {}, // loginState only used in continuousprint.js
    {onServerDisconnect: jest.fn(), onServerConnect: jest.fn()},
    {currentProfileData: () => {return {extruder: {count: () => 1}}}},
    {init: jest.fn(), getState: jest.fn(), setActive: jest.fn(), getSpoolManagerState: jest.fn(), add: jest.fn(), rm: jest.fn(), reset: jest.fn()},
  ];
}

const DATA = {
  name: `item`,
  path: `item.gcode`,
  sd: false,
  idx: 0,
  job: "testjob",
  run: 0,
  start_ts: null,
  end_ts: null,
  result: null,
  retries: 0,
};

function items(njobs = 1, nsets = 2) {
  let jobs = [];
  for (let j = 0; j < njobs; j++) {
    let job = {name: `job${j}`, count: 1, remaining: 1, sets: [], id: j};
    for (let s = 0; s < nsets; s++) {
      job.sets.push({...DATA, name: `set${s}`, id: s, materials: []});
    }
    jobs.push(job);
  }
  return jobs;
}

function init(njobs = 1, filename="test.gcode") {
  let v = new VM(mocks(filename=filename));
  v._setState({
    active: false,
    status: 'Test Status',
    jobs: items(njobs),
  });
  return v;
}


test('onTabChange to continuous print tab triggers state reload', () => {
  let v = new VM(mocks());
  v.onTabChange('#tab_plugin_continuousprint', null);
  expect(v.api.getState).toHaveBeenCalled();

  v = new VM(mocks());
  v.onTabChange('#a_random_tab', null);
  expect(v.api.getState).not.toHaveBeenCalled();
  v.onTabChange('#a_random_tab', '#tab_plugin_continuousprint'); // Not on nav away
  expect(v.api.getState).not.toHaveBeenCalled();
});

test('setActive notifies server', () => {
  let v = new VM(mocks());
  v.loading(false); // Inits to loading by default
  v.setActive(true);
  expect(v.api.setActive).toHaveBeenCalledWith(true, expect.any(Function));
});

test('refreshQueue triggers state reload', () => {
  let v = new VM(mocks());
  v.loading(false); // Inits to loading by default
  v.refreshQueue();
  expect(v.api.getState).toHaveBeenCalled();
});

test.only('files.add adds to bottom job and syncs to server', () => {
  let v = init();
  let data = {name: 'new file', path: 'test.gcode', origin: 'local'};
  v.api.add = (_, data, cb) => cb({job_id: 1, set_: []});
  v.files.add(data);
  expect(v.api.add).toHaveBeenCalled();
});

/*
test('setSelected sets/clears the indexes', () => {
  let v = init();
  expect(v.selected()).toBe(null);
  v.setSelected(0, 2);
  expect(v.selected()).toStrictEqual([0,2]);
  v.setSelected(0, 2); // Clear selection
  expect(v.selected()).toBe(null);
});

test('sortStart turns off default drag-drop', () => {
  let v = init();
  v.sortStart();
  expect(v.files.onServerDisconnect).toHaveBeenCalled();
});

test('sortMove rejects sorts across different item types', () => {
  let v = init();
  expect(v.sortMove({from: {id: 'a'}, to: {id: 'b'}})).toBe(false);
  expect(v.sortMove({from: {id: 'a'}, to: {id: 'a'}})).toBe(true);
});

test('sortEnd re-enables default drag-drop, notifies jobs, syncs to server', () => {
  let v = init();
  for (let j of v.jobs()) {
    j.sort_end = jest.fn();
  }
  v.sortEnd();
  expect(v.files.onServerConnect).toHaveBeenCalled();
  for (let j of v.jobs()) {
    expect(j.sort_end).toHaveBeenCalled();
  }
  expect(v.api.assign).toHaveBeenCalled();
});
test('setCount allows only positive integers', () => {
  let vm = {set_count: jest.fn()};
  let v = init();
  v.setCount(vm, {target: {value: "-5"}});
  v.setCount(vm, {target: {value: "0"}});
  v.setCount(vm, {target: {value: "apple"}});
  expect(vm.set_count).not.toHaveBeenCalled();

  v.setCount(vm, {target: {value: "5"}});
  expect(vm.set_count).toHaveBeenCalledWith(5);

});
test('setJobName syncs to server', () => {
  let v = init();
  v.setJobName(v.jobs()[0], {target: {value: 'ajobname'}})
  expect(v.api.assign).toHaveBeenCalled();
  let q = v.api.assign.mock.calls[0][0];
  expect(q[0].job).toBe('ajobname');
});
test('setCount syncs to server', () => {
  let v = init();

  // Test with job count
  v.setCount(v.jobs()[0], {target: {value: '1'}})
  expect(v.api.assign).toHaveBeenCalled();
  let q = v.api.assign.mock.calls[0][0];
  expect(q.length).toBe(6);

  // Test with queueset count
  v.setCount(v.jobs()[0].queuesets()[0], {target: {value: '1'}});
  q = v.api.assign.mock.calls[1][0];
  expect(q.length).toBe(4);
});
test('clearAll clears everything & syncs', () => {
  let v = init();
  v.clearAll();
  expect(v.api.assign).toHaveBeenCalledWith([], v._setState);
});
test('remove deletes job/queueset and syncs', () => {
  let v = init(njobs=2);
  v.remove(v.jobs()[0]);
  expect(v.api.assign).toHaveBeenCalled();
  let q = v.api.assign.mock.calls[0][0];
  expect(q.length).toBe(12);
  v.remove(v.jobs()[0].queuesets()[0]);
  q = v.api.assign.mock.calls[1][0];
  expect(q.length).toBe(6);
});
test('activeItem returns indexes for job, queueset, and item', () => {
  let v = init(njobs=2, filename="item.gcode");

  expect(v.activeItem()).toBe(null);

  // Printer printing and with partial item
  let i = v.jobs()[1].queuesets()[0].items()[2];
  i.start_ts(5);
  expect(v.activeItem()).toStrictEqual([1, 0, 2]);
});
*/
