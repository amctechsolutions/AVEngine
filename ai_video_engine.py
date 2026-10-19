#!/usr/bin/env python3
"""
AI Video Generation Engine (Multi-Provider: Fal.ai, RunPod, and Local)
======================================================================
Unified high-performance video generation bridge for FirstSignal Faceless Studio:
- Choice 1: Fal.ai API (Wan 2.1 / LTX-Video / Flux) via programmatic Python SDK.
- Choice 3: RunPod Cloud GPU Worker (On-demand RTX 4090 / ComfyUI / Serverless) with 0% censorship.
- Choice Local: High-speed 2.5D FFmpeg motion cards (100% $0 sovereign fallback).

Usage:
  # Standalone CLI
  python3 ai_video_engine.py --prompt "Roman galley warship slicing through stormy Mediterranean sea, 4k cinematic" --engine fal --model wan2.1 --output scene1.mp4

  # In Python:
  from ai_video_engine import generate_scene_video
  video_file = generate_scene_video(prompt="...", engine="auto")
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional, Dict, Any

KEYS_FILE = Path.home() / ".ai_video_keys.json"
CACHE_DIR = Path.home() / "faceless_content" / "video_cache"


# --------------------------------------------------------------------------- Credentials Manager
def load_keys() -> Dict[str, str]:
    keys = {}
    if KEYS_FILE.exists():
        try:
            with open(KEYS_FILE, "r") as f:
                keys = json.load(f)
        except Exception:
            pass
    # Environment variables override config file
    if "FAL_KEY" in os.environ:
        keys["fal"] = os.environ["FAL_KEY"]
    if "RUNPOD_API_KEY" in os.environ:
        keys["runpod_api_key"] = os.environ["RUNPOD_API_KEY"]
    if "RUNPOD_POD_URL" in os.environ:
        keys["runpod_pod_url"] = os.environ["RUNPOD_POD_URL"]
    return keys


def save_key(service: str, key_val: str):
    keys = load_keys()
    keys[service] = key_val
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(KEYS_FILE, "w") as f:
        json.dump(keys, f, indent=2)
    os.chmod(KEYS_FILE, 0o600)
    print(f"✅ Saved API key for '{service}' to {KEYS_FILE}")


def get_active_engine() -> str:
    keys = load_keys()
    if keys.get("fal"):
        return "fal"
    if keys.get("runpod_pod_url") and _pod_alive(keys["runpod_pod_url"]):
        return "runpod"
    return "local"


def _pod_alive(pod_url: str, timeout: float = 4.0) -> bool:
    """Cheap reachability probe so a stopped/terminated pod never stalls a run for 300s."""
    try:
        import requests
        r = requests.get(pod_url.rstrip("/") + "/", timeout=timeout)
        return r.status_code < 500
    except Exception:
        print(f"⚠️ RunPod pod unreachable ({pod_url}); falling back.")
        return False


# --------------------------------------------------------------------------- Engine 1: Fal.ai (Wan 2.1 / LTX-Video)
def generate_with_fal(prompt: str, output_path: str, model: str = "wan2.1", aspect_ratio: str = "9:16", duration: int = 5) -> str:
    """
    Renders video via Fal.ai API.
    Supported models:
      - 'wan2.1': Alibaba Wan 2.1 text-to-video (Highest cinematic quality & physics)
      - 'ltx': Lightricks LTX-Video (Ultra-fast, ~3-4 seconds per render)
      - 'hunyuan': Tencent Hunyuan Video
    """
    keys = load_keys()
    fal_key = keys.get("fal")
    if not fal_key:
        raise ValueError(
            "Fal.ai API key not found. Set FAL_KEY in your environment or run:\n"
            "python3 ai_video_engine.py --set-key fal YOUR_FAL_KEY"
        )
    os.environ["FAL_KEY"] = fal_key

    try:
        import fal_client
    except ImportError:
        raise RuntimeError("fal_client is not installed. Run: pip3 install fal-client")

    model_endpoints = {
        "wan2.1": "fal-ai/wan/v2.1/text-to-video",
        "wan": "fal-ai/wan/v2.1/text-to-video",
        "ltx": "fal-ai/ltx-video",
        "hunyuan": "fal-ai/hunyuan-video"
    }
    endpoint = model_endpoints.get(model.lower(), "fal-ai/wan/v2.1/text-to-video")

    print(f"🚀 [Fal.ai] Submitting prompt to {endpoint} (Aspect Ratio: {aspect_ratio})...")
    print(f"   Prompt: \"{prompt[:90]}...\"")

    arguments: Dict[str, Any] = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio
    }

    t0 = time.time()
    try:
        result = fal_client.subscribe(endpoint, arguments=arguments)
    except Exception as e:
        # Fallback to LTX if Wan is temporarily busy or rate-limited
        if model != "ltx" and "ltx" in model_endpoints:
            print(f"⚠️ Wan 2.1 encountered an issue ({e}). Retrying with fast LTX-Video...")
            endpoint = model_endpoints["ltx"]
            result = fal_client.subscribe(endpoint, arguments=arguments)
        else:
            raise e

    elapsed = time.time() - t0
    print(f"⚡ [Fal.ai] Generation complete in {elapsed:.1f}s!")

    video_url = None
    if isinstance(result, dict):
        if "video" in result and isinstance(result["video"], dict) and "url" in result["video"]:
            video_url = result["video"]["url"]
        elif "url" in result:
            video_url = result["url"]

    if not video_url:
        raise RuntimeError(f"Could not extract video URL from Fal.ai response: {result}")

    print(f"📥 Downloading video from {video_url[:60]}... -> {output_path}")
    urllib.request.urlretrieve(video_url, output_path)
    return output_path


# --------------------------------------------------------------------------- Engine 3: RunPod Cloud Worker
def generate_with_runpod(prompt: str, output_path: str, aspect_ratio: str = "9:16", duration: int = 5) -> str:
    """
    Renders video via an on-demand RunPod GPU worker (RTX 4090 / ComfyUI / Wan 2.1).
    Censorship: 0% unrestricted.
    """
    import requests
    keys = load_keys()
    pod_url = keys.get("runpod_pod_url")
    api_key = keys.get("runpod_api_key")

    if not pod_url and not api_key:
        raise ValueError(
            "RunPod configuration not found. Set RUNPOD_POD_URL or RUNPOD_API_KEY:\n"
            "python3 ai_video_engine.py --set-key runpod_pod_url https://YOUR-POD-ID-8188.proxy.runpod.net"
        )

    # 1. Dedicated Pod with FastAPI / ComfyUI bridge
    if pod_url:
        target_endpoint = f"{pod_url.rstrip('/')}/generate_video"
        print(f"🚀 [RunPod GPU] Sending prompt to dedicated pod: {target_endpoint}...")
        payload = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "disable_safety_checker": os.environ.get("AI_VIDEO_DISABLE_SAFETY") == "1"
        }
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        resp = requests.post(target_endpoint, json=payload, headers=headers, timeout=300)
        resp.raise_for_status()
        data = resp.json()
        
        video_url = data.get("video_url")
        if video_url:
            urllib.request.urlretrieve(video_url, output_path)
        elif "video_base64" in data:
            import base64
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(data["video_base64"]))
        else:
            raise RuntimeError(f"RunPod response missing video data: {data}")
        return output_path

    # UNVERIFIED: the /generate_video pod server has not been exercised end to end.
    raise RuntimeError("RunPod needs runpod_pod_url set to a pod running a /generate_video server.")


# --------------------------------------------------------------------------- Engine Fallback: Local 2.5D Motion (FFmpeg)
def generate_with_local(prompt: str, output_path: str, aspect_ratio: str = "9:16", duration: int = 5) -> str:
    """
    $0 Local Mac Fallback:
    Generates a dark cinematic gradient background with slow parallax pan & zoom.
    Guaranteed zero network dependencies, runs in ~1.5 seconds.
    Supports 9:16 (Shorts/TikTok), 16:9 (YouTube long-form), 1:1 (Square/Feed).
    """
    res_map = {
        "9:16": (1080, 1920),
        "16:9": (1920, 1080),
        "1:1": (1080, 1080),
        "4:5": (1080, 1350)
    }
    w, h = res_map.get(aspect_ratio, (1080, 1920))
    ffmpeg = shutil.which("ffmpeg") or str(Path.home() / "bin" / "ffmpeg")
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi",
        "-i", f"color=c=0x0a0f1d:s={w}x{h}:d={duration}",
        "-vf", f"zoompan=z='min(zoom+0.0015,1.25)':d={duration*30}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h},format=yuv420p",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        output_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path


# --------------------------------------------------------------------------- Unified Dispatcher & Cache
_paid_clips = 0


def _max_paid_clips() -> int:
    return int(os.environ.get("AI_VIDEO_MAX_PAID_CLIPS", "12"))


def generate_scene_video(prompt: str, output_path: Optional[str] = None, engine: str = "auto", model: str = "wan2.1", aspect_ratio: str = "9:16", duration: int = 5) -> str:
    """
    Main entry point for generating scene videos with prompt-level caching.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    prompt_hash = hashlib.sha256(f"{prompt}_{model}_{aspect_ratio}_{duration}".encode()).hexdigest()[:16]
    cached_file = CACHE_DIR / f"clip_{prompt_hash}.mp4"

    if output_path is None:
        output_path = str(cached_file)

    if cached_file.exists() and cached_file.stat().st_size > 10000:
        print(f"📦 [Cache Hit] Reusing generated scene for prompt: \"{prompt[:50]}...\"")
        if output_path != str(cached_file):
            shutil.copy2(cached_file, output_path)
        return output_path

    target_engine = engine.lower()
    if target_engine == "auto":
        target_engine = get_active_engine()

    print(f"\n🎬 [AI Video Engine] Dispatched to: {target_engine.upper()} (Aspect: {aspect_ratio})")

    global _paid_clips
    if target_engine in ("fal", "runpod"):
        if os.environ.get("AI_VIDEO_DRY_RUN") == "1":
            print(f"🧪 [Dry Run] Would render on {target_engine}; using local.")
            target_engine = "local"
        elif _paid_clips >= _max_paid_clips():
            print(f"💸 Paid-clip cap ({_max_paid_clips()}) reached; using local.")
            target_engine = "local"
        else:
            _paid_clips += 1

    if target_engine == "fal":
        result = generate_with_fal(prompt, output_path, model=model, aspect_ratio=aspect_ratio, duration=duration)
    elif target_engine == "runpod":
        result = generate_with_runpod(prompt, output_path, aspect_ratio=aspect_ratio, duration=duration)
    else:
        result = generate_with_local(prompt, output_path, aspect_ratio=aspect_ratio, duration=duration)

    # Save to cache if different
    if output_path != str(cached_file) and Path(output_path).exists():
        shutil.copy2(output_path, cached_file)

    return result


