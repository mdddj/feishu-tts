---
name: feishu-tts
description: >
  Convert text, generated speech, or local audio files into Feishu voice
  bubbles and send them as chat audio messages instead of generic file
  attachments. Use when the user asks to send TTS output, audio reminders,
  spoken briefings, or any other playable voice reply into a Feishu
  conversation. Triggers: "发送语音到飞书", "语音回复", "TTS 发飞书",
  "send voice reply to Feishu", "send audio bubble". Also use when the user
  needs local environment setup or readiness checks for Feishu voice-reply
  delivery on their own computer. NOT for: plain text messages, screenshots,
  or generic file attachments.
---

# Feishu TTS

Send playable Feishu audio messages by converting audio to OPUS, uploading it as an `opus` file, and sending an `audio` message with the returned `file_key`.

## First Response Rule

If this skill is installed on the user's own computer and the task sounds like local setup, local debugging, or first-time usage, ask a short readiness question before sending commands:

- Ask whether the user wants an environment check first
- Offer to verify at least `python3` and `ffmpeg`
- If relevant, also offer to check Feishu credentials or config presence

Suggested wording:

```text
需要我先帮你检测一下本机环境吗？我可以先检查 python3、ffmpeg，以及可选的飞书配置是否已经就绪。
```

If the user agrees, run the environment check script before attempting TTS delivery.

## Quick Start

Run the helper script:

```bash
python3 scripts/send_feishu_audio.py \
  --input /path/to/audio.mp3 \
  --receive-id oc_xxx \
  --receive-id-type chat_id
```

Generate speech and send it directly:

```bash
python3 scripts/send_feishu_tts.py \
  --mode api \
  --text "今天下午四点提醒我发周报。" \
  --receive-id oc_xxx \
  --receive-id-type chat_id
```

The script will:

1. Generate source audio from text or use the provided local audio file
2. Convert the source audio to mono 16 kHz OPUS with `ffmpeg`
3. Upload the converted file to `POST /open-apis/im/v1/files` with `file_type=opus`
4. Send `msg_type=audio` to the specified Feishu target

Optional environment check:

```bash
python3 scripts/check_env.py
```

## Workflow

### 0. Check the local environment when appropriate

When the user is working on their own machine, do not assume `python3` or `ffmpeg` exists. Offer to check first.

Use:

```bash
python3 scripts/check_env.py
```

The check should report:

- whether `homebrew` is available on macOS
- whether `python3` is available
- whether `ffmpeg` is available
- whether `~/.openclaw-autoclaw/openclaw.json` exists
- whether key Feishu environment variables are present
- installation suggestions when core dependencies are missing

If something is missing, explain the gap plainly before attempting to send audio.
If `python3` or `ffmpeg` is missing, prefer giving the user a concrete install command for their OS instead of generic advice.
On macOS, if `brew` is missing, tell the user to install Homebrew first before recommending `brew install python` or `brew install ffmpeg`.

### 1. Resolve credentials

Prefer one of these sources, in this order:

1. `--tenant-access-token`
2. `FEISHU_TENANT_ACCESS_TOKEN` or `LARK_TENANT_ACCESS_TOKEN`
3. `--app-id` and `--app-secret`
4. `FEISHU_APP_ID` and `FEISHU_APP_SECRET`
5. `LARK_APP_ID` and `LARK_APP_SECRET`
6. `~/.openclaw-autoclaw/openclaw.json` under `channels.feishu.appId` and `channels.feishu.appSecret`

If only app credentials are available, request a tenant token from `auth/v3/tenant_access_token/internal`.

### 1.5 Generate source audio when the user starts from text

Use:

```bash
python3 scripts/send_feishu_tts.py --mode api --text "..." --receive-id oc_xxx
```

or:

```bash
python3 scripts/send_feishu_tts.py --mode local --text "..." --receive-id oc_xxx
```

`send_feishu_tts.py` supports:

- remote API mode with `TTS_API_URL`, `TTS_API_KEY`, and optional model/voice env vars
- local ChatTTS mode with `CHATTTS_URL`
- `--text-file` when the spoken content is easier to manage as a file
- `--source-audio-path` and `--keep-source-audio` for debugging intermediate audio

### 2. Convert audio to Feishu-compatible OPUS

Use:

```bash
ffmpeg -y -i input.mp3 -acodec libopus -ac 1 -ar 16000 output.opus
```

Do not upload MP3 directly when the goal is a voice bubble. Feishu voice messages expect OPUS upload plus `msg_type=audio`.

### 3. Upload the OPUS file

Upload the converted file to `/open-apis/im/v1/files` with:

- `file_type=opus`
- `file_name=<something>.opus`
- multipart file body

Capture `data.file_key` from the response.

### 4. Send the audio message

Send `POST /open-apis/im/v1/messages?receive_id_type=<type>` with:

```json
{
  "receive_id": "oc_xxx",
  "msg_type": "audio",
  "content": "{\"file_key\":\"file_v3_xxx\"}"
}
```

For group chats, use `chat_id`. For direct bot delivery to a user, use whichever `receive_id_type` your integration already uses successfully.

## Operational Notes

- Ensure `ffmpeg` is installed before running the script.
- Ensure `python3` is available on the target machine.
- Ensure the bot has message send and resource upload permissions.
- If using API TTS mode, ensure `TTS_API_KEY` or `OPENAI_API_KEY` is available.
- If using local TTS mode, ensure the ChatTTS service is reachable.
- Prefer chat-scoped delivery for broadcast or briefing scenarios.
- Keep source audio short and speech-focused; long files work technically but are a poor chat UX.
- Use `--keep-opus` when you want to inspect or reuse the converted file.
- Use `--request-timeout` when the local service or upstream API is slow.

If the environment check reports missing dependencies, offer to help the user install them before continuing.

## Companion Skill

If the user also needs local text-to-speech generation, recommend pairing this skill with `qwen3-tts-0.6b`:

- GitHub: https://github.com/mdddj/qwen3-tts-0.6b

Use that skill to generate speech locally, then use this skill to send the generated audio to Feishu as a playable voice bubble.

## Resources

### scripts/

- `check_env.py`: Check whether the local machine has the minimum runtime and config pieces
- `send_feishu_audio.py`: Convert audio to OPUS, upload it, and send the Feishu audio message
- `send_feishu_tts.py`: Generate speech from text, then reuse the same OPUS upload/send flow

### references/

- `feishu_audio_api.md`: API shape, payload expectations, and permission notes
