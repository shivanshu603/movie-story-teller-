import os
import json
import time
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MOVIES_FILE           = "movies_list.json"
STORY_STATE_FILE      = "story_state.json"
PARTS_PER_MOVIE       = 100
AUTO_EXPAND_THRESHOLD = 5

PIXAR_STYLE = (
    "Disney Pixar 3D animated style, soft warm golden rim lighting, "
    "big expressive eyes, smooth rounded textures, vibrant rich colors, "
    "Pixar movie render quality, cinematic depth of field, ultra detailed, 8k"
)


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
Include: sequels/prequels of existing franchises, Marvel, DC, Star Wars,
Disney, Pixar, anime films, Bollywood blockbusters, South Indian hits.
All must be well-known with rich plot. NO TV series. NO repeats.

Return ONLY a JSON array of 20 strings: ["Title 1", ..., "Title 20"]
"""
        for model_name in ["gemini-2.5-flash", "gemini-2.5-flash-lite"]:
            try:
                resp     = client.models.generate_content(
                    model=model_name, contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                clean    = resp.text.strip().replace("```json","").replace("```","").strip()
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
                for m in added:
                    print(f"      • {m}")
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
        return self._fresh_state(first, 0)

    def _fresh_state(self, movie_name, movie_index):
        return {
            "current_movie":       movie_name,
            "current_movie_index": movie_index,
            "current_part":        0,
            "total_parts":         PARTS_PER_MOVIE,
            "movie_outline":       [],   # 100-point outline generated once
            "character_profiles":  {},
            "key_events_covered":  [],
            "character_emotions":  {},
            "last_scene_ending":   "",
            "completed_movies":    self.state.get("completed_movies", []) if hasattr(self, "state") else []
        }

    def _save_state(self):
        with open(STORY_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)

    def _advance_to_next_movie(self):
        completed = self.state.get("completed_movies", [])
        if self.state["current_movie"] not in completed:
            completed.append(self.state["current_movie"])

        if self._remaining_movies() <= AUTO_EXPAND_THRESHOLD:
            self._auto_expand_movies()

        next_idx = self.state["current_movie_index"] + 1
        movies   = self.movies_data["movies"]
        if next_idx >= len(movies):
            print("🔁 All movies done — restarting!")
            next_idx = 0
            completed = []

        next_movie = movies[next_idx]
        print(f"🎬 Next: '{next_movie}'")

        self.state = self._fresh_state(next_movie, next_idx)
        self.state["completed_movies"] = completed
        self.movies_data["current_movie_index"] = next_idx
        self._save_state()
        self._save_movies()

    # ─────────────────────────────────────────────────────────────────
    # STEP 1 — GENERATE MOVIE OUTLINE (once per movie)
    # This is the KEY fix — Gemini maps the entire movie into 100 beats
    # so it never goes off-track
    # ─────────────────────────────────────────────────────────────────

    def _generate_movie_outline(self, movie_name):
        """
        Generate a 100-point story outline for the movie.
        Each point = one Short's worth of story.
        This keeps Gemini on the actual movie's track for all 100 parts.
        """
        print(f"📋 Generating 100-point outline for: {movie_name}...")

        prompt = f"""
You are an expert storyteller and film analyst.

Create a detailed 100-point story outline for: "{movie_name}"

RULES:
- Follow the ACTUAL movie/story exactly — real events, real characters, real plot
- Each point covers one scene or story beat (~30-45 seconds of narration)
- Points must be in chronological order
- Each point must mention: what happens + which characters are involved
- Include ALL major characters — not just the protagonist
- Cover the COMPLETE story from beginning to end across all 100 points
- If this is a creative/original story (like a fan continuation), create a logical, detailed plot
- Do NOT skip important scenes or characters

