# ======================================================================================
# CELL 4 — LAUNCH DEVELOPMENT SURFACE
# ======================================================================================

# First executable action in Cell 4: leave an immediate, flush-visible causal
# marker before Gradio launch, development delay, Drive reads, or Kernel loading.
_ORF_CELL4_CAPTURE_EVENT = _emit_kernel_loader_capture(
    "CELL4_ENTER",
    phase="CELL_4_ENTRY",
    autostart_enabled=bool(DEV_AUTOBOOT_KERNEL),
)

print("=" * 92)
print("ORFMOS BIOS GRADIO v0.1.55 — DEVELOPMENT LAUNCH")
print("=" * 92)
print("Front door     : GitHub boot OFF → POWER → READY → COLD BIOS / WARM DESKTOP (BIOS override)")
print("BIOS pages     : SYSTEM / BOOT / RUNTIME / RECOVERY / MAINTENANCE")
print("BIOS sources   : INDEPENDENT KERNEL + ORFMOS ROOT / DRIVE OR GITHUB")
print("Transition     : POWER starts/restarts Kernel → BIOS request window → runtime-class READY route")
print("BIOS preload   : YES — hidden until transition gate opens")
print("BIOS telemetry : LIVE Kernel state + Kernel-owned 1-second pulse")
print("Utilization    : ORF Kernel Colab runtime_environment")
print("Device link     : ORF_DEVICE_SESSION_V0_1 / BROWSER + NATIVE ORF CONSOLE")
print("Device profile  : BROWSER OBSERVED + DEVICE REPORTED / SHARED SESSION")
print("Footer layout   : RESPONSIVE / WRAP-SAFE")
print("Input modes     : TOUCH / MOUSE / KEYBOARD")
print("Keyboard        : arrows navigate • Enter/Space activate • Esc/Backspace return")
print("Control path    : SHARED GRADIO EVENTS")
print("Source module   : ORF_BIOS_SOURCE_SELECTION_V0_1 / DUAL PROVIDER AUTHORITY")
print("Source selector :", RUNTIME_TARGET_FILE_ID)
print("Kernel source   :", (ROOT_INITIAL_STATE.get("kernel_source") or {}).get("provider") or SOURCE_PROVIDER_GITHUB)
print("Root source     :", (ROOT_INITIAL_STATE.get("root_source") or {}).get("provider"))
print("Source apply    : STAGE BUTTONS → APPLY SELECTIONS → DURABLE AUTHORITY")
print("READY check     : LIVE KERNEL READY / COLD BIOS DEFAULT / WARM DESKTOP DEFAULT / BIOS ONE-SHOT OVERRIDE")
print("Runtime class   :", globals().get("ORF_BIOS_RUNTIME_BOOT_CLASS", "UNKNOWN"))
print("Boot default    :", globals().get("ORF_BIOS_BOOT_DEFAULT_TARGET", "DESKTOP"))
print("BIOS stability  : ACTIVE GENERATION + LOCAL HEALTH WATCHDOG")
print("Surface owner    : BOTH MOUNTED / BACKEND CSS OWNER / BROWSER FALLBACK / ZERO-SURFACE FORBIDDEN")
print("Self restart    : 3 consecutive presentation-health failures")
print("READY arm delay :", f"{BOOT_READY_ELIGIBLE_SECONDS:.1f}s total after boot-screen entry")
print("READY eligible  :", f"{BOOT_READY_ELIGIBLE_SECONDS:.1f}s after each boot-screen entry")
print("READY authority : authoritative live Kernel READY; diagnostics cannot veto handoff")
print("READY fallback  :", f"{BOOT_READY_CONFIRMATIONS_REQUIRED} stable reads after {BOOT_READY_STABLE_FALLBACK_SECONDS:.1f}s")
print("Drive latency   : measured per completed heartbeat read")
print("Dev Kernel boot : POWER-GATED USER EVENT / RUNNING KERNEL RESTARTS BEFORE BOOT")
print("Kernel monitor  : RESIDENT / OWNS POWER-REQUESTED RESTART + KERNEL TICK")
print("Kernel capture  : ORF_KERNEL_LOADER_CAPTURE_V0_1 / STDOUT + SHARED RUNTIME")
print("Kernel target   :", (ROOT_INITIAL_STATE.get("kernel") or {}).get("relative_path") or f"{KERNEL_GITHUB_PREFIX}/{KERNEL_NOTEBOOK_NAME}")
print("Kernel verify   : PROVIDER-SPECIFIC SHA256 CHAIN")
print("Maintenance gate: KORF SIGNER CHALLENGE / EPHEMERAL RUNTIME SESSION")
print("Kernel update   : MAINTENANCE-ONLY MANIFEST STAGE/APPLY / MONITOR RESTART")
print("Runtime shutdown: MAINTENANCE-ONLY 10s QUIESCE / WRITE DRAIN / CLIENT BOOT / COLAB DELETE")
print("Device identity : DEVICE-REPORTED PROFILE / UNVERIFIED UNTIL PAIRING AUTHORITY")
print("Shutdown gate  : NEW WRITES LOCKED / IN-FLIGHT WRITES DRAIN / SERVER-OWNED DEADLINE")
print("Backend polls  : 1 per second total / DEACTIVATED BEFORE EXPECTED DISCONNECT")
print("Drive reads    : 1 per second total")
print("Timer topology : CONSOLIDATED BIOS heartbeat + presentation watchdog")
print("User activity  : CONTROL CALLBACK STAMP / 300s RECENT-ACTIVE WINDOW")
print("Kernel reset   : POWER OR BIOS RESET → MONITOR-OWNED APPLIED-SOURCE RERUN")
print("Presentation gen:", ORF_BIOS_PRESENTATION_GENERATION_ID)
print("Mutation path  : STAGED → APPLY SYNTHETIC → VERIFIED")
print("Boot state     : Drive API / ORF_BOOT_STATE_V0_1 / 1 second poll")
print("Device exports : USER-INITIATED DRIVE JSON / DEVICE-SPECIFIC FOLDERS")
print()

