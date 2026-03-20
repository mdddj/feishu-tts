# Feishu Audio Message API

## Flow

1. Convert source audio to OPUS
2. Upload with `POST /open-apis/im/v1/files`
3. Send message with `POST /open-apis/im/v1/messages`

## Conversion

Recommended command:

```bash
ffmpeg -y -i input.mp3 -acodec libopus -ac 1 -ar 16000 output.opus
```

This produces a mono 16 kHz OPUS file, which is the target format for the voice-message workflow described in the product requirement.

## Upload Request

Endpoint:

```text
POST https://open.feishu.cn/open-apis/im/v1/files
```

Multipart form fields:

- `file_type=opus`
- `file_name=<name>.opus`
- `file=@/path/to/output.opus`

Expected response field:

- `data.file_key`

## Send Audio Message

Endpoint:

```text
POST https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id
```

JSON body:

```json
{
  "receive_id": "oc_xxx",
  "msg_type": "audio",
  "content": "{\"file_key\":\"file_v3_xxx\"}"
}
```

## Permissions

The bot typically needs message send and resource upload capabilities, including:

- `im:message:send_as_bot`
- `im:resource`

## References

- https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/create
- https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/file/create
