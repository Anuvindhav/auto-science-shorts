import asyncio, json, os, random, re, subprocess, sys, time
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
        'Each scene covers ONE idea and ONE visible subject. For each scene, "search" must be a literal 2-3 word stock footage '
        'query for the main visual subject in that scene, for example: sun, planet earth, mars planet, jupiter planet, saturn rings, '
        'neptune planet, solar system planets, spacecraft animation, milky way galaxy, asteroid belt, comet, nebula, black hole, '
        'astronaut spacewalk, night sky stars. Avoid searching mission names alone (like "voyager", "lro", or "soho") or terms that match office meetings; '
        'instead use visual equivalents like "moon surface", "spacecraft deep space", or "icy asteroids". '
        'Never use rocket launches, nature scenery, animals, water or landscapes unless the topic is about them. '
        'Also set topic_is_space to true only if the topic is about astronomy or space, and write a YouTube title (under 70 characters), '
        'a 2-3 sentence description, and hashtags (include #shorts). '
        'Respond ONLY with JSON in this shape: '
        '{"topic_is_space":true,"youtube":{"title":"...","description":"...","hashtags":"#shorts #science"},'
        '"scenes":[{"narration":"spoken text","search":"2-3 word footage query"}]}'
    )
    base = HTTPS + "generativelanguage.googleapis.com/v1beta/"
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


SKIP_TITLES = (
    "briefing", "interview", "press", "conference", "news", "panel", "hearing", "launch", "talk",
    "meeting", "anniversary", "retrospective", "what's up", "whats up", "this month", "promo", "trailer",
    "comparison", "side-by-side", "three-panel", "triptych"
)
SKIP_DESC = (
    "conference room", "control room", "press briefing", "panel discussion", "seated around",
    "at a table", "staff", "personnel", "ceremony", "lecture", "symposium",
    "three-panel", "three panel", "side-by-side", "side by side", "comparison of", "left to right"
)
UA = {"User-Agent": "auto-science-shorts/1.0 (github actions)"}
IMAGE_EVERY = 3
GOOD_LICENSES = ("public domain", "cc0", "cc by", "cc by-sa", "pd")


def query_words(q):
    return [w for w in re.findall(r"[a-z]+", q.lower()) if len(w) > 2]


def file_size(url):
    h = requests.head(url, allow_redirects=True, timeout=60, headers=UA).headers
    return int(h.get("content-length", 0))


def cand(uid, kind, resolve):
    return {"uid": uid, "kind": kind, "resolve": resolve}


def nasa_cands(query, media):
    r = requests.get(HTTPS + "images-api.nasa.gov/search",
                     params={"q": query, "media_type": media}, timeout=60)
    r.raise_for_status()
    words, out = query_words(query), []
    for it in r.json()["collection"]["items"][:25]:
        d = it["data"][0]
        title = d.get("title", "")
        text = (title + " " + d.get("description", "") + " " + " ".join(d.get("keywords", []))).lower()
        if any(k in title.lower() for k in SKIP_TITLES):
            continue
        if any(k in text for k in SKIP_DESC):
            continue
        if sum(w in text for w in words) < max(1, len(words) - 1):
            continue

        def resolve(d=d, title=title):
            a = requests.get(HTTPS + "images-api.nasa.gov/asset/" + d["nasa_id"], timeout=60)
            links = [x["href"].replace(HTTP, HTTPS) for x in a.json()["collection"]["items"]]
            prefs = (("~large.mp4", 80e6), ("~medium.mp4", 80e6), ("~small.mp4", 80e6)) if media == "video" \
                else (("~orig.jpg", 25e6), ("~large.jpg", 25e6), ("~medium.jpg", 25e6))
            for tag, cap in prefs:
                url = next((l for l in links if l.endswith(tag)), None)
                if url and 0 < file_size(url) <= cap:
                    return url, f"NASA Image and Video Library: {title} ({d['nasa_id']})"
            raise RuntimeError("no usable NASA file")
        out.append(cand("nasa:" + d["nasa_id"], media, resolve))
    return out


def pixabay_video_cands(query):
    words = query_words(query)

    def search(q, cat=None):
        p = {"key": PIXABAY_KEY, "q": q, "per_page": 15, "safesearch": "true"}
        if cat:
            p["category"] = cat
        r = requests.get(HTTPS + "[pixabay.com/api/videos/](https://pixabay.com/api/videos/)", params=p, timeout=60)
        r.raise_for_status()
        return r.json().get("hits", [])

    hits = search(query, "science") or search(query)
    hits.sort(key=lambda h: -sum(w in h.get("tags", "").lower() for w in words))
    out = []
    for h in hits:
        if sum(w in h.get("tags", "").lower() for w in words) == 0:
            continue

        def resolve(h=h):
            v = h["videos"]
            url = (v.get("large") or {}).get("url") or v["medium"]["url"]
            return url, f"Pixabay video: {h.get('tags')} ({h.get('pageURL', 'pixabay.com')})"
        out.append(cand(f"pxv:{h['id']}", "video", resolve))
    return out


