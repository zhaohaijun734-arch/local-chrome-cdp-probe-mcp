---
name: local-chrome-cdp-probe
description: "Real-browser measurement and screenshots through your LOCAL Chrome via DevTools Protocol - no Playwright, no agent-browser install. Use when the user asks to actually measure an element (how wide is this box), screenshot a page before/after a change, or debug why an element is squashed - especially behind a login (the probe POSTs a JSON login inside the page, httpOnly cookies work). Trigger words: 真实浏览器实测, 量一下宽度, 截个图看看, before/after 对比."
display_name: Local Chrome CDP Probe
license: MIT
metadata:
  author: local-chrome-cdp-probe
  input_formats: ["url"]
  output_format: ["json", "png"]
---

# Local Chrome CDP Probe (MCP)

Tools:
- `probe_available()` - preflight (Node >= 20, probe script, Chrome).
- `probe_page(url, measure_js=..., viewport_w=1920, viewport_h=1080,
  screenshot=true, login="user:pass", login_url=..., login_body=...)`
  -> {origin, viewport, login_status, measurements, png_base64}.

`measure_js` is an in-page expression (IIFE returning an object) evaluated
after load. Use it for getBoundingClientRect / getComputedStyle facts you
cannot get from static HTML, e.g. the usable text width of an input
(clientWidth - paddings - borders), or to remove an overlaying modal before
the screenshot (`document.getElementById('mask')?.remove()`).

Rules:
- Measure BEFORE changing anything; verify AFTER with the same script -
  numbers beat screenshots for regressions.
- `usable_text_width` of an input = clientWidth - paddingLeft - paddingRight
  - 2 (borders). That - not the outer box width - is whether text fits.
- If every probe dies with ws 1006 even on about:blank, the host sandbox is
  killing Chrome's renderer: the bundled flags already handle it; on exotic
  hosts set CHROME_PATH to a known-good Chromium.
- Login is a JSON POST executed in page context; if the app lacks a JSON
  login API, drop `login` and probe a page reachable without auth.
