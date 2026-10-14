import asyncio, json, os, random, re, subprocess, sys, time, urllib.parse
import requests, edge_tts

TITLE = sys.argv[1] if len(sys.argv) > 1 else "Gravity in 30 seconds"
try:
    SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 else 45
except ValueError:
    SECONDS = 45
SECONDS = max(20, min(SECONDS, 120))
N_SCENES = max(4, round(SECONDS / 7.5))
WORDS_PER_SCENE = round(SECONDS * 2.3 / N_SCENES)
VOICE = "en-US-AndrewNeural"
GEMINI_KEY = os.environ["GEMINI_API_KEY"]
PIXABAY_KEY = os.environ["PIXABAY_API_KEY"]
os.makedirs("work", exist_ok=True)
META = {}

HTTPS = "https://"
HTTP = "http://"


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def write_script():
    prompt = (
        f'You are writing a narrated YouTube Short that clearly answers this question or topic: "{TITLE}". '
        f'Length: about {SECONDS} seconds, which is exactly {N_SCENES} scenes of about {WORDS_PER_SCENE} words of narration each. '
        'Use a calm, humble storytelling voice, but the content must be educational and concrete: open with a one-line hook, '
        'then give specific, real facts with actual numbers and everyday comparisons that directly answer the topic, '
        'and end with one memorable takeaway. Only state well-established facts, never invent numbers, and avoid vague poetry or filler. '
        'Each scene covers ONE core idea from the narration. For each scene, provide TWO visual fields:\n'
        '1. "search": a simple 2-word stock video query if it is a physical celestial body (e.g. "planet earth", "sun solar", "saturn rings", "moon orbit"). If it is an abstract concept, write "none".\n'
        '2. "image_prompt": a vivid, cinematic 15-20 word description that *literally illustrates what the narration in this exact scene is saying* '
        '(e.g., if narration mentions a bowling ball on a trampoline, describe a heavy glowing sphere warping a cosmic grid; '
        'if it mentions a hammer and feather falling, describe a silver hammer and white feather dropping on the lunar surface). '
        'Style: photorealistic 8K astronomy documentary, dramatic lighting, professional vertical 9:16, no text, no humans.\n'
        'Also set topic_is_space to true only if the topic is about astronomy or space, and write a YouTube title (under 70 characters), '
        'a 2-3 sentence description, and hashtags (include #shorts). '
        'Respond ONLY with JSON in this shape: '
        '{"topic_is_space":true,"youtube":{"title":"...","description":"...","hashtags":"#shorts #science"},'
        '"scenes":[{"narration":"spoken text","search":"2-word query or none","image_prompt":"exact visual illustration"}]}'
    )
    api_host = "generativelanguage.googleapis.com"
    base = HTTPS + api_host + "/v1beta/"
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
            if r.status_code in (500, 503):
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


SKIP_PIXABAY_TAGS = (
    "people", "person", "man", "woman", "child", "kids", "girl", "boy", "farmer",
    "forest", "trees", "woods", "grass", "field", "meadow", "hiking", "office", "business", "beach", "ocean"
)
UA = {"User-Agent": "auto-science-shorts/1.0 (github actions)"}


def query_words(q):
    return [w for w in re.findall(r"[a-z]+", q.lower()) if len(w) > 2]


def cand(uid, kind, resolve):
    return {"uid": uid, "kind": kind, "resolve": resolve}


def ai_image_cands(prompt_text, scene_no):
    clean_prompt = (
        f"{prompt_text}, ultra-realistic 8K space astronomy documentary cinematography, "
        "epic scale, deep cosmos, volumetric lighting, vertical 9:16 aspect ratio, sharp focus, no text, no watermark"
    )
    encoded = urllib.parse.quote(clean_prompt)
    seed = random.randint(1000, 999999) + scene_no
    poll_host = "image.pollinations.ai"
    url = HTTPS + poll_host + f"/prompt/{encoded}?width=1080&height=1920&seed={seed}&nologo=true"
    return [cand(f"ai:{seed}", "image", lambda: (url, f"AI Scene Illustration: {prompt_text[:50]}"))]


