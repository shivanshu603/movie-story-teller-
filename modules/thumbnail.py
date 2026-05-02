import os
import re
import requests
import urllib.parse
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from io import BytesIO

W, H = 1080, 1920


class ThumbnailGenerator:

    def __init__(self):
        self.output_dir = os.path.join(os.getcwd(), "assets", "thumbnails")
        self.fonts_dir = os.path.join(os.getcwd(), "assets", "fonts")
        os.makedirs(self.output_dir, exist_ok=True)

    # ─────────────────────────────────────────────────────────────────
    # FONT
    # ─────────────────────────────────────────────────────────────────

    def _font(self, size):
        candidates = [
            os.path.join(self.fonts_dir, "NotoSans-Bold.ttf"),
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
            "/usr/share/fonts/noto/NotoSansDevanagari-Bold.ttf",
        ]
        for p in candidates:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    # ─────────────────────────────────────────────────────────────────
    # BACKGROUND
    # ─────────────────────────────────────────────────────────────────

    def _get_ai_bg(self, prompt):
        try:
            enhanced = f"{prompt}, Disney Pixar 3D animated style, dramatic lighting, movie poster"
            url = (
                f"https://image.pollinations.ai/prompt/"
                f"{urllib.parse.quote(enhanced)}"
                f"?width={W}&height={H}&nologo=true&model=flux"
            )
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200 and len(resp.content) > 5000:
                return Image.open(BytesIO(resp.content)).convert("RGB")
        except Exception as e:
            print(f"   ⚠️ AI bg failed: {e}")
        return None

    def _make_dark_bg(self, bg_image_path=None, ai_prompt=None):
        img = None

        if bg_image_path and os.path.exists(bg_image_path):
            try:
                img = Image.open(bg_image_path).convert("RGB")
            except:
                pass

        if img is None and ai_prompt:
            img = self._get_ai_bg(ai_prompt)

        if img:
            ratio = img.width / img.height
            if ratio > W / H:
                nw, nh = int(H * ratio), H
            else:
                nw, nh = W, int(W / ratio)

            img = img.resize((nw, nh), Image.LANCZOS)
            l = (nw - W) // 2
            t = (nh - H) // 2
            img = img.crop((l, t, l + W, t + H))

            img = ImageEnhance.Brightness(img).enhance(0.45)
            img = img.filter(ImageFilter.GaussianBlur(1))
            return img

        # fallback gradient
        img = Image.new("RGB", (W, H))
        draw = ImageDraw.Draw(img)
        for y in range(H):
            r = int(10 + (y / H) * 20)
            b = int(40 + (y / H) * 80)
            draw.line([(0, y), (W, y)], fill=(r, 0, b))
        return img

    # ─────────────────────────────────────────────────────────────────
    # TEXT
    # ─────────────────────────────────────────────────────────────────

    def _draw_outlined(self, draw, text, font, x, y,
                       fill=(255, 255, 255), outline=(0, 0, 0), ow=5):
        for dx in range(-ow, ow + 1):
            for dy in range(-ow, ow + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
        draw.text((x, y), text, font=font, fill=fill)

    # ─────────────────────────────────────────────────────────────────
    # MAIN CARD
    # ─────────────────────────────────────────────────────────────────

    def _build_card(self, bg, movie_name, part_number, total_parts, channel_name):

        img = bg.copy()
        draw = ImageDraw.Draw(img, "RGBA")

        # overlay
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)

        for y in range(H):
            if y < 300:
                alpha = int(200 * (1 - y / 300))
                od.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
            elif y > H - 400:
                alpha = int(200 * ((y - (H - 400)) / 400))
                od.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))

        img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
        draw = ImageDraw.Draw(img, "RGBA")

        # TOP BAR
        bar_h = 100
        draw.rectangle([(0, 0), (W, bar_h)], fill=(0, 0, 0, 230))

        movie_display = f"🎬 {movie_name[:25]}"
        mf = self._font(34)

        bbox = draw.textbbox((0, 0), movie_display, font=mf)
        x = (W - (bbox[2] - bbox[0])) // 2
        y = (bar_h - (bbox[3] - bbox[1])) // 2

        draw.text((x, y), movie_display, font=mf, fill=(255, 255, 255))

        # PART TEXT
        part_text = f"PART {part_number}"
        pf = self._font(120)

        bbox = draw.textbbox((0, 0), part_text, font=pf)
        x = (W - (bbox[2] - bbox[0])) // 2
        y = (H // 2) - 100

        draw.text((x, y), part_text, font=pf, fill=(255, 210, 0))

        # BOTTOM BAR
        if channel_name:
            draw.rectangle([(0, H - 90), (W, H)], fill=(0, 0, 0, 230))
            cf = self._font(36)

            bbox = draw.textbbox((0, 0), channel_name, font=cf)
            x = (W - (bbox[2] - bbox[0])) // 2
            y = H - 70

            draw.text((x, y), channel_name, font=cf, fill=(200, 200, 200))

        return img

    # ─────────────────────────────────────────────────────────────────
    # GENERATE THUMBNAIL
    # ─────────────────────────────────────────────────────────────────

    def generate_thumbnail(
        self,
        title="",
        script_text="",
        short_number=1,
        image_prompt=None,
        movie_name="Movie",
        part_number=1,
        total_parts=100,
        channel_name="@MovieStoryteller",
        bg_image_path=None,
    ):

        print(f"🖼️ Thumbnail: {movie_name} Part {part_number}")

        bg = self._make_dark_bg(bg_image_path, image_prompt)
        img = self._build_card(bg, movie_name, part_number, total_parts, channel_name)

        out = os.path.join(self.output_dir, f"thumbnail_{short_number}.png")
        img.save(out, "PNG", optimize=True)

        print(f"✅ Thumbnail saved: {out}")
        return out
