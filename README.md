# ABIE GPT V2

MAX client for a persistent ChatGPT Web session.

## V2

The `v2` branch separates:
- MAX transport/UI;
- Selenium ChatGPT adapter;
- typed application configuration/models;
- future config-driven audit workers.

### Commands

- `/new` / `НД` — new ChatGPT conversation
- `/stop` — stop active generation
- `/status` — browser/ChatGPT state
- `/screenshot` / `СШ` — diagnostic screenshot
- any other text — send to ChatGPT and return the completed response

### Run

Copy `.env.template` to `.env`, configure the MAX token, Brave path and persistent browser profile, then:

```bash
uv run python main.py
```

The browser profile must already be authenticated in ChatGPT.
