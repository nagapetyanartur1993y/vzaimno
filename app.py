"""«Банк мини-сервисов» — каталог маленьких готовых сервисов в одном приложении.

Каждый мини-сервис — это страница с функцией main() и константой PAGE
(kogda.py, golos.py, …) и, если ему нужно что-то хранить, её хранилище
(kogda_db.py, golos_db.py, …). Чтобы добавить новый, допиши строку в CATALOG.
"""

import streamlit as st

import dogovorilis
import golos
import kogda
import konvert
import kopilka
import trener
import vzaimno

st.set_page_config(page_title="Банк мини-сервисов", page_icon="🧰")

ALL = "Все"
# Раздел, модуль, название, иконка, что делает.
CATALOG = [
    ("Учёба", trener, "Тренажёр к экзамену", "📚",
     "Вопросы по одному, счёт и разбор ошибок. Готовые наборы или свои вопросы."),
    ("Учёба", golos, "Голосовалка", "🗳️",
     "Вопрос на экране, голоса с телефонов по QR-коду, итог обновляется сам."),
    ("Деньги", kopilka, "Копилка", "💰",
     "Когда накоплю на цель — или сколько откладывать в неделю, чтобы успеть к дате."),
    ("Компания", kogda, "Когда гуляем?", "🚶",
     "Каждый отмечает свободные часы на неделе — сервис находит время, которое подходит большинству."),
    ("Компания", dogovorilis, "Договорились", "🤝",
     "Когда, где и чем займёмся: каждый предлагает варианты, все голосуют."),
    ("Тайные решения", vzaimno, "Взаимно?", "💌",
     "Тайный вопрос на двоих: «да» узнают, только если оба сказали «да»."),
    ("Тайные решения", konvert, "Конверт", "✉️",
     "Группа тайно кладёт ответы в конверт, а открывается только итог: порог, совпадения или общая картина."),
]
PAGES = {module.PAGE: st.Page(module.main, title=title, icon=icon, url_path=module.PAGE)
         for _, module, title, icon, _ in CATALOG}
SECTIONS = list(dict.fromkeys(section for section, *_ in CATALOG))


def home():
    st.title("🧰 Банк мини-сервисов")
    st.caption("Выбери сервис и пользуйся — всё работает прямо в браузере, с телефона тоже.")
    section = st.pills("Раздел", [ALL, *SECTIONS], default=ALL, required=True,
                       label_visibility="collapsed")
    shown = [item for item in CATALOG if section in (ALL, item[0])]
    for row in range(0, len(shown), 2):
        for column, (sec, module, title, icon, about) in zip(st.columns(2), shown[row:row + 2]):
            with column.container(border=True, height="stretch"):
                st.markdown(f"#### {icon} {title}")
                st.caption(sec)
                st.write(about)
                if st.button("Открыть", key=f"open_{module.PAGE}", type="primary", width="stretch"):
                    st.switch_page(PAGES[module.PAGE])


HOME = st.Page(home, title="Все сервисы", icon="🧰", default=True)
page = st.navigation(
    {"": [HOME], **{s: [PAGES[m.PAGE] for sec, m, *_ in CATALOG if sec == s] for s in SECTIONS}}
)
if page is not HOME:
    st.page_link(HOME, label="Все сервисы", icon=":material/arrow_back:")
page.run()

# В самом конце, чтобы всплывашка не сдвигала элементы выше.
if "flash" in st.session_state:
    st.toast(st.session_state.pop("flash"))
