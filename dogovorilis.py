"""«Договорились» — планировщик встреч для компании друзей.

Участники предлагают варианты «когда / где / что делаем» и голосуют,
итог у всех обновляется сам.
"""

import re
from datetime import datetime, time
from urllib.parse import quote_plus

import streamlit as st

import dogovorilis_db as storage
from common import flash, go_home, local_now, md, share_url

PAGE = "dogovorilis"
SECTIONS = {
    "when": ("🕒", "Когда"),
    "where": ("📍", "Где"),
    "what": ("🎬", "Что делаем"),
}
TEXT_INPUTS = {
    "where": ("Место", "Кофейня у метро, парк, у Маши дома"),
    "what": ("Чем займёмся", "Кино, боулинг, квест, настолки"),
}
WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
REFRESH_SECONDS = 5


# --- Мелкие помощники -------------------------------------------------------


def safe_url(url):
    return url.replace("(", "%28").replace(")", "%29")


def time_label(moment):
    return f"{WEEKDAYS[moment.weekday()]}, {moment.day} {MONTHS[moment.month - 1]}, {moment:%H:%M}"


# --- Главная ----------------------------------------------------------------


def home_page():
    st.title("🤝 Договорились")
    st.caption("Решить с друзьями, когда, где и чем займёмся: каждый предлагает варианты, все голосуют.")
    new_tab, code_tab = st.tabs(["👥 Новая встреча", "🔑 Есть код"])

    with new_tab:
        with st.form("new_room"):
            title = st.text_input("Что планируем?", placeholder="Пятничный движ", max_chars=60)
            sections = st.pills(
                "Что решаем",
                list(SECTIONS),
                selection_mode="multi",
                default=list(SECTIONS),
                format_func=lambda s: " ".join(SECTIONS[s]),
            )
            name = st.text_input("Твоё имя", max_chars=30)
            submitted = st.form_submit_button("Создать встречу", type="primary", width="stretch")
        if submitted:
            if not name.strip():
                st.warning("Напиши своё имя — друзьям важно видеть, кто что предложил.")
            elif not sections:
                st.warning("Выбери хотя бы один вопрос.")
            else:
                ordered = [s for s in SECTIONS if s in sections]
                code, member_id = storage.create_room(title.strip() or "Встреча", ordered, name)
                st.session_state[f"me_{code}"] = member_id
                st.query_params.from_dict({"room": code})
                flash("Встреча создана — позови друзей по ссылке")
                st.rerun()

    with code_tab:
        with st.form("by_code"):
            code = st.text_input("Код встречи", max_chars=6, placeholder="K7M2QX")
            submitted = st.form_submit_button("Войти", width="stretch")
        if submitted and code.strip():
            st.query_params.from_dict({"room": code.strip().upper()})
            st.rerun()


# --- Встреча ----------------------------------------------------------------


def room_page(code):
    room = storage.get_room(code)
    if room is None:
        st.error("Встреча не найдена. Проверь ссылку или код — или данные обнулились после перезапуска сервиса.")
        st.button("🏠 На главную", on_click=go_home)
        return

    st.title(md(room["title"]))
    members = storage.members(code)
    names = {m["id"]: m["name"] for m in members}
    me = st.session_state.get(f"me_{code}")
    if me not in names:
        join_form(code, members)
        return

    with st.expander("📨 Позвать друзей", expanded=len(members) < 2):
        st.code(share_url(PAGE, room=code), language=None, wrap_lines=True)
        st.caption(f"Скопируй ссылку и отправь в чат компании. Код встречи — {code}.")

    summary(code, room["sections"])

    labels = [" ".join(SECTIONS[s]) for s in room["sections"]]
    for tab, section in zip(st.tabs(labels, key=f"tabs_{code}"), room["sections"]):
        with tab:
            add_option_form(code, section, me)
            option_list(code, section, me)

    st.divider()
    st.caption(f"Ты здесь как **{md(names[me])}**")
    left, right = st.columns(2)
    left.button("Это не я", on_click=forget_me, args=(code,), width="stretch")
    right.button("🏠 Новая встреча", on_click=go_home, width="stretch")


def join_form(code, members):
    st.subheader("Как тебя зовут?")
    if members:
        picked = st.pills(
            "Уже участвуют — нажми на своё имя, если ты среди них:",
            [m["id"] for m in members],
            format_func={m["id"]: m["name"] for m in members}.get,
        )
        if picked is not None:
            st.session_state[f"me_{code}"] = picked
            st.rerun()
    with st.form("join"):
        name = st.text_input("Новое имя" if members else "Имя", max_chars=30)
        submitted = st.form_submit_button("Войти", type="primary", width="stretch")
    if submitted:
        if name.strip():
            st.session_state[f"me_{code}"] = storage.join_room(code, name)
            st.rerun()
        st.warning("Напиши имя — так друзья поймут, кто голосует.")