import threading
import time
import urllib.request
from urllib.parse import urlsplit
from datetime import datetime, timezone

ORF_PRESENTATION_HEALTH_INTERVAL_SECONDS = 2.0
ORF_PRESENTATION_HEALTH_TIMEOUT_SECONDS = 2.0
ORF_PRESENTATION_HEALTH_FAILURES_BEFORE_RESTART = 3
ORF_PRESENTATION_SUPERSEDE_GRACE_SECONDS = 4.0
ORF_PRESENTATION_RESTART_LIMIT = 2
ORF_USER_ACTIVITY_RECENT_SECONDS = 300.0
ORF_PRESENTATION_LAUNCH_TIMEOUT_SECONDS = 45.0
ORF_PRESENTATION_LAUNCH_ATTEMPTS = 2
ORF_PRESENTATION_LAUNCH_RETRY_DELAY_SECONDS = 2.5
ORF_PRESENTATION_LAUNCH_UNWIND_SECONDS = 4.0


def _user_activity_snapshot():
    record = dict(globals().get("__ORF_BIOS_USER_ACTIVITY__") or {})
    try:
        last_mono = float(record.get("last_interaction_monotonic") or 0.0)
    except Exception:
        last_mono = 0.0
    age = max(0.0, time.monotonic() - last_mono) if last_mono > 0 else None
    record["age_seconds"] = age
    record["recent"] = bool(age is not None and age <= ORF_USER_ACTIVITY_RECENT_SECONDS)
    return record



def _presentation_origin(url):
    url = str(url or "").strip()
    if not url:
        return ""
    try:
        parsed = urlsplit(url)
        return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    except Exception:
        return ""


def _extract_launch_urls(demo_obj, result):
    local_url = str(getattr(demo_obj, "local_url", None) or "")
    share_url = str(getattr(demo_obj, "share_url", None) or "")
    if isinstance(result, (tuple, list)):
        urls = [str(v) for v in result if isinstance(v, str) and v.startswith(("http://", "https://"))]
        if not local_url:
            local_url = next((u for u in urls if "gradio.live" not in u), "")
        if not share_url:
            share_url = next((u for u in urls if "gradio.live" in u), "")
    return local_url, share_url


