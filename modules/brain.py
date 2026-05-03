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
        return {
            "current_movie": first,
            "current_movie_index": 0,
            "current_part": 0,
            "total_parts": PARTS_PER_MOVIE,
            "story_so_far": "",
            "last_scene_ending": "",
            "character_profiles": {},   # Gemini builds these dynamically
            "key_events_covered": [],
            "character_emotions": {},
            "completed_movies": []
        }

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
        print(f"🎬 Next: '{next_movie}'")
        self.state.update({
            "current_movie":       next_movie,
            "current_movie_index": next_idx,
            "current_part":        0,
            "story_so_far":        "",
            "last_scene_ending":   "",
            "character_profiles":  {},
            "key_events_covered":  [],
            "character_emotions":  {},
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
        char_profiles = self.state.get("character_profiles", {})
        events       = self.state.get("key_events_covered", [])
        emotions     = self.state.get("character_emotions", {})
        progress_pct = (part_number / PARTS_PER_MOVIE) * 100

        # Build character context from dynamically saved profiles
        char_context = ""
        if char_profiles:
            char_context = "\n━━━ CHARACTER PROFILES (maintain consistency) ━━━\n"
            for name, profile in list(char_profiles.items())[-8:]:
                char_context += f"• {name}: {profile}\n"

        # Build emotion context
        emotion_context = ""
        if emotions:
            emotion_context = "\n━━━ CURRENT EMOTIONAL STATES ━━━\n"
            for char, emotion in emotions.items():
                emotion_context += f"• {char}: {emotion}\n"

        # Build events context
        events_context = ""
        if events:
            events_context = "\n━━━ KEY EVENTS ALREADY COVERED ━━━\n"
            for e in events[-12:]:
                events_context += f"• {e}\n"

        # Story continuity context
        story_context = ""
        if story_so_far:
            story_context = f"""
━━━ STORY SO FAR ━━━
{story_so_far}

━━━ LAST SCENE ENDED WITH ━━━
{last_ending}"""

        # Arc-based instruction
        if part_number == 1:
            arc_instruction = """
PART 1 — THE BEGINNING:
- Open with a powerful hook line that stops the scroll instantly
- Introduce the movie world and main character vividly
- Show what is missing or wrong in the protagonist's life
- Build curiosity — make viewers desperate for Part 2
- You MUST describe each character's appearance and personality in detail
  (saved for consistency across all 100 parts)

CHARACTER VARIETY RULE:
Real movies have MANY characters. From Part 1 introduce the full cast:
- Main protagonist with full description
- At least 2 supporting characters with their own personality
- Hint at the villain or main antagonist
- Show the world through multiple perspectives
"""
        elif part_number == PARTS_PER_MOVIE:
            movies   = self.movies_data["movies"]
            nxt      = movies[(self.state["current_movie_index"] + 1) % len(movies)]
            arc_instruction = f"""
PART {PARTS_PER_MOVIE} — GRAND FINALE:
- Resolve ALL story threads with emotional satisfaction
- Give EVERY character — hero, villain, all supporting cast — their deserved ending
- The final scene must be unforgettable
- LAST 2 LINES MUST BE:
  "Yeh thi '{movie_name}' ki poori kahani..."
  "Ab shuru hogi '{nxt}' ki kahani — subscribe karo!"

CHARACTER VARIETY: All major characters must appear in the finale.
"""
        else:
            introduce_new = (part_number % 4 == 0) and progress_pct < 80
            arc_instruction = f"""
PART {part_number} of {PARTS_PER_MOVIE} — Story is {progress_pct:.0f}% complete.
- Continue EXACTLY from where last part ended — no gaps
- {"Build world and introduce more of the full cast" if progress_pct < 25 else "Deepen all character relationships — hero, villain, supporting cast" if progress_pct < 50 else "Major twists — betrayal, sacrifice, revelation across all characters" if progress_pct < 75 else "Rush toward epic finale — all characters converging"}
- End on a cliffhanger or emotional hook — make them NEED Part {part_number + 1}
- Do NOT repeat events already covered

CHARACTER VARIETY RULE — CRITICAL:
Movies have LARGE casts. Rotate through ALL characters — not just the main hero:
- Give screen time to villain/antagonist — show THEIR perspective and motivation
- Include supporting and side characters — they have their own story
- Show characters INTERACTING — dialogue, conflict, friendship, rivalry
- Every character must feel ALIVE, not just background
{"- INTRODUCE A NEW CHARACTER this part who has not appeared yet" if introduce_new else "- Show a completely new side of an existing character we haven't seen"}
"""

        prompt = f"""
You are India's best Hindi movie narrator — passionate, dramatic, like a campfire storyteller.

MOVIE: {movie_name}
PART: {part_number} / {PARTS_PER_MOVIE}

{story_context}
{char_context}
{emotion_context}
{events_context}

━━━ YOUR TASK ━━━
{arc_instruction}

━━━ NARRATION RULES ━━━
• Language: Natural Hinglish — mix Hindi + English exactly how Indians speak
• Length: STRICTLY 110-130 words (45-50 seconds when read at normal pace)
• Style: Show emotions physically — "haath kaanp rahe the" not "he was scared"
• Include 1 short dialogue line in quotes
• Use "..." for dramatic pause
• End line must create URGENCY for next part

━━━ IMAGE PROMPT RULES ━━━
Generate exactly 7 image_prompts — each a DIFFERENT visual shot from this scene.

You know this movie well — describe the ACTUAL characters from {movie_name} with their
real appearance (hair color, clothes, physical traits, expressions).

Every prompt MUST end with exactly this style string:
"{PIXAR_STYLE}"

Structure each prompt as:
[Character name + exact appearance] + [what they are doing] + [where/setting] + [lighting/mood] + [Pixar style]

━━━ PEXELS MOOD CLIPS ━━━
2 x 3-4 word English search terms for real atmosphere clips.
Example: "dark castle night fog", "candles stone dungeon"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Return ONLY valid JSON — no markdown, no extra text:

[
  {{
    "id": 1,
    "movie": "{movie_name}",
    "part_number": {part_number},
    "total_parts": {PARTS_PER_MOVIE},
    "title": "{movie_name} | Part {part_number} — [5 word dramatic Hindi scene title]",
    "text": "Full Hinglish narration — EXACTLY 110-130 words, 45-50 seconds",
    "hook_text": "Part {part_number}: [5 dramatic words in Hindi/Hinglish]",
    "image_prompts": [
      "Shot 1: [character appearance + action + setting + mood + Pixar style]",
      "Shot 2: [character appearance + action + setting + mood + Pixar style]",
      "Shot 3: [character appearance + action + setting + mood + Pixar style]",
      "Shot 4: [character appearance + action + setting + mood + Pixar style]",
      "Shot 5: [character appearance + action + setting + mood + Pixar style]",
      "Shot 6: [character appearance + action + setting + mood + Pixar style]",
      "Shot 7: [character appearance + action + setting + mood + Pixar style]"
    ],
    "pexels_moods": ["3-4 word mood clip 1", "3-4 word mood clip 2"],
    "character_profiles": {{
      "Character Name": "appearance: [describe look]. personality: [describe nature]. role: [their role in story]",
      "Character 2": "appearance: [describe look]. personality: [describe nature]. role: [their role in story]"
    }},
    "new_events": ["specific plot point 1 from THIS part", "specific plot point 2", "specific plot point 3"],
    "character_emotions": {{
      "Character Name": "what they feel RIGHT NOW at end of this part"
    }},
    "story_summary": "4-5 sentences summarizing complete story up to and including this part",
    "scene_ending": "Exact last moment/line of this part for seamless Part {part_number + 1} start"
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

                    # Validate Pixar style in image prompts
                    fixed = []
                    for p in scene.get("image_prompts", []):
                        if "Pixar" not in p and "pixar" not in p:
                            p = p.rstrip(" ,") + f", {PIXAR_STYLE}"
                        fixed.append(p)
                    scene["image_prompts"] = fixed
                    result[0] = scene

                    # ── Update story state dynamically ───────────────

                    # Merge character profiles (Gemini builds these)
                    new_profiles = scene.get("character_profiles", {})
                    existing_profiles = self.state.get("character_profiles", {})
                    existing_profiles.update(new_profiles)
                    self.state["character_profiles"] = existing_profiles

                    # Events
                    new_events = scene.get("new_events", [])
                    self.state["key_events_covered"].extend(new_events)
                    self.state["key_events_covered"] = self.state["key_events_covered"][-40:]

                    # Story summary
                    if scene.get("story_summary"):
                        self.state["story_so_far"] = scene["story_summary"]
                    if scene.get("scene_ending"):
                        self.state["last_scene_ending"] = scene["scene_ending"]

                    # Character emotions
                    if scene.get("character_emotions"):
                        self.state["character_emotions"] = scene["character_emotions"]

                    self._save_state()

                    word_count = len(scene.get("text", "").split())
                    print(f"   ✅ Part {part_number} | {word_count} words | {len(fixed)} images")
                    print(f"   📖 Events: {new_events[:2]}")
                    print(f"   👥 Characters: {list(new_profiles.keys())}")
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
            print(f"\n📝 Word count: {len(text.split())} words")
            print(f"📖 Script preview:\n{text[:300]}...")
