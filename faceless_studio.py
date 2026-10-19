#!/usr/bin/env python3
"""
FirstSignal Universal Faceless Video Studio v2.0 (Human-in-the-Loop)
=====================================================================
Autonomous $0 Faceless Channel Engine:
- Universal: Works for ANY topic or niche (History, Stoicism, Crime, Tech, Finance, Science)
- Dual Modes:
    1. Narrative Monologue: Viral 4-beat short (Hook, Stakes, Twist, Cliffhanger)
    2. Dual-Person Dialogue: Conversational conflict (Caesar vs Pirate, Socrates vs Student, Detective vs Suspect)
- Multi-Voice Neural Audio: edge-tts voice synthesis with continuous word timestamps
- 2.5D Visual Motion: Dynamic active-speaker cards, animated progress bar, tone-matched palettes
- Ambient Sound Bed: FFmpeg synthetic warm ambient drone mixed under voiceover (-24 dB)
- Two-Stage Approval Gates: Gate 1 (Script Review) & Gate 2 (Video Inspection)
- SQLite Ledger tracking all runs in ~/faceless_content/faceless_studio.db
"""

import argparse
import asyncio
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import warnings
from pathlib import Path

# Suppress urllib3 warnings on macOS
warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")

try:
    from ai_video_engine import generate_scene_video, get_active_engine
except ImportError:
    generate_scene_video = None
    get_active_engine = lambda: "local"

OLLAMA_API_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "huihui-qwen:7b"
BASE_DIR = Path.home() / "faceless_content"
OUTPUT_DIR = BASE_DIR / "renders"
APPROVED_DIR = BASE_DIR / "approved_for_upload"
DB_PATH = BASE_DIR / "faceless_studio.db"

FPS = 30

# Multi-Platform Aspect Ratios & Formats
ASPECT_CONFIGS = {
    "9:16": {"width": 1080, "height": 1920, "label": "Vertical Short (Shorts / TikTok / Reels)", "alias": "shorts"},
    "16:9": {"width": 1920, "height": 1080, "label": "Horizontal Wide (YouTube Long-form / TV / Web)", "alias": "youtube"},
    "1:1": {"width": 1080, "height": 1080, "label": "Square Feed (Instagram / LinkedIn / X)", "alias": "square"}
}

# Duration & Storyboard Length Profiles
LENGTH_CONFIGS = {
    "short": {"min_words": 80, "target_words": "100-140", "scenes": 4, "desc": "30-60s Viral Short", "predict": 600},
    "medium": {"min_words": 260, "target_words": "300-450", "scenes": 10, "desc": "2-3 min Mini-Doc", "predict": 1200},
    "long": {"min_words": 700, "target_words": "800-1400", "scenes": 20, "desc": "5-10 min Full Documentary", "predict": 2500}
}

# Niche Profiles: (Badge, Voice, Background, Card, Accent)
NICHE_PROFILES = {
    "history": {
        "label": "HISTORY UNCOVERED",
        "voice": "en-GB-BrianNeural",
        "voice2": "en-US-ChristopherNeural",
        "bg": "#0c0a09", "card": "#1c1917", "accent": "#f59e0b"
    },
    "stoicism": {
        "label": "DAILY STOIC",
        "voice": "en-US-ChristopherNeural",
        "voice2": "en-GB-RyanNeural",
        "bg": "#090d16", "card": "#0f172a", "accent": "#38bdf8"
    },
    "crime": {
        "label": "CRIME & MYSTERY",
        "voice": "en-US-RogerNeural",
        "voice2": "en-US-SteffanNeural",
        "bg": "#0a0a0a", "card": "#18181b", "accent": "#ef4444"
    },
    "finance": {
        "label": "MONEY & WEALTH",
        "voice": "en-US-GuyNeural",
        "voice2": "en-US-EricNeural",
        "bg": "#06120d", "card": "#0b241b", "accent": "#10b981"
    },
    "tech": {
        "label": "TECH & FUTURE",
        "voice": "en-US-EricNeural",
        "voice2": "en-US-ChristopherNeural",
        "bg": "#080c14", "card": "#0f172a", "accent": "#00f0ff"
    },
    "science": {
        "label": "SCIENCE & UNIVERSE",
        "voice": "en-US-ChristopherNeural",
        "voice2": "en-US-JennyNeural",
        "bg": "#090914", "card": "#13132b", "accent": "#a855f7"
    },
    "general": {
        "label": "MIND-BLOWING FACTS",
        "voice": "en-US-ChristopherNeural",
        "voice2": "en-US-GuyNeural",
        "bg": "#090d16", "card": "#0f172a", "accent": "#38bdf8"
    }
}


def init_db():
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    APPROVED_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS content_pipeline (
            id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            niche TEXT NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            title TEXT,
            hook TEXT,
            script TEXT,
            voice TEXT,
            duration_sec REAL,
            video_path TEXT,
            aspect_ratio TEXT DEFAULT '9:16',
            length_mode TEXT DEFAULT 'short',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Check and add columns if upgrading existing DB
    cur.execute("PRAGMA table_info(content_pipeline)")
    cols = [r[1] for r in cur.fetchall()]
    if "aspect_ratio" not in cols:
        cur.execute("ALTER TABLE content_pipeline ADD COLUMN aspect_ratio TEXT DEFAULT '9:16'")
    if "length_mode" not in cols:
        cur.execute("ALTER TABLE content_pipeline ADD COLUMN length_mode TEXT DEFAULT 'short'")
    conn.commit()
    conn.close()


def detect_niche(topic: str) -> str:
    t = topic.lower()
    if any(k in t for k in ["caesar", "rome", "ancient", "war", "history", "king", "empire", "medieval", "century"]):
        return "history"
    if any(k in t for k in ["stoic", "philosophy", "marcus aurelius", "seneca", "epictetus", "mindset", "wisdom"]):
        return "stoicism"
    if any(k in t for k in ["crime", "murder", "fbi", "mystery", "killer", "detective", "psychopath", "dark"]):
        return "crime"
    if any(k in t for k in ["money", "rich", "billionaire", "stock", "crypto", "invest", "wealth", "finance", "dollar"]):
        return "finance"
    if any(k in t for k in ["ai", "robot", "quantum", "computer", "tech", "chip", "coding", "software", "apple"]):
        return "tech"
    if any(k in t for k in ["space", "nasa", "physics", "universe", "planet", "biology", "brain", "quantum"]):
        return "science"
    return "general"


def query_ollama(prompt: str, model: str, json_mode: bool = True, num_predict: int = 1500) -> str:
    import requests
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {"temperature": 0.4, "top_p": 0.9, "repeat_penalty": 1.15, "num_predict": num_predict}
    }
    if json_mode:
        payload["format"] = "json"
    
    res = requests.post(OLLAMA_API_URL, json=payload, stream=True, timeout=(10, 300))
    res.raise_for_status()
    text = ""
    for line in res.iter_lines():
        if not line:
            continue
        chunk = json.loads(line.decode("utf-8"))
        if "error" in chunk:
            raise RuntimeError(chunk["error"])
        token = chunk.get("response", "")
        text += token
        sys.stdout.write(token)
        sys.stdout.flush()
    print("")
    return text


