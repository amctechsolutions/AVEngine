#!/usr/bin/env python3
"""
Custom viral short generator. Reuses the Caesar renderer (FLUX stills, Ken Burns,
kinetic captions, sub-bass bed) for any script.

  python3 viral_custom.py                    # built-in sample (honey)
  python3 viral_custom.py --spec my.json     # {"slug","voice","segments":[{"text","prompt"}]}
  python3 viral_custom.py --dry-run          # voiceover + local gradients, no image downloads
"""
import argparse, asyncio, json, re, shutil, subprocess, sys, time
from pathlib import Path
import viral_recreation_caesar as vr
from ai_video_engine import load_keys

STYLE = ", cinematic vertical shot, dramatic lighting, 4k photorealistic, highly detailed"

SAMPLE = {
    "slug": "honey_never_spoils",
    "voice": "adam",
    "segments": [
        {"label": "SEALED TOMB", "query": "egypt pyramid", "tr": {"es": "Unos arqueólogos abrieron una tumba egipcia sellada y encontraron un tarro de miel.", "pt": "Arqueólogos abriram uma tumba egípcia selada e encontraram um pote de mel.", "fr": "Des archéologues ont ouvert une tombe égyptienne scellée et y ont trouvé un pot de miel.", "de": "Archäologen öffneten ein versiegeltes ägyptisches Grab und fanden ein Glas Honig.", "hi": "पुरातत्वविदों ने मिस्र की एक सीलबंद कब्र खोली और उसमें शहद का एक मर्तबान मिला।"},
         "text": "Archaeologists opened a sealed Egyptian tomb and found a jar of honey.",
         "prompt": "archaeologists in an ancient Egyptian tomb by torchlight opening a sealed clay jar, golden glow"},
        {"label": "3,000 YEARS", "query": "honey jar", "tr": {"es": "Tenía tres mil años. Y seguía siendo perfectamente comestible.", "pt": "Tinha três mil anos. E ainda estava perfeitamente comestível.", "fr": "Il avait trois mille ans. Et il était encore parfaitement comestible.", "de": "Er war dreitausend Jahre alt. Und er war immer noch völlig genießbar.", "hi": "वह तीन हज़ार साल पुराना था। और फिर भी पूरी तरह खाने लायक था।"},
         "text": "It was three thousand years old. And it was still perfectly edible.",
         "prompt": "close up of glowing golden honey in an ancient clay jar, hieroglyph wall behind"},
        {"label": "NO BACTERIA", "query": "honey spoon", "tr": {"es": "La miel casi nunca se echa a perder. Las bacterias no pueden sobrevivir en ella.", "pt": "O mel quase nunca estraga. As bactérias não conseguem sobreviver nele.", "fr": "Le miel ne s'abîme presque jamais. Les bactéries n'y survivent pas.", "de": "Honig verdirbt fast nie. Bakterien können darin nicht überleben.", "hi": "शहद लगभग कभी खराब नहीं होता। बैक्टीरिया उसमें ज़िंदा नहीं रह पाते।"},
         "text": "Honey almost never spoils. Bacteria can't survive in it.",
         "prompt": "macro shot of honey dripping from a wooden dipper, amber light"},
        {"label": "DRIES THEM OUT", "query": "microscope bacteria", "tr": {"es": "Tiene tan poca agua que los microbios se deshidratan y mueren al contacto.", "pt": "Tem tão pouca água que os micróbios desidratam e morrem ao contato.", "fr": "Il contient si peu d'eau que les microbes se dessèchent et meurent au contact.", "de": "Er enthält so wenig Wasser, dass Mikroben austrocknen und sofort sterben.", "hi": "उसमें पानी इतना कम होता है कि सूक्ष्मजीव संपर्क में आते ही सूखकर मर जाते हैं।"},
         "text": "It is so low in water that microbes dry out and die on contact.",
         "prompt": "microscopic bacteria shriveling in thick golden syrup, dramatic macro, dark background"},
        {"label": "BEE ENZYME", "query": "bees honeycomb", "tr": {"es": "Además, las abejas añaden una enzima que produce un poco de peróxido de hidrógeno en su interior.", "pt": "As abelhas também adicionam uma enzima que produz um pouco de peróxido de hidrogênio lá dentro.", "fr": "Les abeilles y ajoutent aussi une enzyme qui produit un peu de peroxyde d'hydrogène.", "de": "Außerdem fügen Bienen ein Enzym hinzu, das darin etwas Wasserstoffperoxid erzeugt.", "hi": "मधुमक्खियाँ उसमें एक एंज़ाइम भी मिलाती हैं, जो अंदर थोड़ा हाइड्रोजन पेरोक्साइड बनाता है।"},
         "text": "Bees also add an enzyme that makes a touch of hydrogen peroxide inside.",
         "prompt": "honeybees working inside a glowing hive of hexagonal honeycomb, macro"},
        {"label": "ACIDIC", "query": "honey pouring", "tr": {"es": "Y la propia miel es ácida, lo que la convierte en un lugar hostil para los gérmenes.", "pt": "E o próprio mel é ácido, o que o torna um lugar hostil para os germes.", "fr": "Et le miel est lui-même acide, ce qui en fait un endroit hostile pour les germes.", "de": "Und Honig selbst ist sauer, was ihn zu einem feindlichen Ort für Keime macht.", "hi": "और शहद खुद भी अम्लीय होता है, जो इसे कीटाणुओं के लिए एक मुश्किल जगह बना देता है।"},
         "text": "And the honey itself is acidic, which makes it a hostile place for germs.",
         "prompt": "a jar of honey on a rustic table with a dark moody kitchen background, steam of light"},
        {"label": "OUTLAST YOU", "query": "honey jar shelf", "tr": {"es": "Así que el tarro de tu despensa podría durar más que tú.", "pt": "Então o pote na sua despensa pode durar mais do que você.", "fr": "Alors le pot dans ton placard pourrait te survivre.", "de": "Das Glas in deiner Vorratskammer könnte dich also überleben.", "hi": "यानी आपकी रसोई में रखा शहद का डिब्बा आपसे भी ज़्यादा टिक सकता है।"},
         "text": "So the jar in your pantry could outlast you.",
         "prompt": "a lone jar of honey on a dusty shelf, decades of dust, sunbeam through window"},
        {"label": "YOUR GUESS?", "query": "pharaoh mask egypt", "tr": {"es": "¿Qué alimento crees que puede durar más tiempo?", "pt": "Qual comida você acha que dura mais tempo?", "fr": "Selon toi, quel aliment peut se conserver le plus longtemps ?", "de": "Welches Lebensmittel hält sich deiner Meinung nach am längsten?", "hi": "आपको क्या लगता है, कौन सा खाना सबसे ज़्यादा समय तक टिक सकता है?"},
         "text": "Which food do you think can survive the longest?",
         "prompt": "ancient Egyptian pharaoh golden mask next to a jar of honey, dramatic museum lighting"},
    ],
}


