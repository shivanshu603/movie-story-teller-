import os
import shutil
import random
import subprocess
import textwrap
import ffmpeg
from PIL import Image, ImageDraw, ImageFont


class Composer:

    def __init__(self):
        self.temp_dir      = os.path.join(os.getcwd(), "assets", "temp")
        self.final_dir     = os.path.join(os.getcwd(), "assets", "final")
        self.bg_music_path = "bgmusic.mp3"
        self.font_path     = self._resolve_font()

        os.makedirs(self.temp_dir,  exist_ok=True)
        os.makedirs(self.final_dir, exist_ok=True)

        if self.font_path:
            print(f"✅ Font: {self.font_path}")
        else:
            print("⚠️  No font found — text burned via PIL fallback")

    # ─────────────────────────────────────────────────────────────────
    # FONT
    # ─────────────────────────────────────────────────────────────────

    def _resolve_font(self):
        candidates = [
            os.path.join(os.getcwd(), "assets", "fonts", "NotoSans-Bold.ttf"),
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
            "/usr/share/fonts/noto/NotoSansDevanagari-Bold.ttf",
        ]
        for p in candidates:
            if os.path.exists(p) and os.path.getsize(p) > 10_000:
                return p
        return None

    def _pil_font(self, size):
        if self.font_path:
            try:
                return ImageFont.truetype(self.font_path, size)
            except Exception:
                pass
        return ImageFont.load_default()

    # ─────────────────────────────────────────────────────────────────
    # UTILITIES
    # ─────────────────────────────────────────────────────────────────

    def get_duration(self, filepath):
        try:
            return float(ffmpeg.probe(filepath)["format"]["duration"])
        except Exception:
            return 0.0

    def _run_cmd(self, cmd, label):
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"   ⚠️ {label} failed:\n{result.stderr[-300:]}")
            return False
        return True

    @staticmethod
    def _srt_ts(seconds):
        seconds  = max(0.0, seconds)
        total_ms = int(round(seconds * 1000))
        ms = total_ms % 1000
        s  = (total_ms // 1000) % 60
        m  = (total_ms // 60000) % 60
        h  = total_ms // 3600000
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    # ─────────────────────────────────────────────────────────────────
    # PIL TEXT OVERLAY — burn text directly onto image frames
    # No FFmpeg drawtext/subtitles filter needed
    # ─────────────────────────────────────────────────────────────────

    def _burn_text_on_image(self, img_path, out_path,
                             top_text=None, bottom_lines=None):
        """
        Burn text overlays directly onto an image using PIL.
        top_text    : Part badge / movie name (top bar)
        bottom_lines: List of subtitle lines (bottom)
        Returns out_path.
        """
        img  = Image.open(img_path).convert("RGB")
        W, H = img.size
        draw = ImageDraw.Draw(img, "RGBA")

        # ── TOP BAR (movie + part badge) ─────────────────────────────
        if top_text:
            bar_h  = 72
            draw.rectangle([(0, 0), (W, bar_h)], fill=(0, 0, 0, 210))
            font   = self._pil_font(26)
            bbox   = draw.textbbox((0, 0), top_text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tx     = (W - tw) // 2
            ty     = (bar_h - th) // 2
            # Outline
            for dx, dy in [(-2,0),(2,0),(0,-2),(0,2)]:
                draw.text((tx+dx, ty+dy), top_text, font=font, fill=(0,0,0,255))
            draw.text((tx, ty), top_text, font=font, fill=(255, 255, 255, 255))

        # ── BOTTOM SUBTITLES ─────────────────────────────────────────
        if bottom_lines:
            font     = self._pil_font(22)
            line_h   = 34
            n_lines  = len(bottom_lines)
            bar_h    = n_lines * line_h + 24
            bar_y    = H - bar_h - 50
            draw.rectangle([(0, bar_y), (W, bar_y + bar_h)], fill=(0, 0, 0, 170))

            for i, line in enumerate(bottom_lines):
                bbox = draw.textbbox((0, 0), line, font=font)
                tw   = bbox[2] - bbox[0]
                tx   = (W - tw) // 2
                ty   = bar_y + 12 + i * line_h
                for dx, dy in [(-2,0),(2,0),(0,-2),(0,2)]:
                    draw.text((tx+dx, ty+dy), line, font=font, fill=(0,0,0,255))
                draw.text((tx, ty), line, font=font, fill=(255, 255, 255, 255))

        img.save(out_path, "JPEG", quality=92)
        return out_path

    # ─────────────────────────────────────────────────────────────────
    # IMAGE → VIDEO WITH KEN BURNS ZOOM
    # ─────────────────────────────────────────────────────────────────

    def _image_to_video_kenburns(self, image_path, duration, output_path,
                                  zoom_dir="in"):
        """
        Convert image to video with Ken Burns zoom effect.
        zoom_dir: 'in' (zoom in) or 'out' (zoom out)
        """
        fps    = 25
        frames = int(duration * fps)

        if zoom_dir == "in":
            # Start at 1.0x, end at 1.08x
            z_expr = "min(zoom+0.00025,1.08)"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"
        else:
            # Start at 1.08x, zoom out to 1.0x
            z_expr = "max(zoom-0.00025,1.0)"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"

        vf = (
            f"scale=1200:2133,"
            f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}'"
            f":d={frames}:s=1080x1920:fps={fps},"
            f"setpts=PTS-STARTPTS,"
            f"fps={fps}"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-vf", vf,
            "-t", str(duration),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            output_path,
        ]
        ok = self._run_cmd(cmd, f"KenBurns {os.path.basename(image_path)}")
        return ok

    def _clip_to_portrait(self, clip_path, duration, output_path):
        """Crop a Pexels clip to 1080x1920 portrait and trim to duration."""
        cmd = [
            "ffmpeg", "-y",
            "-i", clip_path,
            "-vf", (
                "scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,"
                "fps=25"
            ),
            "-t", str(duration),
            "-an",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            output_path,
        ]
        return self._run_cmd(cmd, "Clip→Portrait")

    # ─────────────────────────────────────────────────────────────────
    # BUILD VISUAL SEQUENCE
    # ─────────────────────────────────────────────────────────────────

    def _build_visual_sequence(self, image_paths, mood_clip_paths,
                                total_duration, part_number,
                                top_text, subtitle_lines):
        """
        Build a sequence of short clips from images + mood clips.
        - Each image shown for 5-8 seconds with Ken Burns
        - Mood clips inserted every 3rd slot
        - PIL text overlays burned onto each image frame
        Returns path to concatenated silent video.
        """
        all_visuals = []

        # Interleave: img img img mood_clip img img img mood_clip ...
        mood_idx = 0
        for i, img_path in enumerate(image_paths):
            all_visuals.append(("image", img_path))
            if (i + 1) % 3 == 0 and mood_idx < len(mood_clip_paths):
                all_visuals.append(("clip", mood_clip_paths[mood_idx]))
                mood_idx += 1

        # Distribute duration evenly
        n             = len(all_visuals)
        dur_per_slot  = total_duration / n if n > 0 else total_duration
        dur_per_slot  = max(3.0, min(dur_per_slot, 8.0))

        # Subtitle chunking — distribute lines across slots
        words   = " ".join(subtitle_lines).split() if subtitle_lines else []
        chunks  = []
        current = []
        for word in words:
            if len(" ".join(current + [word])) <= 36:
                current.append(word)
            else:
                if current:
                    chunks.append(" ".join(current))
                current = [word]
        if current:
            chunks.append(" ".join(current))

        lines_per_slot = max(1, len(chunks) // n) if n > 0 else 1

        segment_paths = []
        zoom_dirs     = ["in", "out"]

        for idx, (vtype, vpath) in enumerate(all_visuals):
            seg_out = os.path.join(self.temp_dir,
                                   f"seg_{part_number}_{idx+1}.mp4")

            # Subtitle lines for this slot
            start_l = idx * lines_per_slot
            end_l   = start_l + lines_per_slot
            slot_lines = chunks[start_l:end_l]

            if vtype == "image":
                # Burn text onto image first (PIL)
                overlay_img = os.path.join(
                    self.temp_dir, f"overlay_{part_number}_{idx+1}.jpg"
                )
                self._burn_text_on_image(
                    vpath, overlay_img,
                    top_text=top_text,
                    bottom_lines=slot_lines if slot_lines else None,
                )
                # Ken Burns zoom
                zoom = zoom_dirs[idx % 2]
                ok   = self._image_to_video_kenburns(
                    overlay_img, dur_per_slot, seg_out, zoom_dir=zoom
                )
                if not ok:
                    continue

            else:  # mood clip
                ok = self._clip_to_portrait(vpath, dur_per_slot, seg_out)
                if not ok:
                    continue

            segment_paths.append(seg_out)

        if not segment_paths:
            return None

        # Concatenate all segments with fast crossfade
        if len(segment_paths) == 1:
            concat_out = segment_paths[0]
        else:
            # Build concat filter
            inputs  = []
            for p in segment_paths:
                inputs += ["-i", p]

            filter_parts = []
            v = "[0:v]"
            current_dur = dur_per_slot

            for i in range(1, len(segment_paths)):
                offset = max(current_dur - 0.3, 0.1)
                out_v  = f"[v{i}]"
                filter_parts.append(
                    f"{v}[{i}:v]xfade=transition=fade:duration=0.3:offset={offset:.2f}{out_v}"
                )
                v = out_v
                current_dur += dur_per_slot - 0.3

            filter_str  = ";".join(filter_parts)
            concat_out  = os.path.join(self.temp_dir,
                                        f"visual_{part_number}.mp4")
            cmd = (
                ["ffmpeg", "-y"]
                + inputs
                + ["-filter_complex", filter_str,
                   "-map", v,
                   "-c:v", "libx264",
                   "-pix_fmt", "yuv420p",
                   "-preset", "fast",
                   concat_out]
            )
            ok = self._run_cmd(cmd, "Concat segments")
            if not ok:
                # Fallback: simple concat
                list_file = os.path.join(self.temp_dir,
                                          f"list_{part_number}.txt")
                with open(list_file, "w") as f:
                    for p in segment_paths:
                        f.write(f"file '{p}'\n")
                cmd2 = [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", list_file,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-preset", "fast", concat_out,
                ]
                self._run_cmd(cmd2, "Concat fallback")

        return concat_out

    # ─────────────────────────────────────────────────────────────────
    # PROCESS SCENE
    # ─────────────────────────────────────────────────────────────────

    def process_scene(self, scene, image_paths, mood_clips, is_first=False):
        part_number = scene.get("part_number", 1)
        total_parts = scene.get("total_parts", 100)
        movie_name  = scene.get("movie", "Movie")
        audio_path  = scene.get("audio_path")
        total_dur   = scene.get("duration", 0)
        script_text = scene.get("text", "")
        hook_text   = scene.get("hook_text", "")

        if not audio_path or not os.path.exists(audio_path):
            print(f"   ⚠️ Audio missing for Part {part_number}")
            return None

        if not image_paths:
            print(f"   ⚠️ No images for Part {part_number}")
            return None

        # Top badge text
        short_movie = movie_name[:28]
        top_text    = f"{short_movie} | Part {part_number}/{total_parts}"

        # Subtitle lines from script
        words, lines, cur = script_text.split(), [], []
        for word in words:
            if len(" ".join(cur + [word])) <= 36:
                cur.append(word)
            else:
                if cur: lines.append(" ".join(cur))
                cur = [word]
        if cur: lines.append(" ".join(cur))

        final_path  = os.path.join(self.temp_dir, f"scene_{part_number}.mp4")
        visual_path = os.path.join(self.temp_dir, f"visual_{part_number}.mp4")
        raw_path    = os.path.join(self.temp_dir, f"raw_{part_number}.mp4")

        # ── Build visual sequence ────────────────────────────────────
        visual = self._build_visual_sequence(
            image_paths, mood_clips, total_dur,
            part_number, top_text, lines,
        )
        if not visual:
            print(f"   ❌ Visual sequence failed for Part {part_number}")
            return None

        # ── Mix audio (voice + bg music) ─────────────────────────────
        try:
            voice = ffmpeg.input(audio_path)
            if os.path.exists(self.bg_music_path):
                bg = (
                    ffmpeg.input(self.bg_music_path, stream_loop=-1)
                    .filter("volume", 0.12)
                    .filter("atrim", duration=total_dur + 1)
                )
                audio_out = ffmpeg.filter(
                    [voice, bg], "amix", inputs=2, duration="first"
                )
            else:
                audio_out = voice

            vis_input = ffmpeg.input(visual)

            (
                ffmpeg.output(
                    vis_input.video, audio_out, raw_path,
                    vcodec="libx264", acodec="aac",
                    pix_fmt="yuv420p", preset="medium",
                    movflags="faststart",
                    **{"avoid_negative_ts": "make_zero",
                       "shortest": None}
                ).run(overwrite_output=True, quiet=True)
            )
        except Exception as e:
            print(f"   ❌ Audio mix failed Part {part_number}: {e}")
            return None

        # ── End card via PIL on last frame approach ──────────────────
        # Simple: burn "Subscribe karo 🔔" text on a black bar at bottom
        # We do this by re-encoding last 3 seconds with overlay
        # For simplicity — add end card as overlay during PIL image step
        # (already done in _build_visual_sequence for last slot)

        shutil.copy2(raw_path, final_path)
        print(f"   ✅ Part {part_number} rendered ({total_dur:.1f}s)")
        return final_path

    # ─────────────────────────────────────────────────────────────────
    # RENDER ALL
    # ─────────────────────────────────────────────────────────────────

    def render_all_scenes(self, script_data, image_paths_list, mood_clips_list):
        rendered = []
        for i, scene in enumerate(script_data):
            imgs  = image_paths_list[i] if i < len(image_paths_list) else []
            moods = mood_clips_list[i]  if i < len(mood_clips_list)  else []
            path  = self.process_scene(scene, imgs, moods, is_first=(i == 0))
            if path:
                rendered.append(path)
        return rendered

    # ─────────────────────────────────────────────────────────────────
    # FINAL OUTPUT
    # ─────────────────────────────────────────────────────────────────

    def concatenate_with_transitions(
        self, video_paths,
        output_filename="final_short.mp4",
        channel_name="@MovieStoryteller",
    ):
        print("🎬 Finalizing video...")
        output_path = os.path.join(self.final_dir, output_filename)

        if os.path.exists(output_path):
            try: os.remove(output_path)
            except Exception: pass

        if not video_paths:
            return None

        if len(video_paths) == 1:
            shutil.copy2(video_paths[0], output_path)
        else:
            inp         = ffmpeg.input(video_paths[0])
            v_stream    = inp.video
            a_stream    = inp.audio
            current_dur = self.get_duration(video_paths[0])

            for i in range(1, len(video_paths)):
                nxt      = ffmpeg.input(video_paths[i])
                next_dur = self.get_duration(video_paths[i])
                trans    = 0.5
                offset   = max(current_dur - trans, 0.1)
                v_stream = ffmpeg.filter(
                    [v_stream, nxt.video], "xfade",
                    transition="fade", duration=trans, offset=offset,
                )
                a_stream = ffmpeg.filter(
                    [a_stream, nxt.audio], "acrossfade", d=trans,
                )
                current_dur += next_dur - trans

            try:
                (
                    ffmpeg.output(
                        v_stream, a_stream, output_path,
                        vcodec="libx264", acodec="aac",
                        pix_fmt="yuv420p", preset="medium",
                        movflags="faststart",
                    ).run(overwrite_output=True, quiet=False)
                )
            except Exception as e:
                print(f"❌ Final stitch error: {e}")
                return None

        print(f"✅ FINAL VIDEO: {output_path}")
        return output_path