def _publish_active_presentation(demo_obj, result, generation_id, restart_count=0, reason="LAUNCH"):
    local_url, share_url = _extract_launch_urls(demo_obj, result)
    active_url = share_url or local_url
    record = {
        "schema": ORF_BIOS_PRESENTATION_SCHEMA,
        "generation_id": str(generation_id),
        "state": "ACTIVE",
        "stability": "STABLE",
        "published_utc": datetime.now(timezone.utc).isoformat(),
        "local_url": local_url,
        "share_url": share_url,
        "active_url": active_url,
        "active_origin": _presentation_origin(active_url),
        "health_failures": 0,
        "health_sequence": 0,
        "restart_count": int(restart_count),
        "reason": str(reason),
    }
    globals()["__ORF_BIOS_ACTIVE_PRESENTATION__"] = record
    _emit_kernel_loader_capture(
        "PRESENTATION_ACTIVE",
        generation_id=str(generation_id),
        active_url=active_url,
        restart_count=int(restart_count),
        reason=str(reason),
    )
    print("ORF BIOS PRESENTATION ACTIVE:", generation_id, active_url, flush=True)
    return record


def _probe_presentation(record):
    local_url = str((record or {}).get("local_url") or "")
    if not local_url:
        return False, "NO_LOCAL_URL"
    try:
        request = urllib.request.Request(local_url, method="GET")
        with urllib.request.urlopen(request, timeout=ORF_PRESENTATION_HEALTH_TIMEOUT_SECONDS) as response:
            status = int(getattr(response, "status", 200) or 200)
        return 200 <= status < 500, f"HTTP_{status}"
    except Exception as exc:
        return False, f"{type(exc).__name__}:{exc}"


def _retire_superseded_demo(old_demo, old_generation):
    if old_demo is None:
        return
    time.sleep(ORF_PRESENTATION_SUPERSEDE_GRACE_SECONDS)
    active = globals().get("__ORF_BIOS_ACTIVE_PRESENTATION__") or {}
    if str(active.get("generation_id") or "") == str(old_generation or ""):
        return
    try:
        old_demo.close()
        _emit_kernel_loader_capture(
            "PRESENTATION_RETIRED",
            generation_id=str(old_generation or ""),
        )
        print("ORF BIOS PRESENTATION RETIRED:", old_generation, flush=True)
    except Exception as exc:
        print("ORF BIOS PRESENTATION RETIRE WARNING:", repr(exc), flush=True)


def _kill_gradio_share_tunnels():
    killed = 0
    try:
        import gradio.tunneling as _orf_gradio_tunneling
        for tunnel in list(getattr(_orf_gradio_tunneling, "CURRENT_TUNNELS", []) or []):
            try:
                tunnel.kill()
                killed += 1
            except Exception:
                pass
    except Exception:
        pass
    return killed


