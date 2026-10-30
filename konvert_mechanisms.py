"""Механизмы «Конверта»: что участники сдают и что из этого открывается.

Каждый механизм — чистая функция reveal(params, members, answers) -> result.
После вскрытия хранится только result, сами ответы стираются.
"""

import math
import statistics

MIN_SLICE = 5  # при меньшем числе ответов по общей картине можно вычислить, кто как ответил

MECHANISMS = {
    "threshold": {
        "icon": "🎯",
        "title": "Порог",
        "tagline": "Делаем, только если наберётся нужное число «за». До вскрытия никто не знает, кто «за».",
        "theory": "Охота на оленя: каждый готов, если готовы остальные, но рисковать первым не хочет никто.",
        "templates": [
            {"label": "Перенос контрольной", "question": "Просим учителя перенести контрольную?", "size": 25},
            {"label": "Вместе к руководству", "question": "Идём к руководству с проблемой — вместе?",
             "size": 8, "names": True},
            {"label": "Скидываемся", "question": "Скидываемся на подарок по 500 ₽?", "size": 15, "k": 10,
             "names": True},
            {"label": "Свой вопрос", "question": "", "size": 10},
        ],
    },
    "match": {
        "icon": "🤝",
        "title": "Совпадения",
        "tagline": "Каждый тайно отмечает людей из группы — открываются только взаимные выборы.",
        "theory": "Страх отказа: проявить интерес первым рискованно. Здесь интерес виден, только если он взаимный.",
        "templates": [
            {"label": "Команда для проекта", "question": "С кем хочешь быть в команде на проекте?", "size": 12},
            {"label": "Нетворкинг", "question": "С кем хочешь продолжить общение после встречи?", "size": 20},
            {"label": "Тайные симпатии", "question": "Кто тебе нравится?", "size": 15},
            {"label": "Свой вопрос", "question": "", "size": 10},
        ],
    },
    "slice": {
        "icon": "📊",
        "title": "Честный срез",
        "tagline": f"Видна общая картина, но не ответы людей. Итог открывается, только если ответили хотя бы {MIN_SLICE}.",
        "theory": "Парадокс Абилина: все молчат, думая, что остальные согласны, — и группа делает то, чего не хотел никто.",
        "templates": [
            {"label": "Понятна ли тема", "question": "Насколько тебе понятна сегодняшняя тема?", "size": 25,
             "options": ["Всё понятно", "Почти всё", "Мало что", "Ничего не понятно"]},
            {"label": "Верим ли в проект", "question": "Веришь, что проект сработает?", "size": 8,
             "options": ["Точно да", "Скорее да", "Скорее нет", "Точно нет"]},
            {"label": "Нужна ли планёрка", "question": "Эта еженедельная встреча нам нужна?", "size": 8,
             "options": ["Нужна как есть", "Можно реже", "Можно отменить"]},
            {"label": "Свой вопрос", "question": "", "size": 10, "options": ["Да", "Нет"]},
        ],
    },
    "reveal": {
        "icon": "🃏",
        "title": "Карты на стол",
        "tagline": "Все ответы открываются одновременно — первый ответ ни на кого не давит.",
        "theory": "Эффект якоря: первая названная цифра тянет за собой все остальные.",
        "templates": [
            {"label": "Оценка задачи", "question": "Сколько часов займёт задача?", "size": 5},
            {"label": "Прогноз", "question": "Какой будет счёт в матче?", "size": 6},
            {"label": "Вклад", "question": "Сколько можешь вложить в общий проект, ₽?", "size": 4},
            {"label": "Свой вопрос", "question": "", "size": 5},
        ],
    },
    "deal": {
        "icon": "💰",
        "title": "Зона сделки",
        "tagline": "Двое тайно называют свои границы — видно только, сойдутся ли они.",
        "theory": "Кто первым назвал цифру, тот проиграл. Здесь границы называют одновременно и тайно.",
        "templates": [
            {"label": "Цена вещи", "question": "Сойдёмся в цене?",
             "roles": {"seller": "Продавец", "buyer": "Покупатель"}},
            {"label": "Зарплата", "question": "Сойдёмся в зарплате?",
             "roles": {"seller": "Кандидат", "buyer": "Компания"}},
            {"label": "Аренда", "question": "Сойдёмся в цене аренды?",
             "roles": {"seller": "Арендодатель", "buyer": "Арендатор"}},
        ],
    },
}


