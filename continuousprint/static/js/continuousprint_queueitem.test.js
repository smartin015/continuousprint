const QueueItem = require('./continuousprint_queueitem');

const DATA = {
  name: "an item",
  path: "item.gcode",
  sd: false,
  job: "testjob",
  run: 0,
  start_ts: null,
  end_ts: null,
  result: null,
  retries: 0,
};
let now = 10000;

test('object conversion contains all data fields', () => {
  // Ensure all entries are filled
  let data = {
    ...DATA, 
    start_ts: now,
    end_ts: now+1000,
    result: "success",
    retries: 2,
    run: 4
  };
  let i = new QueueItem(DATA);
  expect(i.as_object()).toStrictEqual(DATA);
});

test('duration works for minutes, hours, days', () => {
  let i = new QueueItem({...DATA, start_ts: now, end_ts: now+120});
  expect(i.duration()).toBe('2 minutes');
  i = new QueueItem({...DATA, start_ts: now, end_ts: now+2*60*60});
  expect(i.duration()).toBe('2 hours');
  i = new QueueItem({...DATA, start_ts: now, end_ts: now+2*24*60*60});
  expect(i.duration()).toBe('2 days');
});


