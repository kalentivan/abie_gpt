# Telegram Client — Backend TZ

## Architecture
Separate module under `abie_gpt.telegram`.
Layers:
- domain DTOs/protocol
- TelegramService application layer
- Telethon adapter (lazy import)
- Local/Fake adapter for tests
- standalone desktop bootstrap

The UI must depend on TelegramService/protocol, never Telethon objects.

## Domain
TelegramDialog: id, title, kind(private/group/channel), unread_count, last_message, last_message_at.
TelegramMessage: id, dialog_id, text, sender_name, sent_at, outgoing.

## Port
Async interface:
- connect()
- is_authorized()
- send_code(phone)
- sign_in(phone, code, password=None)
- list_dialogs(limit)
- list_messages(dialog_id, limit)
- send_message(dialog_id, text)
- subscribe(callback)
- disconnect()

## Telethon adapter
Use TelegramClient with local session path. Telethon import must be lazy so tests and the rest of ABIE GPT work without Telethon installed. Map Telethon entities/messages to domain DTOs. Subscribe to NewMessage events and emit DTOs.

## Configuration
Environment:
TELEGRAM_API_ID
TELEGRAM_API_HASH
TELEGRAM_PHONE
TELEGRAM_SESSION
No credentials in source control or logs.

## Concurrency
One dedicated asyncio event loop/thread owns Telethon. Tkinter remains on main thread. No cross-thread Tk calls. UI receives events via queue + root.after polling.

## Logging
Use existing ABIE GPT rotating logging. Log lifecycle and IDs/counts, not API hash, auth code, 2FA password or full private message bodies.

## Testing
FakeTelegramClient with deterministic dialogs/messages/events. Unit tests for service mapping/validation and UI-independent behavior. No real Telegram network required for unit tests.

## Acceptance
Backend can authenticate, enumerate dialogs, load messages, send text, receive NewMessage, reconnect using saved session, and shut down cleanly.
