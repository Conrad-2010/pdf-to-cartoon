"""
PDF → Cartoon Animation with Audio
----------------------------------
Reads a PDF, narrates each page with edge-tts, and renders a
cartoon-style animated video (bouncing mascot, clouds, typewriter text).

Usage:
    python pdf_to_cartoon.py input.pdf output.mp4 [--voice en-US-JennyNeural]
"""

import os, sys, asyncio, math, argparse, tempfile, shutil
import fitz                                  # PyMuPDF
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import AudioFileClip, concatenate_videoclips
from moviepy.video.io.ImageSequenceClip import ImageSequenceClip

W, H, FPS = 1280, 720, 24

# ---------- helpers ----------
def load_font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def extract_pdf_text(pdf_path):
    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        t = page.get_text("text").strip()
        if t:
            pages.append(t)
    if not pages:
        raise ValueError("No extractable text found in PDF (is it scanned images?)")
    return pages

async def tts(text, voice, out_mp3):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(out_mp3)

# ---------- cartoon scene renderer ----------
def draw_cloud(d, x, y, s, color=(255, 255, 255, 220)):
    for dx, dy, r in [(-30, 0, 25), (0, -10, 35), (35, 0, 28), (10, 8, 30)]:
        d.ellipse([x+dx*s-r*s, y+dy*s-r*s, x+dx*s+r*s, y+dy*s+r*s], fill=color)

def draw_mascot(d, cx, cy, scale, t):
    bob = math.sin(t * 2) * 8 * scale
    cy += bob
    # body
    d.ellipse([cx-70*scale, cy-10*scale, cx+70*scale, cy+110*scale], fill=(255, 183, 77))
    # head
    d.ellipse([cx-60*scale, cy-90*scale, cx+60*scale, cy+30*scale], fill=(255, 213, 128))
    # eyes
    for ex in (-25, 25):
        d.ellipse([cx+ex*scale-10*scale, cy-60*scale, cx+ex*scale+10*scale, cy-40*scale],
                  fill=(30, 30, 30))
        d.ellipse([cx+ex*scale-3*scale, cy-58*scale, cx+ex*scale+5*scale, cy-50*scale],
                  fill=(255, 255, 255))
    # smile
    d.arc([cx-30*scale, cy-40*scale, cx+30*scale, cy+10*scale], 20, 160, fill=(120, 60, 0), width=4)
    # arms
    arm_a = math.sin(t * 4) * 20
    d.line([cx-60*scale, cy+20*scale, cx-110*scale, cy+20*scale-arm_a], fill=(255,183,77), width=int(14*scale))
    d.line([cx+60*scale, cy+20*scale, cx+110*scale, cy+20*scale+arm_a], fill=(255,183,77), width=int(14*scale))

def render_scene(text, audio_path, scene_dir, voice_duration):
    """Render one cartoon scene; returns path to silent mp4."""
    os.makedirs(scene_dir, exist_ok=True)
    total_frames = int(voice_duration * FPS)
    font_big = load_font(54)
    font_small = load_font(36)

    # wrap text
    wrapped = textwrap.wrap(text, width=48)
    max_chars = int(voice_duration * 14)   # rough typing speed
    reveal_text = " ".join(wrapped)[:max_chars]

    frames = []
    for i in range(total_frames):
        t = i / FPS
        img = Image.new("RGBA", (W, H), (135, 206, 235, 255))     # sky blue
        d = ImageDraw.Draw(img)

        # sun
        d.ellipse([W-180, 60, W-80, 160], fill=(255, 223, 0))
        # hills
        d.ellipse([-200, H-260, 500, H+100], fill=(124, 202, 35))
        d.ellipse([W-500, H-260, W+300, H+100], fill=(102, 187, 30))
        # clouds drifting
        for k, (cx, cy, s) in enumerate([(200, 120, 1.2), (700, 90, 0.9), (1050, 160, 1.0)]):
            drift = (t * 20 + k * 100) % (W + 200) - 100
            draw_cloud(d, drift, cy, s)
        # mascot
        draw_mascot(d, 200, H - 260, 1.1, t)
        # typewriter text
        shown = reveal_text[: int(len(reveal_text) * min(1.0, (i+1)/max(1,total_frames*0.7)))]
        lines = textwrap.wrap(shown, width=48) or [""]
        y = 180
        for line in lines:
            w = d.textlength(line, font=font_big)
            d.text(((W-w)/2 + 3, y+3), line, font=font_big, fill=(0,0,0,120))
            d.text(((W-w)/2, y), line, font=font_big, fill=(40, 40, 90))
            y += 70

        frames.append(img.convert("RGB"))

    # save frames
    frame_paths = []
    for i, fr in enumerate(frames):
        p = os.path.join(scene_dir, f"f{i:05d}.png")
        fr.save(p)
        frame_paths.append(p)

    clip = ImageSequenceClip(frame_paths, fps=FPS)
    clip = clip.set_audio(AudioFileClip(audio_path))
    return clip

import textwrap  # (used above)

# ---------- main ----------
async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("output", nargs="?", default="cartoon.mp4")
    ap.add_argument("--voice", default="en-US-JennyNeural")
    args = ap.parse_args()

    pages = extract_pdf_text(args.pdf)
    print(f"📖 Extracted {len(pages)} pages from {args.pdf}")

    work = tempfile.mkdtemp()
    clips = []
    for i, page_text in enumerate(pages):
        print(f"🎬 Scene {i+1}/{len(pages)} ...")
        mp3 = os.path.join(work, f"s{i}.mp3")
        await tts(page_text, args.voice, mp3)
        dur = AudioFileClip(mp3).duration
        clip = render_scene(page_text, mp3, os.path.join(work, f"frames{i}"), dur)
        clips.append(clip)

    print("🔗 Stitching video...")
    final = concatenate_videoclips(clips, method="compose")
    final.write_videofile(args.output, fps=FPS, codec="libx264", audio_codec="aac")
    shutil.rmtree(work, ignore_errors=True)
    print(f"✅ Done → {args.output}")

if __name__ == "__main__":
    asyncio.run(main())
