import os
import time
import requests
import urllib.parse
from PIL import Image
from io import BytesIO


class ImageGenerator:
    """
    Generates AI images via Pollinations.ai (free, no API key needed).
    Falls back to a solid colored placeholder if generation fails.
    """

    def __init__(self):
        self.output_dir = os.path.join(os.getcwd(), "assets", "scene_images")
        os.makedirs(self.output_dir, exist_ok=True)
        self.base_url   = "https://image.pollinations.ai/prompt/"

    def generate_image(self, prompt, filename, width=1080, height=1920, retries=3):
        """
        Generate a portrait AI image from prompt.
        Returns local file path or None.
        """
        output_path = os.path.join(self.output_dir, filename)

        # Cache — don't regenerate if exists
        if os.path.exists(output_path) and os.path.getsize(output_path) > 5000:
            print(f"      📦 Cached image: {filename}")
            return output_path

        # Enhance prompt for cinematic quality
        enhanced = (
            f"{prompt}, "
            "cinematic lighting, high detail, dramatic composition, "
            "movie scene, ultra realistic, 4k quality"
        )

        encoded  = urllib.parse.quote(enhanced)
        url      = f"{self.base_url}{encoded}?width={width}&height={height}&nologo=true&enhance=true"

        for attempt in range(retries):
            try:
                print(f"      🎨 Generating image: {filename} (attempt {attempt+1})")
                resp = requests.get(url, timeout=60)

                if resp.status_code == 200 and len(resp.content) > 5000:
                    img = Image.open(BytesIO(resp.content)).convert("RGB")
                    # Ensure exact portrait dimensions
                    if img.size != (width, height):
                        img = img.resize((width, height), Image.LANCZOS)
                    img.save(output_path, "JPEG", quality=92)
                    size_kb = os.path.getsize(output_path) // 1024
                    print(f"      ✅ Image saved ({size_kb} KB): {filename}")
                    return output_path
                else:
                    print(f"      ⚠️ Bad response {resp.status_code} — retrying...")
                    time.sleep(3)

            except Exception as e:
                print(f"      ⚠️ Image gen error (attempt {attempt+1}): {e}")
                time.sleep(3)

        print(f"      ❌ Image generation failed for: {filename}")
        return None

    def get_images_for_scene(self, scene):
        """
        Generate both images for a scene.
        Returns (path_image_1, path_image_2) or (None, None).
        """
        scene_id = scene.get("id", 1)
        part_num = scene.get("part_number", scene_id)
        prompt_1 = scene.get("image_prompt_1", "")
        prompt_2 = scene.get("image_prompt_2", prompt_1)

        if not prompt_1:
            print(f"   ⚠️ No image prompts for scene {scene_id}")
            return None, None

        print(f"   🖼️  Generating images for Part {part_num}...")

        img1 = self.generate_image(prompt_1, f"scene_{part_num}_img1.jpg")
        time.sleep(2)   # Rate limit buffer
        img2 = self.generate_image(prompt_2, f"scene_{part_num}_img2.jpg")

        # If one failed, reuse the other
        if img1 and not img2:
            img2 = img1
        if img2 and not img1:
            img1 = img2

        return img1, img2