# --------------------------------------------------------------------------- CLI Entry Point
def main():
    parser = argparse.ArgumentParser(description="FirstSignal Multi-Engine AI Video Generator")
    parser.add_argument("--prompt", type=str, help="Visual text prompt describing the scene")
    parser.add_argument("--engine", type=str, default="auto", choices=["auto", "fal", "runpod", "local"], help="Generation engine")
    parser.add_argument("--model", type=str, default="wan2.1", choices=["wan2.1", "ltx", "hunyuan"], help="Video model for Fal.ai")
    parser.add_argument("--aspect", type=str, default="9:16", choices=["9:16", "16:9", "1:1"], help="Video aspect ratio")
    parser.add_argument("--duration", type=int, default=5, help="Scene duration in seconds")
    parser.add_argument("--output", type=str, default="output_scene.mp4", help="Output MP4 file path")
    parser.add_argument("--set-key", nargs=2, metavar=("SERVICE", "KEY"), help="Save an API key (e.g. --set-key fal YOUR_KEY)")
    parser.add_argument("--status", action="store_true", help="Display configured engines and API keys")

    args = parser.parse_args()

    if args.set_key:
        save_key(args.set_key[0], args.set_key[1])
        return

    if args.status:
        keys = load_keys()
        print("="*60)
        print("🎥 AI VIDEO ENGINE CONFIGURATION STATUS")
        print("="*60)
        print(f"Fal.ai API Key:      {'✅ Configured (' + keys['fal'][:6] + '...)' if keys.get('fal') else '❌ Not configured'}")
        print(f"RunPod GPU Pod URL:  {'✅ Configured (' + keys['runpod_pod_url'] + ')' if keys.get('runpod_pod_url') else '❌ Not configured'}")
        print(f"RunPod API Key:      {'✅ Configured' if keys.get('runpod_api_key') else '❌ Not configured'}")
        print(f"Active Auto Engine:  {get_active_engine().upper()}")
        print("="*60)
        return

    if not args.prompt:
        parser.print_help()
        return

    out = generate_scene_video(
        prompt=args.prompt,
        output_path=args.output,
        engine=args.engine,
        model=args.model,
        aspect_ratio=args.aspect,
        duration=args.duration
    )
    print(f"\n🎉 Video clip ready: {out}")


if __name__ == "__main__":
    main()
