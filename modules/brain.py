import os
import json
import time
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MOVIES_FILE            = "movies_list.json"
STORY_STATE_FILE       = "story_state.json"
PARTS_PER_MOVIE        = 100
AUTO_EXPAND_THRESHOLD  = 5


class ContentBrain:

    def __init__(self):
        self.movies_data = self._load_movies()
        self.state       = self._load_state()

    # ─────────────────────────────────────────────────────────────────
    # MOVIES LIST
    # ─────────────────────────────────────────────────────────────────

    def _load_movies(self):
        if os.path.exists(MOVIES_FILE):
            with open(MOVIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"movies": [], "parts_per_movie": PARTS_PER_MOVIE,
                "current_movie_index": 0, "auto_expand": True}

    def _save_movies(self):
        with open(MOVIES_FILE, "w", encoding="utf-8") as f:
            json.dump(self.movies_data, f, indent=2, ensure_ascii=False)

    def _remaining_movies(self):
        return len(self.movies_data["movies"]) - self.movies_data.get("current_movie_index", 0)

    def _auto_expand_movies(self):
        if not self.movies_data.get("auto_expand", True):
            return
        existing     = self.movies_data["movies"]
        completed    = self.state.get("completed_movies", [])
        done_str     = ", ".join((completed or existing)[-10:])
        existing_str = ", ".join(existing)
        print(f"🤖 Auto-expanding movie list ({len(existing)} currently)...")

        prompt = f"""
You are a YouTube content planner for a Hindi movie storytelling channel.

Already covered: {done_str}
Full existing list (NO repeats): {existing_str}

Generate exactly 20 NEW movie/story titles for the queue.
Include: sequels/prequels of existing franchises, new popular franchises,
Marvel, DC, Star Wars, Disney, Pixar, anime films, Bollywood blockbusters,
South Indian hits dubbed in Hindi, classic world cinema.
All must be well-known with rich plot — good for 100-part series.
NO TV series. NO repeats.

Return ONLY a JSON array of 20 strings: ["Title 1", ..., "Title 20"]
"""
        for model_name in ["gemini-2.5-flash", "gemini-2.5-flash-lite"]:
            try:
                resp  = client.models.generate_content(
                    model=model_name, contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                clean = resp.text.strip().replace("```json","").replace("```","").strip()
                new_list = json.loads(clean)
                if not isinstance(new_list, list):
                    continue
                existing_lower = [m.lower().strip() for m in existing]
                added = []
                for title in new_list:
                    if isinstance(title, str) and title.lower().strip() not in existing_lower:
                        self.movies_data["movies"].append(title)
                        added.append(title)
                self._save_movies()
                print(f"   ✅ Added {len(added)} new movies")
                for m in added: print(f"      • {m}")
                return
            except Exception as e:
                print(f"   ⚠️ Expand failed ({model_name}): {e}")

    # ─────────────────────────────────────────────────────────────────
    # STORY STATE
    # ─────────────────────────────────────────────────────────────────

    def _load_state(self):
        if os.path.exists(STORY_STATE_FILE):
            with open(STORY_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        first = self.movies_data["movies"][0] if self.movies_data["movies"] else "Harry Potter and the Sorcerer's Stone"
        return {"current_movie": first, "current_movie_index": 0,
                "current_part": 0, "total_parts": PARTS_PER_MOVIE,
                "story_so_far": "", "last_scene_ending": "",
                "characters_introduced": [], "key_events_covered": [],
                "completed_movies": []}

    def _save_state(self):
        with open(STORY_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)

    def _advance_to_next_movie(self):
        completed = self.state.get("completed_movies", [])
        if self.state["current_movie"] not in completed:
            completed.append(self.state["current_movie"])
        self.state["completed_movies"] = completed
        print(f"🎉 '{self.state['current_movie']}' complete!")

        if self._remaining_movies() <= AUTO_EXPAND_THRESHOLD:
            self._auto_expand_movies()

        next_idx = self.state["current_movie_index"] + 1
        movies   = self.movies_data["movies"]

        if next_idx >= len(movies):
            print("🔁 All movies done — restarting!")
            next_idx = 0
            self.state["completed_movies"] = []

        next_movie = movies[next_idx]
        print(f"🎬 Next movie: '{next_movie}'")

        self.state.update({
            "current_movie": next_movie, "current_movie_index": next_idx,
            "current_part": 0, "story_so_far": "",
            "last_scene_ending": "", "characters_introduced": [],
            "key_events_covered": [],
        })
        self.movies_data["current_movie_index"] = next_idx
        self._save_state()
        self._save_movies()

    # ─────────────────────────────────────────────────────────────────
    # SCRIPT GENERATION
    # ─────────────────────────────────────────────────────────────────

    def generate_script(self):
        if self._remaining_movies() <= AUTO_EXPAND_THRESHOLD:
            self._auto_expand_movies()
        if self.state["current_part"] >= PARTS_PER_MOVIE:
            self._advance_to_next_movie()

        self.state["current_part"] += 1
        part_number  = self.state["current_part"]
        movie_name   = self.state["current_movie"]
        story_so_far = self.state.get("story_so_far", "")
        last_ending  = self.state.get("last_scene_ending", "")
        chars        = self.state.get("characters_introduced", [])
        events       = self.state.get("key_events_covered", [])
        progress_pct = (part_number / PARTS_PER_MOVIE) * 100

        chars_str  = ", ".join(chars[-10:])  if chars  else "None yet"
        events_str = ", ".join(events[-8:])  if events else "None yet"

        story_context = ""
        if story_so_far:
            story_context = f"\nSTORY SO FAR:\n{story_so_far[-600:]}\n\nLAST SCENE:\n{last_ending}\n"

        if part_number == 1:
            part_instr = "PART 1 — Introduction. Set the world, introduce protagonist. End with hook for Part 2."
        elif part_number == PARTS_PER_MOVIE:
            movies   = self.movies_data["movies"]
            nxt      = movies[(self.state["current_movie_index"]+1) % len(movies)]
            part_instr = f"PART {PARTS_PER_MOVIE} — GRAND FINALE. Resolve all threads emotionally. Final line MUST be: \"Yeh thi '{movie_name}' ki poori kahani... Ab shuru hogi '{nxt}' ki kahani — subscribe karo!\""
        else:
            part_instr = f"PART {part_number}/{PARTS_PER_MOVIE} ({progress_pct:.0f}% done). Continue EXACTLY from last scene. End on cliffhanger."

        prompt = f"""
You are a master Hindi narrator making a {PARTS_PER_MOVIE}-part Hindi storytelling YouTube Shorts series.

MOVIE: {movie_name}
PART: {part_number}/{PARTS_PER_MOVIE}
CHARACTERS SO FAR: {chars_str}
EVENTS COVERED: {events_str}
{story_context}
INSTRUCTION: {part_instr}

NARRATION: Passionate Hinglish, campfire storyteller energy, 50-60 seconds (~130 words).

IMAGE PROMPTS RULES — VERY IMPORTANT:
Generate exactly 7 image_prompts — each is a DIFFERENT shot/moment from this part's scene.
Each prompt must:
- Describe a specific visual moment from the narration
- Include: who is in the scene, what they are doing, where, what mood/lighting
- End with: "cinematic fantasy illustration, dramatic lighting, ultra detailed, 8k"
- Be varied — wide shots, close-ups, action shots, emotional moments

PEXELS MOOD RULES:
Generate 2 pexels_moods — 3-4 word English search terms for atmosphere clips.
These are SHORT real clips to mix between images.
Examples: "castle fog night", "candles dark room", "forest moonlight mist", "fire sparks dark"
NO abstract words. Real filmable things only.

Return ONLY valid JSON:
[
  {{
    "id": 1,
    "movie": "{movie_name}",
    "part_number": {part_number},
    "total_parts": {PARTS_PER_MOVIE},
    "title": "{movie_name} | Part {part_number} — [catchy Hindi scene name]",
    "text": "Full Hindi narration script (50-60 seconds when read aloud)",
    "hook_text": "Part {part_number}: [5 dramatic Hindi words]",
    "image_prompts": [
      "Shot 1: [specific scene description] Disney Pixar 3D animated style, soft warm golden lighting, big expressive eyes, smooth textures, Pixar movie render quality, ultra detailed, 8k",
      "Shot 2: [specific scene description] Disney Pixar 3D animated style, soft warm golden lighting, big expressive eyes, smooth textures, Pixar movie render quality, ultra detailed, 8k",
      "Shot 3: [specific scene description] Disney Pixar 3D animated style, soft warm golden lighting, big expressive eyes, smooth textures, Pixar movie render quality, ultra detailed, 8k",
      "Shot 4: [specific scene description] Disney Pixar 3D animated style, soft warm golden lighting, big expressive eyes, smooth textures, Pixar movie render quality, ultra detailed, 8k",
      "Shot 5: [specific scene description] Disney Pixar 3D animated style, soft warm golden lighting, big expressive eyes, smooth textures, Pixar movie render quality, ultra detailed, 8k",
      "Shot 6: [specific scene description] Disney Pixar 3D animated style, soft warm golden lighting, big expressive eyes, smooth textures, Pixar movie render quality, ultra detailed, 8k",
      "Shot 7: [specific scene description] Disney Pixar 3D animated style, soft warm golden lighting, big expressive eyes, smooth textures, Pixar movie render quality, ultra detailed, 8k"
    ],
    "pexels_moods": ["3-4 word mood clip 1", "3-4 word mood clip 2"],
    "new_characters": ["new character names only"],
    "new_events": ["2-3 key plot points from this part"],
    "story_summary": "2-3 sentence complete story summary up to this part",
    "scene_ending": "Exact last moment of this part for Part {part_number+1} continuity"
  }}
]
"""

        models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.1-flash"]

        for model_name in models:
            for attempt in range(3):
                try:
                    print(f"   🔄 {model_name} (attempt {attempt+1})")
                    response = client.models.generate_content(
                        model=model_name, contents=prompt,
                        config={"response_mime_type": "application/json"}
                    )
                    clean  = response.text.strip().replace("```json","").replace("```","").strip()
                    result = json.loads(clean)
                    if isinstance(result, dict):
                        result = [result]

                    scene = result[0]

                    # Update state
                    for c in scene.get("new_characters", []):
                        if c not in self.state["characters_introduced"]:
                            self.state["characters_introduced"].append(c)
                    self.state["key_events_covered"].extend(scene.get("new_events", []))
                    self.state["key_events_covered"] = self.state["key_events_covered"][-30:]
                    if scene.get("story_summary"):
                        self.state["story_so_far"]      = scene["story_summary"]
                    if scene.get("scene_ending"):
                        self.state["last_scene_ending"] = scene["scene_ending"]
                    self._save_state()

                    n_imgs = len(scene.get("image_prompts", []))
                    print(f"   ✅ Part {part_number} | {n_imgs} images | moods: {scene.get('pexels_moods', [])}")
                    return result

                except Exception as e:
                    err = str(e)
                    print(f"   ❌ {model_name}: {err[:150]}")
                    if "503" in err or "high demand" in err:
                        time.sleep(10)
                        continue
                    else:
                        break

        self.state["current_part"] -= 1
        self._save_state()
        print("❌ All models failed.")
        return None


if __name__ == "__main__":
    brain = ContentBrain()
    out   = brain.generate_script()
    if out:
        with open("latest_script.json", "w", encoding="utf-8") as f:
            json.dump(out, f, indent=4, ensure_ascii=False)
        print("✅ latest_script.json saved")
