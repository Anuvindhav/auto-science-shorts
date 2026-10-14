import asyncio, json, os, subprocess, sys
import requests, edge_tts

TITLE = sys.argv[1] if len(sys.argv) > 1 else "Gravity in 30 seconds"
VOICE = "en-US-AndrewNeural"  # calm, warm storyteller; change here to switch voice
GEMINI_KEY = os.environ["GEMINI_API_KEY"]
PEXELS_KEY = os.environ["PEXELS_API_KEY"]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
os.makedirs("work", exist_ok=True)


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def write_script():
    prompt = (
        f'Write a YouTube Short script (about 30 seconds, 5 scenes, 12-16 words of '
        f'narration each) for: "{TITLE}". Calm, humble storytelling tone. Hook first, '
        f'one surprising fact, gentle ending. Respond ONLY with JSON: '
        f'{{"scenes":[{{"narration":"spoken text","caption":"max 6 words",'
        f'"search":"2-3 word stock video search"}}]}}'
    )
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-2.5-flash:generateContent?key={GEMINI_KEY}")
    r = requests.post(url, json={
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }, timeout=90)
    r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)["scenes"]


def get_clip(query, path):
    r = requests.get("https://api.pexels.com/videos/search",
                     headers={"Authorization": PEXELS_KEY},
                     params={"query": query, "orientation": "portrait", "per_page": 5},
                     timeout=60)
    r.raise_for_status()
    vids = r.json().get("videos", [])
    if not vids:
        r = requests.get("https://api.pexels.com/videos/search",
                         headers={"Authorization": PEXELS_KEY},
                         params={"query": "space stars", "orientation": "portrait", "per_page": 5},
                         timeout=60)
        vids = r.json()["videos"]
    files = vids[0]["video_files"]
    hd = [f for f in files if f.get("height", 0) >= 1280 and f.get("file_type") == "video/mp4"]
    best = min(hd, key=lambda f: f["height"]) if hd else max(files, key=lambda f: f.get("height", 0))
    with open(path, "wb") as fh:
        fh.write(requests.get(best["link"], timeout=180).content)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


async def main():
    scenes = write_script()
    parts = []
    for i, s in enumerate(scenes):
        base = f"work/s{i}"
        await edge_tts.Communicate(s["narration"], VOICE, rate="-5%").save(base + ".mp3")
        get_clip(s["search"], base + "_src.mp4")
        dur = duration(base + ".mp3") + 0.4
        with open(base + ".txt", "w") as fh:
            fh.write(s["caption"])
        vf = ("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
              f"drawtext=fontfile={FONT}:textfile={base}.txt:fontcolor=white:fontsize=64:"
              "borderw=4:bordercolor=black:x=(w-text_w)/2:y=h*0.72")
        run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", base + "_src.mp4", "-i", base + ".mp3",
             "-t", f"{dur}", "-vf", vf, "-map", "0:v", "-map", "1:a",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             "-r", "30", "-c:a", "aac", "-ar", "44100", base + ".mp4"])
        parts.append(f"file 's{i}.mp4'")
    with open("work/list.txt", "w") as fh:
        fh.write("\n".join(parts))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "work/list.txt",
         "-c", "copy", "short.mp4"])
    print("Done: short.mp4")


asyncio.run(main())