# --------------------------------------------------------------------------- Dialogue Mode Generator
def generate_dialogue_storyboard(topic: str, niche: str, model: str) -> dict:
    profile = NICHE_PROFILES.get(niche, NICHE_PROFILES["general"])
    print(f"\n🧠 [Local Model: {model}] Storyboarding 2-Person Dialogue on '{topic}'...")

    prompt = f"""You are a master dramatic screenwriter for viral YouTube Shorts and TikTok.
Given this topic: "{topic}" (Genre: {profile['label']}).

Create a dramatic, fast-paced two-person conversation (e.g. Master vs Student, Caesar vs Pirate, Detective vs Suspect, Skeptic vs Believer).
Return strictly a JSON object with these exact keys:
{{
  "title": "Punchy title under 8 words",
  "hook": "Opening pattern-interrupt line spoken by Character 1 (under 12 words)",
  "character_1": "Name/Role of Person 1 (e.g. Caesar, Socrates, Detective)",
  "character_2": "Name/Role of Person 2 (e.g. Pirate, Student, Suspect)",
  "dialogue": [
    {{"speaker": 1, "text": "First punchy line by Person 1"}},
    {{"speaker": 2, "text": "Provocative reaction or challenge by Person 2"}},
    {{"speaker": 1, "text": "Escalation or shocking revelation by Person 1"}},
    {{"speaker": 2, "text": "Disbelief or counter-question by Person 2"}},
    {{"speaker": 1, "text": "Pivotal wisdom, mic-drop truth, or conclusion by Person 1"}}
  ],
  "hashtags": ["5 viral hashtags without #"]
}}
Dialogue rules: Total dialogue words must be between 90-120 words. Fast, natural, high-stakes dialogue. No stage directions in text.
"""
    raw = query_ollama(prompt, model, json_mode=True, num_predict=1500)
    data = json.loads(raw.strip())
    # Format a plain text representation for review
    script_lines = []
    for d in data.get("dialogue", []):
        name = data.get("character_1") if d.get("speaker") == 1 else data.get("character_2")
        script_lines.append(f"{name}: {d.get('text')}")
    data["script"] = "\n".join(script_lines)
    data["mode"] = "dialogue"
    return data


## --------------------------------------------------------------------------- Monologue Mode Generator
def generate_monologue_storyboard(topic: str, niche: str, model: str, length_mode: str = "short") -> dict:
    profile = NICHE_PROFILES.get(niche, NICHE_PROFILES["general"])
    cfg = LENGTH_CONFIGS.get(length_mode, LENGTH_CONFIGS["short"])
    n_scenes = cfg["scenes"]
    print(f"\n🧠 [Local Model: {model}] Storyboarding '{topic}' [{cfg['desc']}] (Niche: {niche.upper()})...")
    
    sample_scenes = ", ".join([f'"Visual description for scene {i+1} (cinematic b-roll lighting, subject, motion)"' for i in range(n_scenes)])
    
    prompt = f"""You are an elite documentary filmmaker and viral content creator.
Topic: "{topic}" (Genre: {profile['label']}).
Format Length: {cfg['desc']}.

Produce a high-retention video storyboard. Return strictly a JSON object with these exact keys:
{{
  "title": "Irresistible, click-worthy title under 9 words",
  "hook": "Electrifying 3-second opening hook line that stops scrolling (under 14 words)",
  "takeaways": [
    "Key insight 1 (under 8 words)",
    "Key insight 2 (under 8 words)",
    "Key insight 3 (under 8 words)"
  ],
  "scene_visuals": [
    {sample_scenes}
  ],
  "hashtags": ["5 viral platform tags without hash symbols"],
  "youtube_chapters": [
    {{"time_est": "0:00", "title": "The Hook and Mystery"}},
    {{"time_est": "0:45", "title": "The Hidden Truth"}},
    {{"time_est": "1:30", "title": "The Turning Point"}},
    {{"time_est": "2:15", "title": "The Final Verdict"}}
  ]
}}
"""
    raw = query_ollama(prompt, model, json_mode=True, num_predict=cfg["predict"])
    data = json.loads(raw.strip())
    data["mode"] = "monologue"
    data["length_mode"] = length_mode
    return data