FORMAT — Return ONLY a JSON array of exactly 100 strings:
[
  "Point 1: [what happens, which characters, key detail]",
  "Point 2: [what happens, which characters, key detail]",
  ...
  "Point 100: [final resolution, all character endings]"
]
"""

        models = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]

        for model_name in models:
            for attempt in range(3):
                try:
                    print(f"   🔄 Outline: {model_name} (attempt {attempt+1})")
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config={
                            "response_mime_type": "application/json",
                            "max_output_tokens": 8000,
                        }
                    )
                    clean   = response.text.strip().replace("```json","").replace("```","").strip()
                    outline = json.loads(clean)

                    if isinstance(outline, list) and len(outline) >= 90:
                        # Pad to exactly 100 if needed
                        while len(outline) < 100:
                            outline.append(f"Point {len(outline)+1}: Continuation of story resolution")
                        outline = outline[:100]
                        print(f"   ✅ Outline generated: {len(outline)} points")
                        print(f"   📌 First: {outline[0][:80]}...")
                        print(f"   📌 Last:  {outline[-1][:80]}...")
                        return outline
                    else:
                        print(f"   ⚠️ Only {len(outline) if isinstance(outline, list) else 0} points — retrying")
                        continue

                except Exception as e:
                    err = str(e)
                    print(f"   ❌ {model_name}: {err[:100]}")
                    if "503" in err or "high demand" in err:
                        time.sleep(10)
                        continue
                    else:
                        break

        print("   ⚠️ Outline generation failed — using empty outline")
        return []

    # ─────────────────────────────────────────────────────────────────
    # SCRIPT GENERATION
    # ─────────────────────────────────────────────────────────────────

    def generate_script(self):
        if self._remaining_movies() <= AUTO_EXPAND_THRESHOLD:
            self._auto_expand_movies()
        if self.state["current_part"] >= PARTS_PER_MOVIE:
            self._advance_to_next_movie()

        # Generate outline if this is a new movie (Part 0 → Part 1)
        if self.state["current_part"] == 0 and not self.state.get("movie_outline"):
            outline = self._generate_movie_outline(self.state["current_movie"])
            self.state["movie_outline"] = outline
            self._save_state()

        self.state["current_part"] += 1
        part_number   = self.state["current_part"]
        movie_name    = self.state["current_movie"]
        outline       = self.state.get("movie_outline", [])
        last_ending   = self.state.get("last_scene_ending", "")
        char_profiles = self.state.get("character_profiles", {})
        events        = self.state.get("key_events_covered", [])
        emotions      = self.state.get("character_emotions", {})
        progress_pct  = (part_number / PARTS_PER_MOVIE) * 100

        # ── Get this part's outline point + surrounding context ──────
        current_beat  = outline[part_number - 1] if outline and len(outline) >= part_number else ""
        prev_beat     = outline[part_number - 2] if outline and part_number >= 2 else ""
        next_beat     = outline[part_number]     if outline and len(outline) > part_number else ""

        # ── Character profiles context ───────────────────────────────
        char_context = ""
        if char_profiles:
            char_context = "━━━ CHARACTER PROFILES (maintain consistency) ━━━\n"
            for name, profile in list(char_profiles.items())[-10:]:
                char_context += f"• {name}: {profile}\n"

        # ── Emotion context ──────────────────────────────────────────
        emotion_context = ""
        if emotions:
            emotion_context = "━━━ CHARACTER EMOTIONS AT END OF LAST PART ━━━\n"
            for char, emotion in emotions.items():
                emotion_context += f"• {char}: {emotion}\n"

        # ── Recent events ─────────────────────────────────────────────
        recent_events = ""
        if events:
            recent_events = "━━━ RECENT EVENTS COVERED ━━━\n"
            for e in events[-8:]:
                recent_events += f"• {e}\n"

        # ── Last scene ───────────────────────────────────────────────
        last_scene_context = ""
        if last_ending:
            last_scene_context = f"━━━ LAST PART ENDED WITH ━━━\n{last_ending}\n"

        # ── Finale next movie ────────────────────────────────────────
        if part_number == PARTS_PER_MOVIE:
            movies  = self.movies_data["movies"]
            nxt     = movies[(self.state["current_movie_index"] + 1) % len(movies)]
            finale_note = f"""
FINALE NOTE: Last 2 lines MUST be:
"Yeh thi '{movie_name}' ki poori kahani..."
"Ab shuru hogi '{nxt}' ki kahani — subscribe karo!"
"""
        else:
            finale_note = ""

        prompt = f"""
You are India's best Hindi movie narrator — passionate, dramatic storyteller.

MOVIE: {movie_name}
PART: {part_number} / {PARTS_PER_MOVIE} ({progress_pct:.0f}% complete)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STORY OUTLINE — STAY ON THIS TRACK:

