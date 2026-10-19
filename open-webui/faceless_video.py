"""
title: Faceless Video Studio
author: local
version: 0.1.0
description: Generate a short faceless video (script + neural voice + 1080x1920 MP4) from a topic by calling the local AI Studio render pipeline on 127.0.0.1:8888. Output stays on this Mac; nothing is uploaded.
"""

import urllib.parse

import requests
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        STUDIO_URL: str = Field(
            default="http://127.0.0.1:8888",
            description="Base URL of the local AI Studio server (must be running).",
        )
        TIMEOUT_S: int = Field(
            default=960, description="Max seconds to wait; the server's own limit is 900."
        )

    def __init__(self):
        self.valves = self.Valves()

    async def create_video(
        self,
        topic: str,
        dialogue: bool = False,
        __event_emitter__=None,
    ) -> str:
        """
        Create a short vertical (1080x1920) faceless video about a topic. Takes several
        minutes on this CPU-only Mac and only one render can run at a time.
        :param topic: The topic, question or story the video should be about.
        :param dialogue: True for a two-person alternating dialogue instead of a monologue.
        :return: A link to the finished video, or an error message.
        """
        topic = (topic or "").strip()
        if not topic:
            return "Error: a topic is required."

        async def status(msg, done=False):
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": msg, "done": done}}
                )

        await status("Rendering video (usually 2-4+ minutes on CPU)...")
        try:
            r = requests.post(
                f"{self.valves.STUDIO_URL}/api/create_video",
                json={"topic": topic, "mode": "dialogue" if dialogue else "monologue"},
                timeout=self.valves.TIMEOUT_S,
            )
        except requests.exceptions.ConnectionError:
            await status("AI Studio is not reachable", True)
            return f"Error: cannot reach AI Studio at {self.valves.STUDIO_URL}. Is the local-ai-web service running?"
        except requests.exceptions.Timeout:
            await status("Timed out", True)
            return "Error: the render timed out. It may still finish; check ~/faceless_content later."

        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code == 429:
            await status("Another render is running", True)
            return "A video is already rendering. Try again when it finishes."
        if r.status_code != 200 or data.get("status") != "success":
            await status("Render failed", True)
            return f"Render failed ({r.status_code}): {data.get('error', 'unknown')}. {str(data.get('details', ''))[:300]}"

        path = data["video_path"]
        link = f"{self.valves.STUDIO_URL}/api/video_file?path={urllib.parse.quote(path)}"
        await status("Video ready", True)
        # post the link straight into the chat so a small model cannot garble the URL
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "message",
                    "data": {"content": f"\n\n🎬 **Video ready:** [open the video]({link})\n\nSaved at `{path}`\n"},
                }
            )
        return (
            "SUCCESS: the video was created and the download link has already been shown "
            "to the user. Reply with one short confirmation sentence. Do not write or repeat any URL."
        )