def pixabay_image_cands(query):
    r = requests.get(HTTPS + "[pixabay.com/api/](https://pixabay.com/api/)",
                     params={"key": PIXABAY_KEY, "q": query, "image_type": "photo", "per_page": 15,
                             "safesearch": "true", "min_width": 1200}, timeout=60)
    r.raise_for_status()
    words, out = query_words(query), []
    for h in r.json().get("hits", []):
        if sum(w in h.get("tags", "").lower() for w in words) == 0:
            continue
        out.append(cand(f"pxi:{h['id']}", "image", lambda h=h: (
            h["largeImageURL"], f"Pixabay image: {h.get('tags')} ({h.get('pageURL', 'pixabay.com')})")))
    return out


def wikimedia_cands(query):
    r = requests.get(HTTPS + "commons.wikimedia.org/w/api.php", headers=UA, timeout=60, params={
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": query + " filetype:bitmap", "gsrlimit": 15, "prop": "imageinfo",
        "iiprop": "url|size|extmetadata", "iiurlwidth": 2000})
    r.raise_for_status()
    out = []
    for p in (r.json().get("query", {}).get("pages", {}) or {}).values():
        info = (p.get("imageinfo") or [{}])[0]
        lic = info.get("extmetadata", {}).get("LicenseShortName", {}).get("value", "").lower()
        if info.get("width", 0) < 1400 or not info.get("thumburl"):
            continue
        if not any(lic.startswith(g) for g in GOOD_LICENSES):
            continue
        who = re.sub(r"<[^>]+>", "", info.get("extmetadata", {}).get("Artist", {}).get("value", "unknown"))
        out.append(cand("wm:" + p["title"], "image", lambda p=p, info=info, lic=lic, who=who: (
            info["thumburl"], f"Wikimedia Commons: {p['title']} by {who} ({lic.upper()}) {info.get('descriptionurl', '')}")))
    return out


def get_media(query, base, used, scene_no):
    space = META.get("space")
    videos = ([lambda q: nasa_cands(q, "video")] if space else []) + [pixabay_video_cands]
    images = ([lambda q: nasa_cands(q, "image")] if space else []) + [wikimedia_cands, pixabay_image_cands]
    order = (images + videos) if scene_no % IMAGE_EVERY == IMAGE_EVERY - 1 else (videos + images)
    for fallback_query in (query, " ".join(query_words(query)[-2:]), "space stars" if space else "science physics"):
        for source in order:
            try:
                cands = [c for c in source(fallback_query) if c["uid"] not in used][:6]
            except Exception as e:
                print("source failed:", e)
                continue
            random.shuffle(cands)
            for c in cands:
                try:
                    url, credit = c["resolve"]()
                    ext = ".png" if url.lower().split("?")[0].endswith(".png") else (".jpg" if c["kind"] == "image" else ".mp4")
                    path = base + "_src" + ext
                    with open(path, "wb") as fh:
                        fh.write(requests.get(url, timeout=240, headers=UA).content)
                    used.add(c["uid"])
                    print(f"Scene {scene_no + 1} [{c['kind']}] {query!r} -> {credit}")
                    return c["kind"], path, credit
                except Exception as e:
                    print("candidate failed:", e)
    raise SystemExit(f"Could not find footage for: {query}")


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


STYLE = ("FontName=DejaVu Sans,Bold=1,FontSize=10,PrimaryColour=&H00FFFFFF,"
         "OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=0,Alignment=2,"
         "MarginV=70,MarginL=30,MarginR=30")


def scene_filter(kind, base):
    layout = ("[0:v]split[a][b];"
              "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25[bg];"
              "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")
    if kind == "image":
        layout += (",scale=2160:3840,zoompan=z='min(1.0+0.00045*on,1.18)':"
                   "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30")
    return layout + f",subtitles={base}.srt:force_style='{STYLE}'[v]"


async def main():
    scenes = write_script()
    parts, credits, used = [], [], set()
    for i, s in enumerate(scenes):
        base = f"work/s{i}"
        words = await speak(s["narration"], base + ".mp3")
        kind, src, credit = get_media(s.get("search") or "galaxy stars", base, used, i)
        credits.append(credit)
        audio_len = duration(base + ".mp3")
        dur = audio_len + 0.4
        write_srt(words or even_words(s["narration"], audio_len), dur, base + ".srt")
        vf = scene_filter(kind, base)
        if kind == "image":
            inp = ["-loop", "1", "-framerate", "30", "-i", src]
        else:
            # If the video is long (like a NASA featurette), skip the first 6s to bypass intro title cards
            vid_len = duration(src)
            skip = ["-ss", "6"] if vid_len > dur + 8 else []
            inp = ["-stream_loop", "-1"] + skip + ["-i", src]
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
