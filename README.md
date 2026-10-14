# Auto Science Shorts

Type a topic, get a finished ~30-second vertical video (1080x1920) for YouTube Shorts. It runs free on GitHub.

## What it does

1. **Gemini** writes a short script from your title and picks footage searches. The program finds a working Gemini model by itself and retries if Google is busy.
2. **edge-tts** reads the script in one calm storytelling voice (the same voice every time).
3. **Pixabay** supplies free stock footage that matches each scene.
4. **ffmpeg** joins everything into `short.mp4`. Captions show the words being spoken, 3 to 4 words at a time, timed to the voice.

## Files in this repo

- `auto_science_shorts.py`: the program that does the work.
- `.github/workflows/make-short.yml`: tells GitHub how to run the program when you tap "Run workflow".
- `README.md`: this guide.

## One-time setup

### 1. Get two free keys (like passwords for each service)

- **Google Gemini key:** go to aistudio.google.com, tap Get API key, then Create API key. If it asks for a project, create one first.
- **Pixabay key:** sign up at pixabay.com, then open pixabay.com/api/docs/. Your key appears on that page while you are logged in.

### 2. Save the keys in GitHub

In this repo: **Settings > Secrets and variables > Actions > New repository secret**.

| Name (type exactly) | Value |
| --- | --- |
| `GEMINI_API_KEY` | your Google key |
| `PIXABAY_API_KEY` | your Pixabay key |

Never paste keys into the code files, chats or anywhere public. If a key is ever exposed, create a new one and replace the secret.

## Make a video

1. Open the **Actions** tab.
2. Tap **Make short** on the left.
3. Tap **Run workflow**, type your title (for example `Why do we fall down?`), and tap the green **Run workflow** button.
4. Wait 2 to 4 minutes. A green check means it worked.
5. Tap the finished run, scroll to **Artifacts**, and tap the download icon next to **short**.
6. Unzip it in the Files app (press and hold the zip, then **Uncompress**). Inside is `short.mp4`.

Tip: add the Actions page to your home screen (Safari share icon, then Add to Home Screen) so it is one tap away.

## Change the voice

Open `auto_science_shorts.py` and edit this line near the top:

```
VOICE = "en-US-AndrewNeural"
```

Other good storytelling voices: `en-US-GuyNeural`, `en-GB-RyanNeural`, `en-US-AriaNeural`, `en-US-JennyNeural`.

## Change the caption look

Near the middle of `auto_science_shorts.py` is a line starting with `STYLE =`. `FontSize=10` controls the text size and `MarginV=70` controls how high the captions sit (bigger number means higher).

## If something goes wrong

Open the failed run, tap the red step, and read the last lines.

| Message | Meaning and fix |
| --- | --- |
| `KeyError: GEMINI_API_KEY` or `PIXABAY_API_KEY` | A secret is missing or misspelled. Re-add it exactly as shown above. |
| `503` or "high demand" from Gemini | Google is busy. The program retries by itself. If it still fails, wait 10 minutes and run again. |
| `429` or "exceeded your current quota" | You used up the free Gemini allowance for now. It resets daily. Try again later. |
| `404` or "model no longer available" | The program picks a model automatically. Re-run, and check that the Gemini key is valid. |
| `401` or `403` | The key is wrong or was deleted. Make a new key and update the secret. |
| `No such file or directory: ffprobe` | The workflow file is missing the ffmpeg install step. Re-copy `make-short.yml`. |
| Footage does not match the topic | Re-run for a different result. The footage searches are written by Gemini. |
| "Operation could not be completed" when unzipping | Download again, then press and hold the zip and choose **Uncompress**. Or move it to On My iPhone first. |

## Notes

- Free tiers have limits and can change, so check each service's current terms.
- Pixabay footage is free to use, but check Pixabay's license page for the latest rules before uploading.
- Wide stock clips may appear as a band in the middle of the screen over a blurred background. This keeps them sharp.
