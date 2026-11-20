const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const node = { innerHTML: '', onclick: null };
const context = {
  window: {},
  document: { querySelector: () => node, querySelectorAll: () => [], documentElement: { dataset: {} } },
  localStorage: { getItem: () => null, setItem: () => {} },
  location: { hostname: 'localhost' },
  matchMedia: () => ({ matches: false }),
  fetch: () => new Promise(() => {}),
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8'), context);

const board = context.letterBoard('бананы', { interactive: true });
assert.equal((board.match(/<button /g) || []).length, 3);
assert.deepEqual([...board.matchAll(/data-index="(\d+)"/g)].map(x => Number(x[1])), [1, 3, 5]);
assert.equal((board.match(/is-consonant/g) || []).length, 3);
assert.equal((board.match(/<span class="letter-tile is-consonant/g) || []).length, 3);

const result = context.letterBoard('банты', { stressIndex: 1 });
assert.equal((result.match(/accent-mark/g) || []).length, 1);
assert.equal((result.match(/is-stressed/g) || []).length, 1);
assert.equal((result.match(/<button /g) || []).length, 0);
assert.equal(context.document.documentElement.dataset.theme, 'dark');
console.log('UI letter-board checks passed');
