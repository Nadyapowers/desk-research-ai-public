"""Worker: takes new materials from the database, asks the model, writes findings.

This is the only place in the system where a model is called.
"""

import json
import os
import time
import urllib.request

import db

SERVICE = "worker"
MODEL = os.environ.get("MODEL", "anthropic/claude-haiku-5.5")
PROMPT_VERSION = "v1-corpfood"
POLL_SECONDS = 10
RETRY_SECONDS = 3600
MAX_ANSWER_TOKENS = 2000  # free models spend part of this limit on reasoning; 700 cut their answers off

MARKETS = [
    "корпоративное питание",
    "C&B и льготы",
    "готовая еда",
    "общепит",
    "микромаркеты",
    "вендинг",
    "кейтеринг",
    "рационы",
    "опт и закупки HoReCa",
]

OTHER_EVENT = "Другое"
EVENT_TYPES = [
    "Открытие или обновление точки питания",
    "Контракт, тендер, смена оператора",
    "Новый формат или услуга",
    "Условия питания у работодателя",
    "Финансы и сделки компаний",
    "Исследования и опросы",
    "Законы, налоги, стандарты, госзакупки",
    "Зарубежный рынок",
    OTHER_EVENT,
]

PROMPT = """Ты помогаешь исследователям следить за рынком корпоративного питания.
Материал:
Заголовок: {title}
Текст: {text}

По теме: организация питания сотрудников любым способом. Столовые на предприятиях и в офисах, операторы питания, тендеры и контракты на питание, компенсация и дотация обедов, карты питания, вендинг и микромаркеты на работе, питание как льгота, исследования о питании сотрудников.
Тоже по теме: любая новость о компании-операторе питания, даже если она не про столовые (сделки, выручка, новые направления). Такие операторы, например: РБЕ (RBE), Бахетле, ОМС — питание металлургов, ЭкоСфера, Кафетера, BestPit, Калина Групп, Перерыв на обед, Экипаж-Кейтеринг, Sodexo, Everyx, НаЛанч, Foodcard, Яндекс Ланч Карта, Обед.ру. Также по теме: цифры рынка организованного питания, в том числе объёмы госзакупок питания для школ и больниц.
Не по теме: розничные магазины и сети, рестораны для гостей, доставка еды частным лицам, отдельные случаи школьного, больничного и армейского питания без цифр рынка (конкурсы, меню, жалобы). Например, «ВкусВилл открыл магазин в бизнес-центре» и «школьная столовая победила в конкурсе» не по теме.

Как выбирать тип события: всё, что происходит за пределами России, это «Зарубежный рынок», даже если это контракт или открытие. Опросы и обзоры с долями компаний, в том числе про льготы, это «Исследования и опросы». «Условия питания у работодателя» только про конкретного работодателя.

Ответь строго JSON без пояснений:
{{"about_corp_food": true или false, материал по теме,
  "companies": [все компании и предприятия из текста, как они написаны; пустой список, если их нет],
  "markets": [один или несколько рынков, которые задевает материал, из списка: {markets}],
  "event_type": "один тип события из списка: {event_types}",
  "region": "город или регион, если он назван в тексте, иначе null",
  "summary": "о чем материал, до 3 предложений по-русски, только факты из текста. Если фактов мало, хватит одного предложения. Пиши только о событии: никогда не пиши о самом материале, его длине и о том, чего в нем нет"}}"""


def ask_model(title, text):
    body = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": PROMPT.format(
                    title=title,
                    text=(text or "")[:2000],
                    markets="; ".join(MARKETS),
                    event_types="; ".join(EVENT_TYPES),
                ),
            }
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": MAX_ANSWER_TOKENS,
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        content = json.loads(resp.read())["choices"][0]["message"]["content"]
    content = (
        content.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    )
    # the model sometimes adds text after the answer: read the first JSON object only
    return json.JSONDecoder().raw_decode(content.strip())[0]


def clean_answer(answer):
    """Checks the model's answer. A bad answer raises an error and the material goes to retry."""
    if not answer.get("about_corp_food"):
        return None
    summary = (answer.get("summary") or "").strip()
    if not summary:
        raise ValueError("в ответе нет пересказа")
    event_type = answer.get("event_type")
    return {
        "companies": ", ".join(answer.get("companies") or []),
        "markets": ", ".join(m for m in answer.get("markets") or [] if m in MARKETS),
        "event_type": event_type if event_type in EVENT_TYPES else OTHER_EVENT,
        "region": answer.get("region") or None,
        "summary": summary,
    }


def process_new(conn):
    pending = conn.execute(
        "SELECT id, title, text FROM materials WHERE status = 'new' ORDER BY id"
    ).fetchall()
    if not pending:
        return
    run_id = db.start_run(conn, SERVICE)
    found = 0
    for done, (material_id, title, text) in enumerate(pending, 1):
        try:
            answer = clean_answer(ask_model(title, text))
        except Exception as error:
            conn.execute(
                "UPDATE materials SET status = 'failed' WHERE id = %s", (material_id,)
            )
            db.log(SERVICE, f"материал {material_id}: модель не ответила: {error}")
            continue
        if answer:
            conn.execute(
                """INSERT INTO findings (material_id, companies, markets, event_type, region, summary, model, prompt_version)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (material_id) DO NOTHING""",
                (
                    material_id,
                    answer["companies"],
                    answer["markets"],
                    answer["event_type"],
                    answer["region"],
                    answer["summary"],
                    MODEL,
                    PROMPT_VERSION,
                ),
            )
            conn.execute(
                "UPDATE materials SET status = 'done' WHERE id = %s", (material_id,)
            )
            found += 1
            db.log(
                SERVICE,
                f"материал {material_id} -> находка ({answer['event_type']}): {answer['summary']}",
            )
        else:
            conn.execute(
                "UPDATE materials SET status = 'skipped' WHERE id = %s", (material_id,)
            )
            db.log(SERVICE, f"материал {material_id} не по теме, пропускаю")
        if done % 10 == 0:
            db.progress_run(
                conn, SERVICE, run_id, found, f"разобрано {done} из {len(pending)}"
            )
    db.finish_run(
        conn, SERVICE, run_id, found, f"разобрано {len(pending)}, находок {found}"
    )


def retry_failed(conn):
    retried = conn.execute(
        "UPDATE materials SET status = 'new' WHERE status = 'failed'"
    ).rowcount
    if retried:
        db.log(
            SERVICE,
            f"вернул в разбор {retried} материалов, на которых модель не ответила",
        )


def main():
    conn = db.connect()
    db.init_schema(conn)
    db.log(SERVICE, f"жду новые материалы в базе, модель {MODEL}")
    last_retry = float("-inf")
    while True:
        try:
            # materials the model failed on go back into the queue once an hour
            if time.monotonic() - last_retry >= RETRY_SECONDS:
                retry_failed(conn)
                last_retry = time.monotonic()
            process_new(conn)
        except Exception as error:
            db.log(SERVICE, f"упал: {error}")
            conn = db.connect()
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
