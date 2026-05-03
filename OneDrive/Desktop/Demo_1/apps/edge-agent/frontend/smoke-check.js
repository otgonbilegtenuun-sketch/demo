const fs = require('fs');
const path = require('path');

const root = __dirname;
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const js = fs.readFileSync(path.join(root, 'app.js'), 'utf8');
const backend = fs.readFileSync(path.join(root, '..', 'backend', 'app.py'), 'utf8');

const failures = [];

function fail(message) {
  failures.push(message);
}

const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]);
const duplicateIds = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
if (duplicateIds.length) {
  fail(`duplicate ids: ${duplicateIds.join(', ')}`);
}

const i18nKeys = [...html.matchAll(/data-i18n(?:-[a-z]+)?="([^"]+)"/g)].map(m => m[1]);
const dictKeys = [...js.matchAll(/[,{]\s*([a-zA-Z0-9_]+)\s*:/g)].map(m => m[1]);
const known = new Set(dictKeys);
const missing = [...new Set(i18nKeys.filter(k => !known.has(k)))];
if (missing.length) {
  fail(`missing i18n keys: ${missing.join(', ')}`);
}

[
  'videoProgressMeter',
  'btnVideoCancel',
  'btnVideoRetry',
  'startEventStream',
  'disconnectEventStream',
  'cancelVideoUpload',
  'retryVideoUpload',
].forEach(token => {
  if (!html.includes(token) && !js.includes(token)) {
    fail(`missing ${token}`);
  }
});

if (js.includes('adminNotifLog')) {
  fail('stale adminNotifLog reference remains');
}

if (!js.includes('/ws/events?token=')) {
  fail('WebSocket token is not attached');
}

if (!js.includes('/video_feed?token=')) {
  fail('video feed token is not attached');
}

['app.mount("/photos"', 'app.mount("/clips"', 'app.mount("/eval_clips"'].forEach(token => {
  if (backend.includes(token)) {
    fail(`public media mount remains: ${token}`);
  }
});

['@app.get("/photos/{file_path:path}")', '@app.get("/clips/{filename}")', '@app.get("/eval_clips/{filename}")'].forEach(token => {
  if (!backend.includes(token)) {
    fail(`protected media route missing: ${token}`);
  }
});

if (!js.includes('authMediaUrl(')) {
  fail('authenticated media URL helper is missing');
}

if (!js.includes('_mergenIntentionalClose')) {
  fail('WebSocket intentional-close guard is missing');
}

if (failures.length) {
  console.error(failures.join('\n'));
  process.exit(1);
}

console.log('frontend smoke check passed');