def pixabay_video_cands(query):
    words = query_words(query)
    if not words:
        return []

    def search(q):
        px_host = "pixabay.com"
        p = {"key": PIXABAY_KEY, "q": q, "per_page": 20, "safesearch": "true"}
        r = requests.get(HTTPS + px_host + "/api/videos/", params=p, timeout=60)
        r.raise_for_status()
        return r.json().get("hits", [])

    try:
        hits = search(query)
    except Exception:
        return []

    out = []
    for h in hits:
        tags_lower = h.get("tags", "").lower()
        if any(bad in tags_lower for bad in SKIP_PIXABAY_TAGS):
            continue
        def resolve(h=h):
            v = h["videos"]
            url = (v.get("large") or {}).get("url") or v["medium"]["url"]
            return url, f"Pixabay video: {h.get('tags')} ({h.get('pageURL', 'pixabay.com')})"
        out.append(cand(f"pxv:{h['id']}", "video", resolve))
    return out


def get_media(scene, base, used, scene_no):
    query = (scene.get("search") or "none").lower().strip()
    img_prompt = scene.get("image_prompt") or scene.get("narration")

    # 1. If search is a valid physical body, try to get a matching stock video first
    if query != "none" and len(query) > 2:
        try:
            cands = [c for c in pixabay_video_cands(query) if c["uid"] not in used][:5]
            if cands:
                random.shuffle(cands)
                url, credit = cands[0]["resolve"]()
                path = base + "_src.mp4"
                with open(path, "wb") as fh:
                    fh.write(requests.get(url, timeout=240, headers=UA).content)
                used.add(cands[0]["uid"])
                print(f"Scene {scene_no + 1} [video match] {query!r} -> {credit}")
                return "video", path, credit
        except Exception as e:
            print("Video match fallback:", e)

    # 2. For conceptual audio lines, generate an exact custom AI illustration matching the narration
    try:
        c = ai_image_cands(img_prompt, scene_no)[0]
        url, credit = c["resolve"]()
        resp = requests.get(url, timeout=90, headers=UA)
        if resp.ok and len(resp.content) > 15000:
            path = base + "_src.jpg"
            with open(path, "wb") as fh:
                fh.write(resp.content)
            used.add(c["uid"])
            print(f"Scene {scene_no + 1} [concept ai-art] {img_prompt!r} -> {credit}")
            return "image", path, credit
    except Exception as e:
        print("AI illustration failed:", e)

    # 3. Ultimate fallback to general space video
    for fallback in ("deep space", "galaxy stars", "nebula cosmos"):
        try:
            cands = [c for c in pixabay_video_cands(fallback) if c["uid"] not in used][:5]
            if cands:
                random.shuffle(cands)
                url, credit = cands[0]["resolve"]()
                path = base + "_src.mp4"
                with open(path, "wb") as fh:
                    fh.write(requests.get(url, timeout=240, headers=UA).content)
                used.add(cands[0]["uid"])
                return "video", path, credit
        except Exception:
            continue

    # Final backup AI image
    c = ai_image_cands(img_prompt, scene_no)[0]
    url, credit = c["resolve"]()
    path = base + "_src.jpg"
    with open(path, "wb") as fh:
        fh.write(requests.get(url, timeout=120, headers=UA).content)
    used.add(c["uid"])
    return "image", path, credit


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


async def speak(text, mp3_path):
    try:
        comm = edge_tts.Communicate(text, VOICE, rate="-5%", boundary="WordBoundary")
    except TypeError:
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
    ws = text.split()
    step = total / max(len(ws), 1)
    return [(i * step, (i + 1) * step, w) for i, w in enumerate(ws)]


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def write_srt(words, total, path):
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


STYLE = ("FontName=DejaVu Sans,Bold=1,FontSize=13,PrimaryColour=&H00FFFFFF,"
         "OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,"
         "MarginV=95,MarginL=30,MarginR=30")


def scene_filter(kind, base):
    if kind == "image":
        layout = (
            "[0:v]scale=2160:3840:force_original_aspect_ratio=increase,crop=2160:3840,"
            "zoompan=z='min(1.0+0.0005*on,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            "d=1:s=1080x1920:fps=30"
        )
    else:
        layout = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    return layout + f",subtitles={base}.srt:force_style='{STYLE}'[v]"


async def main():
    scenes = write_script()
    parts, credits, used = [], [], set()
    for i, s in enumerate(scenes):
        base = f"work/s{i}"
        words = await speak(s["narration"], base + ".mp3")
        kind, src, credit = get_media(s, base, used, i)
        credits.append(credit)
        audio_len = duration(base + ".mp3")
        dur = audio_len + 0.4
        write_srt(words or even_words(s["narration"], audio_len), dur, base + ".srt")
        vf = scene_filter(kind, base)
        inp = (["-loop", "1", "-framerate", "30", "-i", src] if kind == "image"
               else ["-stream_loop", "-1", "-i", src])
        run(["ffmpeg", "-y"] + inp + ["-i", base + ".mp3",
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