def generate_voiceover_script(topic: str, hook: str, niche: str, model: str, length_mode: str = "short", attempts: int = 3) -> str:
    cfg = LENGTH_CONFIGS.get(length_mode, LENGTH_CONFIGS["short"])
    target_words = cfg["target_words"]
    min_words = cfg["min_words"]
    print(f"\n🗣️ [Local Model: {model}] Writing narration script ({target_words} words for {cfg['desc']})...")
    
    if length_mode == "short":
        prompt_template = f"""Write the spoken voiceover script for a 45-60 second viral short about:
TOPIC: {topic}
HOOK: "{hook}"

Rules:
1. Exact length: {target_words} words (fast, suspenseful pacing).
2. Follow the 4-beat structure: Beat 1: Hook -> Beat 2: Escalation -> Beat 3: Climax/Reveal -> Beat 4: Cliffhanger thought.
3. Plain sentences only: NO emojis, NO hashtags, NO stage directions, NO asterisks.
4. Output ONLY the spoken narration text.
"""
    elif length_mode == "medium":
        prompt_template = f"""Write an engaging mini-documentary narration script (2-3 minutes) about:
TOPIC: {topic}
HOOK: "{hook}"

Rules:
1. Exact length: {target_words} words (informative, dramatic pacing).
2. Structure:
   - Part 1: The Inciting Incident & Context
   - Part 2: The Core Conflict & Unexpected Discoveries
   - Part 3: The Climax, Revelation, and Long-Term Impact
3. Plain sentences only: NO emojis, NO markdown, NO stage directions.
4. Output ONLY the spoken narration text.
"""
    else:  # long
        prompt_template = f"""Write a comprehensive long-form documentary narration script (5-8 minutes) about:
TOPIC: {topic}
HOOK: "{hook}"

Rules:
1. Length: {target_words} words (deeply detailed, narrative tension, master-class storytelling).
2. Structure into 4 narrative chapters:
   - Chapter 1: The Opening Mystery & The Era
   - Chapter 2: The Rising Tension & The Key Players
   - Chapter 3: The Decisive Turning Point
   - Chapter 4: The Aftermath & Modern Relevance
3. Plain sentences only: NO emojis, NO asterisks, NO stage directions or music cues.
4. Output ONLY the spoken narration text.
"""

    feedback = ""
    best = ""
    for attempt in range(1, attempts + 1):
        prompt = prompt_template + feedback
        text = query_ollama(prompt, model, json_mode=False, num_predict=cfg["predict"])
        cleaned = re.sub(r"\[[^\]]*\]|\([^)]*\)", "", text)
        cleaned = re.sub(r"[*_`#]+", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        words = len(cleaned.split())
        if words > len(best.split()):
            best = cleaned
        if words >= min_words:
            return cleaned
        print(f"⚠️ Narration was {words} words (target >= {min_words}); retrying ({attempt}/{attempts})...")
        feedback = f"\nYour last draft was {words} words. Please expand deeper into the story and specific details to reach {target_words} words."
    return best


def clean_spoken_text(text: str) -> str:
    text = re.sub(r"\[[^\]]*\]|\([^)]*stage[^)]*\)", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"[*_`>#]+", "", text)
    text = re.sub(r"[^\w\s.,!?'’\-:;%$&()/]", "", text)
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------- Approval Gate 1
def prompt_script_approval(package: dict, voice1: str, voice2: str = None) -> str:
    print("\n" + "="*70)
    print("🚦 APPROVAL GATE 1: SCRIPT & STORYBOARD REVIEW")
    print("="*70)
    print(f"📌 TITLE:      {package.get('title')}")
    print(f"🪝 HOOK:       {package.get('hook')}")
    print(f"🎙️ VOICE 1:    {voice1}")
    if package.get("mode") == "dialogue":
        print(f"🎙️ VOICE 2:    {voice2} ({package.get('character_2')})")
        print(f"🎭 CHARACTERS: {package.get('character_1')} vs. {package.get('character_2')}")
    else:
        print(f"⚡ TAKEAWAYS:  {', '.join(package.get('takeaways', []))}")
    print(f"🏷️ HASHTAGS:   {' '.join(['#' + h for h in package.get('hashtags', [])])}")
    print("-" * 70)
    print("📜 SCRIPT CONTENT:")
    print(package.get('script'))
    total_words = len(package.get('script', '').split())
    print(f"\n[Word Count: {total_words} words | Est. Duration: ~{total_words // 2.6:.1f}s]")
    print("="*70)
    
    while True:
        choice = input("\n👉 Operator Action: [A]pprove & Render | [R]e-roll | [V]oice Change | [Q]uit: ").strip().lower()
        if choice in ['a', 'r', 'v', 'q']:
            return choice
        print("Please choose [A], [R], [V], or [Q].")


# --------------------------------------------------------------------------- TTS & Timing
async def synthesize_single(text: str, output_path: str, voice: str, time_offset: float = 0.0, speaker_idx: int = 1) -> list:
    import edge_tts
    tts = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    words, audio = [], bytearray()
    async for chunk in tts.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            start = time_offset + (chunk["offset"] / 1e7)
            words.append({
                "text": chunk["text"],
                "start": start,
                "end": start + (chunk["duration"] / 1e7),
                "speaker": speaker_idx
            })
    if not audio:
        raise RuntimeError("edge-tts returned no audio stream.")
    Path(output_path).write_bytes(bytes(audio))
    return words


async def synthesize_dialogue(dialogue_turns: list, session_dir: Path, voice1: str, voice2: str) -> tuple:
    """Synthesizes alternating dialogue turns, merges them, and aligns word timestamps."""
    ffmpeg = find_ffmpeg()
    turn_files = []
    all_words = []
    current_offset = 0.0

    print(f"\n🎙️ Synthesizing 2-Person Dialogue ({voice1} & {voice2})...")
    for idx, turn in enumerate(dialogue_turns):
        spk = turn.get("speaker", 1)
        v = voice1 if spk == 1 else voice2
        clean_text = clean_spoken_text(turn.get("text", ""))
        part_path = session_dir / f"turn_{idx:02d}.mp3"
        words = await synthesize_single(clean_text, str(part_path), v, time_offset=current_offset, speaker_idx=spk)
        all_words.extend(words)
        
        # Measure duration of this turn
        dur = get_audio_duration(ffmpeg, str(part_path))
        current_offset += dur + 0.18  # 180ms dramatic conversational pause between speakers
        turn_files.append((part_path, dur))

    # Concat all turns into one continuous audio file with FFmpeg concat
    concat_txt = session_dir / "audio_concat.txt"
    with open(concat_txt, "w") as f:
        for p, d in turn_files:
            f.write(f"file '{p.as_posix()}'\n")

    final_audio = session_dir / "narration.mp3"
    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt), "-c", "copy", str(final_audio)]
    subprocess.run(cmd, capture_output=True, check=True)
    concat_txt.unlink(missing_ok=True)
    return str(final_audio), all_words


# --------------------------------------------------------------------------- FFmpeg & Fonts
def find_ffmpeg() -> str:
    cand = os.path.expanduser("~/bin/ffmpeg")
    if os.path.exists(cand):
        return cand
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError("ffmpeg not found in ~/bin/ffmpeg or system PATH.")


def get_audio_duration(ffmpeg: str, path: str) -> float:
    out = subprocess.run([ffmpeg, "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", out)
    if not m:
        raise RuntimeError("Could not determine audio duration.")
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])


_FONT_CACHE = {}
def load_font(size: int, bold: bool = False):
    from PIL import ImageFont
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    paths = (["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"] if bold
             else ["/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc"])
    paths += ["/Library/Fonts/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    font = None
    for p in paths:
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, size)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def wrap_text_px(draw, text: str, font, max_w: int) -> list:
    lines, cur = [], ""
    for w in text.split():
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def chunk_captions(words: list, max_words: int = 4, max_chars: int = 26) -> list:
    chunks, cur = [], []
    for w in words:
        trial = " ".join(x["text"] for x in cur + [w])
        spk = w.get("speaker", 1)
        if cur and (len(cur) >= max_words or len(trial) > max_chars or cur[0].get("speaker") != spk):
            chunks.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.!?]$", w["text"]):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return [{
        "text": " ".join(x["text"] for x in c),
        "start": c[0]["start"],
        "end": c[-1]["end"],
        "speaker": c[0].get("speaker", 1)
    } for c in chunks]


