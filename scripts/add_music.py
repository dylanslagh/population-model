"""Lay a music track under the finished race video.

Writes a new file and never touches the silent master, so the render and the
audio choice stay independent — swapping the music does not mean re-rendering
three thousand frames.

The video stream is copied, not re-encoded. Re-encoding H.264 to add an audio
track would throw away quality for no reason, and it is the kind of loss that
does not show up until the upload has already been transcoded a second time.

    python scripts/add_music.py --music "~/Downloads/Cocktail Lounge - Dyalla.mp3"
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402

FADE_IN = 1.0
FADE_OUT = 4.0  # matches the closing hold, so the music settles as 2100 lands

# YouTube normalises loudness to about -14 LUFS. Handing it something already
# there means it plays at the level it was mixed at rather than being turned
# down by an amount nobody chose.
TARGET_LUFS = -14.0


def tool(name: str, override: Path | None = None) -> str:
    """Locate ffmpeg or ffprobe: explicit path, then $FFMPEG, then PATH."""
    if override:
        return str(override)
    env = os.environ.get("FFMPEG")
    if env:
        candidate = Path(env).parent / f"{name}{Path(env).suffix}"
        if candidate.exists():
            return str(candidate)
    found = shutil.which(name)
    if not found:
        raise SystemExit(
            f"no {name}. Pass --ffmpeg, set $FFMPEG, or put it on PATH. "
            "LOCAL_TOOLS.md records where the portable build lives."
        )
    return found


def duration(ffprobe: str, path: Path) -> float:
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--music", type=Path, required=True)
    parser.add_argument("--video", type=Path,
                        default=paths.OUT / "race-1950-2100.mp4")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--ffmpeg", type=Path)
    args = parser.parse_args()

    music = Path(os.path.expanduser(str(args.music)))
    if not music.exists():
        raise SystemExit(f"no music file at {music}")
    if not args.video.exists():
        raise SystemExit(f"no video at {args.video}; render it first")

    ffmpeg = tool("ffmpeg", args.ffmpeg)
    ffprobe = tool("ffprobe", args.ffmpeg.parent / "ffprobe.exe" if args.ffmpeg
                   else None)

    video_len = duration(ffprobe, args.video)
    music_len = duration(ffprobe, music)
    # Fail rather than let -shortest quietly cut the *video* off at the end of a
    # track that turned out to be too short. Silence under the last ten seconds
    # would be a choice; a truncated ending is a bug.
    if music_len < video_len - 0.05:
        raise SystemExit(
            f"the track is {music_len:.1f}s and the video is {video_len:.1f}s. "
            "Pick a longer track, or loop this one deliberately."
        )

    out = args.out or args.video.with_name(args.video.stem + "-music.mp4")
    fade_out_at = max(0.0, video_len - FADE_OUT)
    chain = (
        f"atrim=0:{video_len:.3f},asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d={FADE_IN},"
        f"afade=t=out:st={fade_out_at:.3f}:d={FADE_OUT},"
        f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11,"
        f"aresample=48000"
    )
    cmd = [
        ffmpeg, "-y", "-i", str(args.video), "-i", str(music),
        "-filter_complex", f"[1:a]{chain}[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", "-shortest", str(out),
    ]
    print(f"{args.video.name} ({video_len:.1f}s) + {music.name} "
          f"({music_len:.1f}s) -> {out.name}")
    subprocess.run(cmd, check=True)

    final = duration(ffprobe, out)
    if abs(final - video_len) > 0.2:
        raise SystemExit(
            f"{out.name} is {final:.1f}s but the silent video is {video_len:.1f}s"
        )
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB, {final:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
