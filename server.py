#!/usr/bin/env python3
"""local-chrome-cdp-probe MCP server.

Real-browser measurement and screenshots through your LOCAL Chrome via the
Chrome DevTools Protocol - no Playwright, no agent-browser, no 500MB install.
The bundled cdp-probe.mjs (Node >= 20, zero npm dependencies) drives Chrome;
this server wraps it as MCP tools so any agent can measure element boxes,
computed styles and capture screenshots with explicit, reproducible viewports.

Every known CDP footgun is already baked in:
- /json/new must be PUT (Chrome >= 111)
- --no-sandbox + --disable-dev-shm-usage on sandboxed hosts (ws 1006 otherwise)
- --remote-allow-origins=* (Node WebSocket sends an Origin header)
- --force-device-scale-factor=1 (Retina would double physical pixels)
"""
import base64
import functools
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

try:  # MCP SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server
except ModuleNotFoundError:  # 2.x renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as _Server

mcp = _Server("local-chrome-cdp-probe")

_PROBE = Path(__file__).resolve().parent / "cdp-probe.mjs"
_TIMEOUT = int(os.environ.get("PROBE_TIMEOUT", "60"))


class KnownError(Exception):
    def __init__(self, code: str, msg: str, hint: str = ""):
        super().__init__(msg)
        self.code, self.msg, self.hint = code, msg, hint


def guard(fn):
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except KnownError as exc:
            return {"ok": False, "errcode": exc.code, "message": exc.msg, "hint": exc.hint}
        except Exception as exc:
            return {"ok": False, "error": type(exc).__name__, "message": str(exc)[:300]}
    return wrapper


def _node() -> str:
    node = os.environ.get("NODE_BIN", "node")
    if shutil.which(node):
        return node
    raise KnownError("NODE_NOT_FOUND", f"node binary not found ({node})",
                     "install Node >= 20 or set NODE_BIN to its path")


@mcp.tool()
@guard
async def probe_available() -> dict:
    """Preflight: check node + the bundled probe script + Chrome detection."""
    node = _node()
    ver = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=15)
    major = int(''.join(c for c in ver.stdout.strip().lstrip('v') if c.isdigit())[:2] or 0)
    return {"ok": True, "node": ver.stdout.strip(), "node_ok": major >= 20,
            "probe_script": str(_PROBE), "probe_exists": _PROBE.exists(),
            "hint": "" if major >= 20 else "Node >= 20 required (global fetch/WebSocket)"}


@mcp.tool()
@guard
async def probe_page(url: str, measure_js: str = "", viewport_w: int = 1920,
                     viewport_h: int = 1080, screenshot: bool = True,
                     login: str = "", login_url: str = "",
                     login_body: str = "", timeout_ms: int = 30000) -> dict:
    """Measure and/or screenshot a page in real local Chrome.

    Args:
        url: full URL to probe (http/https/file)
        measure_js: in-page JS expression (IIFE returning an object) evaluated
            after load; its value comes back as `measurements`. Example that
            measures one element's real text width:
            (() => { const el = document.querySelector('#target'); if (!el) return null;
              const b = el.getBoundingClientRect(); const cs = getComputedStyle(el);
              return { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width),
                       h: Math.round(b.height),
                       usable_text_width: Math.round(el.clientWidth
                         - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) - 2) }; })()
        viewport_w / viewport_h: emulated viewport (also set via
            Emulation.setDeviceMetricsOverride, so it holds regardless of
            the Chrome window size)
        screenshot: capture a PNG and return it as base64
        login: "user:pass" - a JSON POST login executed IN the page context
            before measuring (httpOnly cookies are fine - the page fetch
            carries them). Requires the target app to have a JSON login API.
        login_url: login endpoint path, default /api/auth/login
        login_body: JSON template with %u / %p placeholders,
            default {"username":"%u","password":"%p"}
        timeout_ms: overall probe timeout

    Returns: {ok, origin, viewport, login_status, measurements, png_base64}
    """
    if not url.startswith(("http://", "https://", "file://")):
        raise KnownError("BAD_URL", "url must start with http://, https:// or file://")
    node = _node()
    workdir = Path(tempfile.mkdtemp(prefix="cdp_probe_"))
    js_file = workdir / "measure.js"
    png_file = workdir / "shot.png"
    if measure_js:
        js_file.write_text(measure_js, encoding="utf-8")

    cmd = [node, str(_PROBE), url, str(png_file) if screenshot else "",
           str(js_file) if measure_js else "",
           "--w", str(viewport_w), "--h", str(viewport_h),
           "--timeout-ms", str(timeout_ms)]
    if login:
        cmd += ["--login", login]
        if login_url:
            cmd += ["--login-url", login_url]
        if login_body:
            cmd += ["--login-body", login_body]

    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=_TIMEOUT, cwd=str(workdir))
    trailer = ""
    for line in proc.stdout.splitlines():
        if line.startswith("__PROBE__"):
            trailer = line[len("__PROBE__"):]
    if not trailer:
        raise KnownError("PROBE_NO_RESULT",
                         f"probe produced no result line (rc={proc.returncode})",
                         proc.stderr.strip()[-400:] or proc.stdout.strip()[-400:])
    data = json.loads(trailer)
    if data.get("error"):
        return {"ok": False, "errcode": "PROBE_ERROR", "message": data["error"],
                "hint": "if ws 1006 on every page: host sandbox; --no-sandbox is already set. "
                        "If login_status is 401/404: check login_url/login_body"}

    out = {"ok": True, "origin": data.get("origin"), "viewport": data.get("viewport"),
           "login_status": data.get("login_status"), "measurements": data.get("measurements")}
    if screenshot and png_file.exists():
        out["png_base64"] = base64.b64encode(png_file.read_bytes()).decode()
        out["png_bytes"] = png_file.stat().st_size
    return out


def main():
    mcp.run()


if __name__ == "__main__":
    main()
