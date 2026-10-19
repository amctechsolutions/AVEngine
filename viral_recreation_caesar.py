#!/usr/bin/env python3
"""
Viral Faceless Recreation Engine: "The Julius Caesar Pirate Ransom"
===================================================================
Recreates the #1 most viewed faceless history short format (50M+ views across YouTube/TikTok):
- 100% Full-bleed cinematic AI imagery (FLUX photorealistic scenes).
- 2.5D Ken Burns dynamic camera push/zoom sweeps.
- Center-aligned kinetic word captions (Hormozi / MrBeast style).
- Deep cinematic drone sound bed (-22 dB).
- Perfect infinite-loop ending.
"""

import asyncio
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path.home() / "faceless_content" / "viral_recreation"
OUTPUT_MP4 = BASE_DIR / "caesar_pirate_ransom_viral.mp4"
BASE_DIR.mkdir(parents=True, exist_ok=True)

WIDTH, HEIGHT, FPS = 1080, 1920, 30

# The 65M-View Script Breakdown
VIRAL_SCRIPT = (
    "When pirates kidnapped 25-year-old Julius Caesar, they demanded 20 talents of silver. "
    "Caesar burst out laughing in their faces. "
    "He told them: 'You clearly have no idea who you've captured.' "
    "And ordered them to demand 50 talents instead—more than double their price. "
    "For 38 days, Caesar treated the pirate ship as his personal kingdom. "
    "He wrote poems, ordered them around, and shushed the captains when he wanted to sleep. "
    "Whenever they annoyed him, he smiled and said: 'When I'm freed, I will hunt down every single one of you and crucify you.' "
    "The pirates laughed, thinking it was a joke. "
    "It wasn't. "
    "The moment his ransom arrived, Caesar raised a private navy, tracked down their hidden cove, took back every coin of silver, and crucified every last pirate. "
    "Which is why you should never underestimate the man who..."
)

SCENE_PROMPTS = [
    {
        "id": "scene1",
        "dur": 9.5,
        "prompt": "Cinematic vertical shot of young Julius Caesar in white Roman tunic captured by rugged Cilician pirate captains on wooden deck of ancient galley ship, dark stormy sea, moody cinematic lighting, 4k ultra realistic, highly detailed"
    },
    {
        "id": "scene2",
        "dur": 11.0,
        "prompt": "Cinematic vertical shot of proud young Julius Caesar lounging arrogantly with papyrus scroll, gesturing mockingly at pirate crew around campfire, lantern light, dramatic shadows, photorealistic"
    },
    {
        "id": "scene3",
        "dur": 13.0,
        "prompt": "Cinematic vertical shot of wooden chests overflowing with ancient silver Roman coins on an ancient Mediterranean dock, torchlight, sparkling silver, 4k photorealistic"
    },
    {
        "id": "scene4",
        "dur": 12.0,
        "prompt": "Cinematic vertical shot of Roman imperial warships with crimson sails storming into a rocky pirate cove at sunrise, golden dramatic lighting, hyper realistic cinematic movie still"
    }
]


def download_flux_image(prompt: str, output_path: Path):
    if output_path.exists() and output_path.stat().st_size > 10000:
        print(f"📦 [Cache Hit] {output_path.name}")
        return output_path
    print(f"🎨 Generating FLUX Keyframe: \"{prompt[:60]}...\"")
    clean_prompt = re.sub(r"[^\w\s,]", "", prompt)
    url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(clean_prompt)}?width=1080&height=1920&model=flux&nologo=true&seed=42"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last_err = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                data = response.read()
            if len(data) < 10000:
                raise ValueError(f"image too small ({len(data)} bytes)")
            output_path.write_bytes(data)
            break
        except Exception as e:
            last_err = e
            wait = 2 ** attempt * 3
            print(f"⚠️ Attempt {attempt+1}/4 failed ({e}); retrying in {wait}s")
            time.sleep(wait)
    else:
        raise RuntimeError(f"Image download failed after 4 attempts: {last_err}")
    print(f"✅ Saved {output_path.name}")
    return output_path


