import os
import json
import time
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MOVIES_FILE      = "movies_list.json"
STORY_STATE_FILE = "story_state.json"
PARTS_PER_MOVIE  = 100

# When remaining movies drop below this number, auto-generate more
AUTO_EXPAND_THRESHOLD = 5


class ContentBrain:

    def __init__(self):
        self.movies_data = self._load_movies()
        self.state       = self._load_state()

    # ─────────────────────────────────────────────────────────────────
    # MOVIES LIST MANAGEMENT
    # ─────────────────────────────────────────────────────────────────

    def _load_movies(self):
        if os.path.exists(MOVIES_FILE):
            with open(MOVIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "movies": [],
            "parts_per_movie": PARTS_PER_MOVIE,
            "current_movie_index": 0,
            "auto_expand": True
        }

    def _save_movies(self):
        with open(MOVIES_FILE, "w", encoding="utf-8") as f:
            json.dump(self.movies_data, f, indent=2, ensure_ascii=False)

    def _remaining_movies(self):
        total   = len(self.movies_data["movies"])
        current = self.movies_data.get("current_movie_index", 0)
        return total - current

    def _auto_expand_movies(self):
        """
        Ask Gemini to generate 20 more movie/story ideas that:
        - Are similar in genre/universe to recently completed movies
        - Include sequels, prequels, spin-offs, and completely new universes
        - Have NOT been done before
        Appends them to movies_list.json automatically.
        """
        if not self.movies_data.get("auto_expand", True):
            return

        existing      = self.movies_data["movies"]
        completed     = self.state.get("completed_movies", [])
        all_done      = completed if completed else existing[:5]
        done_str      = ", ".join(all_done[-10:])
        existing_str  = ", ".join(existing)

        print(f"🤖 Auto-expanding movie list (currently {len(existing)} movies)...")

        prompt = f"""
You are a YouTube content planner for a Hindi movie storytelling channel.

The channel has already covered or is covering these movies/stories:
{done_str}

Full existing list (do NOT repeat any of these):
{existing_str}

Generate exactly 20 NEW movie or story titles to add to the channel's content queue.

RULES:
1. Include a MIX of:
   - Direct sequels/prequels of already covered franchises (e.g. if Harry Potter done, add Cursed Child, Fantastic Beasts)
   - Completely new popular franchises (Marvel, DC, Star Wars, Disney, Pixar, anime films, Bollywood blockbusters)
   - Classic world cinema that Hindi audiences love
   - Popular book adaptations not yet done
2. All must be well-known stories with rich characters and plot — good for 100-part series
3. Do NOT include TV series — movies and book series only
4. Hindi audience preference — include some Bollywood and South Indian hits too
5. Absolutely NO repeats from the existing list

Return ONLY a JSON array of 20 title strings, nothing else:
["Title 1", "Title 2", ... "Title 20"]
"""

        models = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]

        for model_name in models:
            try:
                print(f"   🔄 Generating new movies with {model_name}...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                clean    = response.text.strip().replace("```json", "").replace("```", "").strip()
                new_list = json.loads(clean)

                if not isinstance(new_list, list):
                    continue

                # Filter out any duplicates
                existing_lower = [m.lower().strip() for m in existing]
                added = []
                for title in new_list:
                    if isinstance(title, str) and title.lower().strip() not in existing_lower:
                        self.movies_data["movies"].append(title)
                        added.append(title)

                self._save_movies()
                print(f"   ✅ Added {len(added)} new movies/stories:")
                for m in added:
                    print(f"      • {m}")
                return

            except Exception as e:
                print(f"   ⚠️ Movie expansion failed with {model_name}: {e}")
                continue

        print("   ⚠️ Auto-expand failed — continuing with existing list")

    # ─────────────────────────────────────────────────────────────────
    # STORY STATE MANAGEMENT
    # ─────────────────────────────────────────────────────────────────

    def _load_state(self):
        if os.path.exists(STORY_STATE_FILE):
            with open(STORY_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        # Initialize with first movie
        first_movie = self.movies_data["movies"][0] if self.movies_data["movies"] else "Harry Potter and the Sorcerer's Stone"
        return {
            "current_movie": first_movie,
            "current_movie_index": 0,
            "current_part": 0,
            "total_parts": PARTS_PER_MOVIE,
            "story_so_far": "",
            "last_scene_ending": "",
            "characters_introduced": [],
            "key_events_covered": [],
            "completed_movies": []
        }

    def _save_state(self):
        with open(STORY_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)

    def _advance_to_next_movie(self):
        """Called when current movie hits 100 parts. Move to next movie."""
        movies      = self.movies_data["movies"]
        current_idx = self.state["current_movie_index"]

        # Record completion
        completed = self.state.get("completed_movies", [])
        if self.state["current_movie"] not in completed:
            completed.append(self.state["current_movie"])
        self.state["completed_movies"] = completed

        print(f"🎉 '{self.state['current_movie']}' complete! ({len(completed)} movies done)")

        # Check if we need to expand the list
        remaining = self._remaining_movies()
        if remaining <= AUTO_EXPAND_THRESHOLD:
            print(f"⚠️  Only {remaining} movies left — auto-expanding...")
            self._auto_expand_movies()

        next_idx = current_idx + 1
        movies   = self.movies_data["movies"]  # reload after possible expansion

        if next_idx >= len(movies):
            # All movies done — cycle from beginning with fresh eyes
            print("🔁 All movies completed! Restarting from the beginning...")
            next_idx = 0
            self.state["completed_movies"] = []

        next_movie = movies[next_idx]
        print(f"🎬 Starting next: '{next_movie}'")

        self.state.update({
            "current_movie":         next_movie,
            "current_movie_index":   next_idx,
            "current_part":          0,
            "story_so_far":          "",
            "last_scene_ending":     "",
            "characters_introduced": [],
            "key_events_covered":    [],
        })

        self.movies_data["current_movie_index"] = next_idx
        self._save_state()
        self._save_movies()

    # ─────────────────────────────────────────────────────────────────
    # SCRIPT GENERATION
    # ─────────────────────────────────────────────────────────────────

    def generate_script(self):
        # Also check on every run if list is getting low
        if self._remaining_movies() <= AUTO_EXPAND_THRESHOLD:
            self._auto_expand_movies()

        # Advance movie if needed
        if self.state["current_part"] >= PARTS_PER_MOVIE:
            self._advance_to_next_movie()

        self.state["current_part"] += 1
        part_number  = self.state["current_part"]
        movie_name   = self.state["current_movie"]
        story_so_far = self.state.get("story_so_far", "")
        last_ending  = self.state.get("last_scene_ending", "")
        chars        = self.state.get("characters_introduced", [])
        events       = self.state.get("key_events_covered", [])

        print(f"🎬 Generating: {movie_name} — Part {part_number}/{PARTS_PER_MOVIE}")

        progress_pct = (part_number / PARTS_PER_MOVIE) * 100
        chars_str    = ", ".join(chars[-10:]) if chars else "None yet"
        events_str   = ", ".join(events[-8:]) if events else "None yet"

        story_context = ""
        if story_so_far:
            story_context = f"""
STORY SO FAR:
{story_so_far[-800:]}

LAST SCENE ENDED WITH:
{last_ending}
"""

        if part_number == 1:
            part_instruction = f"""
This is PART 1 — The Beginning.
- Set the world, introduce the protagonist and main setting vividly
- Build intrigue and excitement from the very first line
- End with a hook that makes viewers desperate for Part 2
- Opening line example: "Ek aisi kahani jo aapne kabhi nahi bhuli hogi..."
"""
        elif part_number == PARTS_PER_MOVIE:
            movies      = self.movies_data["movies"]
            next_idx    = self.state["current_movie_index"] + 1
            next_movie  = movies[next_idx] if next_idx < len(movies) else movies[0]
            part_instruction = f"""
This is PART {PARTS_PER_MOVIE} — THE GRAND FINALE.
- Resolve ALL major story threads with emotional satisfaction
- Give characters their deserved endings
- Create a memorable, emotional closing moment
- Final line MUST be: "Yeh thi '{movie_name}' ki poori kahani... Ab aage shuru hogi '{next_movie}' ki kahani — subscribe karo taaki ek part bhi miss na ho!"
"""
        else:
            part_instruction = f"""
This is PART {part_number} of {PARTS_PER_MOVIE} — Story progress: {progress_pct:.0f}% complete.
- Continue EXACTLY from where the last part ended — no gaps, no jumps
- Cover the next natural scene/chapter of the story
- Match the emotional tone of where the story currently is
- End on suspense, cliffhanger, or emotional moment — make them need Part {part_number + 1}
- Do NOT recap more than 1 line — viewers have seen all previous parts
"""

        prompt = f"""
You are a master Hindi narrator creating a gripping {PARTS_PER_MOVIE}-part Hindi storytelling YouTube Shorts series.

MOVIE/STORY: {movie_name}
CURRENT PART: {part_number} of {PARTS_PER_MOVIE}
STORY PROGRESS: {progress_pct:.0f}% complete

CHARACTERS INTRODUCED SO FAR: {chars_str}
KEY EVENTS ALREADY COVERED: {events_str}
{story_context}

{part_instruction}

NARRATION STYLE:
- Language: Passionate, dramatic Hinglish — exactly how a desi storyteller speaks
- Tone: Like a grand dadi/nani telling a bedtime story with full emotion
- Length: 50-60 seconds when read aloud naturally (~120-140 words)
- Every character must feel real and alive
- Emotions: joy, fear, love, betrayal, suspense — let viewers FEEL it
- End every part making viewers desperate for the next

VISUAL IMAGE GENERATION RULES:
- image_prompt_1 and image_prompt_2 are used to generate AI images via Pollinations.ai
- Write detailed English visual descriptions of the EXACT scene being narrated
- Include: characters present, setting/location, mood/lighting, action happening
- Style suffix to always add: "cinematic fantasy art, dramatic lighting, ultra detailed, movie scene, 8k"
- Make prompts specific — not generic

Return ONLY valid JSON:
[
  {{
    "id": 1,
    "movie": "{movie_name}",
    "part_number": {part_number},
    "total_parts": {PARTS_PER_MOVIE},
    "title": "{movie_name} | Part {part_number} — [catchy 4-5 word Hindi scene name]",
    "text": "Full Hindi narration (50-60 seconds when read aloud)",
    "hook_text": "Part {part_number}: [4-5 dramatic Hindi/Hinglish words]",
    "image_prompt_1": "Detailed scene description + cinematic fantasy art, dramatic lighting, ultra detailed, movie scene, 8k",
    "image_prompt_2": "Different angle or next moment of same scene + cinematic fantasy art, dramatic lighting, ultra detailed, movie scene, 8k",
    "new_characters": ["only characters appearing for first time in THIS part"],
    "new_events": ["2-3 key plot points from THIS part only"],
    "story_summary": "2-3 sentences: complete story summary up to and including this part",
    "scene_ending": "Exact last sentence/moment of this part — for seamless Part {part_number + 1} continuation"
  }}
]
"""

        models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.1-flash"]

        for model_name in models:
            for attempt in range(3):
                try:
                    print(f"   🔄 {model_name} (attempt {attempt+1}/3)")
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config={"response_mime_type": "application/json"}
                    )

                    clean  = response.text.strip().replace("```json", "").replace("```", "").strip()
                    result = json.loads(clean)

                    if isinstance(result, dict):
                        result = [result]

                    scene = result[0]

                    # ── Update story memory ──────────────────────────
                    new_chars  = scene.get("new_characters", [])
                    new_events = scene.get("new_events", [])

                    existing_chars = self.state.get("characters_introduced", [])
                    for c in new_chars:
                        if c not in existing_chars:
                            existing_chars.append(c)
                    self.state["characters_introduced"] = existing_chars

                    existing_events = self.state.get("key_events_covered", [])
                    existing_events.extend(new_events)
                    self.state["key_events_covered"] = existing_events[-30:]

                    if scene.get("story_summary"):
                        self.state["story_so_far"]      = scene["story_summary"]
                    if scene.get("scene_ending"):
                        self.state["last_scene_ending"] = scene["scene_ending"]

                    self._save_state()

                    print(f"   ✅ SUCCESS: Part {part_number} | New chars: {new_chars}")
                    return result

                except Exception as e:
                    err = str(e)
                    print(f"   ❌ {model_name}: {err[:150]}")
                    if "503" in err or "high demand" in err:
                        time.sleep(10)
                        continue
                    else:
                        break

        # All failed — rollback part counter
        self.state["current_part"] -= 1
        self._save_state()
        print("❌ All models failed.")
        return None


if __name__ == "__main__":
    brain = ContentBrain()
    output = brain.generate_script()
    if output:
        with open("latest_script.json", "w", encoding="utf-8") as f:
            json.dump(output, f, indent=4, ensure_ascii=False)
        print("✅ Saved to latest_script.json")