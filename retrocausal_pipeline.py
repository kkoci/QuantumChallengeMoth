"""
retrocausal_pipeline.py

Moth Hack 2026 — challenges 09 (Quantum-native 1) and 10 (Quantum-native 2).

Two-phase pipeline against the Retrocausal Echo engine (retrocausal-echo-v1):

  Phase 1 — MEASURE
    Sweep theta_x (how "quantum" the taps are) and theta_zz (coupling) across
    a small preset grid. Each preset is one real quantum measurement (Aer by
    default, no IBM token needed). We save:
      - the impulse response itself, as a .json "trajectory" envelope (the
        `ir` output) — this is what lets us re-render for free later
      - a reference WAV of the IR alone (the effect's own impulse, no input
        audio) so you can audition presets without re-rendering anything
      - the tap map as JSON (the `taps` output) for inspection / the notebook

  Phase 2 — RENDER
    Take a real audio file and run it through every saved IR from Phase 1.
    Passing a saved `ir` asset id means the engine skips the quantum
    measurement entirely (per their own docs: "Re-render a measured response
    ... without paying for the measurement again") — so this phase is fast
    and cheap regardless of how many presets you measured.

Usage
-----
    export MOTH_API_KEY=moth_...          # bash
    $env:MOTH_API_KEY="moth_..."          # PowerShell

    python retrocausal_pipeline.py measure
    python retrocausal_pipeline.py render path/to/your_audio.wav

Everything lands under ./output/, organized by preset name. output/presets.json
is the manifest the render phase reads to know which IR asset ids exist —
it's also the thing you'd hand to a notebook to reproduce challenge 10.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

API = "https://api.mothquantum.com/api/v1"
ENGINE = "retrocausal-echo-v1"
OUT_DIR = Path("output")
MANIFEST_PATH = OUT_DIR / "presets.json"

# Cloudflare 403s a bare Python-urllib user agent, per Moth's own code sample.
# Always identify the client, always print response bodies on error.
USER_AGENT = "moth-hack-retrocausal-pipeline/1.0"


def api_key() -> str:
    key = os.environ.get("MOTH_API_KEY")
    if not key:
        sys.exit("MOTH_API_KEY is not set. Export it first.")
    return key


def headers() -> dict:
    return {"Authorization": f"Bearer {api_key()}", "User-Agent": USER_AGENT}


def check(resp: requests.Response) -> dict:
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:800]}")
    return resp.json()


# ---------------------------------------------------------------------------
# Assets: upload / download
# ---------------------------------------------------------------------------

def upload_asset(path: Path, content_type: str) -> str:
    """Register, PUT, complete. Returns the asset id."""
    size = path.stat().st_size
    reg = check(requests.post(
        f"{API}/assets",
        headers=headers(),
        json={"filename": path.name, "content_type": content_type, "size_bytes": size},
    ))
    up = reg["upload"]
    with open(path, "rb") as fh:
        r = requests.put(up["url"], data=fh, headers=up["headers"])
        if not r.ok:
            raise RuntimeError(f"upload HTTP {r.status_code}: {r.text[:400]}")
    check(requests.post(f"{API}/assets/{reg['asset_id']}/complete", headers=headers()))
    return reg["asset_id"]


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url)
    r.raise_for_status()
    dest.write_bytes(r.content)


# ---------------------------------------------------------------------------
# Job submission
# ---------------------------------------------------------------------------

def run_job(params: dict, input_files: dict | None = None) -> tuple[str, dict]:
    """Submit a job, poll to completion, return (job_id, result_body)."""
    submitted = check(requests.post(
        f"{API}/engines/{ENGINE}/process",
        headers=headers(),
        json={"params": params, "input_files": input_files or {}},
    ))
    job_id = submitted["job_id"]

    while True:
        status = check(requests.get(f"{API}/jobs/{job_id}/status", headers=headers()))
        if status["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(2)

    if status["status"] != "completed":
        err = (status.get("error") or {}).get("message")
        raise RuntimeError(f"job {job_id} ended {status['status']}: {err}")

    result = check(requests.get(f"{API}/jobs/{job_id}/result", headers=headers()))
    return job_id, result


def outputs_by_slot(result: dict) -> dict:
    return {o["slot"]: o for o in (result.get("outputs") or [])}


def asset_id_of(output_entry: dict) -> str:
    """Their two docs disagree on the field name (asset_id vs
    output_asset_id) — accept either."""
    aid = output_entry.get("asset_id") or output_entry.get("output_asset_id")
    if not aid:
        raise KeyError(f"no asset id in output entry: {output_entry}")
    return aid


# ---------------------------------------------------------------------------
# Phase 1 — measure a preset grid of impulse responses
# ---------------------------------------------------------------------------

# Sweep across theta_x (how quantum: low=regular taps, high=erased/inverted)
# and theta_zz (coupling: ~0.25*pi is the sparse setting, pi is Clifford / no
# scrambling). Keep this small on purpose — each entry is one real
# measurement job. Add more once you know these render the way you expect.
PI = 3.141592653589793

PRESETS: list[dict[str, Any]] = [
    {
        "name": "sparse_gentle",
        "params": {
            "theta_x": 0.35, "theta_zz": 0.25 * PI, "negative_mode": "invert",
            "n_sites": 8, "depth": 8, "ir_seconds": 4,
        },
    },
    {
        "name": "default_drive",
        "params": {
            # engine defaults for theta_x / theta_zz, explicit here for clarity
            "theta_x": 0.9424777960769379, "theta_zz": 1.0995574287564276,
            "negative_mode": "invert", "n_sites": 8, "depth": 8, "ir_seconds": 4,
        },
    },
    {
        "name": "high_erasure",
        "params": {
            "theta_x": 2.4, "theta_zz": 1.0995574287564276,
            "negative_mode": "invert", "n_sites": 8, "depth": 8, "ir_seconds": 4,
        },
    },
    {
        "name": "reverse_grains",
        "params": {
            "theta_x": 1.2, "theta_zz": 0.25 * PI, "negative_mode": "reverse",
            "grain_ms": 150, "n_sites": 8, "depth": 8, "ir_seconds": 4,
        },
    },
    {
        "name": "phase_rotate",
        "params": {
            "theta_x": 1.2, "theta_zz": 0.6, "theta_z": 0.6,
            "negative_mode": "phase", "n_sites": 8, "depth": 8, "ir_seconds": 4,
        },
    },
    {
        "name": "square_lattice",
        "params": {
            "lattice": "square", "width": 5, "height": 4, "depth": 6,
            "diffusion_ms": 40, "theta_x": 1.0, "theta_zz": 0.25 * PI,
            "negative_mode": "invert", "ir_seconds": 4,
        },
    },
]


def measure_one(name: str, params: dict, manifest: dict) -> None:
    """Run one measurement job, save its files, and update + persist the
    manifest in place. Shared by `measure` (fixed preset grid) and `sweep`
    (parameter search around a point)."""
    preset_dir = OUT_DIR / name
    print(f"[measure] {name} :: {params}")

    job_id, result = run_job(params)
    outs = outputs_by_slot(result)

    download(outs["result"]["url"], preset_dir / "ir_reference.wav")
    download(outs["ir"]["url"], preset_dir / "ir.json")
    download(outs["taps"]["url"], preset_dir / "taps.json")

    ir_asset_id = asset_id_of(outs["ir"])
    manifest[name] = {
        "job_id": job_id,
        "params": params,
        "ir_asset_id": ir_asset_id,
        "ir_reference_wav": str(preset_dir / "ir_reference.wav"),
        "ir_json": str(preset_dir / "ir.json"),
        "taps_json": str(preset_dir / "taps.json"),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    print(f"         -> {preset_dir}/  (ir_asset_id={ir_asset_id})")


def measure_presets() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    manifest: dict[str, dict] = {}
    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text())

    for preset in PRESETS:
        measure_one(preset["name"], preset["params"], manifest)

    print(f"\nDone. {len(PRESETS)} presets measured. Manifest: {MANIFEST_PATH}")


def sweep_theta_x(center: float, steps: int, span: float, base_preset: str) -> None:
    """Measure `steps` points of theta_x centred on `center` (clamped to the
    engine's [0, pi] range), keeping every other param fixed from an
    existing preset in PRESETS (default: high_erasure — the one you're
    refining around). Named theta_x_<value> so repeated sweeps don't clash."""
    OUT_DIR.mkdir(exist_ok=True)
    manifest: dict[str, dict] = {}
    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text())

    base = next((p["params"] for p in PRESETS if p["name"] == base_preset), None)
    if base is None:
        sys.exit(f"No such base preset: {base_preset!r}. Options: "
                  f"{[p['name'] for p in PRESETS]}")

    if steps < 2:
        points = [center]
    else:
        half = span / 2
        lo, hi = max(0.0, center - half), min(PI, center + half)
        points = [lo + i * (hi - lo) / (steps - 1) for i in range(steps)]

    for theta_x in points:
        params = {**base, "theta_x": round(theta_x, 4)}
        name = f"theta_x_{theta_x:.3f}".replace(".", "p")
        measure_one(name, params, manifest)

    print(f"\nDone. {len(points)} points swept around theta_x={center}. "
          f"Manifest: {MANIFEST_PATH}")