def passport(mech, params):
    """«Паспорт приватности»: кто что узнает и что станет с ответами. Его видят до ответа."""
    stored = "До вскрытия свой ответ можно поменять. После вскрытия ответы стираются — хранится только итог."
    if mech == "threshold":
        k = params["k"]
        if params["names"]:
            learn = f"Набран ли порог в {k} «за». Если набран — сколько «за» и кто именно (а значит, видно и тех, кто не «за»)."
            hidden = "Если порог не набран — ни имён, ни числа «за»."
        else:
            learn = f"Набран ли порог в {k} «за». Если набран — сколько было «за»."
            hidden = "Кто как ответил. Если порог не набран — даже сколько было «за»."
    elif mech == "match":
        learn = "Каждый — только свои взаимные совпадения."
        hidden = (f"Выбор без взаимности и чужие совпадения — даже создатель конверта. Отметить можно "
                  f"не больше {params['picks']}: иначе можно было бы отметить всех и узнать, кто отметил тебя.")
    elif mech == "slice":
        learn = f"Сколько человек выбрали каждый вариант — если ответили хотя бы {MIN_SLICE}."
        hidden = "Кто как ответил. Если ответов меньше — даже общая картина: по ней можно было бы вычислить ответы."
    elif mech == "reveal":
        learn = "Все ответы с именами — одновременно, после вскрытия."
        hidden = "До вскрытия — чужие ответы, поэтому первый ответ ни на кого не давит."
        stored = "До вскрытия свой ответ можно поменять. После вскрытия ответы видят все участники."
    else:  # deal
        if params["show_mid"]:
            learn = "Обе стороны — есть ли зона сделки и её середину."
            hidden = ("Границу другой стороны, если сделки нет. Если сделка есть, по середине и своей "
                      "границе можно вычислить чужую — учтите это.")
        else:
            learn = "Обе стороны — только есть ли зона сделки."
            hidden = "Границу другой стороны — при любом итоге."
    return [("👀 Узнают", learn), ("🙈 Не узнает никто", hidden), ("🗑 Ответы", stored)]


def reveal(mech, params, members, answers):
    """members: {id: {"name", "role"}}, answers: {member_id: ответ}."""
    return _REVEALERS[mech](params, members, answers)


def _threshold(params, members, answers):
    yes = [m for m, value in answers.items() if value is True]
    result = {"reached": len(yes) >= params["k"], "answered": len(answers)}
    if result["reached"]:
        result["yes"] = len(yes)
        if params["names"]:
            # По алфавиту, а не по порядку ответов: порядок выдал бы, кто решился первым.
            result["names"] = sorted(members[m]["name"] for m in yes)
    return result


def _match(params, members, answers):
    picks = {m: set(value) for m, value in answers.items()}
    pairs = {(a, b) for a, chosen in picks.items() for b in chosen if a < b and a in picks.get(b, ())}
    return {"pairs": sorted(pairs)}


def _slice(params, members, answers):
    if len(answers) < MIN_SLICE:
        return {"hidden": True, "answered": len(answers)}
    counts = [0] * len(params["options"])
    for value in answers.values():
        if 0 <= value < len(counts):
            counts[value] += 1
    return {"counts": counts, "answered": len(answers)}


def _reveal_all(params, members, answers):
    rows = sorted([members[m]["name"], value] for m, value in answers.items())
    result = {"rows": rows}
    numbers = [as_number(value) for _, value in rows]
    if numbers and None not in numbers:
        result["stats"] = {"min": min(numbers), "median": statistics.median(numbers), "max": max(numbers)}
    return result


def as_number(text):
    """«1 500» и «2,5» — числа; всё остальное — None."""
    try:
        number = float(text.replace(" ", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _deal(params, members, answers):
    bounds = {members[m]["role"]: value for m, value in answers.items()}
    if len(bounds) < 2:
        return {"incomplete": True}
    result = {"deal": bounds["buyer"] >= bounds["seller"]}
    if result["deal"] and params["show_mid"]:
        result["mid"] = (bounds["buyer"] + bounds["seller"]) / 2
    return result


_REVEALERS = {
    "threshold": _threshold,
    "match": _match,
    "slice": _slice,
    "reveal": _reveal_all,
    "deal": _deal,
}
