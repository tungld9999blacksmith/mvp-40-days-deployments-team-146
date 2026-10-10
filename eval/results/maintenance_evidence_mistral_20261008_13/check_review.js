// Synthetic browser-contract check. This does not submit real reviewer labels.
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');
const path = require('node:path');
const assert = require('node:assert/strict');
const folder = __dirname;
const producer = path.resolve(folder, '../generation_mistral_maintenance_100_20261008_13/case_results.jsonl');
const expectedHash = crypto.createHash('sha256').update(fs.readFileSync(producer)).digest('hex');
const html = fs.readFileSync(path.join(folder, 'rag_review.html'), 'utf8');
const ids = [...html.matchAll(/<article id="([^"]+)">/g)].map(m => m[1]);
assert.equal(ids.length, 100);
assert.equal(new Set(ids).size, 100);
function element(dataset = {}) {
  return {dataset, value: '', textContent: '', handlers: {}, addEventListener(k, f) {this.handlers[k] = f;}};
}
const reviewer = element(), count = element(), exporter = element();
const controls = ids.flatMap(key => ['correctness', 'citation_support', 'task_success', 'notes'].map(field => element({key, field})));
const persisted = new Map();
let exported, download;
vm.runInNewContext(fs.readFileSync(path.join(folder, 'rag_review.js'), 'utf8'), {
  document: {
    getElementById(id) {return {reviewer, count, export: exporter}[id];},
    querySelectorAll() {return controls;},
    createElement() {return {download: '', click() {download = this.download;}};},
  },
  localStorage: {getItem(k) {return persisted.get(k) || null;}, setItem(k, v) {persisted.set(k, v);}},
  Blob: class {constructor(parts) {this.text = parts.join('');}},
  URL: {createObjectURL(blob) {exported = JSON.parse(blob.text); return 'blob:synthetic';}, revokeObjectURL() {}},
  alert(message) {throw new Error(message);},
  setTimeout() {return 0;},
});
assert.equal(count.textContent, '0/100 labelled');
assert(controls.every(c => c.value === ''));
reviewer.value = 'SYNTHETIC_TEST_ONLY'; reviewer.handlers.change();
for (const control of controls.filter(c => c.dataset.key === 'M07')) {
  control.value = control.dataset.field === 'notes' ? 'synthetic export check' : 'pass';
  control.handlers.change();
}
assert.equal(count.textContent, '1/100 labelled');
exporter.handlers.click();
assert.equal(exported.source_sha256, expectedHash);
assert.equal(exported.reviewer, 'SYNTHETIC_TEST_ONLY');
assert.equal(Object.keys(exported.labels).length, 1);
assert.equal(exported.labels.M07.citation_support, 'pass');
assert.equal(exported.labels.M07.notes, 'synthetic export check');
assert.equal(download, 'rag-maintenance-review.json');
assert([...persisted.keys()].every(k => k === 'rag-maintenance-review-' + expectedHash));
console.log(JSON.stringify({status: 'PASS', synthetic_only: true, actual_review_labels_submitted: 0, case_panels: 100, initial_controls_blank: true, export_source_hash_verified: true, storage_scoped_to_current_run: true}));
