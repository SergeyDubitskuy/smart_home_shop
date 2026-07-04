import psycopg2
import psycopg2.extras
import pymongo
from flask import g, current_app
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import json
import random
def get_pg():
    if 'pg' not in g:
        g.pg = psycopg2.connect(current_app.config['PG_DSN'])
        g.pg_cursor = g.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    return g.pg, g.pg_cursor
def get_mongo():
    if 'mongo_client' not in g:
        g.mongo_client = pymongo.MongoClient(current_app.config['MONGO_URI'])
        g.mongo = g.mongo_client['smart_home_db']
    return g.mongo
def close_db(exception):
    pg = g.pop('pg', None)
    if pg:
        pg.close()
    mongo_client = g.pop('mongo_client', None)
    if mongo_client:
        mongo_client.close()
def get_avg_rating(product_id):
    mongo = get_mongo()
    reviews = list(mongo.reviews.find({"product_id": product_id}))
    if not reviews:
        return 0.0
    return sum(r["rating"] for r in reviews) / len(reviews)
def format_rating(r):
    return f"{r:.1f}" if r > 0 else "Нет оценок"
def init_db():
    pg, cursor = get_pg()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            description TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            category_id INTEGER REFERENCES categories(id),
            name VARCHAR(200) NOT NULL,
            description TEXT,
            price DECIMAL(10,2) CHECK (price >= 0),
            stock INTEGER DEFAULT 0 CHECK (stock >= 0),
            rating DECIMAL(2,1) DEFAULT 0,
            is_popular BOOLEAN DEFAULT false,
            analogs JSONB DEFAULT '[]',
            image_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            order_number VARCHAR(50) UNIQUE NOT NULL,
            customer_name VARCHAR(200) NOT NULL,
            phone VARCHAR(20) NOT NULL,
            email VARCHAR(100),
            address TEXT NOT NULL,
            comment TEXT,
            total DECIMAL(10,2) NOT NULL,
            status VARCHAR(20) DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id SERIAL PRIMARY KEY,
            order_id INTEGER REFERENCES orders(id),
            product_id INTEGER REFERENCES products(id),
            quantity INTEGER NOT NULL,
            price DECIMAL(10,2) NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    pg.commit()
    cursor.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='products' AND column_name='image_url'
    """)
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE products ADD COLUMN image_url TEXT")
        pg.commit()
    cursor.execute("SELECT COUNT(*) FROM categories")
    if cursor.fetchone()['count'] == 0:
        categories = [
            ("Освещение", "Умные лампы, светильники и системы освещения"),
            ("Датчики и безопасность", "Датчики движения, протечки, открытия"),
            ("Розетки и реле", "Умные розетки, выключатели, реле"),
            ("Климат-контроль", "Термостаты, кондиционеры, увлажнители"),
            ("Бытовая техника", "Роботы-пылесосы, чайники, кофемашины"),
            ("Управление и хабы", "Хабы, голосовые помощники, панели"),
            ("Мультимедиа", "Телевизоры, колонки, медиаплееры"),
            ("Шторы и жалюзи", "Автоматические шторы и карнизы"),
            ("Полив и сад", "Системы автополива, садовые датчики"),
            ("Отопление", "Умные радиаторы, теплые полы"),
            ("Вентиляция", "Рекуператоры, очистители воздуха"),
            ("Замки и доступ", "Умные замки, домофоны"),
            ("Камеры", "Видеокамеры, видеодомофоны"),
            ("Сигнализации", "Охранные системы, сирены"),
            ("Энергомониторинг", "Счетчики, мониторы потребления")
        ]
        cursor.executemany(
            "INSERT INTO categories (name, description) VALUES (%s, %s)",
            categories
        )
        pg.commit()
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()['count'] == 0:
        products_data = [
            (1, "LED лампа E27 9W", "Умная лампа с регулировкой яркости и цвета, Wi-Fi", 890, 150, True,
             '[{"name":"E27 RGB Pro","price":1290},{"name":"E27 Mini","price":590}]'),
            (1, "Светодиодная лента 5м RGB", "Влагозащита IP65, управление через приложение", 1890, 80, True,
             '[{"name":"Лента 10м","price":3200},{"name":"Лента белая","price":1200}]'),
            (1, "Умный выключатель 1-клавишный", "Замена обычного выключателя, работа без нейтрали", 1450, 100, False,
             '[{"name":"2-клавишный","price":1890},{"name":"Сенсорный","price":2100}]'),
            (1, "Настольная лампа с беспроводной зарядкой", "LED, 3 режима яркости, USB-порт", 2490, 45, False,
             '[]'),
            (1, "Уличный прожектор 30W", "Датчик движения, IP65, теплый свет", 3200, 30, True,
             '[{"name":"Прожектор 50W","price":4500}]'),
            (1, "Люстра потолочная LED", "Пульт ДУ, изменение цветовой температуры", 5900, 20, False,
             '[]'),
            (1, "Ночник с датчиком движения", "Автономный, батарейки, мягкий свет", 690, 200, False,
             '[]'),
            (2, "Датчик движения PIR", "Угол 120°, дальность 8м, Zigbee", 1200, 120, True,
             '[{"name":"PIR+Свет","price":1800},{"name":"PIR Outdoor","price":1600}]'),
            (2, "Датчик протечки воды", "Мгновенное уведомление, сирена 80дБ", 950, 150, True,
             '[{"name":"Комплект 3 шт","price":2400}]'),
            (2, "Датчик открытия окна/двери", "Магнитный контакт, батарейка 1 год", 790, 180, False,
             '[{"name":"Датчик+Вибрация","price":1350}]'),
            (2, "Датчик температуры и влажности", "Точность 0.3°C, история данных", 1100, 90, False,
             '[]'),
            (2, "Датчик дыма", "Фотоэлектрический, сирена 85дБ", 1890, 70, True,
             '[{"name":"Датчик+CO","price":2800}]'),
            (2, "Датчик качества воздуха", "PM2.5, CO2, VOC, OLED дисплей", 4500, 35, False,
             '[]'),
            (3, "Умная розетка WiFi", "Макс 3.5кВт, учет энергии, таймер", 890, 200, True,
             '[{"name":"Zigbee Dual","price":1600},{"name":"USB-C 30W","price":1350}]'),
            (3, "Умное реле 16А", "Скрытая установка, работа без нуля", 1190, 85, False,
             '[{"name":"Реле 2-канальное","price":1690}]'),
            (3, "Умный удлинитель 4 розетки", "USB-порты, индивидуальное управление", 2490, 60, True,
             '[]'),
            (3, "Реле времени механическое", "Суточный таймер, 24 программы", 450, 150, False,
             '[]'),
            (3, "Wi-Fi реле с энергомониторингом", "2 канала, MQTT, Home Assistant", 1690, 55, False,
             '[]'),
            (3, "Умный выключатель сцен", "4 сцены, беспроводной, батарейка", 1890, 40, False,
             '[]'),
            (3, "Розетка с USB 2.4A", "2 USB-порта, защита от перегрузки", 690, 180, False,
             '[]'),
            (4, "Умный термостат WiFi", "Поддержка котлов, геозоны, экономия до 30%", 4500, 50, True,
             '[{"name":"Термостат Pro","price":6200},{"name":"Термостат Lite","price":3200}]'),
            (4, "Увлажнитель воздуха 4л", "Ультразвуковой, гигростат, тихий", 3200, 65, True,
             '[{"name":"Увлажнитель+Очистка","price":5900}]'),
            (4, "Контроллер для кондиционера", "Управление ИК-кондиционером, геозоны", 2890, 70, False,
             '[{"name":"Контроллер+Датчик","price":3500}]'),
            (4, "Очиститель воздуха HEPA", "CADR 300м³/ч, ионизация, UV", 7900, 30, True,
             '[]'),
            (4, "Тепловентилятор умный", "2кВт, таймер, защита от перегрева", 3490, 45, False,
             '[]'),
            (4, "Метеостанция домашняя", "Температура, влажность, давление", 2100, 55, False,
             '[]'),
            (5, "Робот-пылесос с картографией", "Лазерная навигация, влажная уборка", 18900, 25, True,
             '[{"name":"Робот+Станция","price":29900},{"name":"Робот Базовый","price":12900}]'),
            (5, "Умный чайник 1.7л", "Выбор температуры 40-100°C, голос", 2490, 80, True,
             '[{"name":"Чайник+Термопот","price":3900}]'),
            (5, "Кофемашина капсульная", "15 бар, 6 программ, WiFi", 12900, 35, False,
             '[]'),
            (5, "Мультиварка 5л", "45 программ, отложенный старт", 5900, 40, False,
             '[]'),
            (5, "Микроволновка с грилем", "20л, 800Вт, гриль 1000Вт", 8900, 30, False,
             '[]'),
            (5, "Посудомоечная машина 6 комплектов", "6 программ, тихая 49дБ", 24900, 15, True,
             '[]'),
            (5, "Холодильник No Frost", "250л, A++, инвертор", 32900, 10, False,
             '[]'),
            (6, "Умная колонка с экраном", "Голосовой помощник, 8 дюймов", 7900, 60, True,
             '[{"name":"Колонка Pro","price":12900},{"name":"Колонка Мини","price":3900}]'),
            (6, "Хаб Zigbee 3.0", "Поддержка 100 устройств, локальное управление", 3900, 75, True,
             '[{"name":"Хаб+Датчик","price":4500}]'),
            (6, "Пульт универсальный ИК", "Управление ТВ, кондиционером, приложение", 1290, 120, False,
             '[]'),
            (6, "Планшет для умного дома", "7 дюймов, настенный, Android", 8900, 25, False,
             '[]'),
            (6, "Кнопка сценариев беспроводная", "4 сцены, Zigbee, батарейка 2 года", 990, 100, False,
             '[]'),
            (6, "Голосовой помощник Mini", "Без экрана, только голос", 2900, 90, True,
             '[]'),
            (7, "Smart TV 43 4K", "HDR10, Netflix, YouTube, голос", 28900, 20, True,
             '[{"name":"TV 55 4K","price":42900},{"name":"TV 32 HD","price":16900}]'),
            (7, "Медиаплеер 4K", "Android TV, Dolby Vision, 2GB RAM", 4900, 55, False,
             '[]'),
            (7, "Саундбар 2.1", "120Вт, сабвуфер, Bluetooth", 8900, 35, True,
             '[{"name":"Саундбар 5.1","price":15900}]'),
            (7, "Проектор Full HD", "3000 люмен, WiFi, 100 дюймов", 24900, 15, False,
             '[]'),
            (7, "Игровая консоль", "4K, 1TB, 2 контроллера", 34900, 12, True,
             '[]'),
            (7, "Наушники беспроводные", "ANC, 30ч работы, влагозащита", 5900, 70, False,
             '[]'),
            (7, "Экран для проектора 100", "Ручной, матовый, 16:9", 3900, 25, False,
             '[]'),
            (8, "Электрокарниз для штор 3м", "Пульт ДУ, таймер, тихий мотор", 8900, 30, True,
             '[{"name":"Карниз 4м","price":11900},{"name":"Карниз 2м","price":6900}]'),
            (8, "Умные жалюзи рулонные", "WiFi, расписание, датчик света", 5900, 40, False,
             '[]'),
            (8, "Привод для штор", "Отдельный мотор, до 50кг", 4500, 35, False,
             '[]'),
            (8, "Карниз для ванной электрический", "1.8м, влагозащита", 6900, 20, False,
             '[]'),
            (8, "Жалюзи вертикальные авто", "Пульт, ткань блэкаут", 7900, 25, True,
             '[]'),
            (8, "Штора рулонная день-ночь", "Ручное управление, 120x180", 1890, 60, False,
             '[]'),
            (9, "Контроллер полива 6 зон", "WiFi, расписание, датчик дождя", 6900, 35, True,
             '[{"name":"Контроллер 12 зон","price":9900}]'),
            (9, "Система автополива капельная", "50м шланг, 30 капельниц", 2490, 50, False,
             '[]'),
            (9, "Насос для полива", "4000л/ч, автоматический", 4500, 30, False,
             '[]'),
            (9, "Датчик влажности почвы", "Zigbee, уведомление", 1290, 70, False,
             '[]'),
            (9, "Фитосветильник для растений", "30W, полный спектр, таймер", 2890, 45, True,
             '[]'),
            (9, "Теплица умная", "Автопроветривание, полив, 3x6м", 45900, 8, False,
             '[]'),
            (9, "Газонокосилка робот", "До 1000м², GPS, дождь-сенсор", 54900, 6, True,
             '[]'),
            (10, "Термоголовка на батарею", "Электронная, расписание, WiFi", 2890, 80, True,
             '[{"name":"Термоголовка Zigbee","price":3490}]'),
            (10, "Конвектор электрический 2кВт", "WiFi, таймер, защита", 4900, 40, False,
             '[]'),
            (10, "Теплый пол мат 2м²", "140Вт/м², терморегулятор", 3900, 35, True,
             '[]'),
            (10, "Инфракрасный обогреватель", "1.5кВт, потолочный, пульт", 3490, 45, False,
             '[]'),
            (10, "Котел электрический 9кВт", "3 контура, WiFi, модуляция", 28900, 12, False,
             '[]'),
            (10, "Бойлер 80л", "Накопительный, сухой ТЭН, Wi-Fi", 12900, 25, True,
             '[]'),
            (11, "Рекуператор настенный", "До 50м², WiFi, КПД 85%", 18900, 15, True,
             '[]'),
            (11, "Вытяжка кухонная", "60см, 750м³/ч, сенсор", 8900, 30, False,
             '[]'),
            (11, "Вентилятор канальный", "150м³/ч, тихий, регулятор", 2490, 50, False,
             '[]'),
            (11, "Осушитель воздуха", "20л/сутки, гигростат, 250Вт", 12900, 20, False,
             '[]'),
            (11, "Вентилятор с датчиком влажности", "100мм, автозапуск", 1890, 60, True,
             '[]'),
            (11, "Приточная установка", "До 100м², фильтрация, нагрев", 24900, 10, False,
             '[]'),
            (12, "Умный замок с отпечатком", "5 способов открытия, WiFi", 8900, 45, True,
             '[{"name":"Замок Pro","price":12900},{"name":"Замок Basic","price":5900}]'),
            (12, "Видеодомофон 7 дюймов", "2 камеры, запись, WiFi", 12900, 35, True,
             '[{"name":"Домофон 10 дюймов","price":18900}]'),
            (12, "Электрозащелка", "Нормально закрыта, 12В", 1890, 80, False,
             '[]'),
            (12, "Считыватель карт RFID", "125кГц, Wiegand, влагозащита", 2490, 60, False,
             '[]'),
            (12, "Кодовая панель", "Сенсорная, 100 кодов, подсветка", 3490, 50, True,
             '[]'),
            (12, "Доводчик дверной", "До 80кг, регулировка скорости", 2890, 40, False,
             '[]'),
            (12, "Кнопка выхода", "Сенсорная, подсветка", 890, 100, False,
             '[]'),
            (13, "IP камера уличная 2K", "POE, ИК 30м, детекция", 4900, 70, True,
             '[{"name":"Камера 4K","price":7900},{"name":"Камера WiFi","price":3200}]'),
            (13, "Камера видеонаблюдения 360", "Панорамная, 4Мп, WiFi", 3900, 60, False,
             '[]'),
            (13, "Видеорегистратор 4 канала", "4K, 2TB HDD, POE", 12900, 25, True,
             '[{"name":"Регистратор 8 каналов","price":18900}]'),
            (13, "Камера скрытая", "Mini, 1080p, датчик движения", 1890, 90, False,
             '[]'),
            (13, "Камера с солнечной панелью", "Беспроводная, 4G, аккумулятор", 8900, 30, True,
             '[]'),
            (13, "Детская камера-няня", "2-сторонняя связь, ночник, колыбельная", 4500, 45, False,
             '[]'),
            (13, "Комплект 4 камеры", "1080p, WiFi, облако", 15900, 20, True,
             '[]'),
            (14, "Охранная система GSM", "8 зон, сирена, приложение", 6900, 40, True,
             '[{"name":"Система WiFi","price":5900},{"name":"Система Pro","price":9900}]'),
            (14, "Сирена уличная", "120дБ, стробоскоп, IP65", 2490, 55, False,
             '[]'),
            (14, "Панель управления", "Сенсорный экран, WiFi, RFID", 4900, 35, True,
             '[]'),
            (14, "Брелок тревожный", "4 кнопки, до 100м", 890, 120, False,
             '[]'),
            (14, "Датчик разбития стекла", "Акустический, до 6м", 1490, 70, False,
             '[]'),
            (14, "GSM модуль", "4 зоны, SMS, звонки", 2890, 50, False,
             '[]'),
            (15, "Счетчик электроэнергии 3-фазный", "WiFi, MQTT, точность 1%", 3900, 45, True,
             '[{"name":"Счетчик 1-фазный","price":2490}]'),
            (15, "Монитор потребления", "Дисплей, история, 100А", 2890, 60, False,
             '[]'),
            (15, "Реле контроля напряжения", "40А, защита 100-400В", 1890, 80, True,
             '[]'),
            (15, "Умный щиток", "8 модулей, WiFi, учет", 8900, 25, False,
             '[]'),
            (15, "Датчик тока бесконтактный", "До 200А, Zigbee", 2490, 50, False,
             '[]'),
            (15, "ИБП 1000VA", "Линейно-интерактивный, USB", 6900, 35, True,
             '[{"name":"ИБП 1500VA","price":9900}]'),
        ]
        products_with_images = []
        for i, p in enumerate(products_data, start=1):
            image_filename = f"{i}.jpg"
            products_with_images.append(p + (image_filename,))
        cursor.executemany("""
            INSERT INTO products (category_id, name, description, price, stock, is_popular, analogs, image_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, products_with_images)
        pg.commit()
        print(f"Добавлено {len(products_data)} товаров в 15 категориях")
        generate_reviews()
    else:
        cursor.execute("UPDATE products SET image_url = id::text || '.jpg' WHERE image_url IS NULL")
        pg.commit()
