import time
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ======================================================================================
# 050 — ORFMOS HOME DESKTOP v0.1.6
# First desktop launcher surface: wallpaper + GitHub Publisher icon.
# BIOS CONTINUE resolves this module lazily and replaces the BIOS browser surface.
# ======================================================================================

ORFMOS_HOME_MODULE_ID = "050_ORFMOS_HOME_DESKTOP_V0_1_0"
ORFMOS_HOME_MODULE_VERSION = "0.1.6"
ORFMOS_HOME_HANDOFF_SCHEMA = "ORFMOS_HOME_HANDOFF_V0_1"

ORFMOS_GITHUB_PUBLISHER_NOTEBOOK_ID = "1UVsNFn3d1Ter5DaxVogA2IHoMorFACWc"
ORFMOS_GITHUB_PUBLISHER_NOTEBOOK_URL = (
    "https://colab.research.google.com/drive/" + ORFMOS_GITHUB_PUBLISHER_NOTEBOOK_ID
)
ORFMOS_HOME_DESKTOP_TARGETS = (
    {
        "id": "github_publisher",
        "title": "GitHub Publisher",
        "kind": "COLAB_NOTEBOOK",
        "target": ORFMOS_GITHUB_PUBLISHER_NOTEBOOK_URL,
        "drive_file_id": ORFMOS_GITHUB_PUBLISHER_NOTEBOOK_ID,
    },
)

_ORFMOS_HOME_LOCK = globals().get("_ORFMOS_HOME_LOCK") or threading.RLock()
globals()["_ORFMOS_HOME_LOCK"] = _ORFMOS_HOME_LOCK

# Module-revision boundary: never reuse a Gradio tree created by an older Home revision.
_previous_home_version = str(globals().get("__ORFMOS_HOME_LOADED_VERSION__") or "")
if _previous_home_version != ORFMOS_HOME_MODULE_VERSION:
    _stale_home_demo = globals().get("__ORFMOS_HOME_DEMO__")
    if _stale_home_demo is not None:
        try:
            close_fn = getattr(_stale_home_demo, "close", None)
            if callable(close_fn):
                close_fn()
        except Exception:
            pass
    globals()["__ORFMOS_HOME_DEMO__"] = None
    globals()["__ORFMOS_HOME_ACTIVE__"] = {}
globals()["__ORFMOS_HOME_LOADED_VERSION__"] = ORFMOS_HOME_MODULE_VERSION

