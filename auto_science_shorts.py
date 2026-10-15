import asyncio, base64, json, os, random, re, subprocess, sys, time, urllib.parse
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
SHOTS_PER_SCENE = 2  # the picture changes this many times inside each scene
GEMINI_IMG = {"ok": True, "models": None}

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
        'Each scene covers ONE core idea. For each scene give THREE visual fields, so the picture changes every few seconds '
        'and shows exactly what is being said:\n'
        '1. "search": a simple 2-word stock video query ONLY if the scene is about a real celestial body (for example "planet earth", '
        '"saturn rings", "moon orbit", "sun solar"); otherwise "none".\n'
        '2. "image_prompt": one concrete, simple, photographable subject for the first picture, 12-18 words, for example '
        '"The Moon orbiting Earth seen from space, Earth large in the foreground, NASA photograph style". '
        'Describe real objects and real scenes, never abstract swirls, glows or metaphors.\n'
        '3. "image_prompt_2": a different second picture for the same scene (different subject or camera angle), same rules.\n'
        'All pictures: photorealistic space documentary look, no text, no people.\n'
        'Also set topic_is_space to true only if the topic is about astronomy or space, and write a YouTube title (under 70 characters), '
        'a 2-3 sentence description, and hashtags (include #shorts). '
        'Respond ONLY with JSON in this shape: '
        '{"topic_is_space":true,"youtube":{"title":"...","description":"...","hashtags":"#shorts #science"},'
        '"scenes":[{"narration":"spoken text","search":"2-word query or none","image_prompt":"first picture","image_prompt_2":"second picture"}]}'
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


