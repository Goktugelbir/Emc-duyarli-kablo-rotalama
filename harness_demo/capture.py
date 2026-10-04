"""README images rendered from the interactive three.js page (docs/index.html).

The page is opened in headless Chrome (driven over the DevTools protocol with `choreographer`,
which kaleido already depends on) in its capture mode (`?capture`): only the 3D view is shown and
the page exposes `window.viewer` to select a method, place the camera and set the routing progress.
Every number in the captions comes from the metrics embedded in the page. Pillow only places the
finished screenshots side by side and assembles the GIF frames; no pixel editing is done.

The page loads three.js from a CDN, so capturing needs an internet connection.
"""

from __future__ import annotations

import asyncio
import base64
import io
from collections.abc import Sequence
from pathlib import Path

from PIL import Image

# Camera presets used for the README: (position, target, vertical fov [deg], floor visible).
PLAN_VIEW = ([3.0, -2.4, -5.6], [3.0, 0.0, 0.9], 50, False)  # looking up into the arch, whole layout
INSIDE_VIEW = ([-1.25, -0.25, 1.05], [3.2, 0.0, 1.25], 60, True)  # standing in the open aft end
PLAYBACK_VIEW = ([-1.3, -0.2, 0.95], [3.2, 0.0, 1.45], 64, True)  # GIF: inside view, a little more of the arch
READY_TIMEOUT_S = 90.0
BACKGROUND = (18, 21, 25)


class _Page:
    """Thin async wrapper around one headless Chrome tab showing the viewer."""

    def __init__(self, tab) -> None:  # noqa: ANN001 (choreographer.Tab)
        self.tab = tab

    async def js(self, expr: str) -> object:
        r = await self.tab.send_command(
            "Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True}
        )
        res = r["result"]
        if "exceptionDetails" in res:
            raise RuntimeError(f"viewer script error: {res['exceptionDetails'].get('text')}")
        return res["result"].get("value")

    async def size(self, width: int, height: int, scale: float = 1.0) -> None:
        await self.tab.send_command("Emulation.setDeviceMetricsOverride",
                                    {"width": width, "height": height, "deviceScaleFactor": scale, "mobile": False})

    async def setup(self, method: str, view: tuple, labels: str = "context") -> None:
        pos, target, fov, floor = view
        await self.js(f"window.viewer.select('{method}'); window.viewer.toggle('floor', {str(floor).lower()}); "
                      f"window.viewer.camera({pos}, {target}, {fov}); window.viewer.labels('{labels}'); "
                      "window.viewer.actuator(0.35); window.viewer.frame()")

    async def shot(self) -> Image.Image:
        await self.js("window.viewer.frame()")
        r = await self.tab.send_command("Page.captureScreenshot", {"format": "png"})
        return Image.open(io.BytesIO(base64.b64decode(r["result"]["data"]))).convert("RGB")


async def _open(browser, html_path: Path) -> _Page:  # noqa: ANN001 (choreographer.Browser)
    tab = await browser.create_tab(url="", window=True)
    page = _Page(tab)
    await tab.send_command("Page.enable")
    await page.size(1280, 800)
    await tab.send_command("Page.navigate", {"url": html_path.resolve().as_uri() + "?capture"})
    loop = asyncio.get_running_loop()
    deadline = loop.time() + READY_TIMEOUT_S
    while not await page.js("window.__viewerReady === true"):
        if loop.time() > deadline:
            raise RuntimeError("the 3D viewer did not load (three.js is loaded from a CDN: internet needed)")
        await asyncio.sleep(0.25)
    return page


def _save_gif(frames: list[Image.Image], durations: list[int], path: Path, key_colors: Sequence[str]) -> None:
    """One shared palette keeps colours stable between frames and lets the GIF store only what changes.

    The palette is built from the first, middle and last frame plus solid swatches of the key colours
    (EMC classes, violations), so small but important areas keep their exact colour.
    """
    w, h = frames[0].size
    swatch = 48
    probe = Image.new("RGB", (w, h * 3 + swatch * 2))
    for i, f in enumerate((frames[0], frames[len(frames) // 2], frames[-1])):
        probe.paste(f, (0, i * h))
    for i, c in enumerate(key_colors):
        probe.paste(Image.new("RGB", (w // len(key_colors), swatch * 2), c), (i * (w // len(key_colors)), h * 3))
    palette = probe.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    gif = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    gif[0].save(path, save_all=True, append_images=gif[1:], duration=durations, loop=0, optimize=True, disposal=1)


async def _capture(html_path: Path, out_dir: Path, methods: Sequence[str], comparison: tuple[str, str],
                   animated: str) -> list[Path]:
    from choreographer import Browser  # imported lazily: only needed for image export

    written: list[Path] = []
    async with Browser(headless=True, enable_gpu=True) as browser:
        page = await _open(browser, html_path)

        # One plan-view image per method (README "all methods" grid).
        await page.size(1000, 700, 1.25)
        stills = {}
        for m in methods:
            await page.setup(m, PLAN_VIEW)
            stills[m] = await page.shot()
            path = out_dir / f"routes_{m}.png"
            stills[m].save(path, optimize=True)
            written.append(path)

        # Side-by-side comparison, same camera and colours.
        left, right = stills[comparison[0]], stills[comparison[1]]
        gap = 6
        sheet = Image.new("RGB", (left.width + gap + right.width, max(left.height, right.height)), BACKGROUND)
        sheet.paste(left, (0, 0))
        sheet.paste(right, (left.width + gap, 0))
        path = out_dir / "comparison.png"
        sheet.save(path, optimize=True)
        written.append(path)

        # Close-up from inside the section (interactive page preview).
        await page.size(1200, 700, 1.25)
        await page.setup(animated, INSIDE_VIEW, labels="context")
        path = out_dir / "viewer_inside.png"
        (await page.shot()).save(path, optimize=True)
        written.append(path)

        # Routing playback: cables are laid one by one in routing order, static camera.
        await page.size(960, 600)
        await page.setup(animated, PLAYBACK_VIEW, labels="none")
        key_colors = list((await page.js("JSON.parse(document.getElementById('data').textContent).classColors")).values())
        n = int(await page.js("window.viewer.cableCount"))
        frames, durations = [], []
        steps = 4
        for k in range(n * steps + 1):
            await page.js(f"window.viewer.progress({k / steps})")
            frames.append(await page.shot())
            durations.append(90)
        durations[-1] = 3500  # hold the finished result (clamps and checks shown)
        path = out_dir / "demo.gif"
        _save_gif(frames, durations, path, key_colors + ["#ff2a3d", "#e34948"])
        written.append(path)
    return written


def capture_readme_images(html_path: Path, out_dir: Path, methods: Sequence[str],
                          comparison: tuple[str, str] = ("bundled", "integrated"),
                          animated: str = "integrated") -> list[Path]:
    """Render routes_<method>.png, comparison.png, viewer_inside.png and demo.gif from the viewer page."""
    out_dir.mkdir(parents=True, exist_ok=True)
    return asyncio.run(_capture(html_path, out_dir, methods, comparison, animated))