ELEVENLABS_VOICES = {  # premade voices available on this account
    "liam": "TX3LPaxmHKxFdv7VOQHJ",      # energetic social-media creator
    "brian": "nPczCjzI2devNBz1zQrb",     # deep, resonant
    "george": "JBFqnCBsd6RMkjVDRZzb",    # warm British storyteller
    "adam": "pNInz6obpgDQGcFmaJgB",      # dominant, firm
    "charlie": "IKne3meq5aSn9XLyUdCD",   # deep, energetic
    "daniel": "onwK4e9ZLuTAKqWW03F9",    # steady British broadcaster
    "callum": "N2lVS1w4EtoT3dr4eOWO",    # husky trickster
    "harry": "SOYHLrjzK2X1ezoPC6cr",     # fierce
    "laura": "FGY2WhTYpPnrIDTdsKH5", "jessica": "cgSgspJ2msm6clMCkdW9", "sarah": "EXAVITQu4vr4xnSDxMaL",
}
TTS_CACHE = Path.home() / "faceless_content" / "tts_cache"
# low stability + style = expressive, less monotone (old 0.5/0.0 was the flattest setting)
VOICE_SETTINGS = {"stability": 0.30, "similarity_boost": 0.75, "style": 0.55, "use_speaker_boost": True, "speed": 1.06}


