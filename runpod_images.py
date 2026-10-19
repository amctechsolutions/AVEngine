#!/usr/bin/env python3
"""
On-demand FLUX image generation on a RunPod GPU pod, with hard cost safety:
  * pod is TERMINATED (not just stopped) in a finally/atexit/signal handler
  * the pod kills itself after MAX_SECONDS even if this machine dies
  * ~/.runpod_active_pod.json lets `--cleanup` remove an orphan after a crash

  python3 runpod_images.py --smoke      # one image, real pod (~$0.10)
  python3 runpod_images.py --list       # pods + balance
  python3 runpod_images.py --cleanup    # terminate any pod this tool started
"""
import argparse, atexit, base64, json, os, secrets, signal, sys, time
from pathlib import Path
import requests, runpod
from runpod.api.graphql import run_graphql_query
from ai_video_engine import load_keys

STATE = Path.home() / ".runpod_active_pod.json"
SERVER = Path(__file__).with_name("runpod_flux_server.py")
IMAGE = "runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04"
GPUS = ["NVIDIA RTX A6000", "NVIDIA A40", "NVIDIA L40S", "NVIDIA GeForce RTX 4090"]
MAX_SECONDS = 2700          # on-pod dead-man timer (45 min)
READY_TIMEOUT = 1500        # model download + load
MIN_BALANCE = 1.0

BOOT = """set -x
( sleep {max_s}; runpodctl remove pod $RUNPOD_POD_ID; runpodctl stop pod $RUNPOD_POD_ID ) &
pip install -q diffusers transformers accelerate sentencepiece protobuf fastapi uvicorn hf_transfer pillow
echo "$SERVER_B64" | base64 -d > /server.py
HF_HUB_ENABLE_HF_TRANSFER=1 python /server.py
"""


def _auth():
    runpod.api_key = load_keys()["runpod_api_key"]


def balance() -> float:
    _auth()
    return float(run_graphql_query("query { myself { clientBalance } }")["data"]["myself"]["clientBalance"])


def terminate(pod_id: str) -> bool:
    _auth()
    try:
        runpod.terminate_pod(pod_id)
    except Exception as e:
        print(f"⚠️ terminate_pod error: {e}")
    for _ in range(10):
        if not any(p["id"] == pod_id for p in runpod.get_pods()):
            STATE.unlink(missing_ok=True) if sys.version_info >= (3, 8) else None
            return True
        time.sleep(3)
    print(f"❌ POD {pod_id} STILL LISTED — terminate it in the RunPod console NOW")
    return False


class FluxPodSession:
    def __init__(self):
        self.pod_id = None
        self.url = None
        self.token = secrets.token_hex(16)
        self.cost_hr = 0.0
        self.t0 = None

    def __enter__(self):
        _auth()
        bal = balance()
        if bal < MIN_BALANCE:
            raise RuntimeError(f"RunPod balance ${bal:.2f} < ${MIN_BALANCE:.2f}")
        hf = os.environ.get("HF_TOKEN") or load_keys().get("hf")  # optional: only enables gated FLUX
        env = {"FS_MODEL": "flux" if hf else "sdxl", **({"HF_TOKEN": hf} if hf else {}), "AUTH_TOKEN": self.token, "SERVER_B64": base64.b64encode(SERVER.read_bytes()).decode(),
               "BOOT_B64": base64.b64encode(BOOT.format(max_s=MAX_SECONDS).encode()).decode()}
        last = None
        for gpu in GPUS:
            try:
                pod = runpod.create_pod(
                    name="fs-flux-session", image_name=IMAGE, gpu_type_id=gpu, cloud_type="ALL",
                    container_disk_in_gb=60, volume_in_gb=0, ports="8000/http", env=env,
                    docker_args="bash -c 'echo $BOOT_B64 | base64 -d > /boot.sh && bash /boot.sh'",
                    support_public_ip=False, start_ssh=False)
                self.pod_id = pod["id"]
                break
            except Exception as e:
                last = e
                print(f"  {gpu}: unavailable ({str(e)[:90]})")
        if not self.pod_id:
            raise RuntimeError(f"No GPU available: {last}")
        STATE.write_text(json.dumps({"pod_id": self.pod_id, "started": time.time()}))
        atexit.register(self.close)
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: (self.close(), sys.exit(130)))
        self.t0 = time.time()
        self.url = f"https://{self.pod_id}-8000.proxy.runpod.net"
        print(f"🚀 Pod {self.pod_id} ({gpu}) starting; self-destruct in {MAX_SECONDS//60} min")
        self._wait_ready()
        return self

    def _wait_ready(self):
        end, last = time.time() + READY_TIMEOUT, None
        while time.time() < end:
            try:
                r = requests.get(self.url + "/health", timeout=8)
                if r.status_code == 200:
                    h = r.json()
                    if h.get("error"):
                        raise RuntimeError(f"server error: {h['error']}")
                    if h.get("stage") != last:
                        last = h.get("stage"); print(f"  … {last}")
                    if h.get("ready"):
                        return
            except requests.RequestException:
                pass
            time.sleep(10)
        raise TimeoutError(f"pod not ready in {READY_TIMEOUT}s")

    def image(self, prompt, out, seed=42, width=None, height=None):
        for attempt in range(3):
            try:
                r = requests.post(self.url + "/image", timeout=180,
                                  headers={"Authorization": f"Bearer {self.token}"},
                                  json={"prompt": prompt, "seed": seed, "width": width, "height": height})
                if r.status_code == 200 and len(r.content) > 10000:
                    Path(out).write_bytes(r.content)
                    return
                raise RuntimeError(f"HTTP {r.status_code} {r.text[:100]}")
            except Exception as e:
                print(f"⚠️ pod image attempt {attempt+1}/3: {e}")
                time.sleep(3)
        raise RuntimeError("pod image generation failed")

    def close(self):
        if not self.pod_id:
            return
        pid, self.pod_id = self.pod_id, None
        ok = terminate(pid)
        mins = (time.time() - self.t0) / 60 if self.t0 else 0
        print(f"🛑 Pod {pid} terminated={ok} after {mins:.1f} min")

    __exit__ = lambda self, *a: self.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--cleanup", action="store_true")
    a = ap.parse_args()
    _auth()
    if a.list:
        print(f"balance ${balance():.2f}")
        for p in runpod.get_pods():
            print(p["id"], p["name"], p["desiredStatus"], p["costPerHr"])
    if a.cleanup:
        if STATE.exists():
            terminate(json.loads(STATE.read_text())["pod_id"])
        else:
            print("no recorded orphan pod")
    if a.smoke:
        out = Path("/private/tmp/claude-501/-Users-user/fd44da8f-b02a-477d-84ce-36857f876d54/scratchpad/pod_smoke.jpg")
        b0 = balance()
        with FluxPodSession() as s:
            t = time.time()
            s.image("a jar of golden honey in an ancient Egyptian tomb, torchlight, cinematic, photorealistic", out)
            print(f"🖼️ image in {time.time()-t:.1f}s -> {out} ({out.stat().st_size} bytes)")
        print(f"💵 spent ≈ ${b0 - balance():.3f}")


if __name__ == "__main__":
    main()
