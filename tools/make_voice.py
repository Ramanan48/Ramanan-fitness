#!/usr/bin/env python3
"""
Generates every coach voice clip (English, female) and packs them into
app/src/main/assets/voice.pack + voice.json.

  - Text comes straight from the Cue enum in engine/WorkoutPlan.kt (single source of truth).
  - Each cue gets a name-free clip "<asset>". Named cues also get "<asset>@<name>" clips for
    every name in NAMES, so those names are spoken in the coach's own voice; any other name is
    spoken by the phone's offline text-to-speech at runtime.
  - Voice: Kokoro-82M (Apache-2.0) via kokoro-onnx, 70 % af_heart + 30 % af_nicole.

Usage: python3 tools/make_voice.py <kokoro_dir> [Name ...]     (default names: Ramanan)
"""
import os, re, subprocess, sys, tempfile
import numpy as np, soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COUNTDOWN = {"five", "four", "three", "two", "one"}


def cues():
    src = open(os.path.join(ROOT, "app/src/main/java/com/ramanan/fit/engine/WorkoutPlan.kt")).read()
    out = []
    for m in re.finditer(r'\b[A-Z_]+\("([a-z_]+)", "((?:[^"\\]|\\.)*)"(?:, "((?:[^"\\]|\\.)*)")?\)', src):
        asset, text, plain = m.group(1), m.group(2), m.group(3) or m.group(2)
        out.append((asset, text, plain))
    return out


def key_for(name):
    return "".join(ch for ch in name.lower() if "a" <= ch <= "z")


def encode(a, sr, out, countdown):
    with tempfile.TemporaryDirectory() as td:
        w = os.path.join(td, "a.wav"); sf.write(w, a, sr)
        t = os.path.join(td, "t.wav")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", w, "-af",
                        "silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.02,areverse,"
                        "silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.06,areverse", t], check=True)
        d = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", t]))
        tempo = f",atempo={min(1.6, d / 0.8):.3f}" if countdown and d > 0.8 else ""
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", t, "-af",
                        f"loudnorm=I=-16:TP=-1.5:LRA=7{tempo},aresample=24000", "-ac", "1",
                        "-c:a", "libvorbis", "-q:a", "5", out], check=True)
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out]))


def main():
    kdir = sys.argv[1]; names = sys.argv[2:] or ["Ramanan"]
    from kokoro_onnx import Kokoro
    k = Kokoro(f"{kdir}/kokoro-v1.0.onnx", f"{kdir}/voices-v1.0.bin")
    style = 0.7 * k.get_voice_style("af_heart") + 0.3 * k.get_voice_style("af_nicole")
    with tempfile.TemporaryDirectory() as clips:
        d = clips
        for asset, text, plain in cues():
            jobs = [(asset, plain)]
            if "{name}" in text:
                jobs += [(f"{asset}@{key_for(n)}", text.replace("{name}", n)) for n in names]
            for fname, line in jobs:
                a, sr = k.create(line, voice=style, speed=1.0, lang="en-us")
                dur = encode(np.asarray(a, np.float32), sr, os.path.join(d, f"{fname}.ogg"), asset in COUNTDOWN)
                print(f"{fname:26s} {dur:4.2f}s  {line}")
        subprocess.run([sys.executable, os.path.join(ROOT, "tools/pack_voice.py"), clips], check=True)


if __name__ == "__main__":
    main()
