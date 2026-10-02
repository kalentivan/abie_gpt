# Telegram Client — Frontend TZ

## Goal
Build a standalone desktop Telegram user client inside this repository. It must not depend on the MAX/ChatGPT UI at runtime.

## MVP screens
1. Login: API ID, API hash, phone; code confirmation; optional 2FA password.
2. Main window: Telegram-like two-pane layout.
3. Left pane: search field and scrollable dialogs list containing private chats, groups and channels.
4. Right pane: selected chat header, scrollable message history, composer and Send button.
5. Status bar: connection/loading/error state.

## Dialog row
Show title, kind, last-message preview, timestamp and unread count when available. Selecting a row loads that dialog.

## Message history
Show sender name for group/channel messages when available, message text, time and outgoing/incoming distinction. Load newest messages first and render chronologically. MVP text messages only.

## Interaction
- Enter sends; Shift+Enter inserts newline.
- Refresh dialogs.
- Opening a dialog loads its recent history.
- New incoming messages update the open chat and corresponding dialog preview.
- UI must never block on network I/O; Telegram work runs on a dedicated asyncio thread/loop and returns data through a thread-safe UI queue.
- Errors are displayed in the status area/dialog, never crash Tk mainloop.

## Visual direction
Telegram Desktop-inspired, not a pixel clone: compact left navigation, clean chat surface, readable bubbles/rows, system-native Tk/ttk controls. No Telegram trademarks/assets copied into the app.

## Out of MVP
Media sending/viewing, calls, stories, reactions, message editing/deleting, folders, contacts management, admin/moderation, secret chats, stickers/GIF UI.

## Acceptance
App launches independently, authenticates a Telegram user, lists dialogs/channels/groups, opens recent messages, sends a text message, receives a new text message without manual restart, and remains responsive.