# IMPORTANT: Home v0.1.6 still contains NO Gradio child components. The previous
# gr.HTML wallpaper path triggered Gradio 6.20 custom-event introspection failures
# (missing load_event_to_attach / info attributes). Desktop icons are injected by the
# proven Blocks load-event JS path, leaving the Gradio child component tree empty.
HOME_CSS = r"""
html, body, #root, .gradio-container {
  margin: 0 !important;
  padding: 0 !important;
  width: 100% !important;
  min-width: 100% !important;
  height: 100% !important;
  min-height: 100vh !important;
  overflow: hidden !important;
  background:
    radial-gradient(circle at 72% 28%, rgba(23,151,117,.18), transparent 34%),
    radial-gradient(circle at 25% 72%, rgba(25,86,112,.18), transparent 38%),
    linear-gradient(135deg, #071014 0%, #091115 38%, #05080b 100%) !important;
}
body {
  position: relative !important;
}
body::before {
  content: "ORFMOS";
  position: fixed;
  left: clamp(22px, 4vw, 58px);
  bottom: clamp(20px, 5vh, 54px);
  z-index: 999999;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: clamp(22px, 4vw, 46px);
  font-weight: 800;
  letter-spacing: .16em;
  color: rgba(214,255,242,.68);
  text-shadow: 0 0 28px rgba(53,225,168,.18);
  pointer-events: none;
  user-select: none;
}
body::after {
  content: "HOME 0.1.6";
  position: fixed;
  right: clamp(18px, 3vw, 42px);
  bottom: clamp(18px, 4vh, 40px);
  z-index: 999999;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 10px;
  letter-spacing: .12em;
  color: rgba(210,236,229,.30);
  pointer-events: none;
  user-select: none;
}
.gradio-container {
  position: fixed !important;
  inset: 0 !important;
  max-width: none !important;
  box-shadow: none !important;
  border: 0 !important;
}
.gradio-container::before {
  content: "";
  position: fixed;
  inset: -20%;
  pointer-events: none;
  background:
    repeating-linear-gradient(115deg, rgba(255,255,255,.018) 0 1px, transparent 1px 34px),
    repeating-linear-gradient(25deg, rgba(70,255,193,.012) 0 1px, transparent 1px 48px);
  transform: rotate(-2deg);
}

#orfHomeDesktopLayer {
  position: fixed;
  inset: 0;
  z-index: 50;
  pointer-events: none;
}
.orf-home-icon {
  appearance: none;
  -webkit-appearance: none;
  position: absolute;
  top: clamp(22px, 4vh, 46px);
  left: clamp(18px, 4vw, 46px);
  width: clamp(92px, 18vw, 126px);
  min-height: clamp(108px, 20vw, 138px);
  padding: 10px 8px 8px;
  border: 1px solid rgba(119, 219, 190, .14);
  border-radius: 18px;
  background: linear-gradient(145deg, rgba(13, 28, 33, .72), rgba(5, 12, 15, .52));
  box-shadow: 0 14px 40px rgba(0, 0, 0, .28), inset 0 1px 0 rgba(255,255,255,.025);
  color: rgba(222, 255, 245, .88);
  cursor: pointer;
  pointer-events: auto;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
  backdrop-filter: blur(3px);
}
.orf-home-icon:active {
  transform: scale(.97);
  border-color: rgba(85, 214, 174, .42);
  background: linear-gradient(145deg, rgba(17, 42, 46, .82), rgba(7, 18, 20, .68));
}
.orf-home-icon-glyph {
  position: relative;
  display: grid;
  place-items: center;
  width: clamp(54px, 11vw, 72px);
  height: clamp(54px, 11vw, 72px);
  margin: 0 auto 9px;
  border: 1px solid rgba(77, 205, 171, .42);
  border-radius: 18px;
  background:
    radial-gradient(circle at 35% 28%, rgba(95, 229, 194, .22), transparent 32%),
    linear-gradient(145deg, rgba(18, 48, 55, .90), rgba(5, 18, 23, .92));
  box-shadow: 0 0 26px rgba(39, 190, 153, .12), inset 0 0 18px rgba(48, 186, 157, .05);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: clamp(16px, 3.8vw, 22px);
  font-weight: 900;
  letter-spacing: -.06em;
}
.orf-home-icon-glyph::after {
  content: "↗";
  position: absolute;
  right: 6px;
  top: 2px;
  font-size: 14px;
  font-weight: 500;
  color: rgba(98, 226, 190, .88);
}
.orf-home-icon-label {
  display: block;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: clamp(9px, 2.1vw, 12px);
  line-height: 1.25;
  letter-spacing: .10em;
  text-align: center;
  color: rgba(213, 246, 237, .78);
  text-shadow: 0 1px 10px rgba(0,0,0,.7);
}
@media (min-aspect-ratio: 1/1) {
  .orf-home-icon {
    top: clamp(18px, 5vh, 34px);
    left: clamp(20px, 4vw, 42px);
    width: clamp(88px, 12vw, 112px);
    min-height: clamp(100px, 16vh, 122px);
  }
  .orf-home-icon-glyph {
    width: clamp(50px, 8vw, 64px);
    height: clamp(50px, 8vw, 64px);
  }
}

footer, .footer, .built-with, .prose, .contain, .gap {
  display: none !important;
}
"""


HOME_DESKTOP_JS = r"""
() => {
  try {
    const layerId = "orfHomeDesktopLayer";
    if (document.getElementById(layerId)) return [];

    const host = document.querySelector(".gradio-container") || document.body;
    const layer = document.createElement("div");
    layer.id = layerId;
    layer.setAttribute("data-orf-home-version", "0.1.6");

    const publisher = document.createElement("button");
    publisher.type = "button";
    publisher.className = "orf-home-icon";
    publisher.id = "orfHomeGithubPublisher";
    publisher.setAttribute("aria-label", "Open GitHub Publisher");
    publisher.title = "GitHub Publisher";
    publisher.innerHTML = '<span class="orf-home-icon-glyph">GH</span><span class="orf-home-icon-label">GITHUB<br>PUBLISHER</span>';
    publisher.addEventListener("click", () => {
      window.location.assign("__ORFMOS_GITHUB_PUBLISHER_URL__");
    });

    layer.appendChild(publisher);
    host.appendChild(layer);
  } catch (err) {
    console.error("ORFMOS Home desktop injection failed", err);
  }
  return [];
}
""".replace(
    "__ORFMOS_GITHUB_PUBLISHER_URL__",
    ORFMOS_GITHUB_PUBLISHER_NOTEBOOK_URL,
)


def build_orfmos_home_demo():
    # Gradio 6.x requires Blocks to pass through its context-manager lifecycle.
    # __enter__/__exit__ establishes/finalizes runtime attributes (including
    # `exited`, config and app) that launch() expects. Keep the surface empty,
    # but finalize it exactly as a normal Blocks application.
    with gr.Blocks(
        title="ORFMOS Home",
        fill_height=True,
        fill_width=True,
    ) as demo:
        demo.load(
            fn=None,
            inputs=None,
            outputs=None,
            js=HOME_DESKTOP_JS,
            queue=False,
        )
    return demo


