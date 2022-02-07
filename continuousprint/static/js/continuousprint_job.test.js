const QueueItem = require('./continuousprint_queueitem');
const QueueSet = require('./continuousprint_queueset');
const Job = require('./continuousprint_job');

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

function queuesets(nsets = 2, count = 3, runs = 2, ncomplete = 1) {
  let sets = [];
  for (let s = 0; s < nsets; s++) {
    let items = [];
    for (let run = 0; run < runs; run++) {
      for (let i = 0; i < count; i++) {
        let idx=count*run+i;
        let data = {...DATA, name: `item ${s}`, idx, run};
        if (idx < ncomplete) {
          items.push({...data, start_ts:100, end_ts:101, result:"success"});
        } else {
          items.push(data);
        }
      }
    }
    sets.push(items);
  }
  return sets;
}
test('basic observables', () => {
  let j = new Job({name: 'bob', queuesets: queuesets()});
  expect(j.name()).toBe('bob');
  expect(j.queuesets().length).not.toBe(0);
});

test('pushQueueItem', () => {
  let j = new Job();
  j.pushQueueItem(DATA);
  expect(j.queuesets().length).toBe(1);
});

test('count and length aggregate queuesets', () => {
  let j = new Job({queuesets: queuesets()});
  expect(j.count()).toBe(2);
  expect(j.length()).toBe(12);
});

test('is_configured respects name and count', () => {
  let j = new Job();
  expect(j.is_configured()).toBe(false);
  j = new Job({queuesets: queuesets()});
  expect(j.is_configured()).toBe(true);
  j = new Job({name: 'foo'});
  expect(j.is_configured()).toBe(true);
});

test('runs_completed uses smallest queueset', () => {
  DEND = {...DATA, end_ts: 5};
  let j = new Job({queuesets: [
    [{...DATA, run:0}, {...DATA, run:1}, {...DEND, run:2}],
    [{...DATA, run:0}, {...DEND, run:1}, {...DEND, run:2}],
  ]});
  expect(j.runs_completed()).toBe(1);
});

test('progress aggregates queuesets', () => {
  let j = new Job({queuesets: queuesets()});
  let stats = {};
  for (let p of j.progress()) {
    stats[p['result']] = (stats[p['result']] || 0) + p['pct'];
  }
  // Note: still separate elements, not normalized, but it does include them all
  expect(stats).toStrictEqual({pending: 166, success: 34});
});

test('as_queue contains all fields and all items in the right order', () => {
  let j = new Job({queuesets: queuesets(), name: "test"});
  // Note that item 0 and item 1 sets are interleaved, 3 then 3 etc.
  // with completed items listed first and runs increasing per full repetition of all items
  expect(j.as_queue()).toStrictEqual([
    {"end_ts": 101, "job": "test", "name": "item 0", "path": "item.gcode", "result": "success", "retries": 0, "run": 0, "sd": false, "start_ts": 100}, 
    {"end_ts": null, "job": "test", "name": "item 0", "path": "item.gcode", "result": null, "retries": 0, "run": 0, "sd": false, "start_ts": null}, 
    {"end_ts": null, "job": "test", "name": "item 0", "path": "item.gcode", "result": null, "retries": 0, "run": 0, "sd": false, "start_ts": null}, 
    {"end_ts": 101, "job": "test", "name": "item 1", "path": "item.gcode", "result": "success", "retries": 0, "run": 0, "sd": false, "start_ts": 100}, 
    {"end_ts": null, "job": "test", "name": "item 1", "path": "item.gcode", "result": null, "retries": 0, "run": 0, "sd": false, "start_ts": null}, 
    {"end_ts": null, "job": "test", "name": "item 1", "path": "item.gcode", "result": null, "retries": 0, "run": 0, "sd": false, "start_ts": null}, 
    {"end_ts": null, "job": "test", "name": "item 0", "path": "item.gcode", "result": null, "retries": 0, "run": 1, "sd": false, "start_ts": null}, 
    {"end_ts": null, "job": "test", "name": "item 0", "path": "item.gcode", "result": null, "retries": 0, "run": 1, "sd": false, "start_ts": null}, 
    {"end_ts": null, "job": "test", "name": "item 0", "path": "item.gcode", "result": null, "retries": 0, "run": 1, "sd": false, "start_ts": null}, 
    {"end_ts": null, "job": "test", "name": "item 1", "path": "item.gcode", "result": null, "retries": 0, "run": 1, "sd": false, "start_ts": null}, 
    {"end_ts": null, "job": "test", "name": "item 1", "path": "item.gcode", "result": null, "retries": 0, "run": 1, "sd": false, "start_ts": null}, 
    {"end_ts": null, "job": "test", "name": "item 1", "path": "item.gcode", "result": null, "retries": 0, "run": 1, "sd": false, "start_ts": null}
  ]);
});

test('set_count affects all queuesets', () => {
  let j = new Job({queuesets: queuesets()});
  j.set_count(1);
  for (let qs of j.queuesets()) {
    expect(qs.count()).toBe(3);
    expect(qs.length()).toBe(3);
  }
});

test('set_name sets the name', () => {
  let j = new Job();
  j.set_name('bob');
  expect(j.name()).toBe('bob');
});

test('sort_end updates queuesets',  () => {
  let j = new Job({queuesets: queuesets()});
  j.queuesets()[0].set_runs(3);
  expect(j.queuesets()[0].length()).toBe(9);
  j.sort_end(j.queuesets()[0]);
  for (let qs of j.queuesets()) {
    expect(qs.count()).toBe(3);
    expect(qs.length()).toBe(6);
  }
});
