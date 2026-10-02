# ABIE GPT V2

MAX client for ChatGPT Web plus a config-driven audit runtime.

## Architecture

```text
src/abie_gpt/
├── app/        # application use-cases; no MAX or Selenium details
├── bot/        # MAX transport and commands
├── chatgpt/    # Selenium adapter and ChatGPT UI selectors
├── audit/      # audit worker configuration and execution
├── core/       # shared settings and domain DTOs
└── bootstrap.py
config/
└── workers.example.yaml
main.py         # thin local entrypoint
```

Dependency direction:

```text
MAX -> bot -> app -> chatgpt -> Selenium/ChatGPT Web
                    ^
audit --------------|
```

The MAX adapter does not access Selenium directly. Audit workers reuse the same ChatGPT adapter, so UI selectors and browser recovery have one implementation.

## MAX commands

- `/new` / `НД` — new conversation
- `/stop` — stop active generation
- `/status` — ChatGPT/browser state
- `/screenshot` / `СШ` — diagnostic screenshot
- any other text — send to ChatGPT

## Run

Copy `.env.template` to `.env`, configure MAX and the persistent Brave profile, then:

```bash
uv sync
uv run python main.py
```

The browser profile must already be authenticated in ChatGPT.

## Audit runtime

Audit configuration lives outside code. See `config/workers.example.yaml`. The audit package deliberately depends on the shared ChatGPT adapter instead of implementing a second Selenium client.
