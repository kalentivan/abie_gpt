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
from selenium.common.exceptions import StaleElementReferenceException

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
            return left.address, right.address, [True, True]

        if "|" not in value:
            raise ValueError("Введи два номера через пробел или два адреса через |.")
        raw_left, raw_right = (part.strip() for part in value.split("|", 1))
        if not raw_left or not raw_right:
            raise ValueError("Нужны оба адреса: откуда | куда.")

        def resolve(part: str) -> tuple[str, bool]:
            if part.isdigit():
                item = self.get(int(part))
                if not item:
                    raise ValueError(f"Адрес №{part} не найден.")
                return item.address, True
            return part, False

        left, left_known = resolve(raw_left)
        right, right_known = resolve(raw_right)
        return left, right, [left_known, right_known]


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

    def _suggestions(self):
        items = []
        try:
            titles = [
                x for x in self.driver.find_elements(
                    "css selector", "[class*='result-title--']"
                ) if x.is_displayed()
            ]
        except Exception:
            titles = []
        for title in titles:
            try:
                try:
                    container = title.find_element(
                        "xpath", "./ancestor::*[contains(@class,'result--') or contains(@class,'suggest')][1]"
                    )
                    full = " ".join((container.text or "").split())
                except StaleElementReferenceException:
                    continue
                except Exception:
                    full = " ".join((title.text or "").split())
                if full and full not in [x["text"] for x in items]:
                    items.append({"text": full, "element": title})
            except StaleElementReferenceException:
                # React rebuilt the suggestions list between find_elements()
                # and reading this node. It is normal after selecting an address.
                continue
        return items

    @staticmethod
    def _norm_address(value: str):
        return re.sub(r"[^0-9a-zа-яё]+", " ", value.casefold()).strip()

    def begin_address(self, kind: str, value: str):
        field = self._open_address_editor(kind)
        field.click()
        # Yandex's React textarea may ignore Selenium's Ctrl+A after the editor
        # has just been mounted. Clear it through the native value setter and
        # dispatch an input event so React updates its state too.
        self.driver.execute_script(
            """
            const el = arguments[0];
            const setter = Object.getOwnPropertyDescriptor(
                HTMLTextAreaElement.prototype, 'value'
            ).set;
            setter.call(el, '');
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            el.focus();
            """,
            field,
        )
        time.sleep(0.15)

        # Do NOT use _field_by_hint here: its fuzzy matching can return the
        # other route textarea. Re-acquire the exact field by placeholder after
        # React processes the clear event, then verify focus once more.
        placeholder = "Откуда поедете?" if kind == "from" else "Куда поедете?"
        exact_fields = [
            x for x in self.driver.find_elements(
                "css selector", f'textarea[placeholder="{placeholder}"]'
            )
            if x.is_displayed() and x.is_enabled()
        ]
        if not exact_fields:
            self._dump_route_editor(kind)
            raise RuntimeError(f"После очистки исчезло поле {placeholder!r}")
        field = exact_fields[0]
        self.driver.execute_script("arguments[0].focus();", field)
        active = self.driver.switch_to.active_element
        if active.get_attribute("placeholder") != placeholder:
            raise RuntimeError(
                f"Перед вводом {kind} активно не то поле: "
                f"{active.get_attribute('placeholder')!r}"
            )
        active.send_keys(value)
        self.log(f"Введён {kind}: {value!r} в {placeholder!r}")
        time.sleep(1.3)
        suggestions = self._suggestions()
        if not suggestions:
            self.diagnostic(f"suggestions-{kind}")
            raise RuntimeError(f"Яндекс не предложил варианты для адреса: {value}")
        rows = [x["text"] for x in suggestions]
        wanted = self._norm_address(value)
        exact = None
        for i, row in enumerate(rows):
            normalized = self._norm_address(row)
            # Exact address text can have the city appended on the next line.
            if normalized == wanted or normalized.startswith(wanted + " "):
                if "краснодар" in normalized or "краснодар" not in " ".join(
                    self._norm_address(x) for x in rows
                ):
                    exact = i
                    break
        preferred = next(
            (i for i, row in enumerate(rows) if "краснодар" in self._norm_address(row)),
            0,
        )
        return rows, exact, preferred

    def choose_suggestion(self, index: int):
        suggestions = self._suggestions()
        if not suggestions or index < 0 or index >= len(suggestions):
            raise RuntimeError("Список подсказок Яндекса изменился. Повтори адрес.")
        item = suggestions[index]
        element = item["element"]
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        try:
            element.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", element)
        self.log(f"Выбрана подсказка адреса: {item['text']!r}")
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                visible = [
                    x for x in self.driver.find_elements(
                        "css selector", "[class*='result-title--']"
                    )
                    if x.is_displayed()
                ]
            except StaleElementReferenceException:
                visible = []
            except Exception:
                visible = []
            if not visible:
                break
            time.sleep(0.2)
        time.sleep(0.4)
        return item["text"]

    def _dump_route_editor(self, kind: str):
        out_dir = TAXI_SCREENSHOT.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"yandex-taxi-editor-{kind}.txt"
        rows = [f"url={self.driver.current_url}", f"kind={kind}", ""]
        selectors = (
            "input, textarea, [role='textbox'], [contenteditable='true'], "
            "[class*='address--'], [class*='route'], [class*='search']"
        )
        try:
            elements = self.driver.find_elements("css selector", selectors)
        except Exception:
            elements = []
        for i, el in enumerate(elements):
            try:
                rows.extend([
                    f"--- {i} ---",
                    f"tag={el.tag_name}",
                    f"displayed={el.is_displayed()} enabled={el.is_enabled()}",
                    f"rect={el.rect}",
                    f"text={el.text!r}",
                    f"value={el.get_attribute('value')!r}",
                    f"placeholder={el.get_attribute('placeholder')!r}",
                    f"aria-label={el.get_attribute('aria-label')!r}",
                    f"class={el.get_attribute('class')!r}",
                    f"outerHTML={el.get_attribute('outerHTML')}",
                    "",
                ])
            except StaleElementReferenceException:
                rows.extend([f"--- {i} ---", "STALE", ""])
        path.write_text("\n".join(rows), encoding="utf-8")
        self.diagnostic(f"editor-{kind}")
        self.log(f"Редактор {kind}: {path}")
        return path

    def _open_address_editor(self, kind: str):
        # Clicking either route row opens Yandex's search sheet. In that sheet
        # there are two real textareas, explicitly distinguished by placeholder.
        # Never choose a textbox by screen coordinates: the sheet is mounted at
        # the top of the page, independently of the row that opened it.
        if kind == "from":
            selectors = [
                ("css selector", ".address--UMqe0:not(.address_to--_yFAc)"),
                ("xpath", "//*[contains(@class,'address--UMqe0') and not(contains(@class,'address_to--'))]"),
            ]
            placeholder = "Откуда поедете?"
        else:
            selectors = [
                ("css selector", ".address_to--_yFAc"),
                ("xpath", "//*[normalize-space()='Куда поедете?']/ancestor::*[contains(@class,'address--UMqe0')][1]"),
            ]
            placeholder = "Куда поедете?"

        row = self._visible(selectors)
        if not row:
            raise RuntimeError(f"Не нашёл строку адреса {kind}")

        # After selecting FROM, Yandex can keep the search sheet open with the
        # FROM textarea still focused. For TO, clicking the row is not enough in
        # that state: explicitly focus the destination textarea after opening.
        try:
            row.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", row)
        time.sleep(0.5)

        deadline = time.time() + 3
        while time.time() < deadline:
            try:
                fields = [
                    x for x in self.driver.find_elements(
                        "css selector", f'textarea[placeholder="{placeholder}"]'
                    )
                    if x.is_displayed() and x.is_enabled()
                ]
                if fields:
                    field = fields[0]
                    # Force focus onto the exact textarea. This matters for TO:
                    # Yandex may leave FROM focused after selecting its suggestion.
                    self.driver.execute_script("arguments[0].focus(); arguments[0].click();", field)
                    time.sleep(0.1)
                    active = self.driver.switch_to.active_element
                    active_placeholder = active.get_attribute("placeholder")
                    if active_placeholder != placeholder:
                        field.click()
                        active = self.driver.switch_to.active_element
                        active_placeholder = active.get_attribute("placeholder")
                    if active_placeholder != placeholder:
                        raise RuntimeError(
                            f"Не удалось активировать поле {kind}: "
                            f"active placeholder={active_placeholder!r}"
                        )
                    self.log(
                        f"Поле {kind}: placeholder={placeholder!r}; "
                        f"value={field.get_attribute('value')!r}; active={active_placeholder!r}"
                    )
                    return active
            except StaleElementReferenceException:
                pass
            time.sleep(0.1)

        self._dump_route_editor(kind)
        raise RuntimeError(
            f"После клика по адресу {kind} не появилось поле {placeholder!r}"
        )

    def route_values(self):
        from_row = self._visible([
            ("css selector", ".address--UMqe0:not(.address_to--_yFAc)"),
        ])
        to_row = self._visible([
            ("css selector", ".address_to--_yFAc"),
        ])
        return (
            " ".join((from_row.text or "").split()) if from_row else "",
            " ".join((to_row.text or "").split()) if to_row else "",
        )

    def verify_selected_address(self, kind: str, expected: str):
        actual_from, actual_to = self.route_values()
        actual = actual_from if kind == "from" else actual_to
        expected_tokens = [
            x for x in self._norm_address(expected).split()
            if len(x) > 1 and x not in {"ул", "д"}
        ]
        actual_norm = self._norm_address(actual)
        matched = sum(1 for x in expected_tokens if x in actual_norm)
        needed = max(1, min(2, len(expected_tokens)))
        if matched < needed:
            self.diagnostic(f"verify-{kind}")
            raise RuntimeError(
                f"Яндекс не установил адрес {kind}: ожидали {expected!r}, "
                f"на странице {actual!r}. FROM={actual_from!r}; TO={actual_to!r}"
            )
        self.log(f"Проверен адрес {kind}: {actual!r}")
        return actual

    def prepare_route(self):
        with self.lock:
            self.start()
            self.driver.get(TAXI_URL)
            time.sleep(2)


    def page_text(self) -> str:
        return self.driver.find_element("tag name", "body").text

    def get_offer(self) -> tuple[int, str]:
        with self.lock:
            text = self.page_text()
            if "Куда поедете?" in text:
                self.diagnostic("route-not-ready")
                raise RuntimeError("Яндекс Go ещё не принял пункт назначения; цену читать нельзя.")

            # Read the Economy tariff card, not an arbitrary ₽ value from DOM.
            economy = self._visible([
                ("xpath", "//*[contains(normalize-space(.), 'Эконом') and contains(normalize-space(.), '₽')]"),
            ])
            if not economy:
                self.diagnostic("economy-price")
                raise RuntimeError("Не удалось найти рассчитанный тариф «Эконом».")

            card_text = " ".join((economy.text or "").split())
            match = re.search(r"(?:от\s*)?(\d{2,6})\s*₽", card_text, flags=re.I)
            if not match:
                # Some revisions put text in a child/ancestor tariff card.
                try:
                    card = economy.find_element(
                        "xpath", "./ancestor::*[contains(@class,'tariff') or contains(@class,'class')][1]"
                    )
                    card_text = " ".join((card.text or "").split())
                except Exception:
                    pass
                match = re.search(r"(?:от\s*)?(\d{2,6})\s*₽", card_text, flags=re.I)
            if not match:
                self.diagnostic("economy-price")
                raise RuntimeError(f"Не удалось прочитать цену Эконом из: {card_text!r}")

            price = int(match.group(1))
            eta_match = re.search(r"(?:через|подача[^\d]{0,20})(\d{1,3})\s*мин", text, flags=re.I)
            eta = f"~{eta_match.group(1)} мин" if eta_match else "не указана"
            self.log(f"Эконом: {price} ₽; подача: {eta}; card={card_text!r}")
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
            noise = re.compile(
                r"^(?:стать водителем|водителям|©|\d+\s*мин)$",
                flags=re.I,
            )

            # Prefer a compact slice around the car plate / driver assignment.
            plate_re = re.compile(
                r"(?:[А-ЯA-Z]\s?\d{3}\s?[А-ЯA-Z]{2}|\d{3}\s?[А-ЯA-Z]{2})",
                flags=re.I,
            )
            plate_index = next(
                (i for i, line in enumerate(lines) if plate_re.search(line)),
                None,
            )
            if plate_index is not None:
                start = max(0, plate_index - 8)
                end = min(len(lines), plate_index + 9)
                candidates = lines[start:end]
            else:
                # Yandex revisions sometimes render the plate without text that
                # matches our regex. Keep vehicle/driver-looking lines instead.
                keywords = re.compile(
                    r"машин|автомоб|водител|рейтинг|цвет|номер|"
                    r"lada|kia|hyundai|renault|volkswagen|skoda|toyota|"
                    r"chery|geely|haval|moskvich|омода|лада|киа|хендай|"
                    r"рено|фольксваген|шкода|тойота",
                    flags=re.I,
                )
                candidates = [line for line in lines if keywords.search(line)]

            result = []
            for line in candidates:
                if noise.search(line):
                    continue
                if line not in result:
                    result.append(line)

            if result:
                return "\n".join(result[:12])

            # Capture diagnostics instead of returning unrelated ETA/footer text.
            self.diagnostic("vehicle")
            return "Машина назначена, но данные автомобиля не удалось распознать."

    def dump_dom(self):
        with self.lock:
            self.start()
            out_dir = TAXI_SCREENSHOT.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            html_path = out_dir / "yandex-taxi-page.html"
            elements_path = out_dir / "yandex-taxi-elements.txt"

            html_path.write_text(self.driver.page_source, encoding="utf-8")

            selectors = "input, textarea, button, [role], [contenteditable], [data-testid]"
            elements = self.driver.find_elements("css selector", selectors)
            rows = [
                f"url={self.driver.current_url}",
                f"title={self.driver.title}",
                f"elements={len(elements)}",
                "",
            ]
            for index, element in enumerate(elements):
                try:
                    rows.extend([
                        f"--- {index} ---",
                        f"tag={element.tag_name}",
                        f"displayed={element.is_displayed()}",
                        f"enabled={element.is_enabled()}",
                        f"text={element.text!r}",
                        f"placeholder={element.get_attribute('placeholder')!r}",
                        f"aria-label={element.get_attribute('aria-label')!r}",
                        f"role={element.get_attribute('role')!r}",
                        f"data-testid={element.get_attribute('data-testid')!r}",
                        f"value={element.get_attribute('value')!r}",
                        f"outerHTML={element.get_attribute('outerHTML')}",
                        "",
                    ])
                except Exception as error:
                    rows.extend([f"--- {index} ---", f"ERROR: {error}", ""])

            elements_path.write_text("\n".join(rows), encoding="utf-8")
            screenshot = self.diagnostic("dom")
            self.log(
                f"DOM dump: {html_path}; elements: {elements_path}; screenshot: {screenshot}"
            )
            return [html_path, elements_path, screenshot]

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
    YES = {"да", "заказывай", "бери", "ок", "окей"}

    def __init__(self):
        self.book = AddressBook()
        self.provider = YandexTaxiSelenium()
        self.state = "IDLE"
        self.route_parts = []
        self.route_known = []
        self.route_resolved = [None, None]
        self.pending_index = None
        self.pending_suggestions = []
        self.pending_preferred = 0
        self.confirmed_price = None

    def is_active(self):
        return self.state != "IDLE"

    def start(self):
        self.state = "WAITING_ROUTE"
        self.confirmed_price = None
        return self.book.render()

    def _ask_address(self, index: int):
        kind = "from" if index == 0 else "to"
        rows, exact, preferred = self.provider.begin_address(kind, self.route_parts[index])

        if self.route_known[index]:
            # A saved address is trusted by the bot, but it still must be
            # physically selected in the fresh Yandex Go page.
            chosen = exact if exact is not None else preferred
            selected = self.provider.choose_suggestion(chosen)
            selected = self.provider.verify_selected_address(kind, selected)
            self.route_resolved[index] = selected
            return self._advance_address(index + 1)
        if exact is not None:
            selected = self.provider.choose_suggestion(exact)
            selected = self.provider.verify_selected_address(kind, selected)
            item = self.book.add(selected)
            self.route_resolved[index] = item.address
            return self._advance_address(index + 1)

        self.pending_index = index
        self.pending_suggestions = rows
        self.pending_preferred = preferred
        self.state = "WAITING_ADDRESS_CONFIRMATION"
        label = "Откуда" if index == 0 else "Куда"
        return f"{label}: Яндекс нашёл «{rows[preferred]}». Это правильный адрес?"

    def _advance_address(self, index: int):
        if index < 2:
            return self._ask_address(index)
        price, eta = self.provider.get_offer()
        self.confirmed_price = price
        self.state = "WAITING_CONFIRMATION"
        return (
            f"Маршрут: {self.route_resolved[0]} → {self.route_resolved[1]}\n"
            f"Эконом — {price} ₽. Подача: {eta}.\nЗаказывать?"
        )

    def handle(self, text: str):
        value = text.strip()
        folded = value.casefold()

        if self.state == "WAITING_ROUTE":
            origin, destination, known = self.book.resolve_route(value)
            self.route_parts = [origin, destination]
            if not isinstance(known, (list, tuple)) or len(known) != 2:
                raise RuntimeError(f"Некорректный результат парсинга маршрута: known={known!r}")
            self.route_known = [bool(known[0]), bool(known[1])]
            self.route_resolved = [None, None]
            self.provider.prepare_route()
            return self._advance_address(0)

        if self.state == "WAITING_ADDRESS_CONFIRMATION":
            index = self.pending_index
            if folded in self.YES:
                selected = self.provider.choose_suggestion(self.pending_preferred)
                kind = "from" if index == 0 else "to"
                selected = self.provider.verify_selected_address(kind, selected)
                item = self.book.add(selected)
                self.route_resolved[index] = item.address
                return self._advance_address(index + 1)
            if folded in {"нет", "не"}:
                self.state = "WAITING_ADDRESS_CHOICE"
                rows = ["Выбери подходящий адрес:"]
                rows.extend(f"{i + 1} — {x}" for i, x in enumerate(self.pending_suggestions))
                return "\n".join(rows)
            return "Ответь «Да» или «Нет»."

        if self.state == "WAITING_ADDRESS_CHOICE":
            if not value.isdigit():
                return "Пришли номер адреса из списка."
            choice = int(value) - 1
            if choice < 0 or choice >= len(self.pending_suggestions):
                return f"Выбери номер от 1 до {len(self.pending_suggestions)}."
            selected = self.provider.choose_suggestion(choice)
            index = self.pending_index
            kind = "from" if index == 0 else "to"
            selected = self.provider.verify_selected_address(kind, selected)
            item = self.book.add(selected)
            self.route_resolved[index] = item.address
            return self._advance_address(index + 1)

        if self.state == "WAITING_CONFIRMATION":
            if folded in {"нет", "не", "отмена", "отмени"}:
                self.state = "IDLE"
                return "Заказ отменён."
            if folded not in self.YES:
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

    def status(self):
        if self.state == "IDLE":
            return "Активного заказа такси нет."
        if self.state in {
            "WAITING_ROUTE", "WAITING_ADDRESS_CONFIRMATION",
            "WAITING_ADDRESS_CHOICE", "WAITING_CONFIRMATION"
        }:
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

