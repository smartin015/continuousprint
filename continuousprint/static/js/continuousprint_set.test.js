const CPSet = require('./continuousprint_set');

const job = {count: () => 2, remaining: () => 1, completed: () => 1};

function data(count=3) {
  return {
    path: "item.gcode",
    id: 1,
    sd: false,
    count,
    remaining: 1,
    materials: [],
  };
}
function api() {
  return {
    update: (_, data, cb) => {
      console.log(data.material);
      cb({...data, id: 1, remaining: (data.count || 1), job_remaining: 2, materials: ((data.materials) ? data.materials.split(',') : [])})
    },
  };
}
test('aggregate observables', () => {
  let i = new CPSet(data(), job, api());
  expect(i.path()).toBe("item.gcode");
  expect(i.length_remaining()).toBe(1);
});

test('materials', () => {
  let i = new CPSet(data(), job, api());
  i.mats(['', 'PLA_black_000000']);
  let m = i.materials();
  expect(m[0].title).toBe("any");
  expect(m[1].title).toBe("PLA (black)");
  expect(m[1].bgColor).toBe("000000");
});

test('pct_complete', () => {
  let i = new CPSet(data(), job, api());
  i.count(5);
  i.remaining(3);
  i.completed(2);
  expect(i.pct_complete()).toBe("40%");
});

test('pct_active', () => {
  let i = new CPSet(data(), job, api());
  i.count(5);
  i.remaining(3);
  i.completed(2);
  expect(i.pct_active()).toBe("20%");
});

test('shortName', () => {
  let i = new CPSet({path: "/foo/bar.gcode"}, job, api());
  expect(i.shortName()).toEqual("bar.gcode");
});

test('length_remaining', () => {
  let i = new CPSet(data(count=1), {count: () => 1, remaining: () => 1, completed: () => 0});
  expect(i.length_remaining()).toBe(1);

  // Completing a job should decrease the length
  i.remaining(0);
  i.completed(1);
  expect(i.length_remaining()).toBe(0);
});

test('set_material', () => {
  let i = new CPSet(data(), job, api());
  i.set_material(1, 'asdf');
  expect(i.mats()).toStrictEqual(['', 'asdf']);
});
