import asyncio
import time
import os
import shutil
import json
from modules.brain import ContentBrain
from modules.image_generator import ImageGenerator
from modules.audio import AudioEngine
from modules.composer import Composer
from modules.thumbnail import ThumbnailGenerator
from modules.uploader import YouTubeUploader

CHANNEL_NAME = os.getenv("CHANNEL_NAME", "@MovieStoryteller")


def clean_cache():
    print("🧹 Cleaning temp files...")
    for folder in [
        os.path.join(os.getcwd(), "assets", "audio_clips"),
        os.path.join(os.getcwd(), "assets", "temp"),
        os.path.join(os.getcwd(), "assets", "scene_images"),
    ]:
        if not os.path.exists(folder):
            continue
        for f in os.listdir(folder):
            fp = os.path.join(folder, f)
            try:
                os.unlink(fp) if os.path.isfile(fp) else shutil.rmtree(fp)
            except Exception:
                pass
    print("✅ Cache cleared")


async def create_one_short(short_number):
    # ── 1. BRAIN — Generate story part ──────────────────────────────
    brain = ContentBrain()
    try:
        script_data = brain.generate_script()
        if not script_data:
            print("❌ Script generation failed")
            return False
    except Exception as e:
        print(f"❌ Brain Error: {e}")
        return False

    scene = script_data[0] if isinstance(script_data, list) else script_data

    movie_name  = scene.get("movie", "Movie")
    part_number = scene.get("part_number", 1)
    total_parts = scene.get("total_parts", 100)

    print(f"\n🎬 {movie_name} — Part {part_number}/{total_parts}")

    # ── 2. AUDIO ─────────────────────────────────────────────────────
    audio_engine = AudioEngine()
    try:
        script_data = await audio_engine.process_script(script_data)
    except Exception as e:
        print(f"❌ Audio Error: {e}")
        return False

    # ── 3. AI IMAGES (replaces Pexels videos) ────────────────────────
    image_gen   = ImageGenerator()
    image_pairs = []
    for s in script_data:
        pair = image_gen.get_images_for_scene(s)
        image_pairs.append(pair)

    # ── 4. COMPOSE VIDEO ─────────────────────────────────────────────
    composer = Composer()
    scene_paths = composer.render_all_scenes(script_data, image_pairs)

    if not scene_paths:
        print("❌ No scenes rendered")
        return False

    final_video = composer.concatenate_with_transitions(
        scene_paths,
        channel_name=CHANNEL_NAME,
    )
    clean_cache()

    if not final_video:
        print("❌ Final video creation failed")
        return False

    # ── 5. THUMBNAIL ─────────────────────────────────────────────────
    thumb_gen = ThumbnailGenerator()
    thumbnail_path = thumb_gen.generate_thumbnail(
        title        = scene.get("title", f"{movie_name} Part {part_number}"),
        script_text  = scene.get("text", ""),
        short_number = short_number,
        image_prompt = scene.get("image_prompt_1", ""),
        movie_name   = movie_name,
        part_number  = part_number,
        total_parts  = total_parts,
        channel_name = CHANNEL_NAME,
    )

    # ── 6. YOUTUBE UPLOAD ────────────────────────────────────────────
    print("📤 Uploading to YouTube...")
    try:
        uploader = YouTubeUploader()

        title = f"{movie_name} | Part {part_number} — Hindi Story | {CHANNEL_NAME}"
        title = title[:100]

        script_text = scene.get("text", "")
        description = f"""🎬 {movie_name} — Part {part_number} of {total_parts}

{script_text[:300]}...

📺 Poori movie series dekhne ke liye channel subscribe karo!
🔔 Bell icon dabao taaki koi part miss na ho

Part {part_number - 1} se continue ho rahi hai yeh kahani...
Agle part ke liye subscribe karo! 👇

#{movie_name.replace(' ', '')} #HindiMovieStory #Part{part_number} #Shorts #MovieSummary #HindiStory"""

        tags = [
            movie_name, f"Part {part_number}", "hindi movie story",
            "movie summary hindi", "hindi shorts", "movie storyteller",
            "hindi kahani", "movie series", "shorts"
        ]

        video_id = uploader.upload(
            video_path     = "assets/final/final_short.mp4",
            title          = title,
            description    = description,
            thumbnail_path = thumbnail_path,
            tags           = tags,
            privacy        = "public",
        )

        if video_id:
            print(f"✅ UPLOADED: https://youtu.be/{video_id}")
            return True
        else:
            print("❌ Upload failed")
            return False

    except Exception as e:
        print(f"❌ Upload Error: {e}")
        return False


async def main():
    # Load current state for display
    state = {}
    if os.path.exists("story_state.json"):
        with open("story_state.json") as f:
            state = json.load(f)

    current_movie = state.get("current_movie", "Starting...")
    current_part  = state.get("current_part", 0)
    print(f"🎬 MOVIE STORYTELLER BOT STARTED")
    print(f"📽️  Current: {current_movie} | Part {current_part}")
    print("Generating continuously until GitHub stops the job...\n")

    short_count = 0
    start_time  = time.time()

    while True:
        short_count += 1
        print(f"\n🔄 === Generating Short #{short_count} ===\n")

        success = await create_one_short(short_number=short_count)

        if success:
            print(f"✅ Short #{short_count} done!")
        else:
            print(f"⚠️  Short #{short_count} had issues. Continuing...")

        print("⏳ Waiting 12 minutes...\n")
        await asyncio.sleep(720)

        if time.time() - start_time > 19800:   # 5.5 hours
            print("⏹️  Max runtime reached. Stopping.")
            break


if __name__ == "__main__":
    asyncio.run(main())