import os
import asyncio
import edge_tts
from mutagen.mp3 import MP3

class AudioEngine:
    def __init__(self):
        # Best Natural Indian Male Hindi Voice
        self.voice = "hi-IN-MadhurNeural"
        self.output_dir = os.path.join(os.getcwd(), "assets", "audio_clips")
        os.makedirs(self.output_dir, exist_ok=True)

    async def generate_audio(self, text, output_filename, retries=3):
        output_path = os.path.join(self.output_dir, output_filename)
       
        for attempt in range(retries):
            try:
                # Natural + Satisfying voice settings
                communicate = edge_tts.Communicate(
                    text=text,
                    voice=self.voice,
                    rate="+12%",      # Thoda fast for energy
                    pitch="-3Hz",    # Masculine aur deep feel
                    volume="+8%"
                )
                
                await communicate.save(output_path)
                print(f"   ✅ Natural Hindi Male Voice (MadhurNeural) generated")
                return output_path
           
            except Exception as e:
                print(f" ⚠️ Audio Error (Attempt {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                else:
                    print(" ❌ Failed to generate audio after max retries.")
                    raise e

    def get_audio_duration(self, file_path):
        try:
            audio = MP3(file_path)
            return audio.info.length
        except:
            return 0.0

    async def process_script(self, script_data):
        print(f"🎙️ Starting Audio Generation (Natural Hindi Male Voice + ASMR Style)...")

        for scene in script_data:
            scene_id = scene.get('id', 1)
            text = scene.get('text', '')
            filename = f"voice_{scene_id}.mp3"
           
            try:
                file_path = await self.generate_audio(text, filename)
                duration = self.get_audio_duration(file_path)
               
                scene['audio_path'] = file_path
                scene['duration'] = duration
               
                print(f"   ✅ Scene {scene_id}: {duration:.2f}s generated")
                
                await asyncio.sleep(1)
               
            except Exception as e:
                print(f"   ❌ Skipping Scene {scene_id}")
                continue
           
        return script_data
