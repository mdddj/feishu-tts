# feishu-tts

Codex skill for sending TTS output or local audio files to Feishu as playable voice bubbles instead of generic file attachments.

## What It Does

- Converts audio to mono 16 kHz OPUS
- Uploads the OPUS file to Feishu and gets a `file_key`
- Sends the message as `msg_type=audio`
- Checks local readiness for `python3`, `ffmpeg`, Homebrew on macOS, and Feishu config

## Files

- `SKILL.md`: skill instructions and invocation guidance
- `scripts/check_env.py`: local environment check
- `scripts/send_feishu_audio.py`: convert, upload, and send audio
- `references/feishu_audio_api.md`: Feishu API notes

## Quick Start

Check local environment first:

```bash
python3 scripts/check_env.py
```

Send an audio message:

```bash
python3 scripts/send_feishu_audio.py \
  --input /path/to/audio.mp3 \
  --receive-id oc_xxx \
  --receive-id-type chat_id
```

## Companion Skill

If you also need local text-to-speech generation, pair this with:

- `qwen3-tts-0.6b`: https://github.com/mdddj/qwen3-tts-0.6b

Generate speech locally with that skill, then send the generated audio to Feishu with this one.

## Feishu Flow

1. Convert source audio to OPUS with `ffmpeg`
2. Upload via `POST /open-apis/im/v1/files` using `file_type=opus`
3. Send via `POST /open-apis/im/v1/messages` using `msg_type=audio`

## Notes

- Voice-bubble delivery is different from sending a generic file attachment
- The bot needs message send and resource upload permissions
- On first use, the skill should ask whether the user wants a local environment check
