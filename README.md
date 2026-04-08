# feishu-tts

Codex skill for sending TTS output or local audio files to Feishu as playable voice bubbles instead of generic file attachments.

## What It Does

- Generates speech from text through either a remote TTS API or a local ChatTTS service
- Converts audio to mono 16 kHz OPUS
- Uploads the OPUS file to Feishu and gets a `file_key`
- Sends the message as `msg_type=audio`
- Checks local readiness for `python3`, `ffmpeg`, Homebrew on macOS, and Feishu config

## Files

- `SKILL.md`: skill instructions and invocation guidance
- `scripts/check_env.py`: local environment check
- `scripts/send_feishu_audio.py`: convert, upload, and send audio
- `scripts/send_feishu_tts.py`: generate speech from text, then upload and send audio
- `references/feishu_audio_api.md`: Feishu API notes

## Quick Start

Check local environment first:

```bash
python3 scripts/check_env.py
```

Send an existing audio file:

```bash
python3 scripts/send_feishu_audio.py \
  --input /path/to/audio.mp3 \
  --receive-id oc_xxx \
  --receive-id-type chat_id
```

Generate speech with an API and send it to Feishu:

```bash
python3 scripts/send_feishu_tts.py \
  --mode api \
  --text "今天下午三点半开组会，请准时参加。" \
  --receive-id oc_xxx \
  --receive-id-type chat_id
```

Generate speech with a local ChatTTS service and send it to Feishu:

```bash
python3 scripts/send_feishu_tts.py \
  --mode local \
  --text "十分钟后提醒我开始周会。" \
  --receive-id oc_xxx \
  --receive-id-type chat_id \
  --chattts-url http://127.0.0.1:8080
```

## Environment Variables

Feishu delivery:

- `FEISHU_TENANT_ACCESS_TOKEN`
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `LARK_TENANT_ACCESS_TOKEN`
- `LARK_APP_ID`
- `LARK_APP_SECRET`

Remote TTS:

- `TTS_API_URL`
- `TTS_API_KEY`
- `OPENAI_API_KEY`
- `TTS_MODEL`
- `TTS_VOICE`
- `TTS_RESPONSE_FORMAT`

Local TTS:

- `CHATTTS_URL`

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
