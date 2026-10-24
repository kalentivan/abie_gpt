# Linux: MAX ↔ ChatGPT через существующий Brave

Ветка `linux` сохраняет обработку сообщений и загрузку файлов из `wnd`, но использует подключение CDP из `stable`. **Бот не запускает браузер и не закрывает окно Brave.**

## Запуск

1. Установите Brave и `uv` (Python 3.11), затем `uv sync`.
2. Скопируйте `.env.template` в `.env`, заполните `MAX_BOT_TOKEN`.
3. Запустите **отдельный** Brave с удалённой отладкой (обычный видимый, не headless):

```bash
brave-browser --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 --user-data-dir="$HOME/.config/brave-max-bot" --no-first-run https://chatgpt.com/
```

Если пакет установлен как `brave-browser-stable`, используйте это имя вместо `brave-browser`. Не запускайте Brave с `sudo`. Авторизуйтесь в ChatGPT в открытом окне.

4. Проверьте локальный CDP и запустите бота:

```bash
curl -fsS http://127.0.0.1:9222/json/version
uv run python main.py
```

Если `curl` не отвечает: закройте именно экземпляр Brave с данным `--user-data-dir` и запустите команду выше повторно. Используйте отдельный профиль, не основной пользовательский. Нужен доступ к рабочему графическому сеансу X11/Wayland: для SSH без дисплея браузер не откроет видимое окно.

ChromeDriver должен быть совместим с версией Brave. Когда `webdriver.Chrome` сообщает о несовместимости версий, обновите Selenium/ChromeDriver и Brave. CDP слушает только loopback — не пробрасывайте порт 9222 наружу.

Тесты синтаксиса: `python -m compileall -q integrations main.py config.py`. Сквозной тест требует локально открытого браузера и действующего MAX-токена.