def forget_me(code):
    st.session_state.pop(f"me_{code}", None)


@st.fragment(run_every=REFRESH_SECONDS)
def summary(code, sections):
    members = storage.members(code)
    with st.container(border=True):
        st.markdown("**📋 Что решили на сейчас**")
        for section in sections:
            icon, title = SECTIONS[section]
            options = storage.section_options(code, section)
            st.markdown(f"{icon} **{title}:** {decision(options, members)}")
        st.caption(f"Участники ({len(members)}): " + ", ".join(md(m["name"]) for m in members))


def decision(options, members):
    """Лидер раздела одной строкой: «сб, 1 ноября, 18:00 — 3 из 4 · ждём: Вася»."""
    if not options:
        return "вариантов пока нет"
    best = max(len(o["voters"]) for o in options)
    if best == 0:
        return "пока никто не голосовал"
    leaders = [md(o["text"]) for o in options if len(o["voters"]) == best]
    total = len(members)
    text = ("ничья: " if len(leaders) > 1 else "") + " / ".join(leaders)
    text += " — все за ✅" if best == total and total > 1 else f" — {best} из {total}"
    voted = set().union(*(o["voter_ids"] for o in options))
    waiting = [md(m["name"]) for m in members if m["id"] not in voted]
    if waiting:
        text += " · ждём: " + ", ".join(waiting)
    return text


def add_option_form(code, section, me):
    with st.expander("➕ Предложить вариант"):
        with st.form(f"add_{section}", clear_on_submit=True, border=False):
            if section == "when":
                today = local_now().date()
                left, right = st.columns(2)
                day = left.date_input("День", value=today, min_value=today, format="DD.MM.YYYY")
                at = right.time_input("Время", value=time(18, 0), step=1800)
                link = ""
            else:
                label, placeholder = TEXT_INPUTS[section]
                text = st.text_input(label, placeholder=placeholder, max_chars=80)
                link = st.text_input("Ссылка, если есть", placeholder="https://…")
            submitted = st.form_submit_button("Добавить", type="primary", width="stretch")
        if not submitted:
            return

        if section == "when":
            moment = datetime.combine(day, at)
            if moment < local_now():
                st.warning("Это время уже прошло.")
                return
            text, sort_key = time_label(moment), moment.isoformat()
        else:
            text, sort_key = text.strip(), ""
            if not text:
                st.warning("Напиши, что предлагаешь.")
                return
        link = link.strip()
        if link and not re.fullmatch(r"https?://\S+", link):
            st.warning("Ссылка должна начинаться с http:// или https://")
            return
        if storage.add_option(code, section, text, link, sort_key, me):
            flash("Вариант добавлен — твой голос за него уже засчитан")
            st.rerun()
        st.warning("Такой вариант уже есть — просто отметь его в списке.")


@st.fragment(run_every=REFRESH_SECONDS)
def option_list(code, section, me):
    options = storage.section_options(code, section)
    if not options:
        st.caption("Вариантов пока нет — предложи первый ☝️")
        return
    total = len(storage.members(code))
    best = max(len(o["voters"]) for o in options)
    for o in options:
        votes = len(o["voters"])
        # Значение кладём в session_state один раз: если передавать value=, Streamlit
        # будет пересоздавать галочку при каждом чужом голосе.
        key = f"vote_{me}_{o['id']}"
        if key not in st.session_state:
            st.session_state[key] = me in o["voter_ids"]
        with st.container(border=True):
            st.checkbox(md(o["text"]), key=key, on_change=save_vote, args=(o["id"], me, key))
            st.progress(votes / total)
            line = ("🏆 " if votes == best and votes else "") + f"{votes} из {total}"
            if o["voters"]:
                line += ": " + ", ".join(md(n) for n in o["voters"])
            if o["link"]:
                line += f" · [ссылка]({safe_url(o['link'])})"
            elif section == "where":
                line += f" · [на карте](https://yandex.ru/maps/?text={quote_plus(o['text'])})"
            st.caption(line)
            if o["author_id"] == me and o["voter_ids"] <= {me}:
                st.button(
                    "Удалить мой вариант",
                    key=f"del_{o['id']}",
                    type="tertiary",
                    on_click=storage.delete_option,
                    args=(o["id"], me),
                )


def save_vote(option_id, member_id, key):
    storage.set_vote(option_id, member_id, st.session_state[key])


# --- Маршрутизация ------------------------------------------------------------


def main():
    room_code = st.query_params.get("room")
    if room_code:
        room_page(room_code.strip().upper())
    else:
        home_page()
