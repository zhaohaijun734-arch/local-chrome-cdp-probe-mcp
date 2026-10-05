#!/usr/bin/env python3
"""Live smoke test: file:// page, measure title + box, screenshot."""
import asyncio
import base64
import json
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent
PAGE = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8")
PAGE.write("<!DOCTYPE html><html><head><title>probe-target</title></head>"
           "<body><div id='box' style='width:300px;height:50px;padding:10px'>x</div>"
           "</body></html>")
PAGE.close()
MEASURE = """(() => {
  const el = document.getElementById('box');
  const b = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  return { title: document.title,
           box: { w: Math.round(b.width), h: Math.round(b.height) },
           usable_text_width: Math.round(el.clientWidth
             - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) - 2) };
})()"""


async def main() -> int:
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server.py")])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            avail = await session.call_tool("probe_available", {})
            info = json.loads(avail.content[0].text)
            assert info.get("ok") and info.get("node_ok"), info
            print(f"[1] env ok: node {info.get('node')}")

            r = await session.call_tool("probe_page", {
                "url": Path(PAGE.name).as_uri(),
                "measure_js": MEASURE, "viewport_w": 1280, "viewport_h": 800,
            })
            res = json.loads(r.content[0].text)
            assert res.get("ok") is True, res
            m = res["measurements"]
            assert m["title"] == "probe-target", m
            assert m["box"]["w"] == 320 and m["usable_text_width"] == 298, m
            png = base64.b64decode(res["png_base64"])
            assert png[:8] == b"\x89PNG\r\n\x1a\n" and res["png_bytes"] > 1000
            print(f"[2] probe ok: {m['box']} usable_text_width={m['usable_text_width']}, "
                  f"viewport={res['viewport']}, png={res['png_bytes']}B")

    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