def synthesize_elevenlabs(text: str, audio_path: Path, voice_name_or_id: str = "adam", model: str = "eleven_multilingual_v2", cjk: bool = False):
    """Synthesizes human-grade voiceover via ElevenLabs with word-level timestamps."""
    import base64, json, urllib.request
    from ai_video_engine import load_keys
    api_key = load_keys().get("elevenlabs")
    if not api_key:
        raise ValueError("Missing ElevenLabs API key in .ai_video_keys.json")

    voice_id = ELEVENLABS_VOICES.get(voice_name_or_id.lower(), voice_name_or_id)
    import hashlib
    ck = hashlib.sha256(json.dumps([text, voice_id, VOICE_SETTINGS] + ([model] if model != "eleven_multilingual_v2" else []) + (["cjk"] if cjk else []), sort_keys=True).encode()).hexdigest()[:16]
    TTS_CACHE.mkdir(parents=True, exist_ok=True)
    c_mp3, c_meta = TTS_CACHE / f"{ck}.mp3", TTS_CACHE / f"{ck}.json"
    if c_mp3.exists() and c_meta.exists():
        print(f"📦 [TTS Cache Hit] {voice_name_or_id}")
        shutil.copy2(c_mp3, audio_path)
        return json.loads(c_meta.read_text())
    print(f"🎙️ Synthesizing Human-Grade Voiceover via ElevenLabs (Voice: {voice_name_or_id})...")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
    payload = {
        "text": text,
        "model_id": model,
        "voice_settings": VOICE_SETTINGS
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    })

    with urllib.request.urlopen(req, timeout=60) as resp:
        res = json.loads(resp.read().decode("utf-8"))

    audio_bytes = base64.b64decode(res["audio_base64"])
    audio_path.write_bytes(audio_bytes)

    align = res.get("alignment", {})
    chars = align.get("characters", [])
    starts = align.get("character_start_times_seconds", [])
    ends = align.get("character_end_times_seconds", [])

    words, cur, c0, cs, ce = [], "", None, None, None

    def flush(last_idx):
        nonlocal cur, c0, cs, ce
        if cur:
            words.append({"text": cur, "start": cs, "end": ce, "c0": c0, "c1": last_idx})
        cur, c0, cs, ce = "", None, None, None

    for idx, (ch, st, en) in enumerate(zip(chars, starts, ends)):
        if ch.isspace():
            flush(idx - 1)
            continue
        if cur and cjk and (len(cur) >= 5 or cur[-1] in "，。！？、；：,.!?"):
            flush(idx - 1)
        if not cur:
            c0, cs = idx, st
        ce = en
        cur += ch
    flush(len(chars) - 1)

    c_mp3.write_bytes(audio_bytes)
    c_meta.write_text(json.dumps(words))
    return words


async def synthesize_edge_tts(text: str, audio_path: Path, voice: str = "en-US-ChristopherNeural"):
    """Synthesizes voiceover with accurate word-level boundary timestamps using edge-tts."""
    import edge_tts
    print(f"🎙️ Synthesizing Voiceover ({voice})...")
    comm = edge_tts.Communicate(text, voice, rate="+6%", pitch="+0Hz", boundary="WordBoundary")
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


def synthesize_voiceover(text: str, audio_path: Path, voice: str = "adam", voice_backend: str = "auto", lang: str = "en"):
    """ElevenLabs when a key exists (required for non-English), Edge-TTS fallback for English only."""
    from ai_video_engine import load_keys
    has_el = bool(load_keys().get("elevenlabs"))
    L = LANGS[lang]
    if lang != "en" or (voice_backend == "elevenlabs") or (voice_backend == "auto" and has_el and not voice.startswith("en-")):
        try:
            return synthesize_elevenlabs(text, audio_path, voice_name_or_id=voice, model=L.get("model", "eleven_multilingual_v2"), cjk=L["tier"] == "cjk")
        except Exception as e:
            if lang != "en":
                raise RuntimeError(f"ElevenLabs failed for '{lang}' (no fallback voice): {e}")
            print(f"⚠️ ElevenLabs voiceover failed ({e}); falling back to Edge-TTS.")
    edge_voice = voice if voice.startswith("en-") else "en-US-ChristopherNeural"
    return asyncio.run(synthesize_edge_tts(text, audio_path, voice=edge_voice))