def generate_reviews():
    mongo = get_mongo()
    existing_reviews = mongo.reviews.count_documents({})
    if existing_reviews > 0:
        print(f"Отзывы уже существуют ({existing_reviews} шт.). Пропускаем генерацию.")
        return
    pg, cursor = get_pg()
    cursor.execute("SELECT id FROM products")
    products = cursor.fetchall()
    authors = [
        "Алексей", "Мария", "Дмитрий", "Елена", "Сергей", "Анна", "Иван", "Ольга",
        "Николай", "Татьяна", "Андрей", "Екатерина", "Владимир", "Наталья", "Михаил",
        "Юлия", "Павел", "Светлана", "Константин", "Ирина", "Александр", "Виктория",
        "Роман", "Людмила", "Артём", "Ксения", "Максим", "Дарья", "Евгений", "Полина",
        "Аноним", "Покупатель", "Клиент", "Довольный пользователь"
    ]
    reviews_5_stars = [
        "Отличный товар! Полностью соответствует описанию. Рекомендую!",
        "Превосходное качество! Пользуюсь уже месяц, никаких нареканий.",
        "Лучшая покупка в этом году! Всё работает идеально.",
        "Замечательный товар за свои деньги. Очень доволен!",
        "Качество на высоте, доставка быстрая. Спасибо!",
        "Отличный продукт! Работает стабильно, настройки интуитивные.",
        "Просто супер! Все функции работают как заявлено.",
        "Рекомендую всем! Отличное соотношение цена-качество.",
        "Пользуюсь каждый день, очень удобно и практично.",
        "Идеальный выбор! Соответствует всем ожиданиям."
    ]
    reviews_4_stars = [
        "Хороший товар, но есть мелкие недочеты. В целом доволен.",
        "Качественная вещь, работает стабильно. Четыре звезды за цену.",
        "Неплохой продукт, но ожидал немного большего.",
        "В целом всё хорошо, но инструкция могла бы быть подробнее.",
        "Работает хорошо, но настройка заняла больше времени, чем ожидал.",
        "Добротный товар за свои деньги. Рекомендую.",
        "Качество хорошее, но упаковка могла бы быть лучше.",
        "Пользуюсь вторую неделю, пока всё устраивает."
    ]
    reviews_3_stars = [
        "Средний товар. Есть как плюсы, так и минусы.",
        "Работает, но не без проблем. За такую цену ожидал большего.",
        "Нормальный продукт, но есть куда расти.",
        "Троек за функционал, но качество сборки среднее.",
        "Пойдет для базовых задач, но для продвинутых не подойдет.",
        "Обычный товар без изюминки. Свои функции выполняет."
    ]
    reviews_2_stars = [
        "Товар не оправдал ожиданий. Есть серьезные недочеты.",
        "Работает нестабильно, приходится постоянно перенастраивать.",
        "Качество ниже среднего. Не рекомендую к покупке.",
        "Разочарован покупкой. Лучше выбрать другой вариант.",
        "Функции работают, но с перебоями. Не стоит своих денег.",
        "Ожидал большего за эту цену. Придется возвращать."
    ]
    reviews_1_star = [
        "Ужасный товар! Сломался через неделю использования.",
        "Полное разочарование. Не работает как заявлено.",
        "Крайне не рекомендую! Потраченные деньги.",
        "Брак с завода. Вернул сразу после получения.",
        "Не соответствует описанию. Обман покупателей.",
        "Худшая покупка в моей жизни. Избегайте этого товара."
    ]
    total_reviews = 0
    for product in products:
        product_id = product['id']
        num_reviews = random.randint(3, 23)
        for _ in range(num_reviews):
            rating_weights = [5, 10, 15, 30, 40]
            rating = random.choices([1, 2, 3, 4, 5], weights=rating_weights)[0]
            if rating == 5:
                text = random.choice(reviews_5_stars)
            elif rating == 4:
                text = random.choice(reviews_4_stars)
            elif rating == 3:
                text = random.choice(reviews_3_stars)
            elif rating == 2:
                text = random.choice(reviews_2_stars)
            else:
                text = random.choice(reviews_1_star)
            author = random.choice(authors)
            days_ago = random.randint(1, 180)
            created_at = datetime.utcnow() - timedelta(days=days_ago)
            mongo.reviews.insert_one({
                "product_id": product_id,
                "author": author,
                "text": text,
                "rating": rating,
                "created_at": created_at
            })
            total_reviews += 1
    print(f"Сгенерировано {total_reviews} отзывов для {len(products)} товаров")
