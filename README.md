# 🔭 Auto Science Shorts

**Type a topic. Get a ready-to-post, captioned YouTube Short. Free, and it runs entirely from your phone.**

> 🎬 **See a video it made:** [PASTE YOUR BEST SHORT LINK HERE](https://youtube.com)

No video editing. No local setup. No paid subscriptions. You tap **Run workflow**, type something like *"How big is our solar system?"*, and a few minutes later you download a finished 1080x1920 video.

## What it makes

- ✍️ **A fact-focused script** written by Gemini that answers your question, with real numbers and everyday comparisons
- 🎙️ **A calm storytelling voice**, the same one every time (free, no limits)
- 🖼️ **Matching visuals** that change every few seconds, from free stock footage and AI illustrations
- 💬 **Captions timed to the spoken words**
- 📝 **A YouTube title, description and hashtags** in a text file, plus a footage credits list
- ⏱️ **Your choice of length:** 30, 45, 60 or 90 seconds

## How it works

```
Your topic → Gemini writes the script → edge-tts reads it aloud
          → pictures and clips found or generated for every scene
          → ffmpeg adds captions and joins everything → short.mp4
```

Everything runs on free GitHub Actions. You only need two free API keys.

## Quick start (about 10 minutes)

1. **Use this repo as a template:** tap **Use this template** (or **Fork**) at the top of the page.
2. **Get two free keys**
   - Google Gemini: [aistudio.google.com](https://aistudio.google.com), then Get API key
   - Pixabay: sign up at [pixabay.com](https://pixabay.com), then open pixabay.com/api/docs/
3. **Save them as secrets:** Settings → Secrets and variables → Actions → New repository secret
   - `GEMINI_API_KEY`
   - `PIXABAY_API_KEY`
4. **Run it:** Actions → **Make short** → Run workflow → type a topic and pick a length.
5. **Download:** open the newest item under **Releases** and tap `short.mp4`.

Never put keys in the code files. Keep them in secrets only.

## Make it yours

- **Voice:** change `VOICE` near the top of `auto_science_shorts.py` (for example `en-GB-RyanNeural`).
- **Caption look:** edit the `STYLE` line.
- **Length and number of pictures per scene:** `length` in the run box, `SHOTS_PER_SCENE` in the code.

## Good to know

- Free services have limits and can be busy. The program retries and falls back on its own.
- Always read the script before posting. AI can get facts wrong.
- If your pictures look realistic, use YouTube's AI disclosure toggle.
- Stock footage and AI images have their own terms. Check each service before you post, and see `metadata.txt` for what was used in each video.

## Ideas for next versions

- [ ] A weekly topic queue so it makes a video every day
- [ ] Drop in your own Google Flow clips for key scenes
- [ ] More languages and voices
- [ ] Different script styles (myth-buster, "what if", comparison)
- [ ] Auto-upload as a private draft

Ideas and pull requests are welcome. Open an **Issue** to suggest something.

## License

MIT, see [LICENSE](LICENSE).

If this helped you, a ⭐ at the top of the page really helps other people find it.
