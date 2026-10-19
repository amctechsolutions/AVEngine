"""
title: Video Studio (local drafts)
author: local
version: 0.1.0
description: Draft private local-only scripts with the local model, check stock footage for them, and render local-only preview videos with the viral_custom pipeline. Rendering shows an on-screen confirmation before it spends ElevenLabs credits or a GPU pod. Output stays on this Mac (~/faceless_content/local_only); nothing is uploaded.
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path

from pydantic import BaseModel, Field

SAFE_SLUG = re.compile(r"^[a-z0-9_]{1,60}$")


class Tools:
    class Valves(BaseModel):
        PROJECT_DIR: str = Field(default=str(Path.home()), description="Folder holding script_gen.py, topic_check.py, viral_custom.py, drafts/")
        PYTHON: str = Field(
            default="/Library/Developer/CommandLineTools/usr/bin/python3",
            description="Interpreter that has requests, Pillow, runpod installed.",
        )

    def __init__(self):
        self.valves = self.Valves()

    # ---------- helpers (state lives on disk: the tool may be re-instantiated between calls) ----------
    def _dir(self):
        return Path(self.valves.PROJECT_DIR)

    def _jobs_dir(self):
        d = self._dir() / "faceless_content" / "jobs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _alive(self, pid):
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _jobs(self):
        out = []
        for f in sorted(self._jobs_dir().glob("job_*.json")):
            try:
                out.append(json.loads(f.read_text()))
            except Exception:
                pass
        return out

    def _running(self):
        return [j for j in self._jobs() if self._alive(j["pid"])]

    def _spawn(self, kind, args):
        if self._running():
            return None, "Another job is still running. Use job_status, wait for it to finish, then try again."
        jid = f"{int(time.time())}"
        log = self._jobs_dir() / f"job_{jid}.log"
        proc = subprocess.Popen(
            [self.valves.PYTHON, "-u"] + args,
            cwd=str(self._dir()),
            stdout=open(log, "w"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        (self._jobs_dir() / f"job_{jid}.json").write_text(json.dumps({"id": jid, "kind": kind, "pid": proc.pid, "log": str(log)}))
        return jid, None

    def _spec(self, slug):
        slug = (slug or "").strip().lower()
        if not SAFE_SLUG.match(slug):
            return None, None, "Invalid draft name. Use list_drafts to see the names."
        p = self._dir() / "drafts" / f"{slug}.json"
        if not p.exists():
            # small models retype long names (often restoring a truncated word), so accept a unique prefix match either way
            stems = [f.stem for f in (self._dir() / "drafts").glob("*.json")]
            hits = [s for s in stems if s.startswith(slug) or slug.startswith(s) or slug.startswith(s[:-3])]
            if len(hits) != 1:
                return None, None, f"No draft named '{slug}'. Available: {', '.join(sorted(stems)) or 'none'}."
            slug = hits[0]
            p = self._dir() / "drafts" / f"{slug}.json"
        return slug, json.loads(p.read_text()), None

    # ---------- tools ----------
    async def draft_script(self, topic: str, facts: str = "", __event_emitter__=None) -> str:
        """
        Start drafting a private, local-only video script with the local model. Takes about 3 minutes and runs in the
        background; call job_status to follow it. Supplying facts (one per line) makes the draft far more reliable.
        :param topic: The topic of the video, e.g. "Termite mound cooling".
        :param facts: Optional verified facts, one per line (or separated by semicolons). The model only rephrases them.
        :return: A job id to check with job_status.
        """
        topic = (topic or "").strip()
        if not topic or len(topic) > 120:
            return "Error: give a topic of up to 120 characters."
        args = [str(self._dir() / "script_gen.py"), topic]
        fl = [x.strip() for x in re.split(r"[\n;]+", facts or "") if x.strip()]
        if fl:
            ff = self._jobs_dir() / f"facts_{int(time.time())}.txt"
            ff.write_text("\n".join(fl))
            args += ["--facts", str(ff)]
        jid, err = self._spawn("draft", args)
        if err:
            return err
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": "Drafting script in the background (~3 min)", "done": True}})
        mode = f"with {len(fl)} supplied facts" if fl else "WITHOUT facts (the model will guess facts; treat it as unreliable)"
        return f"Started drafting '{topic}' {mode}. Job {jid}. Ask for job_status in about 3 minutes."

    async def job_status(self, job_id: str = "") -> str:
        """
        Show progress of the latest (or a given) draft or render job.
        :param job_id: Optional job id; leave empty for the latest job.
        :return: Whether the job is running or finished, plus the end of its log.
        """
        jobs = self._jobs()
        if not jobs:
            return "No jobs yet."
        j = next((x for x in jobs if x["id"] == job_id), None) if job_id else jobs[-1]
        if not j:
            return f"No job {job_id}."
        running = self._alive(j["pid"])
        tail = "\n".join(Path(j["log"]).read_text(errors="replace").splitlines()[-12:])
        return f"Job {j['id']} ({j['kind']}): {'RUNNING' if running else 'FINISHED'}\n{tail}"

    async def list_drafts(self) -> str:
        """
        List the local-only script drafts that exist, with scene counts.
        :return: One line per draft.
        """
        d = self._dir() / "drafts"
        rows = []
        for f in sorted(d.glob("*.json")) if d.exists() else []:
            try:
                s = json.loads(f.read_text())
                segs = s.get("segments", [])
                rows.append(f"- {f.stem}: {len(segs)} scenes, {sum(1 for x in segs if x.get('ai'))} AI-image scenes, "
                            f"{sum(len(x['text'].split()) for x in segs)} words, local_only={s.get('local_only', False)}")
            except Exception:
                continue
        return "\n".join(rows) or "No drafts yet. Use draft_script."

    async def show_draft(self, slug: str) -> str:
        """
        Show the scenes of a draft.
        :param slug: Draft name from list_drafts.
        :return: The numbered narration lines with their footage search words.
        """
        slug, spec, err = self._spec(slug)
        if err:
            return err
        lines = [f"{i}. [{'AI' if s.get('ai') else s.get('query')}] {s['text']}" for i, s in enumerate(spec["segments"], 1)]
        return f"{slug} ({spec.get('title', '')})\n" + "\n".join(lines)

    async def check_footage(self, slug: str) -> str:
        """
        Free preflight: check that real stock footage exists for every scene of a draft.
        :param slug: Draft name from list_drafts.
        :return: A table of scenes with footage counts, flagging scenes with none.
        """
        slug, spec, err = self._spec(slug)
        if err:
            return err
        r = subprocess.run([self.valves.PYTHON, str(self._dir() / "topic_check.py"), str(self._dir() / "drafts" / f"{slug}.json")],
                           cwd=str(self._dir()), capture_output=True, text=True, timeout=180)
        return (r.stdout or r.stderr)[-1800:]

    async def render_preview(self, slug: str, lang: str = "en", dry_run: bool = False, __event_call__=None, __event_emitter__=None) -> str:
        """
        Render a private local-only preview video from a draft. A confirmation dialog is shown to the user first,
        because rendering spends ElevenLabs credits and (for AI-image scenes) a short GPU pod session.
        :param slug: Draft name from list_drafts.
        :param lang: Language code (en, es, fr, de, pt, ja, hi, ...). Default en.
        :param dry_run: True uses placeholder visuals (no GPU pod, still uses ElevenLabs credits for the voice).
        :return: A job id to check with job_status.
        """
        slug, spec, err = self._spec(slug)
        if err:
            return err
        if not re.match(r"^[a-z]{2,3}$", (lang or "en").lower()):
            return "Invalid language code."
        chars = sum(len(s["text"]) for s in spec["segments"])
        ai_n = sum(1 for s in spec["segments"] if s.get("ai"))
        pod = "no GPU pod (dry run)" if dry_run else (f"a GPU pod for {ai_n} AI scene(s), about $0.03-0.05" if ai_n else "no GPU pod needed")
        msg = (f"Render '{slug}' ({lang}) as a LOCAL-ONLY preview?\n\n"
               f"- ElevenLabs voice: about {chars} characters of your quota\n- Visuals: {pod}\n"
               f"- Output stays in ~/faceless_content/local_only")
        if not __event_call__:
            return "Cannot ask for confirmation in this client, so nothing was rendered."
        ok = await __event_call__({"type": "confirmation", "data": {"title": "Spend credits to render?", "message": msg}})
        if not ok:
            return "Cancelled by the user. Nothing was spent."
        args = [str(self._dir() / "viral_custom.py"), "--spec", str(self._dir() / "drafts" / f"{slug}.json"), "--stock-sources", "pixabay",
                "--lang", lang.lower(), "--open"]
        if dry_run:
            args.append("--dry-run")
        jid, err = self._spawn("render", args)
        if err:
            return err
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": "Rendering in the background", "done": True}})
        return f"Rendering '{slug}' in the background. Job {jid}. Use job_status to follow it; the video opens on the Mac when done."
