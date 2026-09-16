# -*- coding: utf-8 -*-
"""
=======================================================================
 JARDIN ROSE — движок сайта салона флористики (Python + Flask)
=======================================================================

КАК УСТРОЕН ПРОЕКТ (кто что делает)

    vikanastya.html      витрина: вся разметка страницы
    style.css            фирменное оформление по макету «проект.psd»
    static/css/animations.css  анимации и эффекты
    static/js/main.js    «мозг» страницы в браузере: рисует карточки,
                         корзину, модальные окна, шлёт запросы движку
    static/js/petals.js  фоновая анимация падающих лепестков (canvas)
    static/js/catalog-data.js  снимок каталога для работы без сервера

    app.py               ЭТОТ ФАЙЛ — веб-сервер и адреса (маршруты) API
    engine/config.py     настройки: валюта, доставка, контакты
    engine/db.py         структура базы SQLite и исходные данные каталога
    engine/catalog.py    выборка товаров: фильтры, сортировка, поиск
    engine/cart.py       корзина, промокоды, все денежные расчёты
    engine/orders.py     проверка формы и оформление заказа
    engine/graphics.py   генератор картинок букетов на Pillow
    engine/export.py     выгрузка каталога в JS для офлайн-режима
    data/jardin.db       база данных (создаётся при первом запуске)

ПУТЬ ОДНОГО КЛИКА (откуда берутся данные на экране)

    Посетитель нажал «В корзину»
      → main.js отправляет POST /api/cart/add с id товара
      → app.py принимает запрос и зовёт cart.add_product()
      → cart.py кладёт id в сессию и берёт ЦЕНУ ИЗ БАЗЫ (не из браузера)
      → cart.build_state() считает сумму, скидку, доставку
      → app.py отвечает JSON-ом
      → main.js перерисовывает корзину и показывает уведомление

ЗАПУСК
      python app.py           затем открыть http://127.0.0.1:5000
"""

import math
import os
import webbrowser
from threading import Timer

from flask import (Flask, jsonify, request, send_from_directory, session)
from markupsafe import escape

from engine import cart as cart_module
from engine import config, orders
from engine.assets import ensure_all, is_offline_ready
from engine.catalog import (builder_options, categories_with_counts,
                            get_product, list_addons, list_occasions,
                            list_products)
from engine.db import init_db, session as db_session
from engine.export import export_catalog
from engine.graphics import generate_all
from engine.photos import fetch_all, missing_slugs

# static_folder — папка со статикой, отдаётся по адресу /static/...
# Шаблонизатор не используем: vikanastya.html отдаётся как есть,
# чтобы этот же файл открывался и двойным кликом, без сервера.
app = Flask(__name__, static_folder="static", static_url_path="/static")

# Ключ для подписи cookie-сессии. На реальном сервере задаётся
# переменной окружения, локально берётся значение из config.py.
app.secret_key = os.environ.get("JARDIN_SECRET", config.SECRET_KEY)

WISHLIST_KEY = "wishlist"


# =====================================================================
# СТРАНИЦЫ
# =====================================================================
@app.route("/")
def index():
    """Главная страница — тот самый vikanastya.html из корня проекта."""
    return send_from_directory(config.BASE_DIR, "vikanastya.html")


@app.route("/style.css")
def style():
    """Основной файл стилей лежит в корне рядом с HTML."""
    return send_from_directory(config.BASE_DIR, "style.css")


@app.route("/<path:filename>.jpeg")
@app.route("/<path:filename>.jpg")
def root_images(filename):
    """Картинки из корня проекта (фон шапки из макета и т.п.)."""
    for ext in (".jpeg", ".jpg"):
        if (config.BASE_DIR / f"{filename}{ext}").exists():
            return send_from_directory(config.BASE_DIR, f"{filename}{ext}")
    return ("Файл не найден", 404)


# =====================================================================
# API КАТАЛОГА
# ---------------------------------------------------------------------
# Каждый обработчик делает одно и то же: разбирает параметры запроса,
# зовёт нужную функцию движка и отдаёт результат в формате JSON.
# =====================================================================
# Границы разумных значений. Всё, что приходит из браузера, обязано
# в них укладываться — иначе это не покупатель, а любопытный с консолью.
MAX_MONEY = 100_000_000      # сто миллионов тенге: заведомо больше любого букета
MAX_INDEX = 10_000           # позиций в корзине столько быть не может


