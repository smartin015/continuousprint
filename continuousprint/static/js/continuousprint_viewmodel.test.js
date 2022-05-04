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
    {
      init: jest.fn(),
      getState: jest.fn(),
      setActive: jest.fn(),
      getSpoolManagerState: jest.fn(),
      add: jest.fn(),
      rm: jest.fn(),
      mv: jest.fn(),
      update: jest.fn(),
      reset: jest.fn(),
    },
  ];
}

const DATA = {
  name: `item`,
  path: `item.gcode`,
  sd: false,
  count: 1,
  remaining: 1,
  job: "testjob",
};

function items(njobs = 1, nsets = 2) {
  let jobs = [];
  let sid = 1;
  for (let j = 0; j < njobs; j++) {
    let job = {name: `job${j}`, count: 1, remaining: 1, sets: [], id: j+1};
    for (let s = 0; s < nsets; s++) {
      job.sets.push({...DATA, name: `set${s}`, id: sid, materials: []});
      sid++;
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

test('files.add, new job', () => {
  let v = init();
  let data = {name: 'new file', path: 'test.gcode', origin: 'local'};
  v.api.add = (_, data, cb) => cb({job_id: 2, set_: {...data, materials: []}});
  v.files.add(data);
  expect(v.jobs().length).toEqual(2);
  expect(v.jobs()[1].sets()[0].path()).toEqual('test.gcode');
});

test('files.add, existing job', () => {
  let v = init();
  let data = {name: 'new file', path: 'test.gcode', origin: 'local'};
  v.api.add = (_, data, cb) => cb({job_id: 1, set_: {...data, materials: []}});
  v.files.add(data);
  expect(v.jobs().length).toEqual(1);
  expect(v.jobs()[0].sets()[2].path()).toEqual('test.gcode');
});

test('newEmptyJob', () => {
  let v = init();
  v.api.add = (_, data, cb) => cb({id: 2, name: '', count: 1});
  v.newEmptyJob();
  expect(v.jobs().length).toEqual(2);
  expect(v.jobs()[1].id()).toEqual(2);
});

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

test('sortEnd job to start', () => {
  let v = init();
  let j = v.jobs()[0];
  v.sortEnd(null, j, null);
  expect(v.files.onServerConnect).toHaveBeenCalled();
  expect(v.api.mv).toHaveBeenCalled();
  let data = v.api.mv.mock.calls[0][1];
  expect(data.id).toEqual(j.id);
  expect(data.after_id).toEqual(-1);
});

test('sortEnd job to end', () => {
  let v = init(njobs=2);
  let j = v.jobs()[1];
  v.sortEnd(null, j, null);
  expect(v.files.onServerConnect).toHaveBeenCalled();
  expect(v.api.mv).toHaveBeenCalled();
  let data = v.api.mv.mock.calls[0][1];
  expect(data.id).toEqual(j.id);
  expect(data.after_id).toEqual(1);
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

test('setJobName', () => {
  let v = init();
  v.setJobName(v.jobs()[0], {target: {value: 'ajobname'}})
  expect(v.api.update).toHaveBeenCalled();
  let j = v.api.update.mock.calls[0][1];
  expect(j.name).toBe('ajobname');
});
test('setCount', () => {
  let v = init();

  // Test with job count
  v.setCount(v.jobs()[0], {target: {value: '1'}})
  expect(v.api.update).toHaveBeenCalled();
  let j = v.api.update.mock.calls[0][1];
  expect(j.count).toBe(1);

  // Test with set count
  v.setCount(v.jobs()[0].sets()[0], {target: {value: '1'}});
  j = v.api.update.mock.calls[1][1];
  expect(j.count).toBe(1);
});

describe('batchSelect', () => {
  let v = init(njobs=4);
  v.jobs()[0].sets([]); // job 1 is empty
  // job 2 is unstarted; no action needed
  v.jobs()[2].sets()[0].count(3); // Job 3 is incomplete, set 5 is incomplete
  v.jobs()[3].remaining(0); // job 4 is complete
  v.jobs()[3].sets()[0].remaining(0); // job 4 is complete
  v.jobs()[3].sets()[1].remaining(0); // job 4 is complete

  let cases = [ // mode, jobids, setids
    ['None', [], []],
    ['All', [1,2,3,4], [3,4,5,6,7,8]],
    ['Empty Jobs', [1], []],
    ['Unstarted Jobs', [2], []],
    ['Incomplete Jobs', [3], []],
    ['Completed Jobs', [4], []],
    ['Unstarted Sets', [], [3,4,6]],
    ['Incomplete Sets', [], [5]],
    ['Completed Sets', [], [7,8]],
  ]
  for (let tc of cases) {
    it(`mode ${tc[0]}`, () => {
      v.batchSelect(null, {target: {innerText: tc[0]}});
      let selJobIds = [];
      let selSetIds = []
      for (let j2 of v.jobs()) {
        if (j2.selected()) {
          selJobIds.push(j2.id());
        }
        for (let s2 of j2.sets()) {
          if (s2.selected()) {
            selSetIds.push(s2.id);
          }
        }
      }
      expect([tc[0], selJobIds, selSetIds]).toEqual(tc);
    });
  }
});

test('deleteSelected', () => {
  let v = init(njobs=2);
  v.jobs()[0].selected(true);
  v.jobs()[1].sets()[0].selected(true);
  v.api.rm.mockImplementationOnce((_, cb) => cb());
  v.deleteSelected();
  expect(v.api.rm).toHaveBeenCalledWith({job_ids: [1], set_ids: [3]}, expect.any(Function));
  expect(v.jobs()[0].sets().length).toBe(1);
});

test('resetSelected', () => {
  let v = init(njobs=2);
  v.jobs()[0].selected(true);
  v.jobs()[0].remaining(0);
  v.jobs()[1].sets()[0].selected(true);
  v.jobs()[1].sets()[0].remaining(0);
  v.api.reset.mockImplementationOnce((_, cb) => cb());
  v.resetSelected();
  expect(v.api.reset).toHaveBeenCalledWith({job_ids: [1], set_ids: [3]}, expect.any(Function));
  expect(v.jobs()[0].remaining()).toBe(1);
  expect(v.jobs()[1].sets()[0].remaining()).toBe(1);
});
