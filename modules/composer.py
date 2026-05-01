import os
import shutil
import random
import subprocess
import json
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
            print("⚠️  No Devanagari font — PIL default fallback")

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

    # ─────────────────────────────────────────────────────────────────
    # SUBTITLE SYSTEM — Voice-synced, large, center-bottom
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _srt_ts(seconds):
        seconds  = max(0.0, seconds)
        total_ms = int(round(seconds * 1000))
        ms = total_ms % 1000
        s  = (total_ms // 1000) % 60
        m  = (total_ms // 60000) % 60
        h  = total_ms // 3600000
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    def _make_synced_srt(self, text, audio_duration, scene_id):
        """
        Create SRT file where each subtitle line is timed to match
        natural speech pace (~2.5 words per second).
        Lines are short (3-5 words) for easy reading.
        """
        words = text.split()
        if not words:
            return None

        # Group into short lines of 4-5 words max
        lines   = []
        current = []
        for word in words:
            current.append(word)
            if len(current) >= 5:
                lines.append(" ".join(current))
                current = []
        if current:
            lines.append(" ".join(current))

        if not lines:
            return None

        # Time each line proportionally to word count
        total_words   = len(words)
        srt_path      = os.path.join(self.temp_dir, f"sub_{scene_id}.srt")
        current_time  = 0.0

        with open(srt_path, "w", encoding="utf-8") as f:
            for i, line in enumerate(lines):
                line_words  = len(line.split())
                # Duration proportional to words in this line
                line_dur    = (line_words / total_words) * audio_duration
                line_dur    = max(line_dur, 0.8)  # minimum 0.8 sec per line

                start = current_time
                end   = min(current_time + line_dur - 0.05, audio_duration - 0.05)

                f.write(f"{i+1}\n")
                f.write(f"{self._srt_ts(start)} --> {self._srt_ts(end)}\n")
                f.write(f"{line}\n\n")

                current_time += line_dur

        return srt_path

    def _burn_subtitles_ffmpeg(self, src, srt_path, dst):
        """
        Burn subtitles using FFmpeg subtitles filter.
        Large font, center-bottom position, bold white with black outline.
        """
        if not self.font_path:
            shutil.copy2(src, dst)
            return False

        safe_srt  = srt_path.replace("\\", "/")
        safe_font = self.font_path.replace("\\", "/")

        # Escape Windows drive letter colon
        if len(safe_srt) >= 2 and safe_srt[1] == ":":
            safe_srt = safe_srt[0] + "\\:" + safe_srt[2:]

        style = (
            f"fontfile={safe_font},"
            "FontSize=22,"                   # Large enough for mobile
            "PrimaryColour=&H00FFFFFF,"      # White text
            "OutlineColour=&H00000000,"      # Black outline
            "BackColour=&H80000000,"         # Semi-transparent bg bar
            "Bold=1,"
            "Outline=3,"
            "Shadow=1,"
            "Alignment=2,"                   # Centre-bottom
            "MarginV=120,"                   # Above bottom edge
            "MarginL=40,"
            "MarginR=40"
        )

        cmd = [
            "ffmpeg", "-y", "-i", src,
            "-vf", f"subtitles='{safe_srt}':force_style='{style}'",
            "-c:v", "libx264", "-c:a", "copy",
            "-pix_fmt", "yuv420p", "-preset", "fast", dst,
        ]
        ok = self._run_cmd(cmd, "Subtitles FFmpeg")
        if not ok:
            shutil.copy2(src, dst)
        return ok

    # ─────────────────────────────────────────────────────────────────
    # PIL IMAGE OVERLAYS — top badge only (no subtitles here)
    # ─────────────────────────────────────────────────────────────────

    def _burn_badge_on_image(self, img_path, out_path, top_text):
        """
        Burn ONLY the part badge on top of image.
        Subtitles are handled separately by FFmpeg for proper sync.
        """
        img  = Image.open(img_path).convert("RGB")
        W, H = img.size
        draw = ImageDraw.Draw(img, "RGBA")

        # Dark top bar
        draw.rectangle([(0, 0), (W, 80)], fill=(0, 0, 0, 220))

        # Badge text
        font = self._pil_font(28)
        bbox = draw.textbbox((0, 0), top_text, font=font)
        tw   = bbox[2] - bbox[0]
        th   = bbox[3] - bbox[1]
        tx   = (W - tw) // 2
        ty   = (80 - th) // 2

        # Outline
        for dx, dy in [(-2,0),(2,0),(0,-2),(0,2),(-2,-2),(2,2)]:
            draw.text((tx+dx, ty+dy), top_text, font=font, fill=(0,0,0,255))
        draw.text((tx, ty), top_text, font=font, fill=(255,255,255,255))

        img.save(out_path, "JPEG", quality=92)
        return out_path

    # ─────────────────────────────────────────────────────────────────
    # IMAGE → VIDEO WITH KEN BURNS
    # ─────────────────────────────────────────────────────────────────

    def _image_to_video_kenburns(self, image_path, duration, output_path, zoom_dir="in"):
        fps    = 25
        frames = int(duration * fps)

        if zoom_dir == "in":
            z_expr = "min(zoom+0.0003,1.08)"
        else:
            z_expr = "max(zoom-0.0003,1.0)"

        vf = (
            f"scale=1200:2133,"
            f"zoompan=z='{z_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s=1080x1920:fps={fps},"
            f"setpts=PTS-STARTPTS,fps={fps}"
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
        return self._run_cmd(cmd, f"KenBurns")

    def _clip_to_portrait(self, clip_path, duration, output_path):
        cmd = [
            "ffmpeg", "-y", "-i", clip_path,
            "-vf", (
                "scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,fps=25"
            ),
            "-t", str(duration),
            "-an", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", "-preset", "fast",
            output_path,
        ]
        return self._run_cmd(cmd, "Clip→Portrait")

    # ─────────────────────────────────────────────────────────────────
    # BUILD VISUAL SEQUENCE — images + mood clips, NO subtitles yet
    # ─────────────────────────────────────────────────────────────────

    def _build_visual_sequence(self, image_paths, mood_clip_paths,
                                total_duration, part_number, top_text):
        """
        Build silent video from images + clips.
        Subtitles are added AFTER this step on the final video.
        """
        # Interleave images and mood clips
        all_visuals = []
        mood_idx    = 0
        for i, img_path in enumerate(image_paths):
            all_visuals.append(("image", img_path))
            if (i + 1) % 3 == 0 and mood_idx < len(mood_clip_paths):
                all_visuals.append(("clip", mood_clip_paths[mood_idx]))
                mood_idx += 1

        n            = max(len(all_visuals), 1)
        dur_per_slot = max(3.0, min(total_duration / n, 8.0))
        zoom_dirs    = ["in", "out"]
        segment_paths = []

        for idx, (vtype, vpath) in enumerate(all_visuals):
            seg_out = os.path.join(self.temp_dir, f"seg_{part_number}_{idx+1}.mp4")

            if vtype == "image":
                # Burn ONLY badge on image (no subtitles — added later)
                overlay_img = os.path.join(
                    self.temp_dir, f"overlay_{part_number}_{idx+1}.jpg"
                )
                self._burn_badge_on_image(vpath, overlay_img, top_text)
                ok = self._image_to_video_kenburns(
                    overlay_img, dur_per_slot, seg_out,
                    zoom_dir=zoom_dirs[idx % 2]
                )
            else:
                ok = self._clip_to_portrait(vpath, dur_per_slot, seg_out)

            if ok and os.path.exists(seg_out):
                segment_paths.append(seg_out)

        if not segment_paths:
            return None

        if len(segment_paths) == 1:
            return segment_paths[0]

        # Concat all segments
        list_file = os.path.join(self.temp_dir, f"list_{part_number}.txt")
        with open(list_file, "w") as f:
            for p in segment_paths:
                f.write(f"file '{p}'\n")

        concat_out = os.path.join(self.temp_dir, f"visual_{part_number}.mp4")
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-preset", "fast", concat_out,
        ]
        ok = self._run_cmd(cmd, "Concat segments")
        return concat_out if ok else segment_paths[0]

    # ─────────────────────────────────────────────────────────────────
    # PROCESS SCENE — main function
    # ─────────────────────────────────────────────────────────────────

    def process_scene(self, scene, image_paths, mood_clips, is_first=False):
        part_number = scene.get("part_number", 1)
        total_parts = scene.get("total_parts", 100)
        movie_name  = scene.get("movie", "Movie")
        audio_path  = scene.get("audio_path")
        total_dur   = scene.get("duration", 0)
        script_text = scene.get("text", "")

        if not audio_path or not os.path.exists(audio_path):
            print(f"   ⚠️ Audio missing for Part {part_number}")
            return None

        if not image_paths:
            print(f"   ⚠️ No images for Part {part_number}")
            return None

        short_movie = movie_name[:26]
        top_text    = f"🎬 {short_movie} | Part {part_number}/{total_parts}"

        raw_path    = os.path.join(self.temp_dir, f"raw_{part_number}.mp4")
        nosub_path  = os.path.join(self.temp_dir, f"nosub_{part_number}.mp4")
        subbed_path = os.path.join(self.temp_dir, f"subbed_{part_number}.mp4")
        final_path  = os.path.join(self.temp_dir, f"scene_{part_number}.mp4")

        # ── Step 1: Build silent visual sequence ────────────────────
        visual = self._build_visual_sequence(
            image_paths, mood_clips, total_dur, part_number, top_text
        )
        if not visual:
            print(f"   ❌ Visual failed for Part {part_number}")
            return None

        # ── Step 2: Add voice + bg music ────────────────────────────
        try:
            voice = ffmpeg.input(audio_path)
            vis   = ffmpeg.input(visual)

            if os.path.exists(self.bg_music_path):
                bg = (
                    ffmpeg.input(self.bg_music_path, stream_loop=-1)
                    .filter("volume", 0.10)
                    .filter("atrim", duration=total_dur + 1)
                )
                audio_out = ffmpeg.filter(
                    [voice, bg], "amix", inputs=2, duration="first"
                )
            else:
                audio_out = voice

            (
                ffmpeg.output(
                    vis.video, audio_out, nosub_path,
                    vcodec="libx264", acodec="aac",
                    pix_fmt="yuv420p", preset="medium",
                    movflags="faststart",
                    **{"avoid_negative_ts": "make_zero", "shortest": None}
                ).run(overwrite_output=True, quiet=True)
            )
        except Exception as e:
            print(f"   ❌ Audio mix failed Part {part_number}: {e}")
            return None

        # ── Step 3: Burn voice-synced subtitles ─────────────────────
        # Get actual audio duration for precise subtitle timing
        actual_dur = self.get_duration(nosub_path)
        srt = self._make_synced_srt(script_text, actual_dur, part_number)

        if srt:
            ok = self._burn_subtitles_ffmpeg(nosub_path, srt, subbed_path)
            current = subbed_path if ok else nosub_path
        else:
            current = nosub_path

        if current != final_path:
            shutil.copy2(current, final_path)

        print(f"   ✅ Part {part_number} rendered ({total_dur:.1f}s) with synced subtitles")
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
            print(f"✅ FINAL VIDEO: {output_path}")
            return output_path

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
