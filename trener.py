"""«Тренажёр к экзамену» — вопросы по одному, счёт и разбор ошибок.

Можно взять готовый набор или вставить свои вопросы строками «вопрос = ответ».
"""

import random

import streamlit as st

from common import md, plural

PAGE = "trener"

# Вопрос, правильный ответ, неправильные варианты (None — ответ вводят сами).
SETS = {
    "🔬 Наука": [
        ("Сколько планет в Солнечной системе?", "8", ["7", "9", "10"]),
        ("Химический символ золота", "Au", ["Ag", "Zn", "Ga"]),
        ("Какой газ растения поглощают при фотосинтезе?", "Углекислый газ", ["Кислород", "Азот", "Водород"]),
        ("Кто открыл закон всемирного тяготения?", "Исаак Ньютон",
         ["Галилео Галилей", "Альберт Эйнштейн", "Михаил Ломоносов"]),
        ("В чём измеряют частоту?", "В герцах", ["В ваттах", "В джоулях", "В паскалях"]),
        ("Какая планета ближе всего к Солнцу?", "Меркурий", ["Венера", "Марс", "Земля"]),
        ("Кто создал периодическую таблицу химических элементов?", "Дмитрий Менделеев",
         ["Михаил Ломоносов", "Мария Кюри", "Антуан Лавуазье"]),
        ("Скорость света в вакууме — примерно…", "300 000 км/с",
         ["300 км/с", "30 000 км/с", "3 000 000 км/с"]),
        ("Какой орган вырабатывает инсулин?", "Поджелудочная железа",
         ["Печень", "Почки", "Щитовидная железа"]),
    ],
    "🌍 Столицы": [
        ("Столица Австралии", "Канберра", ["Сидней", "Мельбурн", "Перт"]),
        ("Столица Канады", "Оттава", ["Торонто", "Монреаль", "Ванкувер"]),
        ("Столица Турции", "Анкара", ["Стамбул", "Измир", "Анталья"]),
        ("Столица Бразилии", "Бразилиа", ["Рио-де-Жанейро", "Сан-Паулу", "Сальвадор"]),
        ("Столица Казахстана", "Астана", ["Алматы", "Шымкент", "Караганда"]),
        ("Столица Швейцарии", "Берн", ["Цюрих", "Женева", "Базель"]),
        ("Столица США", "Вашингтон", ["Нью-Йорк", "Лос-Анджелес", "Чикаго"]),
        ("Столица Вьетнама", "Ханой", ["Хошимин", "Дананг", "Хюэ"]),
    ],
    "🧮 Устный счёт": [
        ("7 × 8", "56", None),
        ("12 × 12", "144", None),
        ("15 % от 200", "30", None),
        ("2 в десятой степени", "1024", None),
        ("1/4 в виде десятичной дроби", "0,25", None),
        ("1000 − 365", "635", None),
        ("3 в четвёртой степени", "81", None),
        ("Сколько минут в трёх часах?", "180", None),
    ],
}
EXAMPLE = "Столица Франции = Париж\nКто написал «Евгения Онегина»? = Пушкин\n9 × 7 = 63"


def normalize(answer):
    """«Ёлка», «елка » и «ЕЛКА.» — один ответ; «0.25» и «0,25» — тоже."""
    text = answer.casefold().replace("ё", "е").replace(",", ".")
    text = "".join(ch for ch in text if ch not in "«»\"'")
    return " ".join(text.split()).strip(".!?;:")


def parse_own(text):
    """Строки «вопрос = ответ» → вопросы. Строки без «=» или с пустой половиной пропускаем."""
    questions = []
    for line in text.splitlines():
        question, _, answer = line.rpartition("=")
        if question.strip() and answer.strip():
            questions.append({"q": question.strip(), "a": answer.strip(), "options": None})
    return questions


def start(title, questions):
    """Новый заход: свои копии вопросов в случайном порядке, варианты тоже перемешаны."""
    questions = [dict(q, options=random.sample(q["options"], len(q["options"])) if q["options"] else None)
                 for q in questions]
    random.shuffle(questions)
    st.session_state["trener_round"] = st.session_state.get("trener_round", 0) + 1
    st.session_state["trener"] = {"title": title, "questions": questions, "i": 0, "log": [],
                                  "checked": False, "round": st.session_state["trener_round"]}


