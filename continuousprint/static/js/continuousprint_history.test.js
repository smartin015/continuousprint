const VM = require('./continuousprint_history');

function mocks() {
  return [
    {
        init: jest.fn(),
        history: jest.fn(),
        clearHistory: jest.fn(),
    },
  ];
}

test('refresh', () => {
  let v = new VM(mocks());
  v.refresh();
  expect(v.api.history).toHaveBeenCalled();
});

test('clearHistory', () => {
  let v = new VM(mocks());
  v.clearHistory();
  expect(v.api.clearHistory).toHaveBeenCalled();
});

test('_setState', () => {
  let v = new VM(mocks());
  v._setState([
    {job_name: "j1", set_path: "s1"},
    {job_name: "j2", set_path: "s2"},
  ]);
  let ents = v.entries();
  expect(ents.length).toEqual(4); // Include dividers
});
