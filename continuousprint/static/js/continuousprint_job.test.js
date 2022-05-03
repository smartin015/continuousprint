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
    update: (_, obj, cb) => cb({...obj, id: 1, remaining: (obj.count || 1)}),
  }
}

test('basic observables', () => {
  let j = new Job({name: 'bob', sets: sets()}, api());
  expect(j.name()).toBe('bob');
  expect(j.sets().length).not.toBe(0);
});

test('onSetModified new', () => {
  let j = new Job({sets: sets()}, api());
  j.onSetModified({...DATA, id: 5, path: "asdf"});
  expect(j.sets().length).toBe(3); // Added onto the end
});

test('onSetModified existing', () => {
  let j = new Job({sets: sets()}, api());
  j.onSetModified({...DATA, id: 1, path: "asdf"});
  expect(j.sets().length).toBe(2); // Replaced
  expect(j.sets()[1].path()).toBe('asdf');
});

test('length and length_completed', () => {
  let j = new Job({sets: sets()}, api());
  j.count(3);
  j.remaining(1);
  // 2 jobs done, each with 2 sets of 2 --> 8
  // plus an extra 1 each in current run --> 10
  expect(j.length_completed()).toBe(10);
  expect(j.length()).toBe(12);
});

test('checkFraction', () => {
  let j = new Job({sets: sets()}, api());
  expect(j.checkFraction()).toBe(0);
  j.selected(true);
  expect(j.checkFraction()).not.toBe(0);
  j.sets()[0].selected(true);
  j.selected(false);
  expect(j.checkFraction()).not.toBe(0);
});

test('pct_complete', () => {
  let j = new Job({sets: sets()}, api());
  j.count(5);
  j.remaining(3);
  expect(j.pct_complete()).toBe('40%');
});

test('set_count', () => {
  let j = new Job({sets: sets()}, api());
  j.set_count(5);
  expect(j.count()).toBe(5);
  expect(j.remaining()).toBe(5);
});

test('set_name', () => {
  let j = new Job({}, api());
  j.set_name('bob');
  expect(j.name()).toBe('bob');
});
