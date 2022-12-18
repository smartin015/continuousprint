const Job = require('./continuousprint_job');

const DATA = {
  path: `item.gcode`,
  sd: false,
  materials: [],
  count: 2,
  remaining: 1,
  completed: 1,
  metadata: JSON.stringify({estimatedPrintTime: 100, filamentLengths: [100]}),
};

function sets(nsets = 2) {
  let sets = [];
  for (let s = 0; s < nsets; s++) {
    sets.push({...DATA, path: `item${s}.gcode`, id: s});
  }
  return sets;
}

function prof() {
  return null;
}

function api() {
  return {
    edit: jest.fn((_, obj, cb) => cb(obj)),
  }
}

function mats() {
  return ko.observableArray([{density: 0.4, diameter: 1.75}]);
}

test('basic observables', () => {
  let j = new Job({name: 'bob', sets: sets()}, [], api(), prof(), mats());
  expect(j._name()).toBe('bob');
  expect(j.sets().length).not.toBe(0);
});

test('onSetModified new', () => {
  let j = new Job({sets: sets()}, [], api(), prof(), mats());
  j.onSetModified({...DATA, id: 5, path: "asdf"});
  expect(j.sets().length).toBe(3); // Added onto the end
});

test('onSetModified existing', () => {
  let j = new Job({sets: sets()}, [], api(), prof(), mats());
  j.onSetModified({...DATA, id: 1, path: "asdf"});
  expect(j.sets().length).toBe(2); // Replaced
  expect(j.sets()[1].path()).toBe('asdf');
});

test('totals', () => {
  let j = new Job({count: 3, completed: 2, remaining: 1, sets: sets()}, [], api(), prof(), mats());

  let t = j.totals();
  expect(t[0]).toStrictEqual({
    completed: "2", // sets have 1/2 completed this run
    count: "4", // 2 sets each with count=2
    remaining: "2", // 2 left in this run, one from each set
    total: "2", // 2 pending
    error: "",
    legend: "Total items",
    title: null,
  });

  // Values are as above, but x100 and converted to minutes
  expect(t[1]).toStrictEqual({
    completed: "3m",
    count: "7m",
    remaining: "3m",
    total: "3m",
    error: "",
    legend: "Total time",
    title: expect.anything(),
  });

  // Values are as above, but factored by filamentLength, density, and filament diameter
  expect(t[2]).toStrictEqual({
    completed: "0.2g",
    count: "0.4g",
    remaining: "0.2g",
    total: "0.2g",
    error: "",
    legend: "Total mass",
    title: expect.anything(),
  });
});

test('checkFraction', () => {
  let j = new Job({sets: sets()}, [], api(), prof(), mats());
  expect(j.checkFraction()).toBe(0);
  j.selected(true);
  expect(j.checkFraction()).not.toBe(0);
});

test('pct_complete', () => {
  let j = new Job({count: 5, remaining: 3, sets: sets()}, [], api(), prof(), mats());
  expect(j.pct_complete()).toBe('40%');
});

test('editStart', () =>{
  let a = api();
  let j = new Job({}, [], a, prof(), mats());
  j.editStart();
  expect(a.edit).toHaveBeenCalled();
  expect(j.draft()).toBe(true);
});

test('editEnd', () => {
  let a = api();
  let j = new Job({draft: true, name: 'bob', count: 2}, [], a, prof(), mats());
  j.editEnd();
  let call = a.edit.mock.calls[0][1];
  expect(call.name).toEqual('bob');
  expect(call.count).toEqual(2);
  expect(call.draft).toEqual(false);
});