def create_order(customer_name, phone, email, address, comment, items, total):
    pg, cursor = get_pg()
    order_number = f"SH-{int(datetime.utcnow().timestamp())}"
    cursor.execute("""
        INSERT INTO orders (order_number, customer_name, phone, email, address, comment, total, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (order_number, customer_name, phone, email, address, comment, total, 'new'))
    order_id = cursor.fetchone()['id']
    for item in items:
        cursor.execute("""
            INSERT INTO order_items (order_id, product_id, quantity, price)
            VALUES (%s, %s, %s, %s)
        """, (order_id, item['product']['id'], item['qty'], item['product']['price']))
        cursor.execute("UPDATE products SET stock = stock - %s WHERE id = %s",
                      (item['qty'], item['product']['id']))
    pg.commit()
    return order_number
def get_order_by_number(order_number):
    pg, cursor = get_pg()
    cursor.execute("SELECT * FROM orders WHERE order_number = %s", (order_number,))
    return cursor.fetchone()
def get_order_items(order_id):
    pg, cursor = get_pg()
    cursor.execute("""
        SELECT oi.*, p.name, p.image_url, c.name as category_name
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        JOIN categories c ON p.category_id = c.id
        WHERE oi.order_id = %s
    """, (order_id,))
    return cursor.fetchall()
def create_user(username, email, password):
    pg, cursor = get_pg()
    password_hash = generate_password_hash(password)
    try:
        cursor.execute("""
            INSERT INTO users (username, email, password_hash)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (username, email, password_hash))
        pg.commit()
        return cursor.fetchone()['id']
    except psycopg2.IntegrityError:
        pg.rollback()
        return None
def get_user_by_username(username):
    pg, cursor = get_pg()
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    return cursor.fetchone()
def get_user_by_email(email):
    pg, cursor = get_pg()
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    return cursor.fetchone()
def verify_user(username, password):
    user = get_user_by_username(username)
    if user and check_password_hash(user['password_hash'], password):
        return user
    return None
def get_user_by_id(user_id):
    pg, cursor = get_pg()
    cursor.execute("SELECT id, username, email FROM users WHERE id = %s", (user_id,))
    return cursor.fetchone()