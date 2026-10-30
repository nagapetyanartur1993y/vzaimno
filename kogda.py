"""«Когда гуляем?» — общее время для прогулки.

Каждый отмечает часы, когда ему удобно, а сервис ищет окна, в которые
свободно больше всего людей сразу на всю прогулку.
"""

from datetime import datetime, time, timedelta
from html import escape

import streamlit as st

import kogda_db as db
from common import WEEKDAYS, day_label, flash, go_home, local_now, md, share_url

PAGE = "kogda"
DURATIONS = {1: "1 час", 2: "2 часа", 3: "3 часа", 4: "4 часа"}
MAX_DAYS = 14
TOP = 3
REFRESH_SECONDS = 5

# Синяя шкала (заливка, цвет цифры) от «свободны немногие» до «свободны все».
# На тёмной теме порядок обратный: почти пустые клетки должны сливаться с фоном, а не светиться.
RAMP = [("#b7d3f6", "#0b0b0b"), ("#86b6ef", "#0b0b0b"), ("#5598e7", "#0b0b0b"),
        ("#2a78d6", "#0b0b0b"), ("#1c5cab", "#ffffff"), ("#104281", "#ffffff")]
DARK_RAMP = RAMP[::-1]


# --- Мелкие помощники -------------------------------------------------------


def plan_days(plan):
    return [plan["first_day"] + timedelta(days=i) for i in range(plan["days"])]


def slot(day, hour):
    """Час с hour:00 до hour+1:00 этого дня — так он хранится в базе."""
    return f"{day.isoformat()}T{hour:02d}"


def best_windows(plan, answered, now):
    """Окна, в которые одни и те же люди свободны на всю прогулку.

    Соседние начала прогулки с одинаковым составом склеиваются в одно окно:
    «все свободны с 14 до 18» вместо четырёх почти одинаковых вариантов.
    Сначала окна, где свободно больше людей, потом более широкие, потом более ранние.
    """
    length = plan["duration"]
    windows = []
    for day in plan_days(plan):
        current = None
        for start in range(plan["start_hour"], plan["end_hour"] - length + 1):
            if datetime.combine(day, time(start)) < now:
                continue
            who = frozenset(
                m["id"] for m in answered
                if all(slot(day, start + i) in m["slots"] for i in range(length))
            )
            if current and who == current["who"] and current["end"] == start + length - 1:
                current["end"] += 1
            elif who:
                current = {"day": day, "start": start, "end": start + length, "who": who}
                windows.append(current)
            else:
                current = None
    windows.sort(key=lambda w: (-len(w["who"]), w["start"] - w["end"], w["day"], w["start"]))
    return windows


# --- Новая прогулка -----------------------------------------------------------


def main():
    code = st.query_params.get("plan")
    if code:
        plan_page(code.strip().upper())
    else:
        new_plan_page()


def new_plan_page():
    st.title("🚶 Когда гуляем?")
    st.caption("Каждый отмечает, когда ему удобно, — сервис находит время, которое подходит большинству.")
    today = local_now().date()
    monday = today + timedelta(days=7 - today.weekday())
    with st.form("new_plan"):
        title = st.text_input("Что планируем?", placeholder="Прогулка в парке", max_chars=60)
        days = st.date_input(
            "Какие дни",
            value=(monday, monday + timedelta(days=6)),
            min_value=today,
            format="DD.MM.YYYY",
            help="По умолчанию — следующая неделя. Выбери в календаре первый и последний день.",
        )
        hours = st.select_slider(
            "В какие часы", options=list(range(25)), value=(10, 22), format_func=lambda h: f"{h}:00"
        )
        duration = st.segmented_control(
            "Сколько гуляем", list(DURATIONS), default=2, format_func=DURATIONS.get, required=True
        )
        name = st.text_input("Твоё имя", max_chars=30)
        submitted = st.form_submit_button("Создать прогулку", type="primary", width="stretch")
    if not submitted:
        return

    if not name.strip():
        st.warning("Напиши своё имя — друзьям важно видеть, кто когда может.")
    elif len(days) != 2:
        st.warning("Выбери в календаре и первый, и последний день.")
    elif (days[1] - days[0]).days >= MAX_DAYS:
        st.warning("Можно выбрать не больше двух недель.")
    elif hours[1] - hours[0] < duration:
        st.warning("Прогулка не помещается в выбранные часы — расширь промежуток.")
    else:
        code, member_id = db.create_plan(
            title.strip() or "Прогулка", days[0], (days[1] - days[0]).days + 1,
            hours[0], hours[1], duration, name,
        )
        st.session_state[f"kogda_me_{code}"] = member_id
        st.query_params.from_dict({"plan": code})
        flash("Прогулка создана — отметь свои часы и позови друзей")
        st.rerun()