def _int_or_none(value):
    """'12000' -> 12000, '' и мусор -> None. Пустой фильтр = нет фильтра.

    Почему не просто int(float(value)):
      • float('1e400') даёт бесконечность, а int(inf) роняет обработчик;
      • число длиной в 20 цифр не влезает в целое SQLite, и запрос
        падает уже внутри базы.
    Оба случая находились нагрузочным тестом и давали ошибку 500.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    # isfinite отсекает бесконечность и «не число» (nan)
    if not math.isfinite(number):
        return None

    return max(0, min(MAX_MONEY, int(number)))


def _int(value, default=0, low=None, high=None):
    """Безопасное целое из чего угодно, с необязательными границами.

    Браузер присылает JSON, и там вместо числа легко может оказаться
    строка, None или список. int() на них выбрасывает исключение,
    а посетитель видит ошибку сервера вместо понятного сообщения.
    """
    try:
        number = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default

    if low is not None:
        number = max(low, number)
    if high is not None:
        number = min(high, number)
    return number


# =====================================================================
# ОБЩАЯ ЗАЩИТА ОТ ОШИБОК
# ---------------------------------------------------------------------
# Пока обработчиков нет, любая необработанная ошибка отдаёт браузеру
# страницу с трейсбеком. Для посетителя это пугающая мешанина, а для
# постороннего — карта проекта: пути к файлам, имена таблиц, куски кода.
# Поэтому наружу уходит короткий JSON, а подробности пишутся в консоль
# сервера, где их видит владелец сайта.
# =====================================================================
@app.errorhandler(404)
def handle_404(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Адрес не найден"}), 404
    return "Страница не найдена. <a href='/'>На главную</a>", 404


@app.errorhandler(405)
def handle_405(error):
    return jsonify({"error": "Этот адрес не принимает такой запрос"}), 405


@app.errorhandler(Exception)
def handle_any_error(error):
    """Ловит всё, что не поймали обработчики выше."""
    # HTTP-ошибки (те же 404/405) пропускаем дальше как есть
    from werkzeug.exceptions import HTTPException
    if isinstance(error, HTTPException):
        return error

    # Подробности — в консоль владельцу сайта
    app.logger.exception("Необработанная ошибка на %s", request.path)

    if request.path.startswith("/api/"):
        return jsonify({"error": "Салон временно недоступен, попробуйте ещё раз"}), 500
    return "Что-то пошло не так. <a href='/'>Вернуться на главную</a>", 500


@app.get("/api/settings")
def api_settings():
    """Валюта, контакты и правила доставки — фронтенд берёт их отсюда."""
    return jsonify({
        "currency": config.CURRENCY,
        "city": config.CITY,
        "free_delivery_from": config.FREE_DELIVERY_FROM,
        "delivery_cost": config.DELIVERY_COST,
        "urgent_surcharge": config.URGENT_DELIVERY_SURCHARGE,
        "contacts": config.CONTACTS,
        "categories": categories_with_counts(),
        "occasions": list_occasions(),
        "addons": list_addons(),
    })


@app.get("/api/catalog")
def api_catalog():
    """Список букетов по фильтрам. Вызывается при каждом действии в каталоге."""
    args = request.args
    products = list_products(
        category=args.get("category"),
        query=args.get("q"),
        min_price=_int_or_none(args.get("min_price")),
        max_price=_int_or_none(args.get("max_price")),
        only_in_stock=args.get("in_stock") == "1",
        only_discount=args.get("discount") == "1",
        occasion=args.get("occasion"),
        sort=args.get("sort", "popular"),
    )
    return jsonify({"items": products, "total": len(products)})


@app.get("/api/occasions")
def api_occasions():
    """Поводы для покупки: день рождения, любимой, благодарность и т.д."""
    return jsonify({"items": list_occasions()})


@app.get("/api/addons")
def api_addons():
    """Дополнения к букету — ваза, шоколад, открытка, шар."""
    return jsonify({"items": list_addons()})


@app.post("/api/cart/addon")
def api_cart_addon():
    """Добавляет дополнение к заказу или убирает его."""
    data = request.get_json(silent=True) or {}
    try:
        cart_module.toggle_addon(session, str(data.get("slug", ""))[:40])
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return _cart_response()


@app.get("/api/product/<int:product_id>")
def api_product(product_id):
    """Один букет для окна быстрого просмотра."""
    product = get_product(product_id=product_id)
    if product is None:
        return jsonify({"error": "Букет не найден"}), 404
    return jsonify(product)


@app.get("/api/builder")
def api_builder():
    """Опции конструктора: цветы, зелень, упаковка — с ценами из базы."""
    return jsonify(builder_options())


@app.post("/api/builder/price")
def api_builder_price():
    """Пересчёт цены авторского букета при каждом клике в конструкторе.

    Считает сервер, а не браузер: браузерный расчёт нужен только для
    мгновенной подсветки, доверять ему при оформлении нельзя.
    """
    data = request.get_json(silent=True) or {}
    return jsonify(cart_module.price_custom_bouquet(
        data.get("base", []), data.get("greenery", []), data.get("package")
    ))


# =====================================================================
# API КОРЗИНЫ
# =====================================================================
def _cart_response():
    """Единый ответ на любое действие с корзиной — её полное состояние."""
    return jsonify(cart_module.build_state(
        session,
        promo_code=session.get("promo_code"),
        time_slot=session.get("time_slot"),
    ))


@app.get("/api/cart")
def api_cart():
    return _cart_response()


@app.post("/api/cart/add")
def api_cart_add():
    data = request.get_json(silent=True) or {}
    if data.get("product_id") is None:
        return jsonify({"error": "Не указан товар"}), 400

    product_id = _int(data.get("product_id"), default=0)
    if product_id <= 0 or get_product(product_id=product_id) is None:
        return jsonify({"error": "Букет не найден"}), 404

    cart_module.add_product(session, product_id,
                            _int(data.get("qty"), default=1, low=1,
                                 high=config.MAX_QTY_PER_ITEM))
    return _cart_response()


@app.post("/api/cart/add-custom")
def api_cart_add_custom():
    """Добавление букета из конструктора."""
    data = request.get_json(silent=True) or {}
    try:
        cart_module.add_custom(
            session,
            data.get("base", []),
            data.get("greenery", []),
            data.get("package"),
            data.get("postcard", ""),
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return _cart_response()


@app.post("/api/cart/qty")
def api_cart_qty():
    data = request.get_json(silent=True) or {}
    cart_module.set_qty(session,
                        _int(data.get("index"), default=-1, low=-1, high=MAX_INDEX),
                        _int(data.get("qty"), default=1, low=1,
                             high=config.MAX_QTY_PER_ITEM))
    return _cart_response()


@app.post("/api/cart/remove")
def api_cart_remove():
    data = request.get_json(silent=True) or {}
    cart_module.remove(session, _int(data.get("index"), default=-1, low=-1, high=MAX_INDEX))
    return _cart_response()


@app.post("/api/cart/clear")
def api_cart_clear():
    cart_module.clear(session)
    session.pop("promo_code", None)
    return _cart_response()


@app.post("/api/cart/promo")
def api_cart_promo():
    """Проверка промокода. Удачный код запоминается в сессии."""
    data = request.get_json(silent=True) or {}
    state = cart_module.build_state(session)
    result = cart_module.check_promo(data.get("code"), state["subtotal"])

    if result["ok"]:
        session["promo_code"] = result["code"]
    else:
        session.pop("promo_code", None)

    return _cart_response()


@app.post("/api/cart/slot")
def api_cart_slot():
    """Интервал доставки влияет на цену курьера, поэтому храним его в сессии."""
    data = request.get_json(silent=True) or {}
    slot = data.get("time_slot")
    if slot in orders.TIME_SLOTS:
        session["time_slot"] = slot
    return _cart_response()


# =====================================================================
# API ИЗБРАННОГО
# =====================================================================
@app.get("/api/wishlist")
def api_wishlist():
    ids = session.get(WISHLIST_KEY, [])
    products = [p for p in (get_product(product_id=i) for i in ids) if p]
    return jsonify({"items": products, "ids": ids})


@app.post("/api/wishlist/toggle")
def api_wishlist_toggle():
    """Добавляет товар в избранное или убирает, если он уже там."""
    data = request.get_json(silent=True) or {}
    product_id = _int(data.get("product_id"), default=0)
    if product_id <= 0 or get_product(product_id=product_id) is None:
        return jsonify({"error": "Букет не найден"}), 404

    ids = list(session.get(WISHLIST_KEY, []))

    if product_id in ids:
        ids.remove(product_id)
        added = False
    else:
        ids.append(product_id)
        added = True

    session[WISHLIST_KEY] = ids
    products = [p for p in (get_product(product_id=i) for i in ids) if p]
    return jsonify({"items": products, "ids": ids, "added": added})


# =====================================================================
# API ЗАКАЗА И ПОДПИСКИ
# =====================================================================
@app.post("/api/order")
def api_order():
    """Оформление заказа. Возвращает номер и подробности для окна успеха."""
    data = request.get_json(silent=True) or {}
    try:
        result = orders.create_order(session, data)
    except orders.ValidationError as error:
        # 400 — «клиент прислал неверные данные», это ожидаемая ситуация
        return jsonify({"error": str(error)}), 400

    session.pop("promo_code", None)
    return jsonify(result)


@app.post("/api/subscribe")
def api_subscribe():
    """Подписка на рассылку из подвала — выдаёт промокод на скидку."""
    from datetime import datetime

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    # Проверка адреса нарочно простая: есть «собака», есть точка после неё
    if "@" not in email or "." not in email.split("@")[-1] or len(email) < 6:
        return jsonify({"error": "Проверьте адрес электронной почты"}), 400

    with db_session() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO subscribers (email, created_at, promo) VALUES (?,?,?)",
            (email, datetime.now().isoformat(timespec="seconds"), "JARDIN2500"),
        )

    return jsonify({
        "ok": True,
        "promo": "JARDIN2500",
        "message": "Промокод JARDIN2500 на 2 500 ₸ отправлен на вашу почту",
    })


# =====================================================================
# СЛУЖЕБНАЯ СТРАНИЦА: заказы салона
# =====================================================================
@app.get("/admin")
def admin():
    """Простой список заказов для флориста. Собирается прямо здесь, из строк."""
    rows = orders.list_orders()

    # ВАЖНО: всё, что пришло от посетителя (имя, адрес, комментарий),
    # проходит через escape(). Без этого имя вида <script>…</script>
    # выполнится прямо в браузере флориста — это XSS. Простое правило:
    # данные пользователя никогда не попадают в HTML напрямую.
    def money(value):
        return f"{value:,}".replace(",", " ") + f" {config.CURRENCY}"

    if not rows:
        body = "<p class='empty'>Заказов пока нет. Оформите первый на главной странице.</p>"
    else:
        cards = []
        for order in rows:
            items = "".join(
                f"<li>{escape(item['title'])} × {item['qty']} — {money(item['line_total'])}</li>"
                for item in order["items"]
            )
            slot = orders.TIME_SLOTS.get(order["time_slot"], order["time_slot"])
            payment = orders.PAYMENT_METHODS.get(order["payment_method"], order["payment_method"])
            cards.append(f"""
            <article class="order">
              <header>
                <h2>#{escape(order['number'])}</h2>
                <time>{escape(order['created_at'].replace('T', ' '))}</time>
              </header>
              <p><b>Заказчик:</b> {escape(order['sender_name'])}, {escape(order['sender_phone'])}</p>
              <p><b>Кому:</b> {escape(order['recipient_name'] or '—')} {escape(order['recipient_phone'] or '')}</p>
              <p><b>Адрес:</b> {escape(order['address'])}</p>
              <p><b>Доставка:</b> {escape(order['delivery_date'])}, {escape(slot)}</p>
              <p><b>Оплата:</b> {escape(payment)}</p>
              {f"<p><b>Комментарий:</b> {escape(order['comment'])}</p>" if order['comment'] else ''}
              {f"<p><b>Открытка:</b> {escape(order['postcard'])}</p>" if order['postcard'] else ''}
              <ul>{items}</ul>
              <p class="total">Итого: {money(order['total'])}</p>
            </article>""")
        body = "".join(cards)

    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<title>Заказы — Jardin Rose</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background: #FAF5F6; color: #2D2022;
         margin: 0; padding: 30px 20px; }}
  h1 {{ color: #4E131A; }}
  .order {{ background: #fff; border: 1px solid #F1CED1; border-radius: 14px;
            padding: 18px 22px; margin-bottom: 16px; max-width: 760px; }}
  .order header {{ display: flex; justify-content: space-between; align-items: baseline; }}
  .order h2 {{ margin: 0; color: #7A2530; font-size: 1.2rem; }}
  .order time {{ color: #786466; font-size: .85rem; }}
  .order p {{ margin: 4px 0; font-size: .9rem; }}
  .order ul {{ margin: 10px 0; padding-left: 20px; font-size: .9rem; }}
  .total {{ font-weight: 700; color: #4E131A; font-size: 1.05rem; }}
  .empty {{ color: #786466; }}
  a {{ color: #7A2530; }}
</style></head>
<body>
  <h1>Заказы салона Jardin Rose</h1>
  <p><a href="/">← Вернуться на витрину</a></p>
  {body}
</body></html>"""