def _install_gradio_tunnel_timeout_patch():
    """Bound Gradio 6.20 frpc stdout reads so a silent tunnel cannot hang forever."""
    try:
        import queue as _orf_queue
        import re as _orf_re
        import gradio.tunneling as _orf_tunneling

        tunnel_cls = _orf_tunneling.Tunnel
        if getattr(tunnel_cls, "_orf_nonblocking_timeout_patch", False):
            return "ALREADY_PATCHED"

        def _orf_read_url_from_tunnel_stream(self):
            proc = self.proc
            if proc is None or proc.stdout is None:
                raise ValueError("ORF tunnel patch: tunnel process/stdout unavailable")

            line_queue = _orf_queue.Queue()

            def _reader():
                try:
                    while True:
                        raw = proc.stdout.readline()
                        line_queue.put(raw)
                        if raw == b"":
                            return
                except BaseException as exc:
                    line_queue.put(exc)

            threading.Thread(
                target=_reader,
                name=f"ORF_GRADIO_TUNNEL_STDOUT_{getattr(proc, 'pid', 'UNKNOWN')}",
                daemon=True,
            ).start()

            start = time.monotonic()
            log = []
            timeout_seconds = float(getattr(_orf_tunneling, "TUNNEL_TIMEOUT_SECONDS", 30.0))
            error_prefix = str(
                getattr(
                    _orf_tunneling,
                    "TUNNEL_ERROR_MESSAGE",
                    "Could not create share URL.",
                )
            )

            def _raise(detail):
                log_text = "\\n".join(log)
                suffix = f"\\n{log_text}" if log_text else ""
                raise ValueError(f"{error_prefix} ORF_DETAIL={detail}{suffix}")

            while True:
                elapsed = time.monotonic() - start
                remaining = timeout_seconds - elapsed
                if remaining <= 0:
                    try:
                        self.kill()
                    except Exception:
                        pass
                    _raise(f"TIMEOUT_AFTER_{timeout_seconds:.1f}s")

                try:
                    item = line_queue.get(timeout=min(0.25, max(0.01, remaining)))
                except _orf_queue.Empty:
                    continue

                if isinstance(item, BaseException):
                    _raise(f"STDOUT_READER_{type(item).__name__}")

                raw = item
                if raw == b"":
                    if proc.poll() is not None:
                        _raise(f"FRPC_EXIT_{proc.returncode}")
                    continue

                line = raw.decode("utf-8", errors="replace")
                stripped = line.strip()
                if stripped:
                    log.append(stripped)

                if "start proxy success" in line:
                    result = _orf_re.search(r"start proxy success: (.+?)(?:\\r?\\n)?$", line)
                    if result is None:
                        _raise("SUCCESS_LINE_PARSE_FAILED")
                    return result.group(1).strip()

                if "login to server failed" in line:
                    _raise("LOGIN_TO_SERVER_FAILED")

        tunnel_cls._read_url_from_tunnel_stream = _orf_read_url_from_tunnel_stream
        tunnel_cls._orf_nonblocking_timeout_patch = True
        _emit_kernel_loader_capture(
            "GRADIO_TUNNEL_TIMEOUT_PATCH_INSTALLED",
            gradio_version=str(getattr(gr, "__version__", "UNKNOWN")),
            tunnel_timeout_seconds=float(getattr(_orf_tunneling, "TUNNEL_TIMEOUT_SECONDS", 30.0)),
        )
        print("ORF BIOS GRADIO TUNNEL GUARD: INSTALLED", flush=True)
        return "INSTALLED"
    except Exception as exc:
        _emit_kernel_loader_capture(
            "GRADIO_TUNNEL_TIMEOUT_PATCH_FAILED",
            error=repr(exc),
        )
        print("ORF BIOS GRADIO TUNNEL GUARD WARNING:", repr(exc), flush=True)
        return "FAILED"


def _close_demo_detached(demo_obj, label):
    if demo_obj is None:
        return None

    def _closer():
        try:
            demo_obj.close()
            _emit_kernel_loader_capture("PRESENTATION_DEMO_CLOSE_COMPLETE", label=str(label))
        except Exception as exc:
            _emit_kernel_loader_capture(
                "PRESENTATION_DEMO_CLOSE_FAILED",
                label=str(label),
                error=repr(exc),
            )

    thread = threading.Thread(
        target=_closer,
        name=f"ORF_BIOS_DEMO_CLOSE_{str(label)[-16:]}",
        daemon=True,
    )
    thread.start()
    return thread


def _launch_demo_call(demo_obj, result_box, done_event):
    try:
        result_box["result"] = demo_obj.launch(
            share=True,
            inline=False,
            prevent_thread_lock=True,
        )
    except BaseException as exc:
        result_box["error"] = repr(exc)
    finally:
        done_event.set()