# --- Прогулка -----------------------------------------------------------------


def plan_page(code):
    plan = db.get_plan(code)
    if plan is None:
        st.error("Прогулка не найдена. Проверь ссылку — или данные обнулились после перезапуска сервиса.")
        st.button("🚶 Новая прогулка", on_click=go_home)
        return

    st.title(md(plan["title"]))
    days = plan_days(plan)
    st.caption(
        f"{day_label(days[0])} — {day_label(days[-1])} · с {plan['start_hour']}:00"
        f" до {plan['end_hour']}:00 · гуляем {DURATIONS[plan['duration']]}"
    )
    members = db.members(code)
    me = st.session_state.get(f"kogda_me_{code}")
    mine = next((m for m in members if m["id"] == me), None)
    if mine is None:
        join_form(code, members)
        return

    with st.expander("📨 Позвать друзей", expanded=len(members) < 2):
        st.code(share_url(PAGE, plan=code), language=None, wrap_lines=True)
        st.caption("Скопируй ссылку и отправь в чат компании.")

    # Пока свои часы не отмечены, главное — отметить их; потом главное — итог.
    if mine["slots"] is None:
        availability_form(code, plan, me, set())
        results(code, plan)
    else:
        results(code, plan)
        with st.expander("✏️ Изменить мои часы"):
            availability_form(code, plan, me, mine["slots"])

    st.divider()
    st.caption(f"Ты здесь как **{md(mine['name'])}**")
    left, right = st.columns(2)
    left.button("Это не я", on_click=forget_me, args=(code,), width="stretch")
    right.button("🚶 Новая прогулка", on_click=go_home, width="stretch")


def join_form(code, members):
    st.subheader("Как тебя зовут?")
    if members:
        picked = st.pills(
            "Уже участвуют — нажми на своё имя, если ты среди них:",
            [m["id"] for m in members],
            format_func={m["id"]: m["name"] for m in members}.get,
        )
        if picked is not None:
            st.session_state[f"kogda_me_{code}"] = picked
            st.rerun()
    with st.form("kogda_join"):
        name = st.text_input("Новое имя" if members else "Имя", max_chars=30)
        submitted = st.form_submit_button("Войти", type="primary", width="stretch")
    if submitted:
        if name.strip():
            st.session_state[f"kogda_me_{code}"] = db.join(code, name)
            st.rerun()
        st.warning("Напиши имя — так друзья поймут, кто когда может.")


def forget_me(code):
    st.session_state.pop(f"kogda_me_{code}", None)


def availability_form(code, plan, me, mine):
    hours = list(range(plan["start_hour"], plan["end_hour"]))
    today = local_now().date()
    with st.form("kogda_slots", border=False):
        st.markdown("**Когда тебе удобно?** Отметь все часы, в которые можешь гулять: 18:00 — это с 18 до 19.")
        picked = {}
        for day in plan_days(plan):
            if day < today:
                continue
            picked[day] = st.pills(
                day_label(day),
                hours,
                selection_mode="multi",
                default=[h for h in hours if slot(day, h) in mine],
                format_func=lambda h: f"{h}:00",
                key=f"kogda_pick_{me}_{day}",
            )
        submitted = st.form_submit_button("Сохранить", type="primary", width="stretch")
    if not submitted:
        return
    slots = {slot(day, h) for day, chosen in picked.items() for h in chosen}
    # Прошедших дней в форме уже нет — их отметки оставляем как были.
    slots |= {s for s in mine if s < slot(today, 0)}
    db.save_slots(me, slots)
    flash("Сохранено ✅" if slots else "Сохранено: в эти дни у тебя не получится")
    st.rerun()


# --- Итог ---------------------------------------------------------------------


