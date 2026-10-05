// cdp-probe.mjs - zero-dependency CDP probe: drive local Chrome for real-browser
// measurement + screenshots. Requires Node >= 20 (global fetch / WebSocket).
//
// Usage:
//   node cdp-probe.mjs <url> <outPng> <jsFile> [options]
// Options:
//   --w 1920 --h 1080          viewport size
//   --login user:pass          POST login before measuring
//   --login-url /api/login     login endpoint (default /api/auth/login)
//   --login-body '{"username":"%u","password":"%p"}'
//                              login JSON template; %u/%p are substituted
//   --timeout-ms 30000         overall timeout
//
// Machine-readable result is printed on the last stdout line as:
//   __PROBE__<json>
import { spawn } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';

const args = process.argv.slice(2);
const url = args[0];
const outPng = args[1] || '';
const jsFile = args[2] || '';
const getArg = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const W = +getArg('--w', 1920), H = +getArg('--h', 1080);
const login = getArg('--login', '');
const loginUrl = getArg('--login-url', '/api/auth/login');
const loginBody = getArg('--login-body', '');
const OVERALL_TIMEOUT = +getArg('--timeout-ms', 30000);
const PORT = 9222 + Math.floor(Math.random() * 500);
const PROFILE = `${process.env.TMPDIR || '/tmp'}/cdp-profile-${PORT}`;
const CHROME = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

const result = { measurements: null, origin: null, viewport: null,
                 screenshot: null, login_status: null, error: null };
const emit = () => console.log('__PROBE__' + JSON.stringify(result));

if (!url) { result.error = 'usage: node cdp-probe.mjs <url> <outPng> <jsFile> [options]'; emit(); process.exit(2); }

const chrome = spawn(CHROME, [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${PROFILE}`,
  `--window-size=${W},${H}`, '--hide-scrollbars', '--no-first-run',
  '--no-default-browser-check', '--disable-gpu', '--force-device-scale-factor=1',
  '--remote-allow-origins=*',
  // Sandboxed hosts cannot start Chrome's own sandbox (renderer gets killed,
  // DevTools ws drops with 1006). These flags are NOT optional there.
  '--no-sandbox', '--disable-dev-shm-usage',
  'about:blank',
], { stdio: 'ignore' });

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function waitPort() {
  for (let i = 0; i < 80; i++) {
    try { const r = await fetch(`http://127.0.0.1:${PORT}/json/version`); if (r.ok) return; } catch (e) {}
    await sleep(150);
  }
  throw new Error('chrome debug port never became ready (is Chrome installed? CHROME_PATH set?)');
}

let ws, id = 0;
const pending = new Map();
function send(method, params = {}) {
  const m = { id: ++id, method, params };
  ws.send(JSON.stringify(m));
  return new Promise((res, rej) => {
    pending.set(m.id, { res, rej });
    setTimeout(() => { if (pending.has(m.id)) { pending.delete(m.id); rej(new Error('CDP timeout: ' + method)); } }, 15000);
  });
}

async function evalJs(expr) {
  const r = await send('Runtime.evaluate', {
    expression: expr, awaitPromise: true, returnByValue: true, userGesture: true,
  });
  if (r.exceptionDetails) throw new Error('page JS threw: ' + JSON.stringify(r.exceptionDetails.exception?.description || r.exceptionDetails.text));
  return r.result?.value;
}

async function ready() {
  for (let i = 0; i < 60; i++) {
    try { if (await evalJs('document.readyState') === 'complete') return; } catch (e) {}
    await sleep(200);
  }
  throw new Error('document never reached readyState=complete');
}

async function run() {
  await waitPort();
  // Chrome >= 111 requires PUT for /json/new (GET returns a plain-text error).
  const t = await (await fetch(`http://127.0.0.1:${PORT}/json/new?${encodeURIComponent(url)}`, { method: 'PUT' })).json();
  ws = new WebSocket(t.webSocketDebuggerUrl);
  ws.onmessage = e => {
    const m = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString());
    if (m.id && pending.has(m.id)) { pending.get(m.id).res(m.result || {}); pending.delete(m.id); }
  };
  await new Promise((res, rej) => {
    ws.onopen = () => res();
    ws.onerror = () => rej(new Error('ws error - code 1006 even on about:blank means the host needs --no-sandbox (already set)'));
    setTimeout(() => rej(new Error('ws connect timeout')), 8000);
  });

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url });
  await ready();
  await sleep(600);

  if (login) {
    const [u, p] = login.split(/:(.*)/s);
    const template = loginBody || '{"username":"%u","password":"%p"}';
    const body = template.replaceAll('%u', u).replaceAll('%p', p);
    result.login_status = await evalJs(`(async()=>{const r=await fetch(${JSON.stringify(loginUrl)},{method:'POST',headers:{'Content-Type':'application/json'},body:${JSON.stringify(body)}});return r.status;})()`);
    await send('Page.navigate', { url }); await ready(); await sleep(900);
  }

  result.origin = await evalJs('location.origin');
  result.viewport = await evalJs('innerWidth+"x"+innerHeight');

  if (jsFile) result.measurements = await evalJs(readFileSync(jsFile, 'utf8'));

  if (outPng) {
    const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
    writeFileSync(outPng, Buffer.from(shot.data, 'base64'));
    result.screenshot = outPng;
  }
}

const timeoutPromise = new Promise((_, rej) =>
  setTimeout(() => rej(new Error(`probe timeout ${OVERALL_TIMEOUT}ms`)), OVERALL_TIMEOUT));

try {
  await Promise.race([run(), timeoutPromise]);
} catch (e) {
  result.error = e.message;
} finally {
  try { ws && ws.close(); } catch (e) {}
  chrome.kill('SIGKILL');
  emit();
  process.exit(result.error ? 1 : 0);
}