# ---------------------------------------------------------------------------
# Phase 2 — render real audio through every saved IR (no re-measurement)
# ---------------------------------------------------------------------------

# Their render length cap is 180s INCLUDING the tail appended for the last
# tap/regeneration to ring out, so the safe ceiling for raw input is lower
# than 180. Trim to this by default unless the caller overrides it.
DEFAULT_MAX_SECONDS = 150


def trim_with_ffmpeg(src: Path, max_seconds: float) -> Path:
    import shutil
    import subprocess

    if shutil.which("ffmpeg") is None:
        sys.exit(
            f"{src} may be longer than the engine's render cap and ffmpeg "
            "isn't on PATH to auto-trim it. Install ffmpeg, or trim the "
            "file yourself first, e.g.:\n"
            f"  ffmpeg -i \"{src}\" -t {max_seconds} \"{src.stem}_trimmed{src.suffix}\""
        )
    trimmed = src.with_name(f"{src.stem}_trimmed{src.suffix}")
    print(f"[trim] {src} -> {trimmed} (first {max_seconds}s)")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-t", str(max_seconds), str(trimmed)],
        check=True, capture_output=True,
    )
    return trimmed


def render_over_audio(
    audio_path: Path,
    mix_params: dict | None = None,
    max_seconds: float | None = DEFAULT_MAX_SECONDS,
) -> None:
    if not MANIFEST_PATH.exists():
        sys.exit("No presets.json manifest found — run `measure` first.")
    manifest = json.loads(MANIFEST_PATH.read_text())
    if not manifest:
        sys.exit("Manifest is empty — run `measure` first.")

    if max_seconds is not None:
        import wave
        import contextlib

        duration = None
        if audio_path.suffix.lower() == ".wav":
            try:
                with contextlib.closing(wave.open(str(audio_path), "rb")) as wf:
                    duration = wf.getnframes() / wf.getframerate()
            except wave.Error:
                duration = None  # not a plain PCM wav ffmpeg/wave can read directly
        if duration is None or duration > max_seconds:
            audio_path = trim_with_ffmpeg(audio_path, max_seconds)

    content_type = {
        ".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".flac": "audio/flac",
    }.get(audio_path.suffix.lower(), "audio/wav")

    print(f"[upload] {audio_path}")
    audio_asset_id = upload_asset(audio_path, content_type)

    mix_params = mix_params or {"mix": 0.7, "feedback": 0.4}

    for name, entry in manifest.items():
        print(f"[render] {name}")
        job_id, result = run_job(
            mix_params,
            input_files={"audio": audio_asset_id, "ir": entry["ir_asset_id"]},
        )
        outs = outputs_by_slot(result)
        dest = Path(entry["ir_reference_wav"]).parent / f"rendered_{audio_path.stem}.wav"
        download(outs["result"]["url"], dest)
        print(f"         -> {dest}")

    print("\nDone. Rendered audio sits next to each preset's reference IR.")


# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("measure", help="Measure the preset grid of impulse responses.")

    sweep_cmd = sub.add_parser(
        "sweep", help="Measure a range of theta_x values around a point, "
                      "keeping other params fixed from an existing preset."
    )
    sweep_cmd.add_argument("--center", type=float, required=True, help="theta_x to centre on.")
    sweep_cmd.add_argument("--steps", type=int, default=5, help="Number of points (default 5).")
    sweep_cmd.add_argument("--span", type=float, default=0.8,
                            help="Total width of the sweep in radians (default 0.8).")
    sweep_cmd.add_argument("--base", default="high_erasure",
                            help="Existing preset to copy other params from (default high_erasure).")

    render_cmd = sub.add_parser("render", help="Render an audio file through every saved IR.")
    render_cmd.add_argument("audio_path", type=Path)
    render_cmd.add_argument("--mix", type=float, default=0.7)
    render_cmd.add_argument("--feedback", type=float, default=0.4)
    render_cmd.add_argument(
        "--max-seconds", type=float, default=DEFAULT_MAX_SECONDS,
        help=f"Auto-trim input to this length before upload (default {DEFAULT_MAX_SECONDS}s, "
             "leaves headroom under the engine's 180s-including-tail cap). Requires ffmpeg "
             "on PATH when trimming is actually needed.",
    )
    render_cmd.add_argument(
        "--no-trim", action="store_true",
        help="Skip the length check entirely and upload as-is.",
    )

    args = parser.parse_args()

    if args.command == "measure":
        measure_presets()
    elif args.command == "sweep":
        sweep_theta_x(args.center, args.steps, args.span, args.base)
    elif args.command == "render":
        if not args.audio_path.exists():
            sys.exit(f"No such file: {args.audio_path}")
        render_over_audio(
            args.audio_path,
            {"mix": args.mix, "feedback": args.feedback},
            max_seconds=None if args.no_trim else args.max_seconds,
        )


if __name__ == "__main__":
    main()
