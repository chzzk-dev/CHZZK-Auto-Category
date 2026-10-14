// Browser APIs are mocked; this is not a Chrome Web Store integration test.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const events = {};
const register = name => ({addListener: callback => {events[name] = callback;}});
let manifestVersion = '0.6.0';
let fetches = 0;
const context = vm.createContext({
  crypto: webcrypto, navigator: {userAgent: 'Chrome'}, AbortSignal, setTimeout, clearTimeout,
  chrome: {
    runtime: {id: 'a'.repeat(32), getManifest: () => ({version: manifestVersion}),
      onInstalled: register('installed'), onStartup: register('startup'), onMessage: register('message')},
    alarms: {create: async () => {}, onAlarm: register('alarm')},
    tabs: {query: async () => [], create: async () => ({id: 1}), get: async () => ({status: 'complete'}),
      onUpdated: {addListener(){}, removeListener(){}}},
    scripting: {executeScript: async () => [{result: {status: 200}}]}
  },
  fetch: async () => {fetches++; return new Promise(() => {});}
});
vm.runInContext(fs.readFileSync('extension/background.js', 'utf8'), context);
const first = vm.runInContext('extensionInfo()', context);
assert.equal(first.extensionId, 'a'.repeat(32));
assert.equal(first.version, manifestVersion);
assert.equal(first.protocolVersion, 1);
assert.equal(first.type, 'extension_info');
manifestVersion = '0.6.1';
context.navigator.userAgent = 'Edg/155';
const second = vm.runInContext('extensionInfo()', context);
assert.equal(second.version, '0.6.1');
assert.equal(second.browser, 'Edge');
assert(second.sequence > first.sequence);
assert.equal(first.sessionId, second.sessionId);
const callsBefore = fetches;
vm.runInContext('bridgeLoop(); bridgeLoop();', context);
assert.equal(fetches, callsBefore, 'duplicate loops must be coalesced');
vm.runInContext('setBridgeState(false, "offline")', context);
events.message({type: 'bridge-kick'}, {}, () => {});
let state;
events.message({type: 'bridge-status'}, {}, x => state = x);
assert.equal(state.connected, false, 'reconnect is not a successful handshake');
console.log('Extension mocked tests passed: actual manifest, ID, protocol, sequence, browser, loop coalescing, honest reconnect state');
