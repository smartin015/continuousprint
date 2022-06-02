const Job = require('./continuousprint_job');

const DATA = {
  path: `item.gcode`,
  sd: false,
  materials: [],
  count: 2,
  remaining: 1,
};

function sets(nsets = 2) {
  let sets = [];
  for (let s = 0; s < nsets; s++) {
    sets.push({...DATA, path: `item${s}.gcode`, id: s});
  }
  return sets;
}

function api() {
  return {
    edit: jest.fn((_, obj, cb) => cb(obj)),
  }
}

test('basic observables', () => {
  let j = new Job({name: 'bob', sets: sets()}, [], api());
  expect(j._name()).toBe('bob');
  expect(j.sets().length).not.toBe(0);
});

test('onSetModified new', () => {
  let j = new Job({sets: sets()}, [], api());
  j.onSetModified({...DATA, id: 5, path: "asdf"});
  expect(j.sets().length).toBe(3); // Added onto the end
});

test('onSetModified existing', () => {
  let j = new Job({sets: sets()}, [], api());
  j.onSetModified({...DATA, id: 1, path: "asdf"});
  expect(j.sets().length).toBe(2); // Replaced
  expect(j.sets()[1].path()).toBe('asdf');
});

test('length and length_completed', () => {
  let j = new Job({count: 3, remaining: 1, sets: sets()}, [], api());
  // 2 jobs done, each with 2 sets of 2 --> 8
  // plus an extra 1 each in current run --> 10
  expect(j.length_completed()).toBe(10);
  expect(j.length()).toBe(12);
});

test('checkFraction', () => {
  let j = new Job({sets: sets()}, [], api());
  expect(j.checkFraction()).toBe(0);
  j.selected(true);
  expect(j.checkFraction()).not.toBe(0);
});

test('pct_complete', () => {
  let j = new Job({count: 5, remaining: 3, sets: sets()}, [], api());
  expect(j.pct_complete()).toBe('40%');
});

test('editStart', () =>{
  let a = api();
  let j = new Job({}, [], a);
  j.editStart();
  expect(a.edit).toHaveBeenCalled();
  expect(j.draft()).toBe(true);
});

test('editEnd', () => {
  let a = api();
  let j = new Job({draft: true, name: 'bob', count: 2}, [], a);
  j.editEnd();
  let call = a.edit.mock.calls[0][1];
  expect(call.name).toEqual('bob');
  expect(call.count).toEqual(2);
  expect(call.draft).toEqual(false);
});