# --------------------------------------------------------------------------- Visual Frame Renderers
def render_dialogue_frame(package: dict, profile: dict, chunk: dict, progress: float, output_path: Path, width: int = 1080, height: int = 1920, aspect_ratio: str = "9:16"):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (width, height), profile["bg"])
    d = ImageDraw.Draw(img)

    # Top progress bar
    bar_h = 10 if aspect_ratio == "16:9" else 16
    d.rectangle([0, 0, width, bar_h], fill="#1e293b")
    d.rectangle([0, 0, int(width * progress), bar_h], fill=profile["accent"])

    active_spk = chunk.get("speaker", 1)
    c1_name = package.get("character_1", "CHARACTER 1").upper()
    c2_name = package.get("character_2", "CHARACTER 2").upper()
    f_badge = load_font(34 if aspect_ratio == "16:9" else 36, bold=True)
    accent_col = profile["accent"] if active_spk == 1 else "#10b981"

    if aspect_ratio == "16:9":
        # Horizontal Split Screen (Left vs Right)
        card_w = (width - 150) // 2
        card_h = 700
        y_top = 80
        # Speaker 1 (Left)
        c1_active = (active_spk == 1)
        d.rounded_rectangle([50, y_top, 50 + card_w, y_top + card_h], radius=28,
                            fill=profile["card"] if c1_active else "#11141d",
                            outline=profile["accent"] if c1_active else "#334155", width=4 if c1_active else 2)
        d.rounded_rectangle([75, y_top + 25, 75 + int(d.textlength(c1_name, font=f_badge)) + 40, y_top + 85], radius=16,
                            fill="#f59e0b" if c1_active else "#475569")
        d.text((95, y_top + 40), c1_name, font=f_badge, fill="white")
        if c1_active:
            d.text((85, y_top + 160), "🗣️ SPEAKING NOW", font=load_font(36, bold=True), fill=profile["accent"])

        # Speaker 2 (Right)
        c2_active = (active_spk == 2)
        x2 = 50 + card_w + 50
        d.rounded_rectangle([x2, y_top, x2 + card_w, y_top + card_h], radius=28,
                            fill=profile["card"] if c2_active else "#11141d",
                            outline="#10b981" if c2_active else "#334155", width=4 if c2_active else 2)
        d.rounded_rectangle([x2 + 25, y_top + 25, x2 + 25 + int(d.textlength(c2_name, font=f_badge)) + 40, y_top + 85], radius=16,
                            fill="#10b981" if c2_active else "#475569")
        d.text((x2 + 45, y_top + 40), c2_name, font=f_badge, fill="white")
        if c2_active:
            d.text((x2 + 35, y_top + 160), "🗣️ SPEAKING NOW", font=load_font(36, bold=True), fill="#10b981")

        # Lower-third Subtitle Bar
        d.rounded_rectangle([120, height - 220, width - 120, height - 40], radius=24, fill="#000000")
        f_cap = load_font(56, bold=True)
        cap_lines = wrap_text_px(d, chunk.get("text", ""), f_cap, width - 300)[:2]
        cy = height - 200 + (140 - len(cap_lines) * 65) // 2
        for ln in cap_lines:
            w = d.textlength(ln, font=f_cap)
            d.text(((width - w) / 2, cy), ln, font=f_cap, fill=accent_col)
            cy += 65
    else:
        # Vertical 9:16 or Square 1:1 Split Screen (Top vs Bottom)
        c1_active = (active_spk == 1)
        d.rounded_rectangle([50, 130, width - 50, 680], radius=32,
                            fill=profile["card"] if c1_active else "#11141d",
                            outline=profile["accent"] if c1_active else "#334155", width=5 if c1_active else 2)
        d.rounded_rectangle([80, 160, 80 + int(d.textlength(c1_name, font=f_badge)) + 50, 230], radius=18,
                            fill="#f59e0b" if c1_active else "#475569")
        d.text((105, 178), c1_name, font=f_badge, fill="white")
        if c1_active:
            d.text((100, 300), "🗣️ SPEAKING NOW", font=load_font(38, bold=True), fill=profile["accent"])

        c2_active = (active_spk == 2)
        d.rounded_rectangle([50, 720, width - 50, 1270], radius=32,
                            fill=profile["card"] if c2_active else "#11141d",
                            outline="#10b981" if c2_active else "#334155", width=5 if c2_active else 2)
        d.rounded_rectangle([80, 750, 80 + int(d.textlength(c2_name, font=f_badge)) + 50, 820], radius=18,
                            fill="#10b981" if c2_active else "#475569")
        d.text((105, 768), c2_name, font=f_badge, fill="white")
        if c2_active:
            d.text((100, 890), "🗣️ SPEAKING NOW", font=load_font(38, bold=True), fill="#10b981")

        # Bottom Caption Box
        sub_top = 1320 if height > 1200 else 760
        sub_h = 370 if height > 1200 else 240
        d.rounded_rectangle([50, sub_top, width - 50, sub_top + sub_h], radius=36, fill="#000000")
        f_cap = load_font(76 if height > 1200 else 50, bold=True)
        cap_lines = wrap_text_px(d, chunk.get("text", ""), f_cap, width - 180)[:3]
        cy = sub_top + (sub_h - len(cap_lines) * 85) // 2
        for ln in cap_lines:
            w = d.textlength(ln, font=f_cap)
            d.text(((width - w) / 2, cy), ln, font=f_cap, fill=accent_col)
            cy += 85

    # Watermark Footer
    f_ft = load_font(26)
    d.text((50, height - 35), f"Topic: {package.get('title', 'Dialogue')[:40]} | FirstSignal Universal Studio", font=f_ft, fill="#64748b")
    img.save(output_path)