def _launch_demo_bounded(demo_obj, generation_id, attempt, reason):
    result_box = {}
    done_event = threading.Event()
    worker = threading.Thread(
        target=_launch_demo_call,
        args=(demo_obj, result_box, done_event),
        name=f"ORF_BIOS_GRADIO_SERVE_{str(generation_id)[-8:]}_{attempt}",
        daemon=True,
    )
    _emit_kernel_loader_capture(
        "PRESENTATION_LAUNCH_ATTEMPT_BEGIN",
        generation_id=str(generation_id),
        attempt=int(attempt),
        reason=str(reason),
        timeout_seconds=float(ORF_PRESENTATION_LAUNCH_TIMEOUT_SECONDS),
    )
    print(
        f"ORF BIOS GRADIO SERVE ATTEMPT {attempt}/{ORF_PRESENTATION_LAUNCH_ATTEMPTS}: BEGIN",
        flush=True,
    )
    worker.start()

    if done_event.wait(ORF_PRESENTATION_LAUNCH_TIMEOUT_SECONDS):
        if "error" in result_box:
            return False, None, "ERROR", str(result_box["error"])
        launch_result = result_box.get("result")
        local_url, share_url = _extract_launch_urls(demo_obj, launch_result)
        if not share_url:
            return False, launch_result, "NO_SHARE_URL", local_url or "UNRESOLVED_LOCAL_URL"
        return True, launch_result, "COMPLETE", share_url

    local_url = str(getattr(demo_obj, "local_url", None) or "")
    share_url = str(getattr(demo_obj, "share_url", None) or "")
    phase = "SHARE_TUNNEL" if local_url else "LOCAL_SERVER_OR_STARTUP_EVENTS"
    killed = _kill_gradio_share_tunnels()
    _emit_kernel_loader_capture(
        "PRESENTATION_LAUNCH_TIMEOUT",
        generation_id=str(generation_id),
        attempt=int(attempt),
        reason=str(reason),
        phase=phase,
        local_url=local_url,
        share_url=share_url,
        killed_tunnels=int(killed),
    )
    print(
        "ORF BIOS GRADIO SERVE TIMEOUT:",
        f"phase={phase}",
        f"attempt={attempt}",
        f"local={local_url or 'UNRESOLVED'}",
        f"tunnels_killed={killed}",
        flush=True,
    )
    _close_demo_detached(demo_obj, f"TIMEOUT_ATTEMPT_{attempt}")
    return False, None, "TIMEOUT", phase


def _presentation_launch_supervisor(
    first_demo,
    generation_id,
    restart_count=0,
    reason="NOTEBOOK_LAUNCH",
    retire_demo=None,
    retire_generation=None,
):
    candidate = first_demo
    last_kind = "UNSTARTED"
    last_detail = ""

    for attempt in range(1, ORF_PRESENTATION_LAUNCH_ATTEMPTS + 1):
        if candidate is None:
            candidate = build_bios_demo(generation_id)

        ok, launch_result, last_kind, last_detail = _launch_demo_bounded(
            candidate, generation_id, attempt, reason
        )
        if ok:
            globals()["demo"] = candidate
            globals()["ORF_BIOS_PRESENTATION_GENERATION_ID"] = generation_id
            _publish_active_presentation(
                candidate,
                launch_result,
                generation_id,
                restart_count=restart_count,
                reason=reason,
            )
            _start_presentation_watchdog(candidate, generation_id, restart_count)
            if retire_demo is not None and retire_demo is not candidate:
                threading.Thread(
                    target=_retire_superseded_demo,
                    args=(retire_demo, retire_generation),
                    name=f"ORF_BIOS_RETIRE_{str(retire_generation or '')[-8:]}",
                    daemon=True,
                ).start()
            _emit_kernel_loader_capture(
                "PRESENTATION_LAUNCH_SUPERVISOR_COMPLETE",
                generation_id=str(generation_id),
                attempt=int(attempt),
                restart_count=int(restart_count),
                reason=str(reason),
            )
            return

        _emit_kernel_loader_capture(
            "PRESENTATION_LAUNCH_ATTEMPT_FAILED",
            generation_id=str(generation_id),
            attempt=int(attempt),
            failure_kind=str(last_kind),
            detail=str(last_detail),
            reason=str(reason),
        )
        _close_demo_detached(candidate, f"FAILED_ATTEMPT_{attempt}_{last_kind}")
        candidate = None
        if attempt < ORF_PRESENTATION_LAUNCH_ATTEMPTS:
            print(
                f"ORF BIOS GRADIO SERVE: RETRYING AFTER {ORF_PRESENTATION_LAUNCH_RETRY_DELAY_SECONDS:.1f}s",
                flush=True,
            )
            time.sleep(ORF_PRESENTATION_LAUNCH_RETRY_DELAY_SECONDS)

    failed = dict(globals().get("__ORF_BIOS_ACTIVE_PRESENTATION__") or {})
    failed.update({
        "schema": ORF_BIOS_PRESENTATION_SCHEMA,
        "generation_id": str(generation_id),
        "state": "FAILED",
        "stability": "PRESENTATION_LAUNCH_FAILED",
        "restart_count": int(restart_count),
        "reason": str(reason),
        "launch_failure_kind": str(last_kind),
        "launch_failure_detail": str(last_detail),
        "failed_utc": datetime.now(timezone.utc).isoformat(),
    })
    globals()["__ORF_BIOS_ACTIVE_PRESENTATION__"] = failed
    _emit_kernel_loader_capture(
        "PRESENTATION_LAUNCH_FAILED",
        generation_id=str(generation_id),
        restart_count=int(restart_count),
        reason=str(reason),
        failure_kind=str(last_kind),
        detail=str(last_detail),
    )
    print(
        "ORF BIOS PRESENTATION FAILED TO SERVE AFTER BOUNDED RETRIES:",
        last_kind,
        last_detail,
        flush=True,
    )


