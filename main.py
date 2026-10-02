import asyncio

from dotenv import load_dotenv

load_dotenv()

from abie_gpt.config import Settings
from abie_gpt.max_app import MaxChatApp
from abie_gpt.selenium_handler import ChatGPTHandler


async def main() -> None:
    settings = Settings.from_env()
    handler = ChatGPTHandler(settings)
    app = MaxChatApp(settings, handler)
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