# =====================================================================
# ЗАПУСК
# =====================================================================
def bootstrap():
    """Подготовка перед первым запросом: база, картинки, офлайн-данные.

    Порядок такой:
      1) создать базу и залить каталог, если её ещё нет;
      2) докачать фотографии букетов (только те, которых нет на диске);
      3) дорисовать вспомогательную графику — лепестки, паттерн, фавиконку;
      4) выгрузить снимок каталога для работы сайта без сервера.
    """
    print("Jardin Rose · подготовка движка")
    init_db()
    print(f"  база данных: {config.DB_PATH}")

    created_assets = ensure_all(verbose=False)
    ready, checks = is_offline_ready()
    if created_assets:
        print(f"  шрифты и иконки: скачано файлов {created_assets}")
    print(f"  работа без интернета: {'готова' if ready else 'НЕ ГОТОВА — ' + ', '.join(k for k, v in checks.items() if not v)}")

    absent = missing_slugs()
    if absent:
        print(f"  нет фотографий для {len(absent)} букетов — скачиваю…")
        downloaded, drawn, failed = fetch_all(verbose=False)
        print(f"  фотографии: скачано {downloaded}, нарисовано генератором {drawn}, "
              f"не получилось {failed}")
    else:
        print("  фотографии букетов: на месте")

    # Букеты уже есть (фото), поэтому генератору остаются только
    # лепестки для анимации, фоновый паттерн, баннер и фавиконка.
    created = generate_all(force=False, verbose=False, animations=False, bouquets=False)
    print(f"  графика: {'создано файлов ' + str(created) if created else 'уже готова'}")

    export_catalog()
    print("  каталог выгружен в static/js/catalog-data.js")