# ---- languages: tier "latin" = space-delimited Latin/Cyrillic/Greek (Arial Black captions); "cjk" = char-chunked captions
ARIAL_BLACK = "/System/Library/Fonts/Supplemental/Arial Black.ttf"
ARIAL_UNI = "/Library/Fonts/Arial Unicode.ttf" if Path("/Library/Fonts/Arial Unicode.ttf").exists() else "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
_L = lambda name, tier="latin": {"name": name, "tier": tier, "font": ARIAL_UNI if tier == "cjk" else ARIAL_BLACK}
LANGS = {
    "en": _L("English"),
    "es": _L("Spanish"), "pt": _L("Portuguese"), "fr": _L("French"), "de": _L("German"), "it": _L("Italian"),
    "nl": _L("Dutch"), "pl": _L("Polish"), "tr": _L("Turkish"), "id": _L("Indonesian"), "ms": _L("Malay"),
    "sv": _L("Swedish"), "da": _L("Danish"), "fi": _L("Finnish"), "ro": _L("Romanian"), "cs": _L("Czech"),
    "sk": _L("Slovak"), "hr": _L("Croatian"), "fil": _L("Filipino"),
    "ru": _L("Russian"), "uk": _L("Ukrainian"), "bg": _L("Bulgarian"), "el": _L("Greek"),
    "ja": _L("Japanese", "cjk"), "zh": _L("Chinese", "cjk"), "ko": _L("Korean", "cjk"),
}
LANGS["hi"] = {"name": "Hindi", "tier": "ass", "font": "Kohinoor Devanagari"}  # captions burned via libass/HarfBuzz (Pillow lacks raqm)
UNSUPPORTED = {"ta": "Tamil", "ar": "Arabic"}  # voice works; captions untested/unshaped (Arabic needs bidi) - not enabled


def _ass_time(t):
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def make_ass(chunks, total, path, fontname):
    """Kinetic captions as an ASS file (libass shapes Devanagari correctly). Alternates yellow/white like the PNG path."""
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
            "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Cap,{fontname},98,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,8,3,2,60,60,520,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    lines = []
    for i, c in enumerate(chunks):
        st = 0.0 if i == 0 else c["start"]
        en = total if i == len(chunks) - 1 else chunks[i + 1]["start"]
        col = "&H15CCFA&" if i % 2 == 1 else "&HFFFFFF&"
        lines.append(f"Dialogue: 0,{_ass_time(st)},{_ass_time(max(en, st + 0.04))},Cap,,0,0,0,,{{\\c{col}}}{c['text']}")
    Path(path).write_text(head + "\n".join(lines) + "\n", encoding="utf-8")

TR_CACHE = Path.home() / "faceless_content" / "translation_cache.json"


def translate_text(text, lang, model="qwen2.5:3b"):
    """Local translation via Ollama, cached. A segment's own {"tr": {"es": "..."}} always wins over this."""
    import hashlib, requests
    cache = json.loads(TR_CACHE.read_text()) if TR_CACHE.exists() else {}
    key = hashlib.sha256(f"{model}|{lang}|{text}".encode()).hexdigest()[:16]
    if key in cache:
        return cache[key]
    prompt = (f"Translate this narration into {LANGS[lang]['name']}. Keep the meaning, sound natural and conversational for a short "
              f"video voiceover. Keep numbers and names unchanged. Output ONLY the translation, no notes or quotes.\n\n{text}")
    r = requests.post("http://localhost:11434/api/generate", timeout=180,
                      json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.2}})
    r.raise_for_status()
    out = r.json()["response"].strip().strip('"')
    if not out:
        raise RuntimeError(f"empty translation for {lang}")
    cache[key] = out
    TR_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    return out


IMG_CACHE = Path.home() / "faceless_content" / "image_cache"
FATAL = ("401", "402", "403", "locked", "balance", "unauthorized")


class BackendFatal(Exception):
    """Auth/balance failure: retrying or degrading would hide a real problem."""


def fal_image(prompt, out):
    """FLUX schnell via Fal.ai (~$0.003/img). Cached by prompt hash across runs."""
    import fal_client, hashlib, os, urllib.request
    IMG_CACHE.mkdir(parents=True, exist_ok=True)
    cached = IMG_CACHE / (hashlib.sha256(prompt.encode()).hexdigest()[:16] + ".jpg")
    if cached.exists() and cached.stat().st_size > 10000:
        print(f"📦 [Cache Hit] {cached.name}")
        shutil.copy2(cached, out)
        return
    fal_key = load_keys().get("fal")
    if not fal_key:
        raise BackendFatal("Missing FAL API key")
    os.environ["FAL_KEY"] = fal_key
    last = None
    for attempt in range(3):
        try:
            r = fal_client.subscribe("fal-ai/flux/schnell", arguments={
                "prompt": prompt, "image_size": "portrait_16_9", "num_images": 1,
                "num_inference_steps": 4, "enable_safety_checker": True})
            urllib.request.urlretrieve(r["images"][0]["url"], str(cached))
            shutil.copy2(cached, out)
            return
        except Exception as e:
            last = e
            if any(f in str(e).lower() for f in FATAL):
                raise BackendFatal(str(e))
            print(f"⚠️ Fal attempt {attempt+1}/3 failed ({e}); retrying")
            time.sleep(2 ** attempt * 2)
    raise RuntimeError(f"Fal failed after 3 attempts: {last}")


