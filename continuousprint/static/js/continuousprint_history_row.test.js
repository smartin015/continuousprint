const CPHistoryRow = require('./continuousprint_history_row');

const DATA = {
  name: "an item",
  path: "item.gcode",
  sd: false,
  job: "testjob",
  materials: [],
  run: 0,
  start: null,
  end: null,
  result: null,
  retries: 0,
};
let now = 10000;

test('duration works for minutes, hours, days', () => {
  let i = new CPHistoryRow({...DATA, start: now, end: now+120});
  expect(i.duration()).toBe('2 minutes');
  i = new CPHistoryRow({...DATA, start: now, end: now+2*60*60});
  expect(i.duration()).toBe('2 hours');
  i = new CPHistoryRow({...DATA, start: now, end: now+2*24*60*60});
  expect(i.duration()).toBe('2 days');
});
