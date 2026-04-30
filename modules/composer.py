import os
import shutil
import random
import subprocess
import ffmpeg


class Composer:

    def __init__(self):
        self.temp_dir      = os.path.join(os.getcwd(), "assets", "temp")
        self.final_dir     = os.path.join(os.getcwd(), "assets", "final")
        self.bg_music_path = "bgmusic.mp3"
        self.font_path     = self._resolve_font()

        os.makedirs(self.temp_dir,  exist_ok=True)
        os.makedirs(self.final_dir, exist_ok=True)

        self.transitions = ["fade", "wipeleft", "wiperight", "slideleft", "slideright"]

        if self.font_path:
            print(f"✅ Font: {self.font_path}")
        else:
            print("⚠️  No Devanagari font — text overlays will be skipped.")

    # ─────────────────────────────────────────────────────────────────
    # FONT
    # ─────────────────────────────────────────────────────────────────

    def _resolve_font(self):
        candidates = [
            os.path.join(os.getcwd(), "assets", "fonts", "NotoSans-Bold.ttf"),
            os.path.join(os.getcwd(), "assets", "fonts", "NotoSansDevanagari-Bold.ttf"),
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
            "/usr/share/fonts/noto/NotoSansDevanagari-Bold.ttf",
        ]
        for p in candidates:
            if os.path.exists(p) and os.path.getsize(p) > 10_000:
                return p
        return None

    # ─────────────────────────────────────────────────────────────────
    # UTILITIES
    # ─────────────────────────────────────────────────────────────────

    def get_duration(self, filepath):
        try:
            return float(ffmpeg.probe(filepath)["format"]["duration"])
        except Exception:
            return 0.0

    def _font_arg(self):
        if self.font_path:
            return f"fontfile={self.font_path.replace(chr(92), '/')}:"
        return ""

    @staticmethod
    def _srt_ts(seconds):
        seconds  = max(0.0, seconds)
        total_ms = int(round(seconds * 1000))
        ms  = total_ms % 1000
        s   = (total_ms // 1000) % 60
        m   = (total_ms // 60000) % 60
        h   = total_ms // 3600000
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    def _make_srt(self, text, duration, scene_id):
        words, lines, current = text.split(), [], []
        for word in words:
            if len(" ".join(current + [word])) <= 38:
                current.append(word)
            else:
                if current:
                    lines.append(" ".join(current))
                current = [word]
        if current:
            lines.append(" ".join(current))
        if not lines:
            return None

        srt_path      = os.path.join(self.temp_dir, f"sub_{scene_id}.srt")
        time_per_line = duration / len(lines)

        with open(srt_path, "w", encoding="utf-8") as f:
            for i, line in enumerate(lines):
                start = i * time_per_line
                end   = min((i + 1) * time_per_line - 0.04, duration - 0.04)
                f.write(f"{i+1}\n{self._srt_ts(start)} --> {self._srt_ts(end)}\n{line}\n\n")
        return srt_path

    def _run_cmd(self, cmd, label):
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"   ⚠️ {label} failed:\n{result.stderr[-400:]}")
            return False
        return True

    # ─────────────────────────────────────────────────────────────────
    # IMAGE → VIDEO CONVERSION
    # ─────────────────────────────────────────────────────────────────

    def _image_to_video(self, image_path, duration, output_path):
        """
        Convert a still image into a video of given duration.
        Adds a subtle Ken Burns zoom effect for visual interest.
        """
        # Ken Burns: slow zoom from 1.0x to 1.05x
        vf = (
            f"scale=1200:2133,"          # slightly larger than 1080x1920 for zoom room
            f"zoompan=z='min(zoom+0.0003,1.05)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={int(duration * 25)}:s=1080x1920:fps=25,"
            f"setpts=PTS-STARTPTS"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image_path,
            "-vf", vf,
            "-t", str(duration + 0.1),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "medium",
            output_path,
        ]
        return self._run_cmd(cmd, f"Image→Video {os.path.basename(image_path)}")

    # ─────────────────────────────────────────────────────────────────
    # TEXT OVERLAYS
    # ─────────────────────────────────────────────────────────────────

    def _burn_subtitles(self, src, srt_path, dst):
        if not self.font_path:
            shutil.copy2(src, dst)
            return
        safe_srt  = srt_path.replace("\\", "/")
        if len(safe_srt) >= 2 and safe_srt[1] == ":":
            safe_srt = safe_srt[0] + "\\:" + safe_srt[2:]
        style = (
            f"fontfile={self.font_path.replace(chr(92), '/')}:"
            "FontSize=17,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "BackColour=&H60000000,Bold=1,Outline=2,Shadow=1,Alignment=2,MarginV=65"
        )
        cmd = [
            "ffmpeg", "-y", "-i", src,
            "-vf", f"subtitles='{safe_srt}':force_style='{style}'",
            "-c:v", "libx264", "-c:a", "copy",
            "-pix_fmt", "yuv420p", "-preset", "medium", dst,
        ]
        if not self._run_cmd(cmd, "Subtitles"):
            shutil.copy2(src, dst)

    def _burn_part_badge(self, src, movie_name, part_number, total_parts, dst):
        """
        Top bar showing:  ◀ Movie Name | Part X/100 ▶
        """
        if not self.font_path:
            shutil.copy2(src, dst)
            return

        font = self.font_path.replace("\\", "/")
        # Short movie name (first 20 chars to avoid overflow)
        short_name = movie_name[:22].replace("'", "\\'").replace(":", "\\:")
        badge_text = f"{short_name} | Part {part_number}/{total_parts}"
        safe_badge = badge_text.replace("'", "\\'").replace(":", "\\:")

        vf = (
            # Dark top bar
            "drawbox=x=0:y=0:w=iw:h=70:color=black@0.75:t=fill,"
            # Badge text
            f"drawtext=fontfile={font}:"
            f"text='{safe_badge}':"
            f"fontsize=20:fontcolor=white:borderw=2:bordercolor=black:"
            f"x=(w-text_w)/2:y=22"
        )
        cmd = [
            "ffmpeg", "-y", "-i", src,
            "-vf", vf,
            "-c:v", "libx264", "-c:a", "copy",
            "-pix_fmt", "yuv420p", "-preset", "medium", dst,
        ]
        if not self._run_cmd(cmd, "Part badge"):
            shutil.copy2(src, dst)

    def _burn_hook_text(self, src, hook_text, dst):
        if not hook_text or not self.font_path:
            shutil.copy2(src, dst)
            return
        font     = self.font_path.replace("\\", "/")
        safe_txt = hook_text.replace("'", "\\'").replace(":", "\\:")
        vf = (
            f"drawtext=fontfile={font}:"
            f"text='{safe_txt}':"
            f"fontsize=24:fontcolor=white:borderw=3:bordercolor=black:"
            f"x=(w-text_w)/2:y=90:enable='between(t,0,4)'"
        )
        cmd = [
            "ffmpeg", "-y", "-i", src,
            "-vf", vf,
            "-c:v", "libx264", "-c:a", "copy",
            "-pix_fmt", "yuv420p", "-preset", "medium", dst,
        ]
        if not self._run_cmd(cmd, "Hook text"):
            shutil.copy2(src, dst)

    def _burn_end_card(self, src, dst):
        """Bottom strip: 'Subscribe for Part X+1 🔔'"""
        if not self.font_path:
            shutil.copy2(src, dst)
            return
        font = self.font_path.replace("\\", "/")
        dur  = self.get_duration(src)
        # Show last 3 seconds
        start_t = max(dur - 3.0, 0)
        vf = (
            "drawbox=x=0:y=ih-80:w=iw:h=80:color=black@0.8:t=fill,"
            f"drawtext=fontfile={font}:"
            f"text='Subscribe karo agle part ke liye 🔔':"
            f"fontsize=18:fontcolor=white:borderw=2:bordercolor=black:"
            f"x=(w-text_w)/2:y=ih-55:"
            f"enable='gte(t,{start_t:.2f})'"
        )
        cmd = [
            "ffmpeg", "-y", "-i", src,
            "-vf", vf,
            "-c:v", "libx264", "-c:a", "copy",
            "-pix_fmt", "yuv420p", "-preset", "medium", dst,
        ]
        if not self._run_cmd(cmd, "End card"):
            shutil.copy2(src, dst)

    def _burn_watermark(self, src, dst, channel_name):
        if not channel_name or not self.font_path:
            shutil.copy2(src, dst)
            return
        font      = self.font_path.replace("\\", "/")
        safe_name = channel_name.replace("'", "\\'").replace(":", "\\:")
        vf = (
            f"drawtext=fontfile={font}:"
            f"text='{safe_name}':"
            f"fontsize=13:fontcolor=white@0.6:borderw=2:bordercolor=black@0.4:"
            f"x=w-text_w-18:y=28"
        )
        cmd = [
            "ffmpeg", "-y", "-i", src,
            "-vf", vf,
            "-c:v", "libx264", "-c:a", "copy",
            "-pix_fmt", "yuv420p", "-preset", "medium", dst,
        ]
        if not self._run_cmd(cmd, "Watermark"):
            shutil.copy2(src, dst)

    # ─────────────────────────────────────────────────────────────────
    # SCENE PROCESSING
    # ─────────────────────────────────────────────────────────────────

    def process_scene(self, scene, image_pair, is_first=False):
        scene_id    = scene.get("id", 1)
        part_number = scene.get("part_number", scene_id)
        total_parts = scene.get("total_parts", 100)
        movie_name  = scene.get("movie", "Movie")
        audio_path  = scene.get("audio_path")
        total_dur   = scene.get("duration", 0)
        script_text = scene.get("text", "")
        hook_text   = scene.get("hook_text", "")

        if not audio_path or not os.path.exists(audio_path):
            print(f"   ⚠️ Audio missing for Part {part_number}")
            return None

        img1, img2 = image_pair if image_pair else (None, None)

        vid1_path  = os.path.join(self.temp_dir, f"img1_vid_{part_number}.mp4")
        vid2_path  = os.path.join(self.temp_dir, f"img2_vid_{part_number}.mp4")
        raw_path   = os.path.join(self.temp_dir, f"scene_{part_number}_raw.mp4")
        sub_path   = os.path.join(self.temp_dir, f"scene_{part_number}_sub.mp4")
        badge_path = os.path.join(self.temp_dir, f"scene_{part_number}_badge.mp4")
        hook_path  = os.path.join(self.temp_dir, f"scene_{part_number}_hook.mp4")
        end_path   = os.path.join(self.temp_dir, f"scene_{part_number}_end.mp4")
        final_path = os.path.join(self.temp_dir, f"scene_{part_number}.mp4")

        try:
            # ── Build video from images ──────────────────────────────
            dur_half = total_dur / 2

            if img1 and os.path.exists(img1):
                self._image_to_video(img1, dur_half, vid1_path)
            else:
                # Solid black placeholder
                cmd = [
                    "ffmpeg", "-y", "-f", "lavfi",
                    "-i", f"color=c=black:s=1080x1920:r=25:d={dur_half}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", vid1_path,
                ]
                self._run_cmd(cmd, "Placeholder vid1")

            if img2 and os.path.exists(img2) and img2 != img1:
                self._image_to_video(img2, dur_half + 0.5, vid2_path)
            else:
                shutil.copy2(vid1_path, vid2_path)

            # ── Concat two image clips ───────────────────────────────
            v1 = ffmpeg.input(vid1_path).video
            v2 = ffmpeg.input(vid2_path).video

            # Crossfade between images
            v_stream = ffmpeg.filter(
                [v1, v2], "xfade",
                transition="fade", duration=0.5, offset=dur_half - 0.5,
            )

            # ── Add voice + bg music ─────────────────────────────────
            voice = ffmpeg.input(audio_path)
            if os.path.exists(self.bg_music_path):
                bg = (
                    ffmpeg.input(self.bg_music_path, stream_loop=-1)
                    .filter("volume", 0.12)
                    .filter("atrim", duration=total_dur + 1)
                )
                audio_out = ffmpeg.filter([voice, bg], "amix", inputs=2, duration="first")
            else:
                audio_out = voice

            (
                ffmpeg.output(
                    v_stream, audio_out, raw_path,
                    vcodec="libx264", acodec="aac",
                    pix_fmt="yuv420p", preset="medium",
                    movflags="faststart",
                    **{"avoid_negative_ts": "make_zero"}
                ).run(overwrite_output=True, quiet=True)
            )

        except Exception as e:
            print(f"❌ Render Fail Part {part_number}: {e}")
            return None

        current = raw_path

        # ── Subtitles ────────────────────────────────────────────────
        if script_text.strip():
            srt = self._make_srt(script_text, total_dur, part_number)
            if srt:
                self._burn_subtitles(current, srt, sub_path)
                current = sub_path

        # ── Part badge (top bar) ─────────────────────────────────────
        self._burn_part_badge(current, movie_name, part_number, total_parts, badge_path)
        current = badge_path

        # ── Hook text (first 4 seconds) ──────────────────────────────
        if is_first and hook_text:
            self._burn_hook_text(current, hook_text, hook_path)
            current = hook_path

        # ── End card (last 3 seconds) ────────────────────────────────
        self._burn_end_card(current, end_path)
        current = end_path

        if current != final_path:
            shutil.copy2(current, final_path)

        print(f"   ✅ Part {part_number} rendered")
        return final_path

    # ─────────────────────────────────────────────────────────────────
    # RENDER ALL
    # ─────────────────────────────────────────────────────────────────

    def render_all_scenes(self, script_data, image_pairs):
        rendered = []
        for i, scene in enumerate(script_data):
            pair = image_pairs[i] if i < len(image_pairs) else (None, None)
            path = self.process_scene(scene, pair, is_first=(i == 0))
            if path:
                rendered.append(path)
        return rendered

    # ─────────────────────────────────────────────────────────────────
    # CONCATENATE
    # ─────────────────────────────────────────────────────────────────

    def concatenate_with_transitions(
        self, video_paths,
        output_filename="final_short.mp4",
        channel_name="@MovieStoryteller",
    ):
        print("🎬 Stitching final video...")
        nowm_path   = os.path.join(self.final_dir, "final_nowm.mp4")
        output_path = os.path.join(self.final_dir, output_filename)

        for p in (nowm_path, output_path):
            if os.path.exists(p):
                try: os.remove(p)
                except Exception: pass

        if not video_paths:
            return None

        if len(video_paths) == 1:
            shutil.copy2(video_paths[0], nowm_path)
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
                    transition=random.choice(self.transitions),
                    duration=trans, offset=offset,
                )
                a_stream = ffmpeg.filter(
                    [a_stream, nxt.audio], "acrossfade", d=trans,
                )
                current_dur = current_dur + next_dur - trans

            try:
                (
                    ffmpeg.output(
                        v_stream, a_stream, nowm_path,
                        vcodec="libx264", acodec="aac",
                        pix_fmt="yuv420p", preset="medium",
                        movflags="faststart",
                    ).run(overwrite_output=True, quiet=False)
                )
            except Exception as e:
                print(f"❌ Stitching Error: {e}")
                return None

        self._burn_watermark(nowm_path, output_path, channel_name)

        try: os.remove(nowm_path)
        except Exception: pass

        print(f"✅ FINAL VIDEO: {output_path}")
        return output_path