def is_image(data):
    return len(data) > 15000 and (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n")


def img_ext(data):
    return ".png" if data[:4] == b"\x89PNG" else ".jpg"


def gemini_image(prompt_text, path_base):
    """Try Gemini's own image model with the same key. Returns (path, credit) or None."""
    if not GEMINI_IMG["ok"]:
        return None
    base = HTTPS + "generativelanguage.googleapis.com" + "/v1beta/"
    hdr = {"x-goog-api-key": GEMINI_KEY}
    try:
        if GEMINI_IMG["models"] is None:
            ml = requests.get(base + "models?pageSize=200", headers=hdr, timeout=60).json().get("models", [])
            GEMINI_IMG["models"] = sorted((m["name"].split("/")[-1] for m in ml
                                           if "image" in m["name"] and "imagen" not in m["name"]
                                           and "generateContent" in m.get("supportedGenerationMethods", [])), reverse=True)[:2]
            print("Gemini image models:", GEMINI_IMG["models"])
        text = (prompt_text + ". Photorealistic space documentary photograph, vertical 9:16 composition, "
                "sharp detail, natural lighting, no text, no watermark, no people.")
        for model in GEMINI_IMG["models"]:
            for modalities in (["IMAGE"], ["TEXT", "IMAGE"]):
                r = requests.post(base + f"models/{model}:generateContent", headers=hdr, timeout=120, json={
                    "contents": [{"parts": [{"text": text}]}],
                    "generationConfig": {"responseModalities": modalities}})
                if r.status_code in (403, 429):
                    print("Gemini image not available on this key:", r.status_code)
                    GEMINI_IMG["ok"] = False
                    return None
                if not r.ok:
                    continue
                for part in r.json()["candidates"][0]["content"].get("parts", []):
                    blob = part.get("inlineData") or part.get("inline_data")
                    if blob:
                        data = base64.b64decode(blob["data"])
                        if is_image(data):
                            path = path_base + img_ext(data)
                            with open(path, "wb") as fh:
                                fh.write(data)
                            return path, f"AI illustration (Gemini): {prompt_text[:60]}"
    except Exception as e:
        print("Gemini image failed:", e)
    return None


def pollinations_image(prompt_text, scene_no, path_base):
    clean_prompt = (
        f"{prompt_text}, photorealistic space documentary photograph, sharp focus, natural lighting, "
        "vertical composition, no text, no watermark, no people"
    )
    encoded = urllib.parse.quote(clean_prompt)
    poll_host = "image.pollinations.ai"
    for attempt in range(3):
        seed = random.randint(1000, 999999) + scene_no
        url = HTTPS + poll_host + f"/prompt/{encoded}?width=1080&height=1920&seed={seed}&model=flux&nologo=true"
        try:
            resp = requests.get(url, timeout=120, headers=UA)
            if resp.ok and is_image(resp.content):
                path = path_base + img_ext(resp.content)
                with open(path, "wb") as fh:
                    fh.write(resp.content)
                return path, f"AI illustration (Pollinations): {prompt_text[:60]}"
            print("Pollinations try", attempt + 1, "not usable:", resp.status_code)
        except Exception as e:
            print("Pollinations try", attempt + 1, "failed:", e)
        time.sleep(5 * (attempt + 1))
    return None


def make_ai_image(prompt_text, scene_no, path_base):
    """Returns (path, credit, has_watermark) or None."""
    got = gemini_image(prompt_text, path_base)
    if got:
        return got[0], got[1], False
    got = pollinations_image(prompt_text, scene_no, path_base)
    if got:
        return got[0], got[1], True  # Pollinations puts a small logo at the bottom; it gets cropped out
    return None


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


def download_video(cands, used, path):
    random.shuffle(cands)
    for c in cands[:5]:
        try:
            url, credit = c["resolve"]()
            with open(path, "wb") as fh:
                fh.write(requests.get(url, timeout=240, headers=UA).content)
            used.add(c["uid"])
            return credit
        except Exception as e:
            print("video download failed:", e)
    return None


def get_shot(shot_no, search, img_prompt, base, used, scene_no):
    """One picture or clip for part of a scene. Returns (kind, path, credit, has_watermark)."""
    path_base = f"{base}_shot{shot_no}_src"
    query = (search or "none").lower().strip()
    if shot_no == 0 and query != "none" and len(query) > 2:
        credit = download_video([c for c in pixabay_video_cands(query) if c["uid"] not in used],
                                used, path_base + ".mp4")
        if credit:
            print(f"Scene {scene_no + 1}.{shot_no + 1} [video] {query!r}")
            return "video", path_base + ".mp4", credit, False
    got = make_ai_image(img_prompt, scene_no * 10 + shot_no, path_base)
    if got:
        print(f"Scene {scene_no + 1}.{shot_no + 1} [image] {img_prompt!r}")
        return "image", got[0], got[1], got[2]
    for fallback in ("deep space", "galaxy stars", "nebula cosmos"):
        credit = download_video([c for c in pixabay_video_cands(fallback) if c["uid"] not in used],
                                used, path_base + ".mp4")
        if credit:
            return "video", path_base + ".mp4", credit, False
    raise SystemExit(f"Could not find a picture for scene {scene_no + 1}")


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


def probe_size(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True)
    w, h = out.stdout.strip().split(",")[:2]
    return int(w), int(h)


def shot_filter(kind, src, wm, zoom_in):
    if kind == "video":
        return "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[v]"
    w, h = probe_size(src)
    z = "min(1.0+0.0012*on,1.25)" if zoom_in else "max(1.25-0.0012*on,1.0)"
    zoom = f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30[v]"
    pre = "[0:v]crop=iw:trunc(ih*0.93/2)*2:0:0," if wm else "[0:v]"  # cut off a watermark strip if present
    if w / h < 0.62:  # tall picture: fill the screen
        return pre + "scale=2160:3840:force_original_aspect_ratio=increase,crop=2160:3840," + zoom
    return (pre + "split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25[bg];"
            "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,scale=2160:3840," + zoom)


ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30"]


async def main():
    scenes = write_script()
    parts, credits, used = [], [], set()
    for i, s in enumerate(scenes):
        base = f"work/s{i}"
        words = await speak(s["narration"], base + ".mp3")
        audio_len = duration(base + ".mp3")
        dur = audio_len + 0.4
        write_srt(words or even_words(s["narration"], audio_len), dur, base + ".srt")
        prompts = [s.get("image_prompt") or s["narration"],
                   s.get("image_prompt_2") or s.get("image_prompt") or s["narration"]]
        shot_len = dur / SHOTS_PER_SCENE
        lines = []
        for k in range(SHOTS_PER_SCENE):
            kind, src, credit, wm = get_shot(k, s.get("search") if k == 0 else "none", prompts[k], base, used, i)
            credits.append(credit)
            inp = (["-loop", "1", "-framerate", "30", "-i", src] if kind == "image"
                   else ["-stream_loop", "-1", "-i", src])
            out = f"{base}_shot{k}.mp4"
            run(["ffmpeg", "-y"] + inp + ["-t", f"{shot_len:.3f}", "-filter_complex",
                 shot_filter(kind, src, wm, zoom_in=(k % 2 == 0)), "-map", "[v]", "-an"] + ENC + [out])
            lines.append(f"file 's{i}_shot{k}.mp4'")
        with open(f"{base}_shots.txt", "w") as fh:
            fh.write("\n".join(lines))
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", f"{base}_shots.txt", "-c", "copy", f"{base}_v.mp4"])
        run(["ffmpeg", "-y", "-i", f"{base}_v.mp4", "-i", base + ".mp3",
             "-vf", f"subtitles={base}.srt:force_style='{STYLE}'", "-af", "apad", "-t", f"{dur:.3f}",
             "-map", "0:v", "-map", "1:a"] + ENC + ["-c:a", "aac", "-ar", "44100", base + ".mp4"])
        parts.append(f"file 's{i}.mp4'")
    with open("work/list.txt", "w") as fh:
        fh.write("\n".join(parts))
    # re-encode while joining so timestamps are clean and YouTube / iPhone can always read the file
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "work/list.txt",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-profile:v", "high", "-level", "4.1",
         "-pix_fmt", "yuv420p", "-r", "30", "-video_track_timescale", "30000",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         "-movflags", "+faststart", "-map_metadata", "-1", "short.mp4"])
    with open("metadata.txt", "w", encoding="utf-8") as fh:
        fh.write(f"TITLE:\n{META.get('title') or TITLE}\n\n")
        fh.write(f"DESCRIPTION:\n{META.get('description', '')}\n\n")
        fh.write(f"HASHTAGS:\n{META.get('hashtags') or '#shorts #science'}\n\n")
        fh.write("FOOTAGE CREDITS:\n" + "\n".join("- " + c for c in credits) + "\n")
    print("Done: short.mp4 and metadata.txt")


asyncio.run(main())
