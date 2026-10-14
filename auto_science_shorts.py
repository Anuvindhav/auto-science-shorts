import asyncio, json, os, subprocess, sys, time
import requests, edge_tts

TITLE = sys.argv[1] if len(sys.argv) > 1 else "Gravity in 30 seconds"
VOICE = "en-US-AndrewNeural"  # calm, warm storyteller; change here to switch voice
GEMINI_KEY = os.environ["GEMINI_API_KEY"]
PIXABAY_KEY = os.environ["PIXABAY_API_KEY"]
os.makedirs("work", exist_ok=True)


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def write_script():
    prompt = (
        f'Write a YouTube Short script (about 30 seconds, 5 scenes, 12-16 words of '
        f'narration each) for: "{TITLE}". Calm, humble storytelling tone. Hook first, '
        f'one surprising fact, gentle ending. For every scene, the search field must be a literal 2-3 word stock footage query showing the science itself, '
        f'for example planet earth space, galaxy stars, black hole, falling apple, astronaut floating, nebula, telescope night sky. '
        f'Always include the main topic. NEVER use nature scenery, animals, water, forests or landscapes. Respond ONLY with JSON: '
        f'{{"scenes":[{{"narration":"spoken text","caption":"max 6 words",'
        f'"search":"literal 2-3 word footage query"}}]}}'
    )
    base = "https://generativelanguage.googleapis.com/v1beta/"
    hdr = {"x-goog-api-key": GEMINI_KEY}
    ml = requests.get(base + "models?pageSize=200", headers=hdr, timeout=60)
    ml.raise_for_status()
    names = [m["name"].split("/")[-1] for m in ml.json().get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    bad = ("image", "tts", "live", "audio", "embed", "robotics", "computer", "customtools")
    flash = sorted((n for n in names if "flash" in n and not any(b in n for b in bad)), reverse=True)
    order = [n for n in ("gemini-flash-latest", "gemini-2.5-flash") if n in names]
    candidates = (order + flash)[:5]
    print("Models to try:", candidates)
    r = None
    for model in candidates:
        for attempt in range(3):
            r = requests.post(base + f"models/{model}:generateContent", headers=hdr, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            }, timeout=90)
            if r.ok:
                break
            print(model, "failed:", r.status_code, r.text[:120].replace("\n", " "))
            if r.status_code in (500, 503):  # busy: wait and retry the same model
                time.sleep(10 * (attempt + 1))
                continue
            break
        if r.ok:
            try:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
                data = json.loads(text)
                if isinstance(data, dict):
                    data = data.get("scenes") or next(v for v in data.values() if isinstance(v, list))
                scenes = [x for x in data if isinstance(x, dict) and "narration" in x]
                if len(scenes) >= 3:
                    print("Using model:", model)
                    return scenes
                print(model, "gave unusable script, trying next model")
            except Exception as e:
                print(model, "bad response:", e)
    raise SystemExit("No Gemini model could write the script. Wait a few minutes and run again.")


def get_clip(query, path):
    words = [w for w in query.lower().split() if len(w) > 2]

    def search(q, cat=None):
        p = {"key": PIXABAY_KEY, "q": q, "per_page": 10, "safesearch": "true"}
        if cat:
            p["category"] = cat
        r = requests.get("https://pixabay.com/api/videos/", params=p, timeout=60)
        r.raise_for_status()
        return r.json().get("hits", [])

    hits = search(query, "science") or search(query) or search("space stars", "science") or search("galaxy")
    # prefer a clip whose tags actually mention the search words
    best = next((h for h in hits if any(w in h.get("tags", "").lower() for w in words)), hits[0])
    print("Clip for", repr(query), "->", best.get("tags"))
    v = best["videos"]
    url = (v.get("large") or {}).get("url") or v["medium"]["url"]
    with open(path, "wb") as fh:
        fh.write(requests.get(url, timeout=180).content)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


async def speak(text, mp3_path):
    """Save narration audio and return word timings [(start, end, word), ...] in seconds."""
    try:
        comm = edge_tts.Communicate(text, VOICE, rate="-5%", boundary="WordBoundary")
    except TypeError:  # older edge-tts versions
        comm = edge_tts.Communicate(text, VOICE, rate="-5%")
    audio, words = bytearray(), []
    async for ch in comm.stream():
        if ch["type"] == "audio":
            audio += ch["data"]
        elif ch["type"] == "WordBoundary":
            st = ch["offset"] / 1e7
            words.append((st, st + ch["duration"] / 1e7, ch["text"]))
    with open(mp3_path, "wb") as fh:
        fh.write(audio)
    return words


def even_words(text, total):
    """Fallback: spread the words evenly across the audio length."""
    ws = text.split()
    step = total / max(len(ws), 1)
    return [(i * step, (i + 1) * step, w) for i, w in enumerate(ws)]


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def write_srt(words, total, path):
    """Group the spoken words into short 3-4 word captions that appear as they are said."""
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= 4 or w[2].endswith((",", ".", "!", "?", ";", ":")):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    with open(path, "w", encoding="utf-8") as fh:
        for i, c in enumerate(chunks, 1):
            start = c[0][0]
            end = chunks[i][0][0] if i < len(chunks) else min(total, c[-1][1] + 0.3)
            fh.write(f"{i}\n{srt_time(start)} --> {srt_time(end)}\n{' '.join(x[2] for x in c)}\n\n")


STYLE = ("FontName=DejaVu Sans,Bold=1,FontSize=10,PrimaryColour=&H00FFFFFF,"
         "OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=0,Alignment=2,"
         "MarginV=70,MarginL=30,MarginR=30")


async def main():
    scenes = write_script()
    parts = []
    for i, s in enumerate(scenes):
        base = f"work/s{i}"
        words = await speak(s["narration"], base + ".mp3")
        get_clip(s.get("search") or "galaxy stars", base + "_src.mp4")
        audio_len = duration(base + ".mp3")
        dur = audio_len + 0.4
        write_srt(words or even_words(s["narration"], audio_len), dur, base + ".srt")
        vf = ("[0:v]split[a][b];"
              "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25[bg];"
              "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,"
              f"subtitles={base}.srt:force_style='{STYLE}'[v]")
        run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", base + "_src.mp4", "-i", base + ".mp3",
             "-t", f"{dur}", "-filter_complex", vf, "-map", "[v]", "-map", "1:a",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             "-r", "30", "-c:a", "aac", "-ar", "44100", base + ".mp4"])
        parts.append(f"file 's{i}.mp4'")
    with open("work/list.txt", "w") as fh:
        fh.write("\n".join(parts))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "work/list.txt",
         "-c", "copy", "short.mp4"])
    print("Done: short.mp4")


asyncio.run(main())