def render_monologue_frame(package: dict, profile: dict, scene_idx: int, caption: str, progress: float, output_path: Path, width: int = 1080, height: int = 1920, aspect_ratio: str = "9:16"):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (width, height), profile["bg"])
    d = ImageDraw.Draw(img)

    # Top progress bar
    bar_h = 10 if aspect_ratio == "16:9" else 16
    d.rectangle([0, 0, width, bar_h], fill="#1e293b")
    d.rectangle([0, 0, int(width * progress), bar_h], fill=profile["accent"])

    f_badge = load_font(34 if aspect_ratio == "16:9" else 42, bold=True)
    badge_text = profile["label"]
    bw = int(d.textlength(badge_text, font=f_badge)) + 50

    if aspect_ratio == "16:9":
        # Horizontal Wide Format (1920x1080)
        # Top Left Niche Badge
        d.rounded_rectangle([60, 35, 60 + bw, 95], radius=16, fill="#dc2626")
        d.text((85, 48), badge_text, font=f_badge, fill="white")

        # Top Right Title
        f_top_title = load_font(36, bold=True)
        title_text = package.get("title", "")[:50]
        tw = int(d.textlength(title_text, font=f_top_title))
        d.text((width - tw - 60, 48), title_text, font=f_top_title, fill="#94a3b8")

        # Center Hero Card
        card_w = width - 120
        d.rounded_rectangle([60, 130, 60 + card_w, 780], radius=30, fill=profile["card"], outline=profile["accent"], width=3)

        # Hook / Topic on Card
        f_title = load_font(52, bold=True)
        y = 180
        for ln in wrap_text_px(d, package.get("title", ""), f_title, card_w - 80)[:2]:
            d.text((100, y), ln, font=f_title, fill="white")
            y += 65

        # Key Insight Pills (Horizontal row)
        tks = package.get("takeaways", [])
        y = max(y + 30, 420)
        d.text((100, y), "KEY TAKEAWAYS", font=load_font(28, bold=True), fill="#94a3b8")
        y += 50
        f_tk = load_font(34)
        for i, t in enumerate(tks[:3]):
            active = (i == (scene_idx % max(len(tks[:3]), 1)))
            col = "#ffffff" if active else "#64748b"
            d.ellipse([100, y + 8, 122, y + 30], fill=profile["accent"] if active else "#334155")
            d.text((135, y), t[:65], font=f_tk, fill=col)
            y += 50

        # Lower-third Subtitle Bar
        d.rounded_rectangle([140, height - 220, width - 140, height - 40], radius=24, fill="#000000")
        f_cap = load_font(60, bold=True)
        cap_lines = wrap_text_px(d, caption, f_cap, width - 340)[:2]
        cy = height - 200 + (140 - len(cap_lines) * 68) // 2
        for ln in cap_lines:
            w = d.textlength(ln, font=f_cap)
            d.text(((width - w) / 2, cy), ln, font=f_cap, fill=profile["accent"] if scene_idx % 2 == 0 else "white")
            cy += 68

    elif aspect_ratio == "1:1":
        # Square Format (1080x1080)
        d.rounded_rectangle([50, 40, 50 + bw, 95], radius=16, fill="#dc2626")
        d.text((75, 52), badge_text, font=f_badge, fill="white")

        d.rounded_rectangle([50, 120, width - 50, 720], radius=28, fill=profile["card"], outline=profile["accent"], width=3)
        f_title = load_font(48, bold=True)
        y = 160
        for ln in wrap_text_px(d, package.get("title", ""), f_title, width - 160)[:3]:
            d.text((80, y), ln, font=f_title, fill="white")
            y += 58

        # Lower Subtitle Box
        d.rounded_rectangle([50, 760, width - 50, height - 50], radius=28, fill="#000000")
        f_cap = load_font(58, bold=True)
        cap_lines = wrap_text_px(d, caption, f_cap, width - 160)[:3]
        cy = 760 + ((height - 810) - len(cap_lines) * 68) // 2
        for ln in cap_lines:
            w = d.textlength(ln, font=f_cap)
            d.text(((width - w) / 2, cy), ln, font=f_cap, fill=profile["accent"] if scene_idx % 2 == 0 else "white")
            cy += 68

    else:
        # Vertical 9:16 Format (1080x1920)
        d.rounded_rectangle([50, 130, width - 50, 1220], radius=36, fill=profile["card"], outline=profile["accent"], width=4)
        d.rounded_rectangle([90, 175, 90 + bw, 255], radius=20, fill="#dc2626")
        d.text((120, 192), badge_text, font=f_badge, fill="white")

        f_title = load_font(62, bold=True)
        y = 300
        for ln in wrap_text_px(d, package.get("title", ""), f_title, width - 180)[:3]:
            d.text((90, y), ln, font=f_title, fill="white")
            y += 74

        tks = package.get("takeaways", [])
        y = max(y + 40, 620)
        d.text((90, y), "KEY INSIGHTS", font=load_font(34, bold=True), fill="#94a3b8")
        y += 65
        f_tk = load_font(44)
        for i, t in enumerate(tks[:3]):
            active = (i == (scene_idx % max(len(tks[:3]), 1)))
            col = "#ffffff" if active else "#64748b"
            d.ellipse([90, y + 10, 116, y + 36], fill=profile["accent"] if active else "#334155")
            for ln in wrap_text_px(d, t, f_tk, width - 230)[:2]:
                d.text((135, y), ln, font=f_tk, fill=col)
                y += 54
            y += 18

        d.rounded_rectangle([50, 1280, width - 50, 1650], radius=36, fill="#000000")
        f_cap = load_font(84, bold=True)
        cap_lines = wrap_text_px(d, caption, f_cap, width - 200)[:3]
        total_h = len(cap_lines) * 98
        cy = 1280 + (370 - total_h) // 2
        for ln in cap_lines:
            w = d.textlength(ln, font=f_cap)
            d.text(((width - w) / 2, cy), ln, font=f_cap, fill=profile["accent"] if scene_idx % 2 == 0 else "white")
            cy += 98

    # Watermark Footer
    f_ft = load_font(26)
    d.text((50, height - 35), "FirstSignal Autonomous Sovereign Studio | Multi-Platform Video Engine", font=f_ft, fill="#475569")
    img.save(output_path)


