-- Питание на работе: five tables.
-- sources     -> where we collect from
-- materials   -> what the collector brought (one row per link)
-- findings    -> what the worker extracted with the model
-- runs        -> every run of every block, with status
-- subscribers -> who pressed Start in the Telegram bot

CREATE TABLE IF NOT EXISTS sources (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    kind        TEXT NOT NULL,            -- hn | arxiv | rss | tg
    url         TEXT NOT NULL,
    source_group TEXT NOT NULL,           -- for example, HR and C&B sources go separately
    active      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS runs (
    id           SERIAL PRIMARY KEY,
    service      TEXT NOT NULL,           -- collector | worker | bot
    status       TEXT NOT NULL,           -- started | running | finished | failed
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    items        INTEGER NOT NULL DEFAULT 0,
    note         TEXT
);

CREATE TABLE IF NOT EXISTS materials (
    id            SERIAL PRIMARY KEY,
    source_id     INTEGER NOT NULL REFERENCES sources(id),
    run_id        INTEGER REFERENCES runs(id),
    url           TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL,
    text          TEXT,
    published_at  TIMESTAMPTZ,
    collected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    status        TEXT NOT NULL DEFAULT 'new'   -- new | done | skipped | failed
);

CREATE TABLE IF NOT EXISTS findings (
    id              SERIAL PRIMARY KEY,
    material_id     INTEGER NOT NULL UNIQUE REFERENCES materials(id),
    companies       TEXT,                 -- all companies from the text, as written, comma separated
    markets         TEXT,                 -- one or several markets, comma separated
    event_type      TEXT NOT NULL,        -- one type from EVENT_TYPES in worker/main.py
    region          TEXT,                 -- city or region, if the text names one
    summary         TEXT NOT NULL,        -- 2-3 sentences in Russian
    model           TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- the bot marks a finding when it has been sent to subscribers
ALTER TABLE findings ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS subscribers (
    chat_id     BIGINT PRIMARY KEY,
    name        TEXT,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO sources (name, kind, source_group, url) VALUES
    ('РБЕ', 'rss', 'операторы питания', 'https://rbegroup.ru/news/rss/'),
    ('FoodService', 'rss', 'общепит', 'https://www.cafe-future.ru/news/rss/'),
    ('Льготы и Бенефиты', 'rss', 'HR и C&B', 'https://perkbenefits.ru/feed/'),
    ('Фудтех в России', 'tg', 'фудтех', 'https://t.me/s/foodtech_russia'),
    ('HR Bazaar', 'tg', 'HR и C&B', 'https://t.me/s/hrbazaar_magazine'),
    ('FMCG Report', 'tg', 'ритейл и FMCG', 'https://t.me/s/fmcg_ru'),
    ('Google Новости: корпоративное питание', 'rss', 'поиск по новостям', 'https://news.google.com/rss/search?q=%22%D0%BA%D0%BE%D1%80%D0%BF%D0%BE%D1%80%D0%B0%D1%82%D0%B8%D0%B2%D0%BD%D0%BE%D0%B5%20%D0%BF%D0%B8%D1%82%D0%B0%D0%BD%D0%B8%D0%B5%22%20OR%20%22%D0%BA%D0%BE%D1%80%D0%BF%D0%BE%D1%80%D0%B0%D1%82%D0%B8%D0%B2%D0%BD%D0%BE%D0%B3%D0%BE%20%D0%BF%D0%B8%D1%82%D0%B0%D0%BD%D0%B8%D1%8F%22%20OR%20%22%D0%BF%D0%B8%D1%82%D0%B0%D0%BD%D0%B8%D0%B5%20%D1%81%D0%BE%D1%82%D1%80%D1%83%D0%B4%D0%BD%D0%B8%D0%BA%D0%BE%D0%B2%22%20when%3A7d&hl=ru&gl=RU&ceid=RU:ru'),
    ('Google Новости: оператор питания', 'rss', 'поиск по новостям', 'https://news.google.com/rss/search?q=%22%D0%BE%D0%BF%D0%B5%D1%80%D0%B0%D1%82%D0%BE%D1%80%20%D0%BF%D0%B8%D1%82%D0%B0%D0%BD%D0%B8%D1%8F%22%20-%D1%88%D0%BA%D0%BE%D0%BB%D1%8C%D0%BD%20when%3A7d&hl=ru&gl=RU&ceid=RU:ru')
ON CONFLICT (name) DO NOTHING;
