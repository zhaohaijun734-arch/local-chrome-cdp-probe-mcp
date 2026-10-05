# local-chrome-cdp-probe-mcp

Real-browser measurement + screenshots through your **local Chrome** via the
Chrome DevTools Protocol. Zero npm dependencies (Node >= 20 global
fetch/WebSocket), zero Python deps beyond the MCP SDK. For when Playwright is
not cached and agent-browser is not installed, but the bug report is "this
button looks squashed on my screen".

## Why this exists — the traps it removes

| Trap | Symptom | Handled by |
|---|---|---|
| `/json/new` with GET | plain text "Using unsafe HTTP verb GET..." then `.json()` explodes | probe uses PUT (Chrome >= 111 contract) |
| Host sandbox kills Chrome's sandbox | renderer dies, DevTools ws closes with 1006 immediately | `--no-sandbox --disable-dev-shm-usage` baked in |
| Node WebSocket sends an Origin header | DevTools rejects the upgrade, 1006 | `--remote-allow-origins=*` baked in |
| Retina display doubles physical pixels | measured sizes 2x of CSS px | `--force-device-scale-factor=1` baked in |
| httpOnly login cookies unreachable from scripts | "just set document.cookie" fails | login is a `fetch POST` executed INSIDE the page - the browser's cookie jar applies |
| Modal overlays ruin screenshots | shot full of forced-password-change mask | your measure_js can remove the mask before capture |

## Install & run

```bash
pip install -e .            # mcp only
node --version              # must be >= 20
python server.py            # stdio transport
```

```json
{
  "mcpServers": {
    "local-chrome-cdp-probe": {
      "command": "python",
      "args": ["/path/to/local-chrome-cdp-probe-mcp/server.py"]
    }
  }
}
```

Optional env: `CHROME_PATH` (any Chromium), `NODE_BIN` (default `node`),
`PROBE_TIMEOUT` (wrapper timeout, default 60s; per-probe `--timeout-ms`
default 30s).

## Smoke test

```bash
python test_smoke.py    # real Chrome round trip on a local file:// page
```

License: MIT.
