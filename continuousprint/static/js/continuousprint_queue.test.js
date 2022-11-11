const VM = require('./continuousprint_queue');

function mocks(filename="test.gcode") {
  return {
      add: jest.fn(),
      rm: jest.fn(),
      mv: jest.fn(),
      reset: jest.fn(),
    };
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

function init(njobs = 1) {
  return new VM({name:"test", jobs:items(njobs), peers:[
    {name: "localhost", profile: {name: "profile"}, status: "IDLE"}
  ]}, mocks());
}

test('newEmptyJob', () => {
  let v = init();
  v.api.add = (_, data, cb) => cb({id: 2, name: '', count: 1});
  v.newEmptyJob();
  expect(v.jobs().length).toEqual(2);
  expect(v.jobs()[1].id()).toEqual(2);
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
  let j = {'set_name': jest.fn()};
  v.setJobName(j, {target: {value: 'ajobname'}});
  expect(j.set_name).toHaveBeenCalledWith('ajobname');
});
test('setCount', () => {
  let v = init();
  let j = {'set_count': jest.fn()};
  v.setCount(j, {target: {value: '1'}});
  expect(j.set_count).toHaveBeenCalledWith(1);
});

describe('batchSelect', () => {
  let v = init(njobs=4);
  v.jobs()[0].sets([]); // job 1 is empty
  // job 2 is unstarted; no action needed
  v.jobs()[2].sets()[0].count(3); // Job 3 is incomplete, set 5 is incomplete
  v.jobs()[2].sets()[0].completed(1);
  v.jobs()[2].sets()[0].remaining(2);
  v.jobs()[3].remaining(0); // job 4 is complete
  v.jobs()[3].completed(1);
  v.jobs()[3].sets()[0].completed(1); // job 4 is complete
  v.jobs()[3].sets()[0].remaining(0); // job 4 is complete
  v.jobs()[3].sets()[1].completed(1); // job 4 is complete
  v.jobs()[3].sets()[1].remaining(0); // job 4 is complete

  let cases = [ // mode, jobids
    ['None', []],
    ['All', [1,2,3,4]],
    ['Empty Jobs', [1]],
    ['Unstarted Jobs', [2]],
    ['Incomplete Jobs', [3]],
    ['Completed Jobs', [4]],
  ]
  for (let tc of cases) {
    it(`mode ${tc[0]}`, () => {
      v.batchSelect(null, {target: {innerText: tc[0]}});
      let selJobIds = [];
      for (let j2 of v.jobs()) {
        if (j2.selected()) {
          selJobIds.push(j2.id());
        }
      }
      expect([tc[0], selJobIds]).toEqual(tc);
    });
  }
});

test('deleteSelected', () => {
  let v = init(njobs=2);
  v.jobs()[0].selected(true);
  v.api.rm.mockImplementationOnce((_1, _2, cb) => cb());
  v.deleteSelected();
  expect(v.api.rm).toHaveBeenCalledWith(undefined, {queue: 'test', job_ids: [1]}, expect.any(Function));
  expect(v.jobs().length).toBe(1);
});

test('resetSelected', () => {
  let v = init(njobs=2);
  v.jobs()[0].selected(true);
  v.jobs()[0].remaining(0);
  v.jobs()[0].sets()[0].remaining(0);
  v.api.reset.mockImplementationOnce((_1, _2, cb) => cb());
  v.resetSelected();
  expect(v.api.reset).toHaveBeenCalledWith(undefined, {queue: 'test', job_ids: [1]}, expect.any(Function));
  expect(v.jobs()[0].remaining()).toBe(1);
  expect(v.jobs()[0].sets()[0].remaining()).toBe(1);
});

test('addFile (profile inference disabled)', () => {
  let v = init(njobs=0);
  v.addFile({name: "foo", path: "foo.gcode", origin: "local", continuousprint: {profile: "testprof"}});
  expect(v.api.add).toHaveBeenCalledWith(v.api.SET, {
     "count": 1,
     "job": null,
     "jobName": "Job 1",
     "name": "foo",
     "path": "foo.gcode",
     "sd": false,
  }, expect.any(Function));
});

test('addFile (profile inference enabled)', () => {
  let v = init(njobs=0);
  v.addFile({name: "foo", path: "foo.gcode", origin: "local", continuousprint: {profile: "testprof"}}, true);
  expect(v.api.add).toHaveBeenCalledWith(v.api.SET, {
     "count": 1,
     "job": null,
     "jobName": "Job 1",
     "name": "foo",
     "path": "foo.gcode",
     "sd": false,
     "profiles": ["testprof"],
  }, expect.any(Function));
});
