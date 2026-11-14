"""
MP4 Cutter core: ffmpeg wrapper functions (no GUI code here).

- probe(): read duration / video info
- grab_frame(): PNG preview frame at a given time
- cut(): export one or more segments, lossless (stream copy) or precise (re-encode)
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

# Hide console windows on Windows when calling ffmpeg
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def find_ffmpeg():
    """Bundled ffmpeg (exe build) -> imageio-ffmpeg -> system PATH."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for name in ("ffmpeg.exe", "ffmpeg"):
        p = os.path.join(base, name)
        if os.path.isfile(p):
            return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    p = shutil.which("ffmpeg")
    if p:
        return p
    raise FileNotFoundError(
        "ffmpeg를 찾을 수 없습니다. 'pip install imageio-ffmpeg' 를 실행하거나 ffmpeg를 설치하세요."
    )


def _run(args, **kw):
    return subprocess.run(args, capture_output=True, stdin=subprocess.DEVNULL,
                          creationflags=_NO_WINDOW, **kw)


def fmt_time(sec):
    """seconds -> 'HH:MM:SS.mmm'"""
    if sec < 0:
        sec = 0
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def parse_time(text):
    """'HH:MM:SS.mmm', 'MM:SS', '75.5' -> seconds (float)"""
    text = text.strip().replace(",", ".")
    if not text:
        raise ValueError("빈 시간값")
    parts = text.split(":")
    if len(parts) > 3:
        raise ValueError(f"잘못된 시간 형식: {text}")
    total = 0.0
    for p in parts:
        total = total * 60 + float(p)
    return total


def probe(ffmpeg, path):
    """Return dict(duration, width, height, fps, vcodec, acodec)."""
    r = _run([ffmpeg, "-hide_banner", "-i", path])
    err = r.stderr.decode("utf-8", "replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if not m:
        raise ValueError("영상 정보를 읽을 수 없습니다 (지원하지 않는 파일일 수 있습니다).")
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    info = {"duration": dur, "width": 0, "height": 0, "fps": 0.0, "vcodec": "", "acodec": ""}
    v = re.search(r"Stream #.*?Video:\s*(\w+).*?(\d{2,5})x(\d{2,5})", err)
    if v:
        info["vcodec"], info["width"], info["height"] = v.group(1), int(v.group(2)), int(v.group(3))
    f = re.search(r"(\d+(?:\.\d+)?)\s*fps", err)
    if f:
        info["fps"] = float(f.group(1))
    a = re.search(r"Stream #.*?Audio:\s*(\w+)", err)
    if a:
        info["acodec"] = a.group(1)
    return info


def grab_frame(ffmpeg, path, t, max_w=800, max_h=450):
    """Return PNG bytes of the frame at time t (seconds), or None."""
    vf = f"scale=w={max_w}:h={max_h}:force_original_aspect_ratio=decrease"
    r = _run([ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{max(t, 0):.3f}",
              "-i", path, "-frames:v", "1", "-vf", vf, "-f", "image2pipe", "-vcodec", "png", "-"])
    return r.stdout if r.returncode == 0 and r.stdout else None


def _cut_one(ffmpeg, src, start, end, out, precise, on_progress, offset, total, cancel):
    dur = end - start
    args = [ffmpeg, "-hide_banner", "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1",
            "-ss", f"{start:.3f}", "-i", src, "-t", f"{dur:.3f}",
            "-map", "0:v:0?", "-map", "0:a?", "-map_metadata", "0"]
    if precise:
        args += ["-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "192k"]
    else:
        args += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
    args += ["-movflags", "+faststart", out]

    p = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, creationflags=_NO_WINDOW)
    for raw in p.stdout:
        if cancel and cancel():
            p.kill()
            p.wait()
            raise InterruptedError("취소되었습니다.")
        line = raw.decode("utf-8", "replace").strip()
        if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
            try:
                done = int(line.split("=")[1]) / 1_000_000
            except ValueError:
                continue
            if on_progress and total > 0:
                on_progress(min((offset + min(done, dur)) / total, 1.0))
    err = p.stderr.read().decode("utf-8", "replace")
    if p.wait() != 0:
        raise RuntimeError("ffmpeg 오류:\n" + err[-1500:])


def cut(ffmpeg, src, segments, out_path, precise=False, merge=True,
        on_progress=None, cancel=None):
    """
    segments: list of (start, end) seconds.
    merge=True  -> one output file (segments joined in order)
    merge=False -> out_path is a base name; writes name_01.mp4, name_02.mp4 ...
    Returns list of written file paths.
    """
    segs = [(s, e) for s, e in segments if e - s > 0.01]
    if not segs:
        raise ValueError("유효한 구간이 없습니다.")
    total = sum(e - s for s, e in segs)

    if not merge or len(segs) == 1:
        if len(segs) == 1:
            outs = [out_path]
        else:
            root, ext = os.path.splitext(out_path)
            outs = [f"{root}_{i + 1:02d}{ext or '.mp4'}" for i in range(len(segs))]
        offset = 0.0
        for (s, e), o in zip(segs, outs):
            _cut_one(ffmpeg, src, s, e, o, precise, on_progress, offset, total, cancel)
            offset += e - s
        if on_progress:
            on_progress(1.0)
        return outs

    # merge: cut parts into temp dir, then concat with stream copy
    tmp = tempfile.mkdtemp(prefix="mp4cut_")
    try:
        parts, offset = [], 0.0
        for i, (s, e) in enumerate(segs):
            part = os.path.join(tmp, f"part_{i:03d}.mp4")
            _cut_one(ffmpeg, src, s, e, part, precise,
                     (lambda f: on_progress(f * 0.95)) if on_progress else None,
                     offset, total, cancel)
            parts.append(part)
            offset += e - s
        lst = os.path.join(tmp, "list.txt")
        with open(lst, "w", encoding="utf-8") as fh:
            for part in parts:
                fh.write("file '" + part.replace("\\", "/").replace("'", r"'\''") + "'\n")
        r = _run([ffmpeg, "-hide_banner", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                  "-i", lst, "-c", "copy", "-movflags", "+faststart", out_path])
        if r.returncode != 0:
            raise RuntimeError("합치기 실패:\n" + r.stderr.decode("utf-8", "replace")[-1500:])
        if on_progress:
            on_progress(1.0)
        return [out_path]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
