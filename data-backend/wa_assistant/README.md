# WhatsApp Assistant (wa_assistant)

Django app that connects to the WhatsApp Cloud API, receives messages via webhook, and stores them in PostgreSQL. Media is saved using the same hierarchical content-addressable storage as other apps (`wa_assistant/abc/def/abcdef...xyz.ext`).

## Setup

### 1. Environment variables

```bash
# Required for webhook verification - set the same value in Meta App Dashboard
export WHATSAPP_WEBHOOK_VERIFY_TOKEN="your-secret-verify-token"

# Required for downloading media from WhatsApp
export WHATSAPP_ACCESS_TOKEN="your-whatsapp-cloud-api-access-token"
```

### 2. Meta Developer Dashboard

1. Create or use an existing Meta App with WhatsApp Business API.
2. In **WhatsApp > Configuration**, set the Webhook URL to:
   ```
   https://your-domain.com/api/wa-assistant/webhook/
   ```
3. Set the **Verify Token** to match `WHATSAPP_WEBHOOK_VERIFY_TOKEN`.
4. Subscribe to the `messages` webhook field.

### 3. Run migrations

```bash
python manage.py migrate wa_assistant
```

## Webhook

- **GET** `/api/wa-assistant/webhook/` – Verification. Meta sends `hub.mode`, `hub.verify_token`, `hub.challenge`. If the token matches, the endpoint returns `hub.challenge`.
- **POST** `/api/wa-assistant/webhook/` – Receives incoming messages and events. Messages are stored in the database; media is downloaded and saved to hierarchical storage.

## Models

- **WhatsAppMessage** – Incoming messages (text, image, audio, video, document, etc.)
- **WhatsAppMedia** – Media attachments, stored under `MEDIA_ROOT/wa_assistant/` with SHA256-based paths

## Media storage

Media is stored under `media/wa_assistant/{hash_prefix_3}/{hash_sub_3}/{full_hash}.ext`, matching the pattern used in `people/utils.py`. Images get thumbnails when Pillow is available.