def cache_path(prompt, backend):
    import hashlib
    IMG_CACHE.mkdir(parents=True, exist_ok=True)
    return IMG_CACHE / f"{backend}_{hashlib.sha256(prompt.encode()).hexdigest()[:16]}.jpg"


def placeholder(img, i, label):
    """Local fallback still (gradient + keyword) used when no image backend is available."""
    from PIL import Image, ImageDraw, ImageFont
    pal = [(251, 191, 36), (234, 88, 12), (14, 116, 144), (79, 70, 229)]
    c = pal[i % len(pal)]
    im = Image.new("RGB", (1080, 1920))
    d = ImageDraw.Draw(im)
    for y in range(1920):
        t = y / 1920
        d.line([(0, y), (1080, y)], fill=tuple(int(v * (0.55 - 0.45 * t)) for v in c))
    f = "/System/Library/Fonts/Supplemental/Arial Black.ttf"
    font = ImageFont.truetype(f, 110) if Path(f).exists() else ImageFont.load_default()
    words = label.upper().split()[:3]
    for k, w in enumerate(words):
        d.text((540, 620 + k * 140), w, font=font, fill=(255, 255, 255), anchor="mm", stroke_width=5, stroke_fill="black")
    im.save(img)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--backend", choices=["stock", "runpod", "fal"], default="stock", help="visuals: stock footage (falls back to AI images per scene), runpod, or fal")
    ap.add_argument("--stock-sources", default="auto", help="comma list from pexels,pixabay,nasa (auto = keyed providers only; add nasa explicitly)")
    ap.add_argument("--allow-unchecked", action="store_true", help="render a spec still flagged needs_fact_check (drafts only; do not publish)")
    ap.add_argument("--lang", default="en", help="narration/caption language code (en, es, pt, fr, de, ja, ...) - see LANGS")
    ap.add_argument("--translator", default="qwen2.5:3b", help="local Ollama model used when a segment has no own translation")
    ap.add_argument("--voice", help="ElevenLabs voice name (liam, brian, george, adam, charlie...) or id; or an en-US-*Neural Edge voice")
    ap.add_argument("--audition", nargs="*", metavar="VOICE", help="render the first line in several voices, then exit")
    ap.add_argument("--voice-backend", choices=["auto", "elevenlabs", "edge"], default="auto", help="TTS voice backend (default auto)")
    a = ap.parse_args()
    spec = json.loads(Path(a.spec).read_text()) if a.spec else SAMPLE
    if a.audition is not None:
        out_dir = vr.BASE_DIR / "audition"; out_dir.mkdir(parents=True, exist_ok=True)
        for v in (a.audition or ["liam", "brian", "george", "charlie"]):
            f = out_dir / f"{v}.mp3"
            synthesize_elevenlabs(spec["segments"][0]["text"], f, voice_name_or_id=v)
            print("🔊", f)
        return
    local_only = bool(spec.get("local_only"))  # local-model drafts: render freely, but only into local_only/ (never the publish folder)
    if spec.get("needs_fact_check") and not (a.allow_unchecked or local_only):
        sys.exit("❌ This spec is an unchecked draft (needs_fact_check: true). Verify its claims, then remove the flag "
                 "(or pass --allow-unchecked for a preview you will NOT publish).")
    segs = spec["segments"]
    lang = a.lang.lower()
    if lang in UNSUPPORTED:
        sys.exit(f"❌ {UNSUPPORTED[lang]} ({lang}): voice works, but captions need complex-text shaping this Mac's Pillow lacks. Not supported yet.")
    if lang not in LANGS:
        sys.exit(f"❌ Unsupported language '{lang}'. Supported: {', '.join(LANGS)}")
    if lang != "en":
        segs = [{**sg, "text": (sg.get("tr") or {}).get(lang) or translate_text(sg["text"], lang, a.translator)} for sg in segs]
        spec = {**spec, "slug": f"{spec['slug']}_{lang}"}
        print(f"🌐 {LANGS[lang]['name']} script:\n   " + "\n   ".join(sg["text"] for sg in segs))
    base = (vr.BASE_DIR.parent / "local_only") if (local_only or a.allow_unchecked) else vr.BASE_DIR
    sd = base / f"{spec['slug']}_{int(time.time())}"
    sd.mkdir(parents=True, exist_ok=True)
    ff = shutil.which("ffmpeg") or str(Path.home() / "bin" / "ffmpeg")
    ffp = shutil.which("ffprobe") or str(Path.home() / "bin" / "ffprobe")

    text = " ".join(s["text"] for s in segs)
    audio = sd / "voiceover.mp3"
    voice = a.voice or spec.get("voice", "liam")
    words = synthesize_voiceover(text, audio, voice=voice, voice_backend=a.voice_backend, lang=lang)

    # Accurate duration extraction via ffprobe (fallback to regex on ffmpeg stderr)
    total = None
    if shutil.which("ffprobe") or Path(ffp).exists():
        try:
            probe = subprocess.check_output([
                ffp, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(audio)
            ]).decode().strip()
            total = float(probe)
        except Exception:
            total = None
    if total is None:
        err = subprocess.run([ff, "-i", str(audio)], capture_output=True, text=True).stderr
        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
        if m:
            h, mn, sec = m.groups()
            total = int(h) * 3600 + int(mn) * 60 + float(sec)
        else:
            total = words[-1]["end"] if words else 30.0
    print(f"⏱️ {total:.1f}s narration, {len(words)} words")

    # per-segment durations aligned to spoken word boundaries
    edges = [0.0]
    w_idx = 0
    n_split = sum(len(x["text"].split()) for x in segs)
    if n_split != len(words):
        print(f"⚠️ Token mismatch (text {n_split} vs TTS {len(words)}); using proportional alignment.")
        k, acc = len(words) / n_split, 0
        for x in segs[:-1]:
            acc += len(x["text"].split())
            edges.append(words[min(int(round(acc * k)) - 1, len(words) - 1)]["end"])
        segs_iter = []
    else:
        segs_iter = segs[:-1]
    for s in segs_iter:
        s_words = s["text"].split()
        w_idx += len(s_words)
        target_idx = min(w_idx - 1, len(words) - 1)
        if target_idx >= 0 and target_idx < len(words):
            edges.append(words[target_idx]["end"])
        else:
            edges.append(edges[-1] + 3.0)
    edges.append(total)
    if words and all("c1" in w for w in words):  # language-agnostic: align scene cuts by character offsets
        edges, start = [0.0], 0
        for sg in segs[:-1]:
            last = start + len(sg["text"]) - 1
            hit = next((w for w in words if w["c0"] <= last <= w["c1"]), None) or max((w for w in words if w["c0"] <= last), key=lambda w: w["c0"], default=None)
            edges.append(hit["end"] if hit else edges[-1] + 3.0)
            start += len(sg["text"]) + 1
        edges.append(total)
    durs = [max(edges[i + 1] - edges[i], 0.8) for i in range(len(segs))]

    clips, used_stock, licenses = [], set(), []
    prov_list = None if a.stock_sources == "auto" else [x.strip() for x in a.stock_sources.split(",") if x.strip()]
    pod = None  # started lazily, only if some scene is not cached
    try:
        for i, (s, d) in enumerate(zip(segs, durs)):
            img = sd / f"s{i}.jpg"
            prompt = s["prompt"] + STYLE
            if a.backend == "stock" and not a.dry_run and not s.get("ai"):  # "ai": true forces an AI illustration for this scene
                try:
                    import stock_footage as sf
                    q = s.get("query") or s.get("label") or " ".join(s["prompt"].split()[:4])
                    pin = s.get("clip", "")
                    hit = sf.nasa_by_id(pin.split(":", 1)[1]) if pin.startswith("nasa:") else \
                        sf.search(q, min_dur=min(d, 4.0), exclude=used_stock, providers=prov_list)
                    if hit:
                        used_stock.add(hit["id"])
                        clip = sd / f"c{i}.mp4"
                        sf.make_clip(sf.fetch(hit), d, clip, ff)
                        clips.append(clip)
                        licenses.append({"scene": i + 1, **hit})
                        print(f"  🎞️ scene {i+1}/{len(segs)} stock '{q}' -> {hit['provider']} {str(hit['id'])[:40]} by {hit['author']} ({d:.1f}s)")
                        continue
                    print(f"  ↪ scene {i+1}: no stock match for '{q}'; using AI image")
                except sf.NoStock as e:
                    sys.exit(f"❌ Stock unavailable: {e}\n   Or use --backend runpod for AI images.")
            if a.dry_run:
                placeholder(img, i, s.get("label") or " ".join(s["prompt"].split()[:3]))
            elif a.backend in ("runpod", "stock"):
                cp = cache_path(prompt, "runpod")
                if cp.exists() and cp.stat().st_size > 10000:
                    print(f"📦 [Cache Hit] scene {i+1}")
                else:
                    if pod is None:
                        from runpod_images import FluxPodSession
                        pod = FluxPodSession().__enter__()
                    pod.image(prompt, cp, seed=42 + i)
                shutil.copy2(cp, img)
            else:  # fal
                try:
                    fal_image(prompt, img)
                except BackendFatal as e:
                    sys.exit(f"❌ Fal unavailable: {e}\n   Use --backend runpod, or --dry-run for placeholder visuals.")
            clip = sd / f"c{i}.mp4"
            vr.create_scene_clip(img, d, clip)
            clips.append(clip)
            print(f"  ✅ scene {i+1}/{len(segs)} {d:.1f}s")
    finally:
        if pod is not None:
            pod.close()  # terminates the GPU pod even on error
        if licenses:
            (sd / "licenses.json").write_text(json.dumps(licenses, indent=2))

    # contact sheet: one frame per scene so matches can be reviewed before publishing
    try:
        from PIL import Image
        thumbs = []
        for i, c in enumerate(clips):
            t = sd / f"th{i}.png"
            subprocess.run([ff, "-y", "-ss", "0.8", "-i", str(c), "-frames:v", "1", "-vf", "scale=270:480", str(t)], check=True, capture_output=True)
            thumbs.append(Image.open(t))
        sheet = Image.new("RGB", (270 * len(thumbs), 480))
        for i, im in enumerate(thumbs):
            sheet.paste(im, (270 * i, 0))
        sheet.save(sd / "contact_sheet.png")
    except Exception as e:
        print(f"(contact sheet skipped: {e})")

    lst = sd / "clips.txt"
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips))
    bg = sd / "bg.mp4"
    subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(bg)],
                   check=True, capture_output=True)
    out = sd / (f"{spec['slug']}_LOCAL_ONLY.mp4" if (local_only or a.allow_unchecked) else f"{spec['slug']}.mp4")
    tier = LANGS[lang]["tier"]
    enc = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.2f}", str(out)]
    if tier == "ass":
        ass = sd / "captions.ass"
        make_ass(vr.chunk_kinetic_words(words, 3), total, ass, LANGS[lang]["font"])
        cmd = [ff, "-y", "-i", str(bg), "-i", str(audio), "-f", "lavfi", "-i", f"sine=frequency=55:duration={total:.2f}",
               "-filter_complex", f"[0:v]subtitles={ass}[v];[2:a]volume=0.035[d];[1:a][d]amix=inputs=2:duration=first[a]",
               "-map", "[v]", "-map", "[a]", *enc]
    else:
        caps = vr.render_caption_overlays(vr.chunk_kinetic_words(words, 1 if tier == 'cjk' else 3, '' if tier == 'cjk' else ' '), total, sd, font_path=LANGS[lang]['font'])
        cmd = [ff, "-y", "-i", str(bg), "-f", "concat", "-safe", "0", "-i", str(caps), "-i", str(audio),
               "-f", "lavfi", "-i", f"sine=frequency=55:duration={total:.2f}",
               "-filter_complex", "[0:v][1:v]overlay=0:0[v];[3:a]volume=0.035[d];[2:a][d]amix=inputs=2:duration=first[a]",
               "-map", "[v]", "-map", "[a]", *enc]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"\n🎉 Output Video Generated: {out}")
    if a.open:
        subprocess.run(["open", str(out)])


if __name__ == "__main__":
    main()