# --------------------------------------------------------------------------- Cross-Platform Social Publishing Kit
def generate_social_publishing_kit(package: dict, duration_sec: float, aspect_ratio: str, length_mode: str, session_dir: Path) -> dict:
    title = package.get("title", "Untitled Story")
    hook = package.get("hook", "")
    niche = package.get("niche", "general").title()
    hashtags = package.get("hashtags", ["facts", "history", "mindblowing", "viral", "documentary"])
    tags_str = " ".join([f"#{h.replace('#', '')}" for h in hashtags])

    # Build YouTube Timestamps
    chapters = package.get("youtube_chapters", [])
    if not chapters:
        chapters = [
            {"time_est": "0:00", "title": f"Intro: {hook[:45]}"},
            {"time_est": f"0:{int(duration_sec*0.3):02d}", "title": "The Hidden Truth"},
            {"time_est": f"0:{int(duration_sec*0.7):02d}", "title": "The Decisive Revelation"},
            {"time_est": f"0:{int(duration_sec*0.9):02d}", "title": "Conclusion & Final Thoughts"}
        ]
    chapter_text = "\n".join([f"{c['time_est']} - {c['title']}" for c in chapters])

    kit = {
        "title": title,
        "format": ASPECT_CONFIGS.get(aspect_ratio, {}).get("label", aspect_ratio),
        "duration": f"{duration_sec:.1f}s",
        "length_mode": length_mode,
        "youtube": {
            "title": f"{title} | Deep Dive Documentary" if aspect_ratio == "16:9" else f"{title} #Shorts",
            "description": f"{hook}\n\nIn this video, we uncover the fascinating story behind {title}.\n\n⏱️ TIMESTAMPS:\n{chapter_text}\n\n🔔 Subscribe to FirstSignal for more untold stories!\n\nTAGS:\n{tags_str}",
            "tags": [h.replace('#', '') for h in hashtags] + [niche.lower(), "documentary", "storytelling", "educational"]
        },
        "tiktok": {
            "caption": f"{hook} 🤯 What would you have done? Let us know below 👇 {tags_str} #fyp #viral",
            "sound_recommendation": "Dramatic Suspense Ambient Drone"
        },
        "instagram_reels": {
            "caption": f"💡 {title}\n\n{hook}\n\nSave this reel for later and share with a friend who loves {niche}! 📌\n\n{tags_str}",
            "cover_frame_sec": 3.0
        },
        "twitter_x": {
            "thread_hook": f"🧵 1/3: {hook}\n\nHere is the untold story behind {title} that history books often leave out 👇\n\n(Watch full video below)",
            "thread_body": f"2/3: {package.get('takeaways', ['Key detail'])[0] if package.get('takeaways') else hook}",
            "thread_outro": f"3/3: What do you think about this? Follow for more daily historical deep dives!"
        }
    }

    # Save JSON package
    json_path = session_dir / "social_package.json"
    json_path.write_text(json.dumps(kit, indent=2))

    # Save Ready-to-Copy Text Kit
    txt_path = session_dir / "SOCIAL_PUBLISHING_KIT.txt"
    txt_content = f"""======================================================================
📱 FIRSTSIGNAL SOCIAL MEDIA PUBLISHING KIT
======================================================================
📌 TITLE:    {title}
⏱️ DURATION: {duration_sec:.1f}s | ASPECT: {aspect_ratio} ({ASPECT_CONFIGS.get(aspect_ratio, {}).get('label', '')})
======================================================================

▶️ 1. YOUTUBE (LONG-FORM & SHORTS)
----------------------------------------------------------------------
TITLE:
{kit['youtube']['title']}

DESCRIPTION:
{kit['youtube']['description']}

----------------------------------------------------------------------
🎵 2. TIKTOK
----------------------------------------------------------------------
CAPTION:
{kit['tiktok']['caption']}

----------------------------------------------------------------------
📸 3. INSTAGRAM REELS
----------------------------------------------------------------------
CAPTION:
{kit['instagram_reels']['caption']}

----------------------------------------------------------------------
🐦 4. TWITTER / X THREAD
----------------------------------------------------------------------
{kit['twitter_x']['thread_hook']}

{kit['twitter_x']['thread_body']}

{kit['twitter_x']['thread_outro']}
======================================================================
"""
    txt_path.write_text(txt_content)
    return kit