def _launch_replacement_presentation(failed_demo, failed_generation, restart_count):
    active = globals().get("__ORF_BIOS_ACTIVE_PRESENTATION__") or {}
    if str(active.get("generation_id") or "") != str(failed_generation):
        return

    active["state"] = "RESTARTING"
    active["stability"] = "FAILED_PRESENTATION_STABILITY"
    globals()["__ORF_BIOS_ACTIVE_PRESENTATION__"] = active
    _emit_kernel_loader_capture(
        "PRESENTATION_STABILITY_FAILED",
        generation_id=str(failed_generation),
        health_failures=int(active.get("health_failures") or 0),
        restart_count=int(restart_count),
    )

    if int(restart_count) > ORF_PRESENTATION_RESTART_LIMIT:
        active["state"] = "FAILED"
        active["stability"] = "RESTART_LIMIT_EXCEEDED"
        globals()["__ORF_BIOS_ACTIVE_PRESENTATION__"] = active
        print("ORF BIOS PRESENTATION FAILED: restart limit exceeded", flush=True)
        return

    new_generation = _new_presentation_generation_id()
    replacement_demo = build_bios_demo(new_generation)
    thread = threading.Thread(
        target=_presentation_launch_supervisor,
        args=(
            replacement_demo,
            new_generation,
            int(restart_count),
            "SELF_PRESERVATION_RESTART",
            failed_demo,
            failed_generation,
        ),
        name=f"ORF_BIOS_PRESENTATION_RESTART_{str(new_generation)[-8:]}",
        daemon=True,
    )
    thread.start()
    globals()["__ORF_BIOS_PRESENTATION_RESTART_THREAD__"] = thread
    _emit_kernel_loader_capture(
        "PRESENTATION_SELF_RESTART_DETACHED",
        previous_generation=str(failed_generation),
        generation_id=str(new_generation),
        restart_count=int(restart_count),
    )


def _presentation_watchdog(demo_obj, generation_id, restart_count):
    consecutive_failures = 0
    while True:
        time.sleep(ORF_PRESENTATION_HEALTH_INTERVAL_SECONDS)
        active = globals().get("__ORF_BIOS_ACTIVE_PRESENTATION__") or {}
        if str(active.get("generation_id") or "") != str(generation_id):
            return
        if str(active.get("state") or "").upper() != "ACTIVE":
            return

        quiesce_reader = globals().get("system_quiesce_status")
        quiesce = dict(quiesce_reader() or {}) if callable(quiesce_reader) else {"state": "RUNNING"}
        if str(quiesce.get("state") or "RUNNING").upper() != "RUNNING":
            active = dict(active)
            active["stability"] = "QUIESCING"
            active["shutdown_state"] = quiesce.get("state")
            globals()["__ORF_BIOS_ACTIVE_PRESENTATION__"] = active
            _emit_kernel_loader_capture(
                "PRESENTATION_WATCHDOG_QUIESCED",
                generation_id=str(generation_id),
                shutdown_state=quiesce.get("state"),
            )
            return

        user_activity = _user_activity_snapshot()
        healthy, detail = _probe_presentation(active)
        active = dict(active)
        active["health_sequence"] = int(active.get("health_sequence") or 0) + 1
        active["last_health_utc"] = datetime.now(timezone.utc).isoformat()
        active["last_health_detail"] = detail
        active["user_activity_sequence"] = int(user_activity.get("sequence") or 0)
        active["last_user_interaction_utc"] = user_activity.get("last_interaction_utc")
        active["last_user_action"] = user_activity.get("action")
        active["user_activity_age_seconds"] = user_activity.get("age_seconds")
        active["user_active_recent"] = bool(user_activity.get("recent"))

        if healthy:
            consecutive_failures = 0
            active["health_failures"] = 0
            active["stability"] = "STABLE"
        else:
            consecutive_failures += 1
            active["health_failures"] = consecutive_failures
            active["stability"] = "DEGRADED_PRESENTATION_STABILITY"

        globals()["__ORF_BIOS_ACTIVE_PRESENTATION__"] = active

        if consecutive_failures >= ORF_PRESENTATION_HEALTH_FAILURES_BEFORE_RESTART:
            _launch_replacement_presentation(
                demo_obj,
                generation_id,
                int(restart_count) + 1,
            )
            return


