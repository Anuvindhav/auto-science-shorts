import asyncio, json, os, re, subprocess, sys, time
import requests, edge_tts

TITLE = sys.argv[1] if len(sys.argv) > 1 else "Gravity in 30 seconds"
try:
    SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 else 45  # target video length
except ValueError:
    SECONDS = 45
SECONDS = max(20, min(SECONDS, 120))
N_SCENES = max(4, round(SECONDS / 7.5))
WORDS_PER_SCENE = round(SECONDS * 2.3 / N_SCENES)  # narration speaks about 2.3 words/second
VOICE = "en-US-AndrewNeural"  # calm, warm storyteller; change here to switch voice
GEMINI_KEY = os.environ["GEMINI_API_KEY"]
PIXABAY_KEY = os.environ["PIXABAY_API_KEY"]
os.makedirs("work", exist_ok=True)
META = {}  # filled from Gemini: youtube title/description/hashtags, space flag


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def write_script():
    prompt = (
        f'You are writing a narrated YouTube Short that clearly answers this question or topic: "{TITLE}". '
        f'Length: about {SECONDS} seconds, which is exactly {N_SCENES} scenes of about {WORDS_PER_SCENE} words of narration each. '
        'Use a calm, humble storytelling voice, but the content must be educational and concrete: open with a one-line hook, '
        'then give specific, real facts with actual numbers and everyday comparisons that directly answer the topic, '
        'and end with one memorable takeaway. Only state well-established facts, never invent numbers, and avoid vague poetry or filler. '
        'Each scene covers ONE idea and ONE visible subject. For each scene, "search" must be a literal 2-3 word stock footage '
        'query for the main subject named in that scene, for example: sun, planet earth, mars planet, jupiter planet, saturn rings, '
        'neptune planet, solar system planets, voyager spacecraft, milky way galaxy, asteroid belt, comet, nebula, black hole, '
        'astronaut, telescope night sky. Never use rocket launches, nature scenery, animals, water or landscapes unless the topic is about them. '
        'Also set topic_is_space to true only if the topic is about astronomy or space, and write a YouTube title (under 70 characters), '
        'a 2-3 sentence description, and hashtags (include #shorts). '
        'Respond ONLY with JSON in this shape: '
        '{"topic_is_space":true,"youtube":{"title":"...","description":"...","hashtags":"#shorts #science"},'
        '"scenes":[{"narration":"spoken text","search":"2-3 word footage query"}]}'
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
                    META.update(data.get("youtube") or {})
                    META["space"] = bool(data.get("topic_is_space"))
                    data = data.get("scenes") or next(v for v in data.values() if isinstance(v, list))
                scenes = [x for x in data if isinstance(x, dict) and "narration" in x]
                if len(scenes) >= 3:
                    print("Using model:", model)
                    return scenes
                print(model, "gave unusable script, trying next model")
            except Exception as e:
                print(model, "bad response:", e)
    raise SystemExit("No Gemini model could write the script. Wait a few minutes and run again.")


SKIP_TITLES = ("briefing", "interview", "press", "conference", "news", "panel", "hearing", "launch", "talk")


def nasa_clip(query, path):
    """Try the free NASA Image and Video Library. Returns a credit string, or None."""
    try:
        words = [w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 2]
        r = requests.get("https://images-api.nasa.gov/search",
                         params={"q": query, "media_type": "video"}, timeout=60)
        r.raise_for_status()
        for it in r.json()["collection"]["items"][:12]:
            d = it["data"][0]
            title = d.get("title", "")
            text = (title + " " + d.get("description", "") + " " + " ".join(d.get("keywords", []))).lower()
            if any(k in title.lower() for k in SKIP_TITLES):
                continue
            if sum(w in text for w in words) < max(1, len(words) - 1):
                continue
            a = requests.get("https://images-api.nasa.gov/asset/" + d["nasa_id"], timeout=60)
            links = [x["href"].replace("http://", "https://") for x in a.json()["collection"]["items"]
                     if x["href"].endswith(".mp4")]
            for tag in ("~large.mp4", "~medium.mp4", "~small.mp4"):
                url = next((l for l in links if l.endswith(tag)), None)
                if not url:
                    continue
                size = int(requests.head(url, allow_redirects=True, timeout=60).headers.get("content-length", 0))
                if 0 < size <= 80_000_000:
                    with open(path, "wb") as fh:
                        fh.write(requests.get(url, timeout=240).content)
                    return f"NASA Image and Video Library: {title} ({d['nasa_id']})"
    except Exception as e:
        print("NASA lookup failed, using Pixabay:", e)
    return None


def get_clip(query, path):
    if META.get("space"):
        credit = nasa_clip(query, path)
        if credit:
            print("NASA clip for", repr(query), "->", credit)
            return credit
    words = [w for w in query.lower().split() if len(w) > 2]

    def search(q, cat=None):
        p = {"key": PIXABAY_KEY, "q": q, "per_page": 10, "safesearch": "true"}
        if cat:
            p["category"] = cat
        r = requests.get("https://pixabay.com/api/videos/", params=p, timeout=60)
        r.raise_for_status()
        return r.json().get("hits", [])

    hits = search(query, "science") or search(query) or search("space stars", "science") or search("galaxy")
    best = next((h for h in hits if any(w in h.get("tags", "").lower() for w in words)), hits[0])
    print("Pixabay clip for", repr(query), "->", best.get("tags"))
    v = best["videos"]
    url = (v.get("large") or {}).get("url") or v["medium"]["url"]
    with open(path, "wb") as fh:
        fh.write(requests.get(url, timeout=180).content)
    return f"Pixabay: {best.get('tags')} ({best.get('pageURL', 'pixabay.com')})"


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
    parts, credits = [], []
    for i, s in enumerate(scenes):
        base = f"work/s{i}"
        words = await speak(s["narration"], base + ".mp3")
        credits.append(get_clip(s.get("search") or "galaxy stars", base + "_src.mp4"))
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
    with open("metadata.txt", "w", encoding="utf-8") as fh:
        fh.write(f"TITLE:\n{META.get('title') or TITLE}\n\n")
        fh.write(f"DESCRIPTION:\n{META.get('description', '')}\n\n")
        fh.write(f"HASHTAGS:\n{META.get('hashtags') or '#shorts #science'}\n\n")
        fh.write("FOOTAGE CREDITS:\n" + "\n".join("- " + c for c in credits) + "\n")
    print("Done: short.mp4 and metadata.txt")


asyncio.run(main())

