COMPOSERS = (
    "#prompt-textarea",
    "#mobile-composer-prompt",
    '[contenteditable="true"][role="textbox"]',
    "textarea",
)

SEND_BUTTONS = (
    'button[data-testid="send-button"]',
    'button[aria-label="Send prompt"]',
    'button[aria-label*="Send"]',
    'button[aria-label*="Отправ"]',
)

STOP_BUTTONS = (
    'button[data-testid="stop-button"]',
    'button[aria-label*="Stop"]',
    'button[aria-label*="Останов"]',
)

ASSISTANT_MESSAGES = '[data-message-author-role="assistant"]'