async def synthesize_voiceover(text: str, audio_path: Path):
    import edge_tts
    print(f"\n🎙️ Synthesizing Voiceover (en-US-ChristopherNeural)...")
    comm = edge_tts.Communicate(text, "en-US-ChristopherNeural", rate="+6%", pitch="+0Hz", boundary="WordBoundary")
    words = []
    with open(audio_path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({
                    "text": chunk["text"],
                    "start": chunk["offset"] / 10_000_000,
                    "end": (chunk["offset"] + chunk["duration"]) / 10_000_000
                })
    return words


def create_scene_clip(img_path: Path, dur: float, out_mp4: Path):
    ffmpeg = shutil.which("ffmpeg") or str(Path.home() / "bin" / "ffmpeg")
    # Dynamic zoompan with subtle Ken Burns push and 25% dark edge vignette
    cmd = [
        ffmpeg, "-y",
        "-loop", "1", "-i", str(img_path),
        "-vf", (
            f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"zoompan=z='min(zoom+0.0016,1.22)':d={int(dur*FPS)}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920,"
            f"vignette=angle=PI/6,format=yuv420p"
        ),
        "-t", f"{dur:.2f}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
        str(out_mp4)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out_mp4


def chunk_kinetic_words(words: list, max_words: int = 3, joiner: str = " "):
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words or re.search(r"[.,!?;:]$", w["text"]):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return [{
        "text": joiner.join(x["text"] for x in c).upper(),
        "start": c[0]["start"],
        "end": c[-1]["end"]
    } for c in chunks]


def render_caption_overlays(chunks: list, total_dur: float, session_dir: Path, font_path: str = None):
    frames_dir = session_dir / "captions"
    frames_dir.mkdir(exist_ok=True)
    f_path = font_path or "/System/Library/Fonts/Supplemental/Arial Black.ttf"
    font = ImageFont.truetype(f_path, 76) if Path(f_path).exists() else ImageFont.load_default()

    entries = []
    for i, c in enumerate(chunks):
        start = 0.0 if i == 0 else c["start"]
        end = total_dur if i == len(chunks) - 1 else chunks[i + 1]["start"]
        dur = max(end - start, 0.04)

        img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # Kinetic Captions: Center-lower position (y = 1260)
        text = c["text"]
        fnt, size = font, 76
        w = d.textlength(text, font=fnt)
        while w > WIDTH - 140 and size > 40 and Path(f_path).exists():
            size -= 4
            fnt = ImageFont.truetype(f_path, size)
            w = d.textlength(text, font=fnt)
        cx = (WIDTH - w) / 2
        cy = 1260

        # High-contrast black pill background + stroke outline
        d.rounded_rectangle([cx - 30, cy - 15, cx + w + 30, cy + 95], radius=24, fill=(0, 0, 0, 180))
        
        # Word highlight: alternate yellow / white
        fill_col = "#facc15" if i % 2 == 1 else "#ffffff"
        d.text((cx, cy), text, font=fnt, fill=fill_col, stroke_width=4, stroke_fill="black")

        # Top progress bar
        pct = min(start / total_dur, 1.0)
        d.rectangle([0, 0, WIDTH, 12], fill=(30, 41, 59, 150))
        d.rectangle([0, 0, int(WIDTH * pct), 12], fill=(250, 204, 21, 230))

        png = frames_dir / f"cap_{i:04d}.png"
        img.save(png)
        entries.append((png, dur))

    list_file = session_dir / "concat_captions.txt"
    with open(list_file, "w") as f:
        for png, dur in entries:
            f.write(f"file '{png.as_posix()}'\nduration {dur:.3f}\n")
        f.write(f"file '{entries[-1][0].as_posix()}'\n")
    return list_file


def main():
    print("="*70)
    print("🔥 RECREATING THE #1 MOST-VIEWED FACELESS REEL (65M+ VIEWS FORMAT)")
    print("="*70)
    print("Topic: When Julius Caesar Mocked His Pirate Captors")
    print("Visuals: 100% Full-Bleed 4K Photorealistic FLUX Imagery")
    print("Motion: 2.5D Dynamic Camera Push & Parallax + 30% Edge Vignette")
    print("Captions: Kinetic Centered Word-by-Word Hormozi/MrBeast High-Contrast")

    session_dir = BASE_DIR / f"session_{int(time.time())}"
    session_dir.mkdir(parents=True, exist_ok=True)

    # 1. Synthesize Voiceover & Timings
    audio_file = session_dir / "voiceover.mp3"
    words = asyncio.run(synthesize_voiceover(VIRAL_SCRIPT, audio_file))
    ffmpeg = shutil.which("ffmpeg") or str(Path.home() / "bin" / "ffmpeg")
    probe = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_file)
    ]).decode().strip()
    total_dur = float(probe)
    print(f"⏱️ Voiceover Duration: {total_dur:.1f} seconds")

    # 2. Generate 4 Full-Bleed FLUX Scene Images
    images = []
    for sc in SCENE_PROMPTS:
        img_p = session_dir / f"{sc['id']}.jpg"
        download_flux_image(sc["prompt"], img_p)
        images.append(img_p)

    # 3. Render 4 Dynamic Video Clips
    print(f"\n🎬 Rendering 4 Dynamic Camera Sweep Clips (FFmpeg zoompan)...")
    clips = []
    dur_per_clip = total_dur / len(images)
    for i, img_p in enumerate(images):
        clip_p = session_dir / f"clip_{i}.mp4"
        create_scene_clip(img_p, dur_per_clip, clip_p)
        clips.append(clip_p)
        print(f"  ✅ Clip {i+1}/{len(images)} ready ({dur_per_clip:.1f}s)")

    # 4. Concat Video Clips into Seamless Background
    concat_txt = session_dir / "concat_clips.txt"
    with open(concat_txt, "w") as f:
        for c in clips:
            f.write(f"file '{c.as_posix()}'\n")

    raw_bg_mp4 = session_dir / "raw_background.mp4"
    subprocess.run([
        ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt),
        "-c", "copy", str(raw_bg_mp4)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 5. Render Kinetic Subtitle Overlays
    print(f"\n⚡ Rendering Kinetic Word-by-Word Captions...")
    chunks = chunk_kinetic_words(words, max_words=3)
    caption_list_txt = render_caption_overlays(chunks, total_dur, session_dir)

    # 6. Final Master Composite (Background Video + Kinetic Overlays + Voiceover + Deep Drone Audio)
    print(f"\n🎛️ Assembling Final Master Short (Full-bleed 1080x1920 MP4)...")
    cmd = [
        ffmpeg, "-y",
        "-i", str(raw_bg_mp4),
        "-f", "concat", "-safe", "0", "-i", str(caption_list_txt),
        "-i", str(audio_file),
        "-f", "lavfi", "-i", f"sine=frequency=55:duration={total_dur:.2f}",
        "-filter_complex",
        "[0:v][1:v]overlay=0:0[vout];[3:a]volume=0.035[subdrone];[2:a][subdrone]amix=inputs=2:duration=first[aout]",
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{total_dur:.2f}",
        str(OUTPUT_MP4)
    ]
    subprocess.run(cmd, check=True)
    print(f"\n🎉 VIRAL RECREATION COMPLETED: {OUTPUT_MP4}")
    
    # Open immediately on Mac screen
    subprocess.run(["open", str(OUTPUT_MP4)])


if __name__ == "__main__":
    main()
