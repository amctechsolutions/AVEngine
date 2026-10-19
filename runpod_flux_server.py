"""Runs ON the RunPod pod: FLUX.1-schnell image server (token-protected)."""
import io, os, threading, torch, uvicorn
from fastapi import FastAPI, Header, HTTPException, Response

TOKEN = os.environ["AUTH_TOKEN"]
state = {"ready": False, "error": None, "stage": "starting"}
lock = threading.Lock()
app = FastAPI()
pipe = None


MODEL = os.environ.get("FS_MODEL", "sdxl")
SIZE = {"sdxl": (768, 1344), "flux": (864, 1536)}  # (w, h), both 9:16-ish


def load():
    global pipe
    try:
        state["stage"] = f"downloading/loading {MODEL}"
        if MODEL == "flux":
            from diffusers import FluxPipeline
            pipe = FluxPipeline.from_pretrained("black-forest-labs/FLUX.1-schnell", torch_dtype=torch.bfloat16)
            vram = torch.cuda.get_device_properties(0).total_memory / 2**30
            pipe.to("cuda") if vram >= 40 else pipe.enable_model_cpu_offload()
        else:  # SDXL-Lightning 4-step: open weights, no login needed
            from diffusers import StableDiffusionXLPipeline, UNet2DConditionModel, EulerDiscreteScheduler
            from huggingface_hub import hf_hub_download
            from safetensors.torch import load_file
            base = "stabilityai/stable-diffusion-xl-base-1.0"
            unet = UNet2DConditionModel.from_config(base, subfolder="unet").to("cuda", torch.float16)
            unet.load_state_dict(load_file(hf_hub_download("ByteDance/SDXL-Lightning", "sdxl_lightning_4step_unet.safetensors"), device="cuda"))
            pipe = StableDiffusionXLPipeline.from_pretrained(base, unet=unet, torch_dtype=torch.float16, variant="fp16").to("cuda")
            pipe.scheduler = EulerDiscreteScheduler.from_config(pipe.scheduler.config, timestep_spacing="trailing")
        state.update(ready=True, stage="ready")
    except Exception as e:  # surfaced to the client via /health
        state["error"] = repr(e)


@app.get("/health")
def health():
    return state


@app.post("/image")
def image(body: dict, authorization: str = Header(default="")):
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "bad token")
    if not state["ready"]:
        raise HTTPException(503, state["stage"])
    w0, h0 = SIZE[MODEL]
    kw = dict(prompt=body["prompt"], height=int(body.get("height") or h0), width=int(body.get("width") or w0),
              num_inference_steps=4, guidance_scale=0.0,
              generator=torch.Generator("cpu").manual_seed(int(body.get("seed", 42))))
    if MODEL == "flux":
        kw["max_sequence_length"] = 256
    with lock:
        img = pipe(**kw).images[0]
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return Response(content=buf.getvalue(), media_type="image/jpeg")


if __name__ == "__main__":
    threading.Thread(target=load, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
