const QueueSet = require('./continuousprint_queueset');

function items(count = 3, runs = 2, ncomplete = 1) {
  const DATA = {
    name: "an item",
    path: "item.gcode",
    sd: false,
    idx: 0,
    job: "testjob",
    run: 0,
    start_ts: null,
    end_ts: null,
    result: null,
    retries: 0,
  };

  let items = [];
  for (let run = 0; run < runs; run++) {
    for (let i = 0; i < count; i++) {
      let idx=count*run+i;
      if (idx < ncomplete) {
        items.push({...DATA, idx, run, start_ts:100, end_ts:101, result:"success"});
      } else {
        items.push({...DATA, idx, run});
      }
    }
  }
  return items;
}
test('aggregate observables', () => {
  let i = new QueueSet(items());
  expect(i.length()).toBe(6);
  expect(i.name()).toBe("an item");
  expect(i.count()).toBe(3);
  expect(i.runs_completed()).toBe(0);
  expect(i.active()).toBe(false);
});

test('progress indicator', () => {
  let i = new QueueSet(items());
  let stats = {};
  for (let p of i.progress()) {
    stats[p['result']] = p['pct'];
  }
  expect(stats).toStrictEqual({"success": 17, "pending": 83});
});

test('set_count increase', () => {
  let i = new QueueSet(items());
  i.set_count(4);

  expect(i.count()).toBe(4);
  expect(i.length()).toBe(8);
  expect(i.items()[0].start_ts()).toBe(100); // Preserves state
});

test('set_count decrease', () => {
  let i = new QueueSet(items());
  i.set_count(1);

  expect(i.count()).toBe(1);
  expect(i.length()).toBe(2);
  expect(i.items()[0].start_ts()).toBe(100); // Preserves state
});

test('set_runs increase', () => {
  let i = new QueueSet(items());
  i.set_runs(4);

  expect(i.count()).toBe(3);
  expect(i.length()).toBe(12);
  expect(i.items()[0].start_ts()).toBe(100); // Preserves state

});

test('set_runs decrease', () => {
  let i = new QueueSet(items());
  i.set_runs(1);

  expect(i.count()).toBe(3);
  expect(i.length()).toBe(3);
  expect(i.items()[0].start_ts()).toBe(100); // Preserves state

});
