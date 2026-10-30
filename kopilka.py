"""«Копилка» — когда накоплю на цель и сколько откладывать, чтобы успеть к дате.

Деньги откладываются раз в неделю, считаем в целых рублях и целых неделях.
"""

import math
from datetime import timedelta

import streamlit as st

from common import day_label, local_now, md, money, plural

PAGE = "kopilka"
MODES = ["⏳ Когда накоплю", "📅 Успеть к дате"]


def weeks_word(n):
    """«за 1 неделю», «за 3 недели», «за 5 недель»."""
    return plural(n, "неделю", "недели", "недель")


def main():
    st.title("💰 Копилка")
    st.caption("Посчитай, когда накопишь на цель, — или сколько откладывать, чтобы успеть к нужной дате.")

    goal = st.text_input("На что копим?", placeholder="Наушники", max_chars=40).strip()
    target = f"«{md(goal)}»" if goal else "цель"
    left, right = st.columns(2)
    price = left.number_input("Сколько стоит, ₽", min_value=0, value=12000, step=500)
    have = right.number_input("Уже есть, ₽", min_value=0, value=2000, step=500)
    mode = st.segmented_control("Что считаем", MODES, default=MODES[0], required=True)

    need = price - have
    if price == 0:
        st.info("Впиши, сколько стоит цель.")
        return
    if need <= 0:
        st.success(f"Уже хватает на {target} 🎉 Останется {money(-need)}.")
        return

    today = local_now().date()
    if mode == MODES[0]:
        weekly = st.number_input("Откладываю в неделю, ₽", min_value=0, value=1000, step=100)
        if weekly == 0:
            st.warning("Если откладывать 0 ₽ в неделю, цель не приблизится. Попробуй хотя бы 100 ₽.")
            return
        weeks = math.ceil(need / weekly)
        st.success(
            f"Накопишь на {target} за **{weeks_word(weeks)}** — "
            f"к **{day_label(today + timedelta(weeks=weeks), weekday=False)}**."
        )
        faster = math.ceil(weekly * 1.2)
        saved = weeks - math.ceil(need / faster)
        if saved > 0:
            st.caption(f"Откладывай по {money(faster)} (на 20 % больше) — и накопишь на {weeks_word(saved)} раньше.")
    else:
        deadline = st.date_input("К какой дате", value=today + timedelta(weeks=8),
                                 min_value=today + timedelta(days=1), format="DD.MM.YYYY")
        weeks = (deadline - today).days // 7
        if weeks == 0:
            st.warning(f"До {day_label(deadline, weekday=False)} меньше недели — откладывать по неделям не выйдет. "
                       f"Нужно сразу {money(need)}.")
            return
        weekly = math.ceil(need / weeks)
        st.success(
            f"Чтобы накопить на {target} к **{day_label(deadline, weekday=False)}**, "
            f"откладывай по **{money(weekly)} в неделю** — {weeks_word(weeks)} подряд."
        )

    st.progress(have / price, text=f"Уже есть {money(have)} из {money(price)} — {have * 100 // price} %")
    plan(price, have, weekly, today)


def plan(price, have, weekly, today):
    """Контрольные точки: к какой дате будет четверть, половина, три четверти и вся сумма."""
    rows = ["| | Сумма | Когда |", "|---|---|---|"]
    for share, label in [(0.25, "Четверть"), (0.5, "Половина"), (0.75, "Три четверти"), (1, "Вся сумма")]:
        amount = math.ceil(price * share)
        if amount <= have:
            when = "уже есть ✅"
        else:
            weeks = math.ceil((amount - have) / weekly)
            when = day_label(today + timedelta(weeks=weeks), weekday=False)
        rows.append(f"| {label} | {money(amount)} | {when} |")
    st.markdown("**План по неделям**")
    st.markdown("\n".join(rows))
