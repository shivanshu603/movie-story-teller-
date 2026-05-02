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

    def _font(self, size, bold=True):
        candidates = [
            os.path.join(self.fonts_dir, "NotoSans-Bold.ttf" if bold else "NotoSans-Regular.ttf"),
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
        ]
        for p in candidates:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def _get_bg_image(self, prompt):
        """Fetch AI background image from Pollinations."""
        try:
            enhanced = f"{prompt}, cinematic, dramatic, movie poster style"
            url = (
                f"https://image.pollinations.ai/prompt/"
                f"{urllib.parse.quote(enhanced)}"
                f"?width={W}&height={H}&nologo=true&model=flux"
            )
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200 and len(resp.content) > 5000:
                return Image.open(BytesIO(resp.content)).convert("RGB")
        except Exception as e:
            print(f"   ⚠️ BG fetch failed: {e}")
        return None

    def _outlined_text(self, draw, text, font, x, y,
                        fill=(255,255,255), outline=(0,0,0), ow=4):
        for dx in range(-ow, ow+1):
            for dy in range(-ow, ow+1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x+dx, y+dy), text, font=font, fill=outline)
        draw.text((x, y), text, font=font, fill=fill)

    def _draw_card(self, img, movie_name, part_number, total_parts,
                   channel_name, subtitle_line=""):
        """
        Draw the shared card design used in BOTH thumbnail and intro frame:
        - Dark gradient overlay
        - Movie name at top
        - PART XX in yellow highlighted box (center)
        - Channel name at bottom
        """
        W2, H2 = img.size
        draw   = ImageDraw.Draw(img, "RGBA")

        # ── Dark gradient overlay ────────────────────────────────────
        ov = Image.new("RGBA", (W2, H2), (0,0,0,0))
        od = ImageDraw.Draw(ov)
        # Top fade
        for y in range(350):
            od.line([(0,y),(W2,y)], fill=(0,0,0,int(210*(1-y/350))))
        # Bottom fade
        for y in range(H2-500, H2):
            od.line([(0,y),(W2,y)], fill=(0,0,0,int(210*((y-(H2-500))/500))))
        # Centre dim
        od.rectangle([(0,350),(W2,H2-320)], fill=(0,0,0,110))
        img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
        draw = ImageDraw.Draw(img, "RGBA")

        # ── TOP: Movie name bar ───────────────────────────────────────
        draw.rectangle([(0,0),(W2,90)], fill=(0,0,0,230))
        mf   = self._font(32)
        # Truncate long movie names
        mname = movie_name if len(movie_name) <= 28 else movie_name[:26] + "…"
        mb    = draw.textbbox((0,0), mname, font=mf)
        mx    = (W2-(mb[2]-mb[0])) // 2
        self._outlined_text(draw, mname, mf, mx, 22,
                            fill=(255,255,255), outline=(0,0,0), ow=3)

        # ── CENTRE: PART badge in YELLOW BOX ─────────────────────────
        part_str  = f"PART {part_number}"
        pf        = self._font(110)
        pb        = draw.textbbox((0,0), part_str, font=pf)
        pw, ph    = pb[2]-pb[0], pb[3]-pb[1]
        pad_x, pad_y = 50, 28
        box_w     = pw + pad_x*2
        box_h     = ph + pad_y*2
        box_x     = (W2-box_w)//2
        box_y     = (H2-box_h)//2 - 60   # slightly above centre

        # Yellow box with rounded corners
        draw.rounded_rectangle(
            [box_x, box_y, box_x+box_w, box_y+box_h],
            radius=24,
            fill=(255, 210, 0, 255)   # bright yellow
        )
        # Dark shadow under box
        draw.rounded_rectangle(
            [box_x+6, box_y+8, box_x+box_w+6, box_y+box_h+8],
            radius=24,
            fill=(0,0,0,80)
        )
        # Re-draw yellow on top
        draw.rounded_rectangle(
            [box_x, box_y, box_x+box_w, box_y+box_h],
            radius=24,
            fill=(255, 210, 0, 255)
        )
        # Part text inside yellow box — dark color
        self._outlined_text(
            draw, part_str, pf,
            box_x+pad_x, box_y+pad_y,
            fill=(20, 20, 20),        # near-black on yellow
            outline=(0,0,0,100),
            ow=2
        )

        # ── ABOVE yellow box: "of 100" small text ────────────────────
        of_str = f"of {total_parts}"
        of_f   = self._font(36)
        of_b   = draw.textbbox((0,0), of_str, font=of_f)
        of_x   = (W2-(of_b[2]-of_b[0]))//2
        of_y   = box_y + box_h + 18
        self._outlined_text(draw, of_str, of_f, of_x, of_y,
                            fill=(220,220,220), outline=(0,0,0), ow=3)

        # ── Optional subtitle line ────────────────────────────────────
        if subtitle_line:
            sf  = self._font(38)
            sb  = draw.textbbox((0,0), subtitle_line, font=sf)
            sx  = (W2-(sb[2]-sb[0]))//2
            sy  = box_y - 80
            self._outlined_text(draw, subtitle_line, sf, sx, sy,
                                fill=(255,255,200), outline=(0,0,0), ow=3)

        # ── BOTTOM: Channel name bar ──────────────────────────────────
        if channel_name:
            draw.rectangle([(0,H2-85),(W2,H2)], fill=(0,0,0,220))
            cf  = self._font(38)
            cb  = draw.textbbox((0,0), channel_name, font=cf)
            cx  = (W2-(cb[2]-cb[0]))//2
            draw.text((cx, H2-65), channel_name, font=cf, fill=(180,180,180))

        return img

    # ─────────────────────────────────────────────────────────────────
    # THUMBNAIL
    # ─────────────────────────────────────────────────────────────────

    def generate_thumbnail(
        self, title="", script_text="", short_number=1,
        image_prompt=None, movie_name="", part_number=1,
        total_parts=100, channel_name="@MovieStoryteller",
    ):
        print(f"🖼️  Generating Thumbnail — {movie_name} Part {part_number}...")

        # Get AI background
        bg = self._get_bg_image(image_prompt) if image_prompt else None

        if bg:
            # Resize + crop to portrait
            ratio = bg.width / bg.height
            if ratio > W/H:
                nw, nh = int(H*ratio), H
            else:
                nw, nh = W, int(W/ratio)
            bg = bg.resize((nw, nh), Image.LANCZOS)
            l  = (nw-W)//2
            t  = (nh-H)//2
            bg = bg.crop((l, t, l+W, t+H))
            bg = ImageEnhance.Brightness(bg).enhance(0.55)
        else:
            bg = Image.new("RGB", (W,H), (10,10,30))
            d  = ImageDraw.Draw(bg)
            for y in range(H):
                d.line([(0,y),(W,y)], fill=(int(10+y/H*20), 0, int(20+y/H*60)))

        img = self._draw_card(
            bg, movie_name, part_number, total_parts,
            channel_name,
            subtitle_line=movie_name[:30] if len(movie_name) > 15 else "",
        )

        out = os.path.join(self.output_dir, f"thumbnail_{short_number}.png")
        img.save(out, "PNG", optimize=True)
        print(f"✅ Thumbnail saved: thumbnail_{short_number}.png")
        return out

    # ─────────────────────────────────────────────────────────────────
    # INTRO FRAME — same design as thumbnail, saved as image
    # ─────────────────────────────────────────────────────────────────

    def generate_intro_frame(
        self, movie_name, part_number, total_parts,
        channel_name, bg_image_path=None, short_number=1,
    ):
        """
        Generate a still frame (same design as thumbnail)
        to be used as 2-second intro at video start.
        """
        print(f"🎬 Generating intro frame — {movie_name} Part {part_number}...")

        if bg_image_path and os.path.exists(bg_image_path):
            bg = Image.open(bg_image_path).convert("RGB")
            # Darken more for intro
            bg = ImageEnhance.Brightness(bg).enhance(0.45)
            bg = bg.filter(ImageFilter.GaussianBlur(3))
        else:
            bg = Image.new("RGB", (W,H), (5,5,20))
            d  = ImageDraw.Draw(bg)
            for y in range(H):
                d.line([(0,y),(W,y)], fill=(int(5+y/H*15), 0, int(20+y/H*50)))

        img = self._draw_card(
            bg, movie_name, part_number, total_parts, channel_name
        )

        out = os.path.join(self.output_dir, f"intro_frame_{short_number}.png")
        img.save(out, "PNG", optimize=True)
        print(f"✅ Intro frame saved: intro_frame_{short_number}.png")
        return out