def local_ip():
    """Адрес этого компьютера в домашней сети — по нему зайдёт телефон.

    Хитрость: мы «открываем» соединение к публичному адресу, но ничего
    не отправляем. Система при этом выбирает сетевую карту, через
    которую пошёл бы трафик, и сообщает её адрес. Это надёжнее, чем
    socket.gethostbyname(hostname): тот часто отвечает 127.0.0.1.
    """
    import socket
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


if __name__ == "__main__":
    bootstrap()

    url = "http://127.0.0.1:5000"
    phone_ip = local_ip()

    print(f"\n  Сайт на этом компьютере:  {url}")
    print(f"  Заказы флориста:          {url}/admin")

    if phone_ip:
        print(f"\n  С ТЕЛЕФОНА (в той же сети Wi-Fi):")
        print(f"      http://{phone_ip}:5000")
        print("  Если не открывается — разрешите Python в брандмауэре Windows")
        print("  или подключите телефон к тому же Wi-Fi, что и компьютер.\n")

    # Открываем браузер через секунду после старта сервера
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        Timer(1.0, lambda: webbrowser.open(url)).start()

    # host="0.0.0.0" — принимать запросы не только от самого компьютера,
    # но и от других устройств домашней сети. Без этого телефон
    # достучаться не сможет: сервер слушал бы только 127.0.0.1.
    app.run()
