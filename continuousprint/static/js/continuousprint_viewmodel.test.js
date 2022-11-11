const VM = require('./continuousprint_viewmodel');

function mocks(filename="test.gcode") {
  return [
    {
      isPrinting: jest.fn(() => true),
      isPaused: jest.fn(() => false),
      filename: jest.fn(() => filename)
    },
    {}, // loginState only used in continuousprint.js
    {onServerDisconnect: jest.fn(), onServerConnect: jest.fn(), removeFile: jest.fn()},
    {currentProfileData: () => {return {extruder: {count: () => 1}}}},
    {settings: {plugins: {continuousprint: {cp_infer_profile: () => false}}}},
    {
      init: jest.fn(),
      setActive: jest.fn(),
      getSpoolManagerState: jest.fn(),
      add: jest.fn(),
      get: jest.fn(),
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

function init(njobs = 1, ms=null) {
  if (!ms) {
    ms = mocks(filename="test.gcode");
  }
  let v = new VM(ms);
  v._setState({
    active: false,
    status: 'Test Status',
    queues: [{
      name: 'local',
      jobs: items(njobs),
    }],
  });
  return v;
}


test('onTabChange to continuous print tab triggers state reload', () => {
  let v = new VM(mocks());
  v.onTabChange('#tab_plugin_continuousprint', null);
  expect(v.api.get).toHaveBeenCalled();

  v = new VM(mocks());
  v.onTabChange('#a_random_tab', null);
  expect(v.api.get).not.toHaveBeenCalled();
  v.onTabChange('#a_random_tab', '#tab_plugin_continuousprint'); // Not on nav away
  expect(v.api.get).not.toHaveBeenCalled();
});

test('setActive notifies server', () => {
  let v = new VM(mocks());
  v.loading(false); // Inits to loading by default
  v.setActive(true);
  expect(v.api.setActive).toHaveBeenCalledWith(true, expect.any(Function));
});

test('files.add', () => {
  let v = init();
  v.defaultQueue = {'addFile': jest.fn()};
  let data = {name: 'new file', path: 'test.gcode', origin: 'local'};
  v.api.add = (_, data, cb) => cb({job_id: 2, set_: {...data, materials: []}});
  v.files.add(data);
  expect(v.defaultQueue.addFile).toHaveBeenCalledWith(data, false);
});

test('sortStart turns off default drag-drop', () => {
  let v = init();
  let vm = {constructor: {name: 'CPSet'}};
  v.sortStart(undefined, vm);
  expect(v.files.onServerDisconnect).toHaveBeenCalled();
});

function fakeElem(id, classList=[]) {
  return {
    id,
    classList: {
      contains: (v) => classList.indexOf(v) !== -1,
    },
  };
}

describe('sortMove', () => {
  let v = init();

  it('rejects sorts across different item types', () => {
    expect(v.sortMove({
      from: fakeElem('a'),
      to: fakeElem('b')
    })).toBe(false);
    expect(v.sortMove({
      from: fakeElem('a'),
      to: fakeElem('a')
    })).toBe(true);
  });

  it('prevents moving jobs out of local queue', () => {
    expect(v.sortMove({
      from: fakeElem('a', ['local']),
      to: fakeElem('b', ['nonlocal'])
    })).toBe(false);
    expect(v.sortMove({
      from: fakeElem('a', ['local']),
      to: fakeElem('a', ['local'])
    })).toBe(true);
  });

  it('only allows sets to drag between draft jobs', () => {
    expect(v.sortMove({
      from: fakeElem('queue_sets', ['draft']),
      to: fakeElem('queue_sets', [])
    })).toBe(false);
    expect(v.sortMove({
      from: fakeElem('queue_sets', ['draft']),
      to: fakeElem('queue_sets', ['draft'])
    })).toBe(true);
  });
});

test('sortEnd job to start', () => {
  let v = init();
  v._getElemIdx = () => 0; // To get queue
  let ccont = {classList: {contains: () => true}};
  let evt = {from: ccont, to: ccont, newIndex: 0};
  let j = v.defaultQueue.jobs()[0];
  v.sortEnd(evt, j, v.defaultQueue, dataFor=function(elem) {return v.defaultQueue});
  expect(v.files.onServerConnect).toHaveBeenCalled();
  expect(v.api.mv).toHaveBeenCalled();
  let data = v.api.mv.mock.calls[0][1];
  expect(data.id).toEqual(j.id());
  expect(data.after_id).toEqual(null);
});

test('sortEnd job to end', () => {
  let v = init(njobs=2);
  v._getElemIdx = () => 0; // To get queue
  let ccont = {classList: {contains: () => true}};
  let evt = {from: ccont, to: ccont, newIndex: 1};
  let j = v.defaultQueue.jobs()[1];
  v.sortEnd(evt, j, v.defaultQueue, dataFor=function(elem) {return v.defaultQueue});
  expect(v.files.onServerConnect).toHaveBeenCalled();
  expect(v.api.mv).toHaveBeenCalled();
  let data = v.api.mv.mock.calls[0][1];
  expect(data.id).toEqual(j.id());
  expect(data.after_id).toEqual(1);
});

test('refreshHistory', () => {
  let v = new VM(mocks());
  v.refreshHistory();
  expect(v.api.get).toHaveBeenCalled();
});

test('clearHistory', () => {
  let v = new VM(mocks());
  v.clearHistory();
  expect(v.api.reset).toHaveBeenCalled();
});

test('_setHistory', () => {
  let v = new VM(mocks());
  v._setHistory([
    {job_name: "j1", set_path: "s1"},
    {job_name: "j2", set_path: "s2"},
  ]);
  let ents = v.history();
  expect(ents.length).toEqual(4); // Include dividers
});

test('removeFile shows dialog', () => {
  let m = mocks();
  let rmfile = m[2].removeFile;
  let v = init(1, m);
  v.showRemoveConfirmModal = jest.fn();

  v.files.removeFile(DATA, {});

  expect(v.showRemoveConfirmModal).toHaveBeenCalled();
  expect(rmfile).not.toHaveBeenCalled();
});

test('removeConfirm calls removeFile', () => {
  let m = mocks();
  let rmfile = m[2].removeFile;
  let v = init(1, m);
  v.showRemoveConfirmModal = jest.fn();
  v.hideRemoveConfirmModal = jest.fn();
  v.files.removeFile(DATA, {});

  v.removeConfirm();

  expect(rmfile).toHaveBeenCalled();
});