def _start_presentation_watchdog(demo_obj, generation_id, restart_count=0):
    thread = threading.Thread(
        target=_presentation_watchdog,
        args=(demo_obj, generation_id, restart_count),
        name=f"ORF_BIOS_PRESENTATION_WATCH_{str(generation_id)[-8:]}",
        daemon=True,
    )
    thread.start()
    globals()["__ORF_BIOS_PRESENTATION_WATCHDOG_THREAD__"] = thread
    return thread


ORF_BIOS_GRADIO_TUNNEL_PATCH_STATE = _install_gradio_tunnel_timeout_patch()
ORF_BIOS_STALE_TUNNELS_KILLED = _kill_gradio_share_tunnels()
_emit_kernel_loader_capture(
    "PRESENTATION_PRELAUNCH_TUNNEL_CLEANUP",
    killed_tunnels=int(ORF_BIOS_STALE_TUNNELS_KILLED),
    patch_state=str(ORF_BIOS_GRADIO_TUNNEL_PATCH_STATE),
)
print(
    "ORF BIOS GRADIO PRELAUNCH CLEANUP:",
    f"stale_tunnels_killed={ORF_BIOS_STALE_TUNNELS_KILLED}",
    f"tunnel_guard={ORF_BIOS_GRADIO_TUNNEL_PATCH_STATE}",
    flush=True,
)


ORF_BIOS_PRESENTATION_LAUNCH_THREAD = threading.Thread(
    target=_presentation_launch_supervisor,
    args=(
        demo,
        ORF_BIOS_PRESENTATION_GENERATION_ID,
        0,
        "NOTEBOOK_LAUNCH",
        __ORF_BIOS_PREVIOUS_DEMO__,
        __ORF_BIOS_PREVIOUS_PRESENTATION_GENERATION__,
    ),
    name=f"ORF_BIOS_PRESENTATION_LAUNCH_{str(ORF_BIOS_PRESENTATION_GENERATION_ID)[-8:]}",
    daemon=True,
)
ORF_BIOS_PRESENTATION_LAUNCH_THREAD.start()
globals()["__ORF_BIOS_PRESENTATION_LAUNCH_THREAD__"] = ORF_BIOS_PRESENTATION_LAUNCH_THREAD
_emit_kernel_loader_capture(
    "PRESENTATION_LAUNCH_DETACHED",
    generation_id=str(ORF_BIOS_PRESENTATION_GENERATION_ID),
    timeout_seconds=float(ORF_PRESENTATION_LAUNCH_TIMEOUT_SECONDS),
    attempts=int(ORF_PRESENTATION_LAUNCH_ATTEMPTS),
    kernel_boot_blocked=False,
)
print(
    "ORF BIOS GRADIO SERVE: DETACHED / BOUNDED — LOADER MAY CONTINUE",
    flush=True,
)

# Kernel bootstrap ownership intentionally stops here.
# Presentation establishment is detached and bounded. The boot-screen POWER
# event now requests Kernel execution through the shared power-start contract;
# the one-cell loader no longer autostarts the Kernel.
_emit_kernel_loader_capture(
    "PRESENTATION_MODULE_RETURNING",
    generation_id=str(ORF_BIOS_PRESENTATION_GENERATION_ID),
    kernel_boot_owner="BOOT_SCREEN_POWER_EVENT",
)
print("ORF BIOS PRESENTATION MODULE: RETURNING TO LOADER", flush=True)