def start_set(title):
    start(title, [{"q": q, "a": a, "options": None if wrong is None else [a, *wrong]}
                  for q, a, wrong in SETS[title]])


def next_question():
    quiz = st.session_state["trener"]
    quiz["i"] += 1
    quiz["checked"] = False


def quit_quiz():
    st.session_state.pop("trener", None)


# --- Страницы -------------------------------------------------------------------


def main():
    quiz = st.session_state.get("trener")
    if quiz is None:
        start_page()
    elif quiz["i"] < len(quiz["questions"]):
        question_page(quiz)
    else:
        result_page(quiz)


def start_page():
    st.title("📚 Тренажёр к экзамену")
    st.caption("Вопросы по одному, счёт и разбор ошибок в конце.")
    ready, own = st.tabs(["Готовые наборы", "Свои вопросы"])
    with ready:
        for title, items in SETS.items():
            kind = "с вариантами" if items[0][2] else "ответ вписываешь сам"
            st.button(f"{title} · {plural(len(items), 'вопрос', 'вопроса', 'вопросов')} · {kind}",
                      key=f"set_{title}", on_click=start_set, args=(title,), width="stretch")
    with own:
        text = st.text_area("Каждый вопрос с новой строки: вопрос = ответ", placeholder=EXAMPLE, height=160)
        if st.button("Начать", type="primary", width="stretch"):
            questions = parse_own(text)
            if questions:
                start("Свои вопросы", questions)
                st.rerun()
            st.warning("Не нашёл ни одной строки вида «вопрос = ответ».")


def question_page(quiz):
    i, total = quiz["i"], len(quiz["questions"])
    q = quiz["questions"][i]
    st.caption(f"{quiz['title']} · вопрос {i + 1} из {total}")
    st.progress(i / total)
    st.subheader(md(q["q"]))

    if not quiz["checked"]:
        with st.form(f"trener_{quiz['round']}_{i}"):
            if q["options"]:
                given = st.radio("Ответ", q["options"], index=None, label_visibility="collapsed")
            else:
                given = st.text_input("Твой ответ")
            submitted = st.form_submit_button("Ответить", type="primary", width="stretch")
        if submitted:
            if not given or not given.strip():
                st.warning("Сначала выбери или впиши ответ.")
            else:
                ok = normalize(given) == normalize(q["a"])
                quiz["log"].append({"question": q, "given": given, "ok": ok})
                quiz["checked"] = True
                st.rerun()
    else:
        last = quiz["log"][-1]
        if last["ok"]:
            st.success("✅ Верно!")
        else:
            st.error(f"❌ Неверно. Твой ответ: {md(last['given'])}. Правильный: **{md(q['a'])}**")
        st.button("Дальше" if i + 1 < total else "Узнать результат",
                  type="primary", width="stretch", on_click=next_question)
    st.button("Закончить", type="tertiary", on_click=quit_quiz)


def result_page(quiz):
    log = quiz["log"]
    right, total = sum(e["ok"] for e in log), len(log)
    st.title("📚 Результат")
    st.caption(quiz["title"])
    st.markdown(f"## {right} из {total}")
    st.progress(right / total)
    if right == total:
        st.success("Идеально — все ответы верные! 🏆")
    elif right / total >= 0.7:
        st.info("Хорошо! Осталось подтянуть пару вопросов.")
    else:
        st.warning("Есть над чем поработать — повтори ошибки.")

    mistakes = [e for e in log if not e["ok"]]
    if mistakes:
        st.markdown("**Разбор ошибок**")
        for e in mistakes:
            with st.container(border=True):
                st.markdown(f"**{md(e['question']['q'])}**")
                st.markdown(f"Твой ответ: {md(e['given'])}  \nПравильный: **{md(e['question']['a'])}**")
        st.button("🔁 Повторить только ошибки", type="primary", width="stretch", on_click=start,
                  args=(quiz["title"], [e["question"] for e in mistakes]))
    st.button("Пройти ещё раз", width="stretch", on_click=start,
              args=(quiz["title"], quiz["questions"]))
    st.button("Выбрать другой набор", width="stretch", on_click=quit_quiz)
