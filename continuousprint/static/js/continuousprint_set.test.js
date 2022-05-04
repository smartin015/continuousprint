const CPSet = require('./continuousprint_set');

const job = {count: () => 2, remaining: () => 1};

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
  let i = new CPSet(data(), api(), job);
  expect(i.length()).toBe(6);
  expect(i.path()).toBe("item.gcode");
  expect(i.length_completed()).toBe(5);
});

test('materials', () => {
  let i = new CPSet(data(), api(), job);
  i.mats(['', 'PLA_black_000000']);
  let m = i.materials();
  expect(m[0].title).toBe("any");
  expect(m[1].title).toBe("PLA black 000000");
  expect(m[1].bgColor).toBe("000000");
});
test('pct_complete', () => {
  let i = new CPSet(data(), api(), job);
  i.count(5);
  i.remaining(3);
  expect(i.pct_complete()).toBe("40%");
});
test('pct_active', () => {
  let i = new CPSet(data(), api(), job);
  i.count(5);
  expect(i.pct_active()).toBe("20%");
});
test('length_completed', () => {
  let i = new CPSet(data(count=1), api(), {count: () => 1, remaining: () => 1});
  expect(i.length_completed()).toBe(0);

  // Completing a job should increase the length
  i.remaining(0);
  expect(i.length_completed()).toBe(1);

  // Job completion shouldn't double-count
  i = new CPSet(data(count=1), api(), {count: () => 1, remaining: () => 0});
  i.remaining(0);
  expect(i.length_completed()).toBe(1);
});
test('set_count', () => {
  let i = new CPSet(data(), api(), job);
  i.set_count(4);

  expect(i.count()).toBe(4);
  expect(i.length()).toBe(8);
});

test('set_material', () => {
  let i = new CPSet(data(), api(), job);
  i.set_material(1, 'asdf');
  expect(i.mats()).toStrictEqual(['', 'asdf']);
});
