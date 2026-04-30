import os
import re
import textwrap
import requests
import urllib.parse
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from io import BytesIO

W, H = 1080, 1920


class ThumbnailGenerator:

    def __init__(self):
        self.output_dir = os.path.join(os.getcwd(), "assets", "thumbnails")
        self.fonts_dir  = os.path.join(os.getcwd(), "assets", "fonts")
        os.makedirs(self.output_dir, exist_ok=True)

        self.font_bold    = os.path.join(self.fonts_dir, "NotoSans-Bold.ttf")
        self.font_regular = os.path.join(self.fonts_dir, "NotoSans-Regular.ttf")

    def _font(self, size, bold=True):
        path = self.font_bold if bold else self.font_regular
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            try:
                return ImageFont.truetype(
                    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf", size
                )
            except Exception:
                return ImageFont.load_default()

    def _get_ai_image(self, prompt, width=W, height=H):
        """Get AI-generated image from Pollinations for thumbnail background."""
        try:
            enhanced = f"{prompt}, cinematic, dramatic, movie poster style, high detail"
            encoded  = urllib.parse.quote(enhanced)
            url      = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&nologo=true"
            resp     = requests.get(url, timeout=45)
            if resp.status_code == 200 and len(resp.content) > 5000:
                return Image.open(BytesIO(resp.content)).convert("RGB")
        except Exception as e:
            print(f"   ⚠️ Thumbnail bg image failed: {e}")
        return None

    def _draw_outlined_text(self, draw, text, font, x, y, fill, outline, ow=4):
        for dx in range(-ow, ow + 1):
            for dy in range(-ow, ow + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
        draw.text((x, y), text, font=font, fill=fill)

    def _draw_wrapped(self, draw, text, font, y_start, max_chars=18):
        lines  = textwrap.wrap(text, width=max_chars)
        bbox   = draw.textbbox((0, 0), "A", font=font)
        line_h = (bbox[3] - bbox[1]) + 20
        for i, line in enumerate(lines):
            b = draw.textbbox((0, 0), line, font=font)
            x = (W - (b[2] - b[0])) // 2
            y = y_start + i * line_h
            self._draw_outlined_text(draw, line, font, x, y, (255, 255, 255), (0, 0, 0), 5)

    def generate_thumbnail(
        self,
        title,
        script_text="",
        short_number=1,
        image_prompt=None,
        movie_name="",
        part_number=1,
        total_parts=100,
        channel_name="@MovieStoryteller",
    ):
        print(f"🖼️  Generating Thumbnail — {movie_name} Part {part_number}...")

        clean_title = re.sub(r"[😱🔥💀🤯👁️✨🌍🧠🎬]+", "", title or "").strip()

        # ── Background ───────────────────────────────────────────────
        bg_img = None
        if image_prompt:
            bg_img = self._get_ai_image(image_prompt)

        if bg_img:
            # Resize + crop to portrait
            ratio = bg_img.width / bg_img.height
            if ratio > W / H:
                new_h, new_w = H, int(H * ratio)
            else:
                new_w, new_h = W, int(W / ratio)
            bg_img = bg_img.resize((new_w, new_h), Image.LANCZOS)
            left   = (new_w - W) // 2
            top    = (new_h - H) // 2
            bg     = bg_img.crop((left, top, left + W, top + H))
            bg     = bg.filter(ImageFilter.GaussianBlur(1.5))
            bg     = ImageEnhance.Brightness(bg).enhance(0.5)
        else:
            # Dark gradient
            bg = Image.new("RGB", (W, H), (5, 5, 20))
            d  = ImageDraw.Draw(bg)
            for y in range(H):
                r = int(5  + (y / H) * 20)
                b = int(20 + (y / H) * 60)
                d.line([(0, y), (W, y)], fill=(r, 0, b))

        img  = bg.copy()
        draw = ImageDraw.Draw(img, "RGBA")

        # ── Gradient overlays ────────────────────────────────────────
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        for y in range(300):
            od.line([(0, y), (W, y)], fill=(0, 0, 0, int(200 * (1 - y / 300))))
        for y in range(H - 450, H):
            od.line([(0, y), (W, y)], fill=(0, 0, 0, int(200 * ((y - (H - 450)) / 450))))
        od.rectangle([(0, 300), (W, H - 280)], fill=(0, 0, 0, 80))
        img  = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
        draw = ImageDraw.Draw(img)

        # ── TOP: Movie name bar ───────────────────────────────────────
        draw.rectangle([(0, 0), (W, 75)], fill=(0, 0, 0))
        mf   = self._font(28, bold=True)
        mstr = (movie_name[:30] if movie_name else "Movie Storyteller")
        mb   = draw.textbbox((0, 0), mstr, font=mf)
        draw.text(((W - (mb[2] - mb[0])) // 2, 20), mstr, font=mf, fill=(200, 200, 200))

        # ── PART BADGE ────────────────────────────────────────────────
        badge_str  = f"Part {part_number} / {total_parts}"
        badge_font = self._font(54, bold=True)
        bb         = draw.textbbox((0, 0), badge_str, font=badge_font)
        bw, bh     = bb[2] - bb[0], bb[3] - bb[1]
        pad        = 24
        bx         = (W - bw - pad * 2) // 2
        by         = 100
        draw.rounded_rectangle(
            [bx, by, bx + bw + pad * 2, by + bh + pad],
            radius=18, fill=(180, 30, 30)
        )
        draw.text((bx + pad, by + pad // 2), badge_str, font=badge_font, fill=(255, 255, 255))

        # ── CENTRE: Title ─────────────────────────────────────────────
        title_font = self._font(82, bold=True)
        self._draw_wrapped(draw, clean_title, title_font, y_start=290, max_chars=16)

        # ── BOTTOM: Channel name ──────────────────────────────────────
        if channel_name:
            draw.rectangle([(0, H - 85), (W, H)], fill=(0, 0, 0))
            cf  = self._font(38, bold=True)
            cb  = draw.textbbox((0, 0), channel_name, font=cf)
            draw.text(((W - (cb[2] - cb[0])) // 2, H - 65), channel_name, font=cf, fill=(180, 180, 180))

        out_path = os.path.join(self.output_dir, f"thumbnail_{short_number}.png")
        img.save(out_path, "PNG", optimize=True)
        print(f"✅ Thumbnail saved: thumbnail_{short_number}.png")
        return out_path