const CPH = require('./continuousprint_history_row');
const CPHistoryRow = CPH.CPHistoryRow;
const CPHistoryDivider = CPH.CPHistoryDivider;

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

test('divider job name truncates', () => {
  let i = new CPHistoryDivider('Q', 'A really long job name seriously why is it so long', 'S');
  expect(i.job_name.length).toBeLessThan(25);
});
test('divider set path truncates', () => {
  let i = new CPHistoryDivider('Q', 'J', 'A really long set path I mean come on this is even longer than the job name', 'S');
  expect(i.job_name.length).toBeLessThan(36);
});
test('job name defaults to untitled', () => {
  let i = new CPHistoryDivider('Q', '', 'S');
  expect(i.job_name).toBe('untitled job');
});