def _home_extract_urls(demo_obj, result):
    extractor = globals().get("_extract_launch_urls")
    if callable(extractor):
        try:
            return extractor(demo_obj, result)
        except Exception:
            pass
    values = []
    if isinstance(result, (tuple, list)):
        values.extend(str(v) for v in result if isinstance(v, str) and v.startswith("http"))
    for attr in ("local_url", "share_url"):
        value = getattr(demo_obj, attr, None)
        if isinstance(value, str) and value.startswith("http"):
            values.append(value)
    local_url = next((v for v in values if "gradio.live" not in v), "")
    share_url = next((v for v in values if "gradio.live" in v), "")
    return local_url, share_url


def _home_url_is_live(url, timeout_seconds=4.0):
    """Reject expired gradio.live tunnel pages before browser handoff."""
    url = str(url or "").strip()
    if not url:
        return False
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 ORFMOS-Home-Liveness/0.1"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=float(timeout_seconds)) as response:
            status = int(getattr(response, "status", 200) or 200)
            sample = response.read(16384).decode("utf-8", errors="ignore").lower()
        if not (200 <= status < 400):
            return False
        dead_markers = (
            "no interface is running right now",
            "share link has expired",
            "this gradio app is not running",
        )
        return not any(marker in sample for marker in dead_markers)
    except Exception:
        return False


def _home_retire_stale_launch():
    demo = globals().get("__ORFMOS_HOME_DEMO__")
    if demo is not None:
        try:
            close_fn = getattr(demo, "close", None)
            if callable(close_fn):
                close_fn()
        except Exception:
            pass
    globals()["__ORFMOS_HOME_DEMO__"] = None
    globals()["__ORFMOS_HOME_ACTIVE__"] = {}


def orfmos_home_launch():
    """Return a live Home URL; stale share tunnels are retired and relaunched."""
    with _ORFMOS_HOME_LOCK:
        active = dict(globals().get("__ORFMOS_HOME_ACTIVE__") or {})
        active_url = str(active.get("url") or active.get("share_url") or "").strip()
        if str(active.get("status") or "").upper() == "READY" and active_url:
            if _home_url_is_live(active_url):
                active["liveness"] = "VERIFIED"
                active["verified_utc"] = datetime.now(timezone.utc).isoformat()
                globals()["__ORFMOS_HOME_ACTIVE__"] = active
                return active
            # The cached record can outlive its public Gradio tunnel across BIOS
            # reruns. Never navigate the user to that stale URL.
            _home_retire_stale_launch()

        demo = globals().get("__ORFMOS_HOME_DEMO__")
        if demo is None:
            demo = build_orfmos_home_demo()
            globals()["__ORFMOS_HOME_DEMO__"] = demo

        started = time.monotonic()
        try:
            result = demo.launch(
                share=True,
                prevent_thread_lock=True,
                show_error=True,
                quiet=True,
                css=HOME_CSS,
            )
            local_url, share_url = _home_extract_urls(demo, result)
            url = share_url or local_url
            if not url:
                raise RuntimeError("HOME_LAUNCH_RETURNED_NO_URL")
            record = {
                "schema": ORFMOS_HOME_HANDOFF_SCHEMA,
                "status": "READY",
                "module_id": ORFMOS_HOME_MODULE_ID,
                "module_version": ORFMOS_HOME_MODULE_VERSION,
                "url": url,
                "share_url": share_url,
                "local_url": local_url,
                "launched_utc": datetime.now(timezone.utc).isoformat(),
                "launch_seconds": round(time.monotonic() - started, 3),
                "surface": "WALLPAPER_PLUS_GITHUB_PUBLISHER_ICON",
                "liveness": "NEW_LAUNCH",
                "desktop_targets": [dict(item) for item in ORFMOS_HOME_DESKTOP_TARGETS],
            }
        except Exception as exc:
            record = {
                "schema": ORFMOS_HOME_HANDOFF_SCHEMA,
                "status": "FAILED",
                "module_id": ORFMOS_HOME_MODULE_ID,
                "module_version": ORFMOS_HOME_MODULE_VERSION,
                "url": "",
                "reason": f"{type(exc).__name__}: {exc}",
                "failed_utc": datetime.now(timezone.utc).isoformat(),
                "launch_seconds": round(time.monotonic() - started, 3),
            }
        globals()["__ORFMOS_HOME_ACTIVE__"] = record
        return record


ORFMOS_HOME_MODULE_STATE = {
    "schema": ORFMOS_HOME_HANDOFF_SCHEMA,
    "module_id": ORFMOS_HOME_MODULE_ID,
    "module_version": ORFMOS_HOME_MODULE_VERSION,
    "status": "LOADED",
    "launch_mode": "LAZY_ON_BIOS_CONTINUE",
    "surface": "WALLPAPER_PLUS_GITHUB_PUBLISHER_ICON",
    "desktop_targets": [dict(item) for item in ORFMOS_HOME_DESKTOP_TARGETS],
}
print(
    "ORFMOS HOME MODULE:",
    ORFMOS_HOME_MODULE_VERSION,
    "LOADED / GITHUB PUBLISHER DESKTOP TARGET READY",
    flush=True,
)
