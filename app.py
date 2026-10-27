"""«Взаимно?» — тайный вопрос на двоих.

Двое отвечают «да» или «нет», каждый по своей ссылке. Итог «да» — только если
оба сказали «да»; ответивший «нет» так и не узнает ответ партнёра.
"""

import os
import re

import streamlit as st

import storage

st.set_page_config(page_title="Взаимно?", page_icon="💌")

DEFAULT_QUESTION = "Хочешь, чтобы наши отношения продолжались?"

RULES = """
- Вы с партнёром отвечаете «да» или «нет» — каждый по своей ссылке, не видя ответа другого.
- Итог появится, когда ответите оба. Изменить ответ нельзя.
- Оба «да» — обоим приходит «да» 💚
- Хотя бы одно «нет» — обоим приходит «нет».
- Если ты ответишь «нет», ты не узнаешь, что ответил партнёр.
- Если ты ответишь «да», а итог «нет» — значит, против партнёр. Но твоё «да» останется тайной.
- Как только итог готов, сами ответы стираются — хранится только итог.
"""


def md(text):
    """Экранирует разметку: «**», «$» или «[…](…)» в тексте не должны ничего ломать."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~$:])", r"\\\1", text)


def app_url():
    """Публичный адрес приложения — из него собираются ссылки для двоих."""
    url = os.environ.get("PUBLIC_URL") or st.context.url or "http://localhost:8501/"
    # Streamlit Cloud показывает приложение во фрейме по адресу …/~/+/, партнёру нужна обычная ссылка.
    return url.split("/~/+")[0].rstrip("/") + "/"


def go_home():
    st.query_params.clear()


def home_page():
    st.title("💌 Взаимно?")
    st.caption("Спросить друг друга о главном так, чтобы никому не было неловко.")
    st.markdown(RULES)
    with st.form("new_pair"):
        question = st.text_input(
            "Вопрос",
            value=DEFAULT_QUESTION,
            max_chars=120,
            help="Подойдёт любой вопрос, на который отвечают «да» или «нет».",
        )
        left, right = st.columns(2)
        name_a = left.text_input("Твоё имя", max_chars=30)
        name_b = right.text_input("Имя партнёра", max_chars=30)
        submitted = st.form_submit_button("Создать вопрос", type="primary", width="stretch")
    if submitted:
        if not question.strip():
            st.warning("Напиши вопрос.")
            return
        pair = storage.create_pair(question.strip(), name_a.strip(), name_b.strip())
        st.query_params.from_dict({"id": pair["id"], "key": pair["key_a"]})
        st.rerun()


def pair_page(pair_id, key):
    pair = storage.get_pair(pair_id)
    role = storage.pair_role(pair, key) if pair else None
    if role is None:
        st.error("Ссылка не работает. Проверь, что она скопирована целиком, — или данные обнулились после перезапуска сервиса.")
        st.button("💌 Задать свой вопрос", on_click=go_home)
        return
    partner = "b" if role == "a" else "a"

    st.title("💌 Взаимно?")
    if pair["name_a"] and pair["name_b"]:
        st.caption(f"{md(pair['name_a'])} и {md(pair['name_b'])}")  # без «для»: имена не склоняем
    st.subheader(md(pair["question"]))

    if pair["result"] is not None:
        show_result(pair_id, pair["result"])
    else:
        if role == "a":
            share_links(pair)
        if pair[f"answered_{role}"]:
            wait_for_result(pair_id)
        else:
            partner_name = md(pair[f"name_{partner}"]) or "Партнёр"
            status = "ответ уже есть ✅" if pair[f"answered_{partner}"] else "ответа пока нет"
            st.caption(f"{partner_name}: {status}")
            answer_form(pair_id, role)

    with st.expander("Как это работает"):
        st.markdown(RULES)
    st.button("💌 Задать свой вопрос", on_click=go_home)


def share_links(pair):
    base = f"{app_url()}?id={pair['id']}&key="
    with st.container(border=True):
        st.markdown("**Ссылка для партнёра** — отправь её партнёру, и больше никому:")
        st.code(base + pair["key_b"], language=None, wrap_lines=True)
        st.markdown("**Твоя ссылка** — сохрани, чтобы вернуться к итогу:")
        st.code(base + pair["key_a"], language=None, wrap_lines=True)


def answer_form(pair_id, role):
    with st.form("answer"):
        choice = st.radio("Твой ответ", ["Да", "Нет"], index=None, horizontal=True)
        submitted = st.form_submit_button(
            "Ответить — изменить будет нельзя", type="primary", width="stretch"
        )
    if submitted:
        if choice is None:
            st.warning("Выбери «да» или «нет».")
            return
        storage.answer_pair(pair_id, role, choice == "Да")
        st.rerun()


@st.fragment(run_every=3)
def wait_for_result(pair_id):
    pair = storage.get_pair(pair_id)
    if pair is None or pair["result"] is not None:
        st.rerun()
    st.info("⏳ Ответ сохранён. Ждём второго — итог появится здесь сам.")
    st.caption("Это не твой ответ? Значит, по твоей ссылке ответил кто-то другой.")


def show_result(pair_id, result):
    # Текст одинаковый для обоих: по нему нельзя понять, кто что ответил.
    if result:
        st.success("💚 Вы оба ответили «да»!")
        if not st.session_state.get(f"celebrated_{pair_id}"):
            st.session_state[f"celebrated_{pair_id}"] = True
            st.balloons()
    else:
        st.info("Итог: «нет». Хотя бы один из вас ответил «нет».")
        st.markdown(
            "Если твой ответ был «да» — значит, «нет» сказал партнёр, а твоё «да» останется тайной.\n\n"
            "Если твой ответ был «нет» — ответ партнёра ты не узнаешь."
        )


pair_id = st.query_params.get("id")
if pair_id:
    pair_page(pair_id, st.query_params.get("key", ""))
else:
    home_page()