@st.fragment(run_every=REFRESH_SECONDS)
def results(code, plan):
    members = db.members(code)
    answered = [m for m in members if m["slots"] is not None]
    names = {m["id"]: md(m["name"]) for m in members}
    windows = best_windows(plan, answered, local_now())[:TOP]

    with st.container(border=True):
        st.markdown("**🏆 Лучшее время**")
        if not answered:
            st.caption("Пока никто не отметил свои часы.")
        elif not windows:
            st.caption(f"Пока нет времени, когда хоть кто-то свободен на {DURATIONS[plan['duration']]} подряд.")
        waiting = [names[m["id"]] for m in members if m["slots"] is None]
        for w in windows:
            st.markdown(window_text(w, len(answered), everyone=not waiting))
            free = [names[m["id"]] for m in answered if m["id"] in w["who"]]
            busy = [names[m["id"]] for m in answered if m["id"] not in w["who"]]
            line = "Свободны: " + ", ".join(free)
            if busy:
                line += " · не смогут: " + ", ".join(busy)
            if w["end"] - w["start"] > plan["duration"]:
                line += f" · начать можно с {w['start']}:00 до {w['end'] - plan['duration']}:00"
            st.caption(line)
        if waiting:
            st.caption("⏳ Ещё не отметили: " + ", ".join(waiting))

    if answered:
        heatmap(plan, answered, windows[0] if windows else None)


def window_text(w, total, everyone):
    """«сб, 7 ноября, 14:00–18:00 — 3 из 4»."""
    text = f"**{day_label(w['day'])}, {w['start']}:00–{w['end']}:00** — {len(w['who'])} из {total}"
    if len(w["who"]) == total and total > 1:
        # «Всем» — только когда ответили все участники, а не только те, кто успел.
        text += " — подходит всем ✅" if everyone else " ✅"
    return text


def heatmap(plan, answered, best):
    """Неделя целиком: в клетке — сколько человек свободно в этот час."""
    total = len(answered)
    ramp = DARK_RAMP if st.context.theme.type == "dark" else RAMP
    starred = {slot(best["day"], h) for h in range(best["start"], best["end"])} if best else set()
    days = plan_days(plan)

    head = "".join(f"<th>{WEEKDAYS[d.weekday()]}<br>{d.day}</th>" for d in days)
    rows = []
    for hour in range(plan["start_hour"], plan["end_hour"]):
        cells = []
        for day in days:
            key = slot(day, hour)
            free = [m["name"] for m in answered if key in m["slots"]]
            hint = f"{day_label(day)}, {hour}:00–{hour + 1}:00 — " + (", ".join(free) or "никто")
            if not free:
                cells.append(f'<td class="empty" title="{escape(hint)}"></td>')
                continue
            fill, ink = ramp[max(0, -(-len(free) * len(ramp) // total) - 1)]
            mark = "★" if key in starred else ""
            cells.append(
                f'<td style="background:{fill};color:{ink}" title="{escape(hint)}">{mark}{len(free)}</td>'
            )
        rows.append(f"<tr><th class='hour'>{hour}:00</th>{''.join(cells)}</tr>")

    st.html(f"""
<style>
  .kogda-map {{ overflow-x: auto; }}
  .kogda-map table {{ width: 100%; min-width: {3 + 2.2 * len(days)}em; table-layout: fixed;
                     border-collapse: separate; border-spacing: 2px; font-size: 13px; text-align: center; }}
  .kogda-map th {{ font-weight: 400; opacity: .7; line-height: 1.2; padding: 0 0 4px; }}
  .kogda-map th.hour {{ width: 3.2em; text-align: right; padding: 0 6px 0 0; }}
  .kogda-map td {{ height: 24px; border-radius: 4px; font-weight: 600; cursor: default; }}
  .kogda-map td.empty {{ box-shadow: inset 0 0 0 1px rgba(128, 128, 128, .22); }}
</style>
<div class="kogda-map"><table>
  <tr><th class="hour"></th>{head}</tr>
  {''.join(rows)}
</table></div>
""")
    st.caption(
        f"Цифра — сколько человек из {total} свободно в этот час, ★ — лучшее время."
        " На компьютере наведи на клетку, чтобы увидеть имена."
    )