# --------------------------------------------------------------------------- FFmpeg Video Assembly
def assemble_video(package: dict, profile: dict, audio_path: str, output_mp4: str, session_dir: Path, words: list, ambient: bool = True, video_engine: str = "auto", video_model: str = "wan2.1", aspect_ratio: str = "9:16", length_mode: str = "short") -> float:
    ffmpeg = find_ffmpeg()
    total_dur = get_audio_duration(ffmpeg, audio_path)
    chunks = chunk_captions(words)
    frames_dir = session_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    # Resolution dimensions
    cfg_aspect = ASPECT_CONFIGS.get(aspect_ratio, ASPECT_CONFIGS["9:16"])
    width = cfg_aspect["width"]
    height = cfg_aspect["height"]

    # Check if AI Video Engine is available for b-roll scenes
    active_eng = get_active_engine() if video_engine == "auto" else video_engine
    scene_visuals = package.get("scene_visuals", [])
    scenes_dir = session_dir / "ai_scenes"
    ai_scene_clips = []

    if active_eng in ["fal", "runpod"] and scene_visuals and generate_scene_video:
        print(f"\n🎥 Generating {len(scene_visuals)} AI Video Clips using [{active_eng.upper()}] ({video_model}, Aspect: {aspect_ratio})...")
        scenes_dir.mkdir(exist_ok=True)
        dur_per_scene = max(int(total_dur / len(scene_visuals)), 4)
        for idx, s_prompt in enumerate(scene_visuals):
            scene_target = scenes_dir / f"scene_{idx:02d}.mp4"
            try:
                clip_path = generate_scene_video(
                    prompt=s_prompt,
                    output_path=str(scene_target),
                    engine=active_eng,
                    model=video_model,
                    aspect_ratio=aspect_ratio,
                    duration=dur_per_scene
                )
                if Path(clip_path).exists():
                    ai_scene_clips.append(clip_path)
            except Exception as e:
                print(f"⚠️ Warning: Could not generate scene {idx} via {active_eng}: {e}")

    entries = []
    is_dialogue = (package.get("mode") == "dialogue")
    n_scenes = max(1, len(package.get("takeaways", [])))

    print(f"\n🎬 Rendering {len(chunks)} synchronized {width}x{height} frames ({aspect_ratio}) for {total_dur:.1f}s video...")
    for i, c in enumerate(chunks):
        start = 0.0 if i == 0 else c["start"]
        end = total_dur if i == len(chunks) - 1 else chunks[i + 1]["start"]
        dur = max(end - start, 0.04)
        png = frames_dir / f"f{i:04d}.png"
        progress = min(start / total_dur, 1.0)
        
        if is_dialogue:
            render_dialogue_frame(package, profile, c, progress, png, width=width, height=height, aspect_ratio=aspect_ratio)
        else:
            scene = min(int(start / total_dur * n_scenes), n_scenes - 1)
            render_monologue_frame(package, profile, scene, c["text"], progress, png, width=width, height=height, aspect_ratio=aspect_ratio)
        entries.append((png, dur))

    list_file = session_dir / "concat_frames.txt"
    with open(list_file, "w") as f:
        for png, dur in entries:
            f.write(f"file '{png.as_posix()}'\nduration {dur:.3f}\n")
        f.write(f"file '{entries[-1][0].as_posix()}'\n")

    print(f"\n⚡ Compiling {width}x{height} MP4 via FFmpeg ({'warm ambient sound bed' if ambient else 'clean voice'})...")
    
    if ambient:
        cmd = [
            ffmpeg, "-y",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-i", audio_path,
            "-f", "lavfi", "-i", f"sine=frequency=65:duration={total_dur:.2f}",
            "-filter_complex",
            "[2:a]volume=0.025[drone];[1:a][drone]amix=inputs=2:duration=first[aout]",
            "-vf", f"fps={FPS},scale={width}:{height},format=yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-map", "0:v", "-map", "[aout]",
            "-movflags", "+faststart",
            "-shortest", output_mp4
        ]
    else:
        cmd = [
            ffmpeg, "-y",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-i", audio_path,
            "-vf", f"fps={FPS},scale={width}:{height},format=yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-movflags", "+faststart",
            "-shortest", output_mp4
        ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not Path(output_mp4).exists():
        tail = "\n".join(res.stderr.strip().splitlines()[-10:])
        raise RuntimeError(f"FFmpeg compilation failed:\n{tail}")

    shutil.rmtree(frames_dir, ignore_errors=True)
    list_file.unlink(missing_ok=True)

    # Generate Cross-Platform Social Publishing Package
    generate_social_publishing_kit(package, total_dur, aspect_ratio, length_mode, session_dir)
    return total_dur


# --------------------------------------------------------------------------- Approval Gate 2
def prompt_video_approval(video_path: str, title: str, session_dir: Path) -> str:
    print("\n" + "="*70)
    print("🚦 APPROVAL GATE 2: FINAL VIDEO INSPECTION")
    print("="*70)
    print(f"🎬 Video Rendered: {video_path}")
    print(f"📌 Title:          {title}")
    print(f"📱 Social Kit:     {session_dir / 'SOCIAL_PUBLISHING_KIT.txt'}")
    print("="*70)
    while True:
        choice = input("\n👉 Operator Action: [A]pprove for Upload Queue | [P]review in QuickTime | [D]iscard: ").strip().lower()
        if choice == "p":
            subprocess.run(["open", video_path])
            continue
        if choice in ['a', 'd']:
            return choice
        print("Please choose [A], [P], or [D].")


# --------------------------------------------------------------------------- Main Run Loop
def run_pipeline(topic: str, niche: str = None, voice: str = None, voice2: str = None, dialogue: bool = False, model: str = DEFAULT_MODEL, no_confirm: bool = False, video_engine: str = "auto", video_model: str = "wan2.1", aspect_ratio: str = "9:16", length_mode: str = "short"):
    init_db()
    if not niche:
        niche = detect_niche(topic)
    profile = NICHE_PROFILES.get(niche, NICHE_PROFILES["general"])
    active_voice1 = voice or profile["voice"]
    active_voice2 = voice2 or profile.get("voice2", "en-US-JennyNeural")
    
    cfg_aspect = ASPECT_CONFIGS.get(aspect_ratio, ASPECT_CONFIGS["9:16"])
    cfg_length = LENGTH_CONFIGS.get(length_mode, LENGTH_CONFIGS["short"])

    session_id = f"video_{int(time.time())}_{os.getpid()}"
    session_dir = OUTPUT_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    print("="*70)
    print("🎥 FIRSTSIGNAL UNIVERSAL FACELESS CHANNEL STUDIO v2.0")
    print("="*70)
    print(f"🎯 TOPIC:     {topic}")
    print(f"📂 NICHE:     {niche.upper()} | Mode: {'2-Person Dialogue' if dialogue else 'Narrative Monologue'}")
    print(f"📐 FORMAT:    {aspect_ratio} ({cfg_aspect['label']})")
    print(f"⏱️ LENGTH:    {length_mode.upper()} ({cfg_length['desc']})")
    print(f"🎞️ BACKEND:   {video_engine.upper()} (Model: {video_model})")

    # Generate Storyboard & Script
    while True:
        if dialogue:
            package = generate_dialogue_storyboard(topic, niche, model)
        else:
            package = generate_monologue_storyboard(topic, niche, model, length_mode=length_mode)
            script = generate_voiceover_script(topic, package.get("hook", ""), niche, model, length_mode=length_mode)
            package["script"] = script
        package["niche"] = niche
        package["aspect_ratio"] = aspect_ratio
        package["length_mode"] = length_mode

        if no_confirm:
            action = "a"
        else:
            action = prompt_script_approval(package, active_voice1, active_voice2 if dialogue else None)

        if action == "a":
            break
        elif action == "r":
            print("\n🔄 Re-rolling script with new angle...")
            continue
        elif action == "v":
            print("\nAvailable Voices:")
            voices = ["en-US-ChristopherNeural", "en-GB-BrianNeural", "en-US-RogerNeural", "en-US-GuyNeural", "en-US-EricNeural", "en-US-JennyNeural"]
            for i, v in enumerate(voices, 1):
                print(f"  [{i}] {v}")
            v_choice = input("Select Voice 1 (1-6): ").strip()
            if v_choice.isdigit() and 1 <= int(v_choice) <= len(voices):
                active_voice1 = voices[int(v_choice) - 1]
                print(f"✅ Voice 1 changed to: {active_voice1}")
            continue
        elif action == "q":
            print("\n❌ Studio run cancelled by operator.")
            shutil.rmtree(session_dir, ignore_errors=True)
            return

    # Synthesize Audio & Time
    if dialogue:
        audio_path, words = asyncio.run(synthesize_dialogue(package.get("dialogue", []), session_dir, active_voice1, active_voice2))
    else:
        audio_path = session_dir / "narration.mp3"
        cleaned_spoken = clean_spoken_text(package["script"])
        words = asyncio.run(synthesize_single(cleaned_spoken, str(audio_path), active_voice1))
        audio_path = str(audio_path)

    # Assemble Video
    video_output = session_dir / "final_video.mp4"
    duration = assemble_video(
        package=package,
        profile=profile,
        audio_path=str(audio_path),
        output_mp4=str(video_output),
        session_dir=session_dir,
        words=words,
        ambient=True,
        video_engine=video_engine,
        video_model=video_model,
        aspect_ratio=aspect_ratio,
        length_mode=length_mode
    )
    print(f"\n🎉 Video Successfully Created: {video_output} ({duration:.1f}s)")
    print(f"📱 Cross-Platform Kit Generated: {session_dir / 'SOCIAL_PUBLISHING_KIT.txt'}")

    # Save package metadata
    meta_path = session_dir / "metadata.json"
    package["duration_seconds"] = duration
    package["voice1"] = active_voice1
    package["voice2"] = active_voice2 if dialogue else None
    package["video_path"] = str(video_output)
    meta_path.write_text(json.dumps(package, indent=2))

    # Approval Gate 2
    if no_confirm:
        gate2_action = "a"
    else:
        gate2_action = prompt_video_approval(str(video_output), package.get("title", ""), session_dir)
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if gate2_action == "a":
        approved_target = APPROVED_DIR / f"{session_id}.mp4"
        meta_target = APPROVED_DIR / f"{session_id}.json"
        kit_target = APPROVED_DIR / f"{session_id}_publishing_kit.txt"
        shutil.copy2(video_output, approved_target)
        shutil.copy2(meta_path, meta_target)
        shutil.copy2(session_dir / "SOCIAL_PUBLISHING_KIT.txt", kit_target)
        cur.execute("""
            INSERT INTO content_pipeline (id, topic, niche, mode, status, title, hook, script, voice, duration_sec, video_path, aspect_ratio, length_mode)
            VALUES (?, ?, ?, ?, 'READY_TO_PUBLISH', ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, topic, niche, package.get("mode"), package.get("title"), package.get("hook"), package["script"], active_voice1, duration, str(approved_target), aspect_ratio, length_mode))
        print(f"\n🚀 APPROVED FOR PUBLISHING QUEUE: {approved_target}")
        print(f"📋 Ready-to-Publish Kit: {kit_target}")
    else:
        cur.execute("""
            INSERT INTO content_pipeline (id, topic, niche, mode, status, title, hook, script, voice, duration_sec, video_path, aspect_ratio, length_mode)
            VALUES (?, ?, ?, ?, 'DISCARDED', ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, topic, niche, package.get("mode"), package.get("title"), package.get("hook"), package["script"], active_voice1, duration, str(video_output), aspect_ratio, length_mode))
        print("\n🗑️ Run marked as DISCARDED in content ledger.")
    conn.commit()
    conn.close()
    return str(video_output)


def main():
    parser = argparse.ArgumentParser(description="FirstSignal Universal Faceless Video Studio v2.0")
    parser.add_argument("--topic", help="Topic, question, or story to turn into a video")
    parser.add_argument("--batch", "-b", help="Path to a text file with one topic per line for batch autonomous generation")
    parser.add_argument("--dialogue", "-d", action="store_true", help="Generate a 2-person alternating dialogue scene")
    parser.add_argument("--niche", choices=list(NICHE_PROFILES.keys()), help="Force niche preset")
    parser.add_argument("--voice", help="Override primary neural voice")
    parser.add_argument("--voice2", help="Override secondary neural voice for dialogue")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Local LLM model (default: {DEFAULT_MODEL})")
    parser.add_argument("--no-confirm", action="store_true", help="Auto-approve without interactive prompts (for Web / Cron / Batch)")
    parser.add_argument("--video-engine", choices=["auto", "fal", "runpod", "local"], default="auto", help="Video generation backend (Fal.ai, RunPod GPU, or Local)")
    parser.add_argument("--video-model", default="wan2.1", help="Video model for Fal.ai (wan2.1, ltx, hunyuan)")
    parser.add_argument("--aspect", choices=["9:16", "16:9", "1:1"], default="9:16", help="Video aspect ratio: 9:16 (Shorts/TikTok), 16:9 (YouTube long-form), 1:1 (Square)")
    parser.add_argument("--format", choices=["shorts", "youtube", "square", "tiktok", "reels"], help="Convenience preset for aspect ratio")
    parser.add_argument("--length", choices=["short", "medium", "long"], default="short", help="Video duration: short (30-60s), medium (2-3 min), long (5-10 min)")
    parser.add_argument("--dry-run", action="store_true", help="Never call paid video engines (Fal/RunPod); render local fallback only")
    parser.add_argument("--max-paid-clips", type=int, default=12, help="Cap on paid video clips per run (default 12)")
    args = parser.parse_args()
    os.environ["AI_VIDEO_MAX_PAID_CLIPS"] = str(args.max_paid_clips)
    if args.dry_run:
        os.environ["AI_VIDEO_DRY_RUN"] = "1"

    # Resolve format alias if provided
    aspect = args.aspect
    if args.format:
        format_map = {
            "shorts": "9:16",
            "tiktok": "9:16",
            "reels": "9:16",
            "youtube": "16:9",
            "square": "1:1"
        }
        aspect = format_map.get(args.format, args.aspect)

    # Handle Batch Mode
    if args.batch:
        batch_path = Path(args.batch).expanduser().resolve()
        if not batch_path.exists():
            sys.exit(f"❌ Batch file not found: {batch_path}")
        topics = [line.strip() for line in batch_path.read_text().splitlines() if line.strip() and not line.strip().startswith("#")]
        if not topics:
            sys.exit(f"❌ No valid topics found in {batch_path}")
        print("="*70)
        print(f"🚀 BATCH AUTONOMOUS PIPELINE: {len(topics)} TOPICS QUEUED")
        print("="*70)
        for i, t in enumerate(topics, 1):
            print(f"\n▶️ [{i}/{len(topics)}] Processing: {t}")
            try:
                run_pipeline(
                    topic=t,
                    niche=args.niche,
                    voice=args.voice,
                    voice2=args.voice2,
                    dialogue=args.dialogue,
                    model=args.model,
                    no_confirm=True,
                    video_engine=args.video_engine,
                    video_model=args.video_model,
                    aspect_ratio=aspect,
                    length_mode=args.length
                )
            except Exception as e:
                print(f"⚠️ Error rendering topic '{t}': {e}. Continuing next...")
        print("\n🎉 BATCH COMPLETED! All videos & social kits available in ~/faceless_content/approved_for_upload/")
        return

    topic = args.topic
    if not topic:
        print("="*70)
        print("🎥 FIRSTSIGNAL UNIVERSAL FACELESS CHANNEL STUDIO v2.0")
        print("="*70)
        topic = input("Enter any topic, idea, or debate (e.g. 'Caesar mocking pirates'): ").strip()
        if not topic:
            sys.exit("No topic entered. Exiting.")

    run_pipeline(
        topic=topic,
        niche=args.niche,
        voice=args.voice,
        voice2=args.voice2,
        dialogue=args.dialogue,
        model=args.model,
        no_confirm=args.no_confirm,
        video_engine=args.video_engine,
        video_model=args.video_model,
        aspect_ratio=aspect,
        length_mode=args.length
    )


if __name__ == "__main__":
    main()