PREVIOUS BEAT (Part {part_number-1}): {prev_beat}
THIS PART'S BEAT (Part {part_number}): {current_beat}
NEXT BEAT (Part {part_number+1}): {next_beat}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{last_scene_context}
{char_context}
{emotion_context}
{recent_events}

━━━ YOUR TASK ━━━
Write ONLY the scene described in "THIS PART'S BEAT" above.
- Follow the outline EXACTLY — do NOT invent scenes not in the outline
- Continue from where last part ended
- Include ALL characters mentioned in this beat
- End in a way that leads naturally into the NEXT BEAT
{finale_note}

━━━ NARRATION RULES ━━━
• Language: Natural Hinglish (Hindi + English as Indians speak)
• Length: STRICTLY 110-130 words (45-50 seconds)
• Show emotions physically — "haath kaanp rahe the" not "he was scared"
• Include 1 short dialogue line in quotes
• Use "..." for dramatic pause
• End line must make them NEED Part {part_number + 1}
• If Part 1: describe each character's appearance in detail

━━━ CHARACTER RULE ━━━
Only use characters who are ACTUALLY in this scene per the outline.
Do NOT add random characters who don't belong in this scene.
If the outline says Harry and Dumbledore are in this scene — focus on them.

━━━ IMAGE PROMPTS ━━━
Generate 7 image_prompts — each a DIFFERENT visual shot from THIS scene.
You know this movie — describe characters with their ACTUAL appearance.
Every prompt MUST end with: "{PIXAR_STYLE}"

Structure: [character name + exact appearance] + [action] + [setting] + [mood] + [Pixar style]

━━━ PEXELS MOOD CLIPS ━━━
2 x 3-4 word English atmosphere clip search terms.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Return ONLY valid JSON:

[
  {{
    "id": 1,
    "movie": "{movie_name}",
    "part_number": {part_number},
    "total_parts": {PARTS_PER_MOVIE},
    "title": "{movie_name} | Part {part_number} — [5 word Hindi scene title]",
    "text": "Full Hinglish narration — 110-130 words STRICTLY",
    "hook_text": "Part {part_number}: [5 dramatic Hindi words]",
    "image_prompts": [
      "Shot 1: [character+appearance+action+setting+mood + Pixar style]",
      "Shot 2: [character+appearance+action+setting+mood + Pixar style]",
      "Shot 3: [character+appearance+action+setting+mood + Pixar style]",
      "Shot 4: [character+appearance+action+setting+mood + Pixar style]",
      "Shot 5: [character+appearance+action+setting+mood + Pixar style]",
      "Shot 6: [character+appearance+action+setting+mood + Pixar style]",
      "Shot 7: [character+appearance+action+setting+mood + Pixar style]"
    ],
    "pexels_moods": ["3-4 word mood 1", "3-4 word mood 2"],
    "character_profiles": {{
      "Character Name": "appearance: [look]. personality: [nature]. role: [role in story]"
    }},
    "new_events": ["plot point 1 from THIS part", "plot point 2", "plot point 3"],
    "character_emotions": {{
      "Character Name": "how they feel RIGHT NOW at end of this part"
    }},
    "scene_ending": "Exact last moment of this part for seamless Part {part_number+1} continuity"
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

                    # Validate Pixar style
                    fixed = []
                    for p in scene.get("image_prompts", []):
                        if "Pixar" not in p and "pixar" not in p:
                            p = p.rstrip(" ,") + f", {PIXAR_STYLE}"
                        fixed.append(p)
                    scene["image_prompts"] = fixed
                    result[0] = scene

                    # Update state
                    new_profiles = scene.get("character_profiles", {})
                    self.state["character_profiles"].update(new_profiles)

                    new_events = scene.get("new_events", [])
                    self.state["key_events_covered"].extend(new_events)
                    self.state["key_events_covered"] = self.state["key_events_covered"][-40:]

                    if scene.get("scene_ending"):
                        self.state["last_scene_ending"] = scene["scene_ending"]
                    if scene.get("character_emotions"):
                        self.state["character_emotions"] = scene["character_emotions"]

                    self._save_state()

                    word_count = len(scene.get("text", "").split())
                    print(f"   ✅ Part {part_number} | {word_count} words | beat: {current_beat[:60]}...")
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
        if isinstance(out, list) and out:
            text = out[0].get("text", "")
            print(f"\n📝 Words: {len(text.split())}")
            print(f"📖 Preview: {text[:200]}...")
