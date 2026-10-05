from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from seleniumbase import Driver
from selenium.webdriver.common.keys import Keys

BRAVE_PATH = os.environ["BRAVE_PATH"]
TAXI_PROFILE = Path(os.getenv("TAXI_PROFILE", "runtime/yandex-taxi-profile")).resolve()
TAXI_ADDRESS_BOOK = Path(os.getenv("TAXI_ADDRESS_BOOK", "runtime/taxi-addresses.json")).resolve()
TAXI_SCREENSHOT = Path(os.getenv("TAXI_SCREENSHOT", "runtime/taxi-screenshot.png")).resolve()
TAXI_URL = os.getenv("TAXI_URL", "https://taxi.yandex.ru/")

LOW_END_MOBILE_UA = os.getenv(
    "TAXI_MOBILE_USER_AGENT",
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
)


@dataclass
class Address:
    id: int
    address: str
    name: str = ""


class AddressBook:
    def __init__(self, path: Path = TAXI_ADDRESS_BOOK):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.items: list[Address] = []
        self.load()

    def load(self):
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.items = [Address(**item) for item in data]

    def save(self):
        self.path.write_text(
            json.dumps([asdict(item) for item in self.items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, item_id: int) -> Address | None:
        return next((item for item in self.items if item.id == item_id), None)

    def add(self, address: str) -> Address:
        normalized = " ".join(address.split()).strip()
        existing = next((x for x in self.items if x.address.casefold() == normalized.casefold()), None)
        if existing:
            return existing
        item = Address(id=max((x.id for x in self.items), default=0) + 1, address=normalized)
        self.items.append(item)
        self.save()
        return item

    def render(self) -> str:
        if not self.items:
            return "Адресная книга пока пустая.\nВведи: адрес откуда | адрес куда"
        rows = ["Адресная книга:"]
        for item in self.items:
            label = f"{item.name} — " if item.name else ""
            rows.append(f"{item.id} — {label}{item.address}")
        rows.append("\nВведи два номера, например: 1 3")
        rows.append("Или: адрес откуда | адрес куда")
        return "\n".join(rows)

    def resolve_route(self, text: str) -> tuple[str, str, list[Address]]:
        value = text.strip()
        number_match = re.fullmatch(r"(\d+)\s+(\d+)", value)
        if number_match:
            left = self.get(int(number_match.group(1)))
            right = self.get(int(number_match.group(2)))
            if not left or not right:
                raise ValueError("Не найден один из номеров в адресной книге.")
            return left.address, right.address, []

        if "|" not in value:
            raise ValueError("Введи два номера через пробел или два адреса через |.")
        raw_left, raw_right = (part.strip() for part in value.split("|", 1))
        if not raw_left or not raw_right:
            raise ValueError("Нужны оба адреса: откуда | куда.")

        created: list[Address] = []

        def resolve(part: str) -> str:
            if part.isdigit():
                item = self.get(int(part))
                if not item:
                    raise ValueError(f"Адрес №{part} не найден.")
                return item.address
            item = self.add(part)
            created.append(item)
            return item.address

        return resolve(raw_left), resolve(raw_right), created


class YandexTaxiSelenium:
    def __init__(self):
        self.driver = None
        self.lock = threading.RLock()

    def log(self, message: str):
        print(f"[TAXI] {message}", flush=True)

    def start(self):
        with self.lock:
            if self.driver:
                return
            TAXI_PROFILE.mkdir(parents=True, exist_ok=True)
            self.driver = Driver(
                browser="chrome",
                binary_location=BRAVE_PATH,
                user_data_dir=str(TAXI_PROFILE),
                headless=False,
                chromium_arg=(
                    f"--user-agent={LOW_END_MOBILE_UA},"
                    "--window-size=412,915,--force-device-scale-factor=1"
                ),
            )
            try:
                self.driver.execute_cdp_cmd(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": 412, "height": 915, "deviceScaleFactor": 1, "mobile": True},
                )
                self.driver.execute_cdp_cmd(
                    "Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5}
                )
            except Exception as error:
                self.log(f"Mobile emulation частично недоступна: {error}")
            self.driver.get(TAXI_URL)
            self.log(f"Открыт {self.driver.current_url}")

    def _visible(self, selectors):
        for by, selector in selectors:
            try:
                for element in self.driver.find_elements(by, selector):
                    if element.is_displayed() and element.is_enabled():
                        return element
            except Exception:
                pass
        return None

    def _route_fields(self):
        result = []
        seen = set()
        selectors = (
            "input",
            "textarea",
            '[role="textbox"]',
            '[contenteditable="true"]',
        )
        for selector in selectors:
            try:
                for element in self.driver.find_elements("css selector", selector):
                    if not element.is_displayed() or not element.is_enabled():
                        continue
                    key = element.id
                    if key not in seen:
                        seen.add(key)
                        result.append(element)
            except Exception:
                pass
        return result

    def _field_by_hint(self, hints):
        hints = tuple(x.casefold() for x in hints)
        for field in self._route_fields():
            attrs = " ".join(
                str(field.get_attribute(name) or "")
                for name in ("placeholder", "aria-label", "value", "textContent")
            ).casefold()
            if any(hint in attrs for hint in hints):
                return field
        return None

    def _replace_field(self, field, value: str):
        field.click()
        time.sleep(0.2)
        field.send_keys(Keys.CONTROL, "a")
        field.send_keys(value)
        time.sleep(1.2)
        # Mobile Yandex Go shows address suggestions after typing.
        # Prefer the first suggestion, but Enter also works when the field
        # accepts the normalized address directly.
        try:
            field.send_keys(Keys.ARROW_DOWN)
            field.send_keys(Keys.ENTER)
        except Exception:
            field.send_keys(Keys.ENTER)
        time.sleep(1.2)

    def set_route(self, origin: str, destination: str):
        with self.lock:
            self.start()
            self.driver.get(TAXI_URL)
            time.sleep(2)

            origin_field = self._field_by_hint(
                ("откуда", "адрес подачи", "место подачи", "улица")
            )
            destination_field = self._field_by_hint(
                ("куда поедете", "куда", "пункт назначения")
            )

            fields = self._route_fields()
            if origin_field is None and len(fields) >= 2:
                origin_field = fields[0]
            if destination_field is None:
                candidates = [x for x in fields if origin_field is None or x.id != origin_field.id]
                if candidates:
                    destination_field = candidates[-1]

            # In the current mobile Yandex Go page the pickup point may be a
            # clickable row rather than an editable input. Click its visible
            # text to switch it into edit mode and search again.
            if origin_field is None:
                pickup = self._visible([
                    ("xpath", "//*[contains(normalize-space(.), 'улица') and not(self::body)]"),
                    ("xpath", "//*[contains(normalize-space(.), 'Откуда') and not(self::body)]"),
                ])
                if pickup:
                    pickup.click()
                    time.sleep(0.5)
                    origin_field = self._field_by_hint(("откуда", "адрес", "улица"))
                    fields = self._route_fields()
                    if origin_field is None and fields:
                        origin_field = fields[0]

            if destination_field is None:
                destination = self._visible([
                    ("xpath", "//*[normalize-space()='Куда поедете?']"),
                    ("xpath", "//*[contains(normalize-space(.), 'Куда поедете') and not(self::body)]"),
                ])
                if destination:
                    destination.click()
                    time.sleep(0.5)
                    destination_field = self._field_by_hint(("куда", "адрес"))
                    fields = self._route_fields()
                    if destination_field is None and fields:
                        destination_field = fields[-1]

            if origin_field is None or destination_field is None:
                self.diagnostic("route-inputs")
                raise RuntimeError(
                    f"Не нашёл поля маршрута Яндекс Go "
                    f"(найдено редактируемых полей: {len(self._route_fields())})."
                )

            self._replace_field(origin_field, origin)
            # DOM can be rebuilt after selecting FROM, so resolve TO again.
            destination_field = self._field_by_hint(
                ("куда поедете", "куда", "пункт назначения")
            ) or destination_field
            self._replace_field(destination_field, destination)
            self.log(f"Маршрут заполнен: {origin!r} -> {destination!r}")
            time.sleep(3)

    def page_text(self) -> str:
        return self.driver.find_element("tag name", "body").text

    def get_offer(self) -> tuple[int, str]:
        with self.lock:
            text = self.page_text()
            prices = re.findall(r"(?<!\d)(\d{2,6})\s*[₽РP](?!\w)", text, flags=re.I)
            if not prices:
                prices = re.findall(r"(?<!\d)(\d{2,6})\s*(?:руб\.?|RUB)(?!\w)", text, flags=re.I)
            if not prices:
                self.diagnostic("price")
                raise RuntimeError("Не удалось прочитать цену со страницы Яндекс Go.")
            price = int(prices[0])
            eta_match = re.search(r"(?:через|подача[^\d]{0,20})(\d{1,3})\s*мин", text, flags=re.I)
            eta = f"~{eta_match.group(1)} мин" if eta_match else "не указана"
            self.log(f"Цена: {price} ₽; подача: {eta}")
            return price, eta

    def create_order(self):
        with self.lock:
            button = self._visible([
                ("xpath", "//*[self::button or @role='button'][contains(., 'Вызвать')]"),
                ("xpath", "//*[self::button or @role='button'][contains(., 'Заказать')]"),
            ])
            if not button:
                self.diagnostic("order-button")
                raise RuntimeError("Не найдена кнопка заказа Яндекс Go.")
            button.click()
            self.log("Кнопка заказа нажата")
            time.sleep(2)

    def order_status(self) -> str:
        with self.lock:
            text = self.page_text()
            for pattern, status in (
                (r"машина.*приех|водитель.*ожида", "ARRIVED"),
                (r"[А-ЯA-Z]\s?\d{3}\s?[А-ЯA-Z]{2}|\d{3}\s?[А-ЯA-Z]{2}", "CAR_ASSIGNED"),
                (r"ищем.*машин|поиск.*машин", "SEARCHING_CAR"),
            ):
                if re.search(pattern, text, flags=re.I | re.S):
                    return status
            return "ORDERING"

    def vehicle_summary(self) -> str:
        with self.lock:
            lines = [line.strip() for line in self.page_text().splitlines() if line.strip()]
            interesting = []
            for line in lines:
                if re.search(r"\d{3}\s*[А-ЯA-Z]{2}|мин|водител|рейтинг", line, flags=re.I):
                    interesting.append(line)
            return "\n".join(interesting[-8:]) or "Машина назначена. Открой Яндекс Go для подробностей."

    def diagnostic(self, suffix: str):
        TAXI_SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
        path = TAXI_SCREENSHOT.with_name(f"{TAXI_SCREENSHOT.stem}-{suffix}{TAXI_SCREENSHOT.suffix}")
        try:
            self.driver.save_screenshot(str(path))
            self.log(f"Диагностика: {path}")
        except Exception:
            pass
        return path

    def close(self):
        with self.lock:
            if self.driver:
                self.driver.quit()
                self.driver = None


class TaxiAgent:
    def __init__(self):
        self.book = AddressBook()
        self.provider = YandexTaxiSelenium()
        self.state = "IDLE"
        self.route: tuple[str, str] | None = None
        self.confirmed_price: int | None = None

    def is_active(self) -> bool:
        return self.state != "IDLE"

    def start(self) -> str:
        self.state = "WAITING_ROUTE"
        self.route = None
        self.confirmed_price = None
        return self.book.render()

    def handle(self, text: str) -> str:
        value = text.strip()
        if self.state == "WAITING_ROUTE":
            origin, destination, created = self.book.resolve_route(value)
            self.route = (origin, destination)
            self.provider.set_route(origin, destination)
            price, eta = self.provider.get_offer()
            self.confirmed_price = price
            self.state = "WAITING_CONFIRMATION"
            added = ""
            if created:
                unique = {item.id: item for item in created}
                added = "\nСохранил: " + ", ".join(f"№{x.id} {x.address}" for x in unique.values())
            return f"Эконом — {price} ₽. Подача: {eta}.{added}\nЗаказывать?"

        if self.state == "WAITING_CONFIRMATION":
            if value.casefold() in {"нет", "не", "отмена", "отмени"}:
                self.state = "IDLE"
                return "Заказ отменён."
            if value.casefold() not in {"да", "заказывай", "бери", "ок", "окей"}:
                return "Ответь «Да», чтобы заказать, или «Нет», чтобы отменить."
            price, eta = self.provider.get_offer()
            if self.confirmed_price is not None and price > self.confirmed_price:
                old = self.confirmed_price
                self.confirmed_price = price
                return f"Цена изменилась: {old} ₽ → {price} ₽. Заказывать за {price} ₽?"
            self.provider.create_order()
            self.state = "ORDERING"
            return f"Заказ отправлен по цене {price} ₽. Ищу машину…"

        return "Заказ уже отправлен. Напиши «где машина», чтобы проверить статус."

    def status(self) -> str:
        if self.state == "IDLE":
            return "Активного заказа такси нет."
        if self.state in {"WAITING_ROUTE", "WAITING_CONFIRMATION"}:
            return "Заказ ещё не создан."
        status = self.provider.order_status()
        self.state = status
        if status == "CAR_ASSIGNED":
            return "Машина найдена:\n" + self.provider.vehicle_summary()
        if status == "ARRIVED":
            return "Машина приехала."
        if status == "SEARCHING_CAR":
            return "Яндекс ещё ищет машину."
        return "Заказ обрабатывается."

    def close(self):
        self.provider.close()
