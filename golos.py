"""«Голосовалка для класса» — вопрос на экране, голоса с телефонов, общий итог.

Ведущий получает свою ссылку: на ней QR-код для зала, живой итог и кнопка
«Завершить». Участники голосуют по общей ссылке и видят итог после своего голоса.
"""

import secrets

import segno
import streamlit as st

import golos_db as db
from common import flash, go_home, md, plural, share_url

PAGE = "golos"
REFRESH_SECONDS = 3
MAX_OPTIONS = 8
EXAMPLE_OPTIONS = "Кино\nБоулинг\nКвест\nПарк"


@st.cache_data
def qr_svg(link):
    """QR-код в SVG: st.image встроит его в страницу как data-URI.

    Не PNG: однобитный PNG Streamlit перекодирует в JPEG, и на Streamlit Cloud
    такая картинка не грузится. Белый фон — чтобы камера считала код и на тёмной теме.
    """
    return segno.make(link, error="m").svg_inline(border=2, dark="#000", light="#fff", omitsize=True)


def main():
    code = st.query_params.get("poll")
    if code:
        poll_page(code.strip().upper(), st.query_params.get("admin", ""))
    else:
        new_poll_page()


# --- Новое голосование ----------------------------------------------------------


def new_poll_page():
    st.title("🗳️ Голосовалка")
    st.caption("Задай вопрос — все голосуют с телефонов по QR-коду, итог обновляется сам.")
    new_tab, code_tab = st.tabs(["🗳️ Новое голосование", "🔑 Есть код"])

    with new_tab:
        with st.form("new_poll"):
            question = st.text_input("Вопрос", placeholder="Куда идём всем классом?", max_chars=120)
            options_text = st.text_area("Варианты — каждый с новой строки", placeholder=EXAMPLE_OPTIONS, height=150)
            submitted = st.form_submit_button("Создать голосование", type="primary", width="stretch")
        if submitted:
            create(question.strip(), options_text)

    with code_tab:
        with st.form("by_code"):
            code = st.text_input("Код голосования", max_chars=6, placeholder="K7M2QX")
            submitted = st.form_submit_button("Войти", width="stretch")
        if submitted and code.strip():
            st.query_params.from_dict({"poll": code.strip().upper()})
            st.rerun()


def create(question, options_text):
    options, seen = [], set()
    for line in options_text.splitlines():
        option = " ".join(line.split())[:80]
        if option and option.casefold() not in seen:  # «Кино» и «кино » — один вариант
            seen.add(option.casefold())
            options.append(option)
    if not question:
        st.warning("Напиши вопрос.")
    elif not 2 <= len(options) <= MAX_OPTIONS:
        st.warning(f"Нужно от 2 до {MAX_OPTIONS} разных вариантов, каждый с новой строки.")
    else:
        code, admin_key = db.create_poll(question, options)
        st.query_params.from_dict({"poll": code, "admin": admin_key})
        flash("Голосование создано. Эта страница — для ведущего, сохрани ссылку")
        st.rerun()


# --- Голосование --------------------------------------------------------------------


def poll_page(code, admin_key):
    poll = db.get_poll(code)
    if poll is None:
        st.error("Голосование не найдено. Проверь код — или данные обнулились после перезапуска сервиса.")
        st.button("🗳️ Новое голосование", on_click=go_home)
        return
    st.title(md(poll["question"]))
    if admin_key and db.is_admin(poll, admin_key):
        host_view(poll, admin_key)
    else:
        voter_view(poll)


def host_view(poll, admin_key):
    link = share_url(PAGE, poll=poll["code"])
    with st.container(border=True):
        st.markdown("**📲 Наведи камеру телефона и голосуй**")
        st.image(qr_svg(link), width=260)
        st.code(link, language=None, wrap_lines=True)
        st.caption(f"Или открой сервис и введи код **{poll['code']}**.")

    if poll["closed"]:
        st.info("Голосование завершено — новые голоса не принимаются.")
    results(poll["code"], poll["options"])
    if poll["closed"]:
        st.button("Открыть голосование снова", width="stretch",
                  on_click=db.set_closed, args=(poll["code"], False))
    else:
        st.button("Завершить голосование", type="primary", width="stretch",
                  on_click=db.set_closed, args=(poll["code"], True))
    with st.expander("🔑 Ссылка ведущего"):
        st.code(share_url(PAGE, poll=poll["code"], admin=admin_key), language=None, wrap_lines=True)
        st.caption("По ней можно завершить голосование — участникам её не отправляй.")


def voter_view(poll):
    code, options = poll["code"], poll["options"]
    # Голос привязан к случайному токену в этой вкладке, а не к имени: голосование анонимное.
    voter = st.session_state.setdefault(f"golos_voter_{code}", secrets.token_urlsafe(9))
    mine = db.my_vote(code, voter)
    changing = f"golos_change_{code}"

    if poll["closed"]:
        st.info("Голосование завершено.")
    elif mine is None or st.session_state.get(changing):
        with st.form("vote"):
            choice = st.radio("Твой выбор", range(len(options)), index=mine,
                              format_func=lambda i: md(options[i]))
            submitted = st.form_submit_button("Проголосовать", type="primary", width="stretch")
        if not submitted:
            return
        if choice is None:
            st.warning("Выбери вариант.")
        elif db.vote(code, voter, choice):
            st.session_state.pop(changing, None)
            flash("Голос принят ✅")
            st.rerun()
        else:
            st.warning("Голосование уже завершено.")
        return
    else:
        st.success(f"Твой голос: **{md(options[mine])}**")
        st.button("Изменить голос", on_click=change_vote, args=(code,))
    results(code, options, mine)


def change_vote(code):
    st.session_state[f"golos_change_{code}"] = True


@st.fragment(run_every=REFRESH_SECONDS)
def results(code, options, mine=None):
    counts = db.counts(code, len(options))
    total = sum(counts)
    with st.container(border=True):
        st.markdown(f"**📊 Итог** · {plural(total, 'голос', 'голоса', 'голосов')}")
        if total == 0:
            st.caption("Пока никто не проголосовал.")
            return
        best = max(counts)
        for i, (option, n) in enumerate(zip(options, counts)):
            label = ("🏆 " if n == best else "") + md(option) + (" · твой голос" if i == mine else "")
            st.progress(n / total, text=f"{label} — {n} ({round(100 * n / total)} %)")
