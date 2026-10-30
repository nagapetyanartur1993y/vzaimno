"""Помощники, общие для всех мини-сервисов."""

import os
import re
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import streamlit as st

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]


def md(text):
    """Экранирует разметку: «**», «$» или «[…](…)» в тексте не должны ничего ломать."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~$:])", r"\\\1", str(text))


def share_url(page, **params):
    """Ссылка на страницу мини-сервиса, которую отправляют друзьям."""
    url = os.environ.get("PUBLIC_URL") or st.context.url or "http://localhost:8501"
    # Streamlit Cloud показывает приложение во фрейме по адресу …/~/+/, друзьям нужна обычная ссылка.
    # А st.context.url заканчивается адресом текущей страницы — отрезаем его, чтобы получить корень.
    base = url.replace("/~/+", "").rstrip("/").removesuffix("/" + page)
    return f"{base}/{page}?{urlencode(params)}"


def local_now():
    """Время пользователя, а не сервера: на Streamlit Cloud часы сервера идут по UTC."""
    try:
        return datetime.now(ZoneInfo(st.context.timezone)).replace(tzinfo=None)
    except (TypeError, ValueError, KeyError):
        return datetime.now()


def day_label(day, weekday=True):
    """«сб, 7 ноября» или без дня недели «7 ноября»; год — только если он не текущий."""
    text = f"{day.day} {MONTHS[day.month - 1]}"
    if day.year != local_now().year:
        text += f" {day.year}"
    return f"{WEEKDAYS[day.weekday()]}, {text}" if weekday else text


def plural(n, one, few, many):
    """plural(5, "неделя", "недели", "недель") → «5 недель», а не «5 недели»."""
    if n % 10 == 1 and n % 100 != 11:
        word = one
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = few
    else:
        word = many
    return f"{n} {word}"


def money(amount):
    """12000 → «12 000 ₽» с неразрывными пробелами: сумма не разорвётся на две строки."""
    return f"{amount:,.0f}".replace(",", " ") + " ₽"


def flash(message):
    """Сообщение, которое переживёт st.rerun() и покажется на следующем прогоне."""
    st.session_state["flash"] = message


def go_home():
    """Назад к началу мини-сервиса: страница та же, параметры из ссылки стираем."""
    st.query_params.clear()
