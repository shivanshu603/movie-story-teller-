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
        self.fonts_dir  = os.path.join(os.getcwd(), "assets", "fonts")
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
        """Fetch AI image from Pollinations for background."""
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
        """
        Create darkened background:
        1. Try provided local image first (fastest)
        2. Try AI generation from prompt
        3. Fallback to dark gradient
        """
        img = None

        # Option 1: Use local image
        if bg_image_path and os.path.exists(bg_image_path):
            try:
                img = Image.open(bg_image_path).convert("RGB")
            except Exception:
                pass

        # Option 2: AI generated
        if img is None and ai_prompt:
            img = self._get_ai_bg(ai_prompt)

        if img:
            # Resize + crop to portrait
            ratio = img.width / img.height
            if ratio > W / H:
                nw, nh = int(H * ratio), H
            else:
                nw, nh = W, int(W / ratio)
            img = img.resize((nw, nh), Image.LANCZOS)
            l   = (nw - W) // 2
            t   = (nh - H) // 2
            img = img.crop((l, t, l + W, t + H))
            # Darken so text is always readable
            img = ImageEnhance.Brightness(img).enhance(0.45)
            img = img.filter(ImageFilter.GaussianBlur(1))
            return img

        # Option 3: Dark gradient fallback
        img  = Image.new("RGB", (W, H))
        draw = ImageDraw.Draw(img)
        for y in range(H):
            r = int(10 + (y / H) * 20)
            b = int(40 + (y / H) * 80)
            draw.line([(0, y), (W, y)], fill=(r, 0, b))
        return img

    # ─────────────────────────────────────────────────────────────────
    # TEXT HELPER
    # ─────────────────────────────────────────────────────────────────

    def _draw_outlined(self, draw, text, font, x, y,
                       fill=(255, 255, 255), outline=(0, 0, 0), ow=5):
        for dx in range(-ow, ow + 1):
            for dy in range(-ow, ow + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
        draw.text((x, y), text, font=font, fill=fill)

    def _centered_text(self, draw, text, font, y, fill=(255,255,255), outline=(0,0,0), ow=5):
        bb = draw.textbbox((0, 0), text, font=font)
        x  = (W - (bb[2] - bb[0])) // 2
        self._draw_outlined(draw, text, font, x, y, fill, outline, ow)
        return bb[3] - bb[1]  # return height

    # ─────────────────────────────────────────────────────────────────
    # MAIN CARD DESIGN
    # ─────────────────────────────────────────────────────────────────

    def _build_card(self, bg, movie_name, part_number, total_parts, channel_name):
        """
        Draw the complete card design:
        ┌──────────────────────────────────┐
        │  🎬 MOVIE NAME (dark top bar)    │
        │                                  │
        │   [background image]             │
        │                                  │
        │   ┌──────────────────────┐       │
        │   │      PART 30         │  ← YELLOW BOX
        │   └──────────────────────┘       │
        │        of 100                    │
        │                                  │
        │  @ChannelName (dark bottom bar)  │
        └──────────────────────────────────┘
        """
        img  = bg.copy()
        draw = ImageDraw.Draw(img, "RGBA")

        # ── Dark gradient overlays ───────────────────────────────────
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        for y in range(H):
            if y < 300:
                alpha = int(200 * (1 - y / 300))
                od.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
            elif y > H - 400:
                alpha = int(200 * ((y - (H - 400)) / 400))
                od.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
        od.rectangle([(0, 300), (W, H - 280)], fill=(0, 0, 0, 100))
        img  = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
        draw = ImageDraw.Draw(img, "RGBA")

        # ── TOP BAR: Movie name ───────────────────────────────────────
        bar_h = 100
        draw.rectangle([(0, 0), (W, bar_h)], fill=(0, 0, 0, 230))

        # Movie icon + name
        movie_display = f"🎬  {movie_name}" if len(movie_name) <= 25 else f"🎬  {movie_name[:23]}…"
        mf = self._font(34)
        mb = draw.textbbox((0, 0), movie_display, font=mf)
        mx = (W - (mb[2] - mb[0])) // 2
        my = (bar_h - (mb[3] - mb[1])) // 2
        # Outline
        for dx, dy in [(-2,0),(2,0),(0,-2),(0,2)]:
            draw.text((mx+dx, my+dy), movie_display, font=mf, fill=(0,0,0,255))
        draw.text((mx, my), movie_display, font=mf, fill=(255, 255, 255, 255))

        # ── CENTRE: PART XX in YELLOW BOX ────────────────────────────
        part_str  = f"PART {part_number}"
        pf        = self._font(130)
        pb        = draw.textbbox((0, 0), part_str, font=pf)
        pw        = pb[2] - pb[0]
        ph        = pb[3] - pb[1]

        pad_x, pad_y = 60, 35
        box_w  = pw + pad_x * 2
        box_h  = ph + pad_y * 2
        box_x  = (W - box_w) // 2
        box_y  = (H - box_h) // 2 - 80  # slightly above center

        # Shadow behind yellow box
        draw.rounded_rectangle(
            [box_x + 8, box_y + 10, box_x + box_w + 8, box_y + box_h + 10],
            radius=28, fill=(0, 0, 0, 120)
        )

        # Yellow box
        draw.rounded_rectangle(
            [box_x, box_y, box_x + box_w, box_y + box_h],
            radius=28, fill=(255, 210, 0, 255)
        )

        # PART text inside yellow box — dark color
        tx = box_x + pad_x
        ty = box_y + pad_y
        # Subtle dark outline on yellow bg
        for dx, dy in [(-3,0),(3,0),(0,-3),(0,3)]:
            draw.text((tx+dx, ty+dy), part_str, font=pf, fill=(80, 60, 0, 180))
        draw.text((tx, ty), part_str, font=pf, fill=(20, 15, 0, 255))

        # ── "of 100" below yellow box ────────────────────────────────
        of_str = f"of {total_parts}"
        of_f   = self._font(44)
        of_b   = draw.textbbox((0, 0), of_str, font=of_f)
        of_x   = (W - (of_b[2] - of_b[0])) // 2
        of_y   = box_y + box_h + 22
        self._draw_outlined(
            draw, of_str, of_f, of_x, of_y,
            fill=(220, 220, 220), outline=(0, 0, 0), ow=4
        )

        # ── BOTTOM BAR: Channel name ──────────────────────────────────
        if channel_name:
            bot_h = 90
            draw.rectangle([(0, H - bot_h), (W, H)], fill=(0, 0, 0, 230))
            cf  = self._font(40)
            cb  = draw.textbbox((0, 0), channel_name, font=cf)
            cx  = (W - (cb[2] - cb[0])) // 2
            cy  = H - bot_h + (bot_h - (cb[3] - cb[1])) // 2
            draw.text((cx, cy), channel_name, font=cf, fill=(180, 180, 180, 255))

        return img

    # ─────────────────────────────────────────────────────────────────
    # THUMBNAIL
    # ─────────────────────────────────────────────────────────────────

    def generate_thumbnail(
        self, title="", script_text="", short_number=1,
        image_prompt=None, movie_name="Movie", part_number=1,
        total_parts=100, channel_name="@MovieStoryteller",
        bg_image_path=None,
    ):
        print(f"🖼️  Thumbnail: {movie_name} Part {part_number}...")

        bg  = self._make_dark_bg(bg_image_path, image_prompt)
        img = self._build_card(bg, movie_name, part_number, total_parts, channel_name)

        out = os.path.join(self.output_dir, f"thumbnail_{short_number}.png")
        img.save(out, "PNG", optimize=True)
        print(f"✅ Thumbnail saved → thumbnail_{short_number}.png")
        return out

    # ─────────────────────────────────────────────────────────────────
    # INTRO FRAME (same design as thumbnail)
    # ─────────────────────────────────────────────────────────────────

    def generate_intro_frame(
        self, movie_name="Movie", part_number=1, total_parts=100,
        channel_name="@MovieStoryteller", bg_image_path=None,
        short_number=1,
    ):
        print(f"🎬 Intro frame: {movie_name} Part {part_number}...")

        bg  = self._make_dark_bg(bg_image_path, ai_prompt=None)
        img = self._build_card(bg, movie_name, part_number, total_parts, channel_name)

        out = os.path.join(self.output_dir, f"intro_frame_{short_number}.png")
        img.save(out, "PNG", optimize=True)
        print(f"✅ Intro frame saved → intro_frame_{short_number}.png")
        return out
