"""«Конверт» — решения, где никому не нужно рисковать первым.

Участники тайно кладут ответы в конверт, а открывается только оговорённый
заранее итог: набран ли порог, взаимные совпадения, общая картина, все
ответы разом или зона сделки. Механизмы и их паспорта — в mechanisms.py.
"""

import streamlit as st

import konvert_db as storage
import konvert_mechanisms as mx
from common import flash, go_home, md, share_url

PAGE = "konvert"
REFRESH_SECONDS = 5
MIN_SIZE = {"threshold": 2, "match": 3, "slice": mx.MIN_SLICE, "reveal": 2}


# --- Мелкие помощники -------------------------------------------------------


def fmt_number(x):
    """12345.5 → «12 345,5» — как принято записывать числа по-русски."""
    text = f"{x:,.0f}" if float(x).is_integer() else f"{x:,.2f}".rstrip("0")
    return text.replace(",", " ").replace(".", ",")


def show_passport(mech, params):
    with st.container(border=True):
        st.markdown("**🔏 Паспорт приватности**")
        for label, text in mx.passport(mech, params):
            st.markdown(f"**{label}:** {text}")


# --- Создание конверта --------------------------------------------------------


def home_page():
    st.title("✉️ Конверт")
    st.caption("Решения, где никому не нужно рисковать первым. Каждый тайно кладёт ответ в конверт — открывается только итог.")

    mech = st.pills(
        "Механизм",
        list(mx.MECHANISMS),
        default="threshold",
        required=True,
        format_func=lambda m: f"{mx.MECHANISMS[m]['icon']} {mx.MECHANISMS[m]['title']}",
    )
    info = mx.MECHANISMS[mech]
    st.markdown(info["tagline"])
    st.caption(f"🎓 {info['theory']}")

    templates = info["templates"]
    tpl = st.pills(
        "Шаблон",
        list(range(len(templates))),
        default=0,
        required=True,
        format_func=lambda i: templates[i]["label"],
        key=f"tpl_{mech}",
    )
    t = templates[tpl]
    k = f"{mech}_{tpl}"  # свои ключи у каждого шаблона, чтобы при смене подставлялись его значения

    question = st.text_input("Вопрос", value=t["question"], max_chars=150,
                             placeholder="О чём спрашиваем?", key=f"q_{k}")
    params, size, role = {}, 2, None
    if mech == "deal":
        params = {"roles": t["roles"], "unit": "₽"}
        role = st.radio("Кто ты в этой сделке", list(t["roles"]), format_func=t["roles"].get,
                        horizontal=True, key=f"role_{k}")
        params["show_mid"] = st.toggle("Если сделка возможна — показать середину", value=True, key=f"mid_{k}")
    else:
        size = st.number_input("Сколько человек участвует, включая тебя", min_value=MIN_SIZE[mech],
                               max_value=300, value=t["size"], key=f"n_{k}")
        if mech == "threshold":
            params["k"] = st.number_input("Порог: сколько нужно «за»", min_value=1, max_value=size,
                                          value=min(size, t.get("k", size // 2 + 1)), key=f"k_{k}_{size}")
            params["names"] = st.toggle("Если порог набран — показать, кто «за»",
                                        value=t.get("names", False), key=f"names_{k}")
        elif mech == "match":
            params["picks"] = st.number_input("Сколько человек можно отметить", min_value=1,
                                              max_value=min(5, size - 1), value=min(3, size - 1),
                                              key=f"picks_{k}_{size}")
        elif mech == "slice":
            raw = st.text_area("Варианты ответа — каждый с новой строки", "\n".join(t["options"]), key=f"opts_{k}")
            params["options"] = list(dict.fromkeys(o.strip() for o in raw.splitlines() if o.strip()))

    name = st.text_input("Твоё имя", max_chars=30)
    show_passport(mech, params)

    if st.button("Создать конверт", type="primary", width="stretch"):
        if not question.strip():
            st.warning("Напиши вопрос.")
        elif not name.strip():
            st.warning("Напиши своё имя — так участники поймут, от кого конверт.")
        elif mech == "slice" and not 2 <= len(params["options"]) <= 8:
            st.warning("Нужно от 2 до 8 разных вариантов ответа.")
        else:
            env_id, key = storage.create_envelope(mech, question.strip(), params, size, name, role)
            st.query_params.from_dict({"e": env_id, "me": key})
            flash("Конверт создан — отправь ссылку участникам")
            st.rerun()


# --- Страница конверта ----------------------------------------------------------


def envelope_page(env_id, key):
    env = storage.get_envelope(env_id)
    if env is None:
        st.error("Конверт не найден. Проверь ссылку — или данные обнулились после перезапуска сервиса.")
        st.button("✉️ Новый конверт", on_click=go_home)
        return

    info = mx.MECHANISMS[env["mech"]]
    st.caption(f"{info['icon']} {info['title']}")
    st.subheader(md(env["question"]))

    me = storage.member_by_key(env_id, key) if key else None
    members = storage.members(env_id)
    if me is None:
        guest_view(env, members)
    elif env["result"] is not None:
        show_result(env, me, members)
        with st.expander("🔏 Паспорт приватности"):
            for label, text in mx.passport(env["mech"], env["params"]):
                st.markdown(f"**{label}:** {text}")
    else:
        invite_links(env, me, members)
        answer_section(env, me, members)
        status(env_id, me["id"], lobby=env["mech"] == "match" and len(members) < env["size"])
        if me["is_creator"]:
            with st.popover("Вскрыть досрочно"):
                st.caption("Итог посчитается по тем, кто уже ответил. Остальные ответить уже не смогут.")
                st.button("Вскрыть сейчас", type="primary", on_click=storage.open_envelope, args=(env_id,))
        show_passport(env["mech"], env["params"])

    if me is not None:
        st.divider()
        role = env["params"].get("roles", {}).get(me["role"])
        st.caption(f"Ты здесь как **{md(me['name'])}**" + (f" — {role.lower()}" if role else ""))
    st.button("✉️ Новый конверт", on_click=go_home)


def guest_view(env, members):
    if env["result"] is not None:
        st.info("Конверт уже вскрыт. Итог видят участники — каждый по своей личной ссылке.")
        return
    if len(members) >= env["size"]:
        st.warning("Все места в конверте заняты. Если ты участник — открой свою личную ссылку.")
        return

    show_passport(env["mech"], env["params"])
    roles = env["params"].get("roles")
    if roles:
        taken = {m["role"] for m in members}
        free = next(r for r in roles if r not in taken)
        st.markdown(f"Ты участвуешь как **{roles[free].lower()}**.")
    with st.form("join"):
        name = st.text_input("Твоё имя", max_chars=30)
        submitted = st.form_submit_button("Участвовать", type="primary", width="stretch")
    if not submitted:
        return
    if not name.strip():
        st.warning("Напиши имя — так участники поймут, кто уже ответил.")
        return
    status_, key = storage.join(env["id"], name)
    if status_ == "ok":
        st.query_params.from_dict({"e": env["id"], "me": key})
        flash("Ты в конверте. Ссылка в адресной строке теперь личная — не пересылай её")
        st.rerun()
    st.warning({
        "taken": "Это имя уже занято. Если это ты — открой свою личную ссылку.",
        "full": "Места в конверте уже закончились.",
        "closed": "Конверт уже вскрыт.",
    }[status_])


def invite_links(env, me, members):
    if len(members) < env["size"]:
        label = "📨 Ссылка для второй стороны" if env["mech"] == "deal" else "📨 Позвать участников"
        with st.expander(label, expanded=bool(me["is_creator"])):
            st.code(share_url(PAGE, e=env["id"]), language=None, wrap_lines=True)
            st.caption(f"Присоединились {len(members)} из {env['size']}.")
    with st.expander("🔑 Твоя личная ссылка"):
        st.code(share_url(PAGE, e=env["id"], me=me["key"]), language=None, wrap_lines=True)
        st.caption("По ней ты вернёшься к конверту. Не пересылай её: по ней можно ответить за тебя.")


def answer_section(env, me, members):
    if env["mech"] == "match" and len(members) < env["size"]:
        st.info(f"Ждём, пока соберутся все: {len(members)} из {env['size']}. "
                "Отмечать можно будет, когда группа соберётся, — иначе последние не попадут в список.")
        return
    current = storage.get_answer(env["id"], me["id"])
    with st.form("answer"):
        value = answer_input(env, me, members, current)
        label = "Изменить ответ" if current is not None else "Положить в конверт"
        submitted = st.form_submit_button(label, type="primary", width="stretch")
    if current is not None:
        st.caption("✅ Твой ответ в конверте. До вскрытия его можно поменять.")
    if not submitted:
        return
    if value is None:
        st.warning("Сначала дай ответ.")
        return
    storage.save_answer(env["id"], me["id"], value)
    flash("Ответ в конверте")
    st.rerun()


def answer_input(env, me, members, current):
    """Поле ответа под механизм. Возвращает ответ или None, если ответа ещё нет."""
    mech, params = env["mech"], env["params"]
    if mech == "threshold":
        choice = st.radio("Твой ответ", ["Да", "Нет"], horizontal=True,
                          index=None if current is None else int(not current))
        return None if choice is None else choice == "Да"
    if mech == "match":
        others = {m["id"]: m["name"] for m in members if m["id"] != me["id"]}
        return st.multiselect(
            f"Кого отмечаешь? Максимум — {params['picks']}, можно никого",
            list(others),
            default=[i for i in current or [] if i in others],
            format_func=others.get,
            max_selections=params["picks"],
            placeholder="Выбери из списка",
        )
    if mech == "slice":
        options = params["options"]
        return st.radio("Твой ответ", list(range(len(options))), index=current, format_func=options.__getitem__)
    if mech == "reveal":
        return st.text_input("Твой ответ", value=current or "", max_chars=100).strip() or None
    # deal
    if me["role"] == "seller":
        label = f"Твой минимум, {params['unit']}: меньше — не соглашусь"
    else:
        label = f"Твой максимум, {params['unit']}: больше — не соглашусь"
    st.caption("Называй честную границу: блеф может сорвать сделку, которая была возможна.")
    return st.number_input(label, min_value=0, value=current, step=1000, placeholder="Например, 50000")


@st.fragment(run_every=REFRESH_SECONDS)
def status(env_id, me_id, lobby):
    env = storage.get_envelope(env_id)
    members = storage.members(env_id)
    # Конверт вскрыли или группа собралась — перерисовываем страницу целиком.
    if env is None or env["result"] is not None or (lobby and len(members) >= env["size"]):
        st.rerun()
    answered = storage.answered_ids(env_id)
    with st.container(border=True):
        st.markdown(f"**Ответили {len(answered)} из {env['size']}**")
        st.progress(len(answered) / env["size"])
        waiting = [md(m["name"]) for m in members if m["id"] not in answered]
        if waiting:
            st.caption("Ждём: " + ", ".join(waiting))
        if len(members) < env["size"]:
            st.caption(f"Ещё не присоединились: {env['size'] - len(members)}")
        st.caption("Конверт вскроется сам, когда ответят все.")


# --- Итоги --------------------------------------------------------------------


def show_result(env, me, members):
    mech, params, result = env["mech"], env["params"], env["result"]
    st.markdown("#### ✉️ Конверт вскрыт")

    if mech == "threshold":
        if result["reached"]:
            st.success(f"Порог набран: «за» — {result['yes']}, нужно было {params['k']}. "
                       f"Ответили {result['answered']} из {env['size']}.")
            if "names" in result:
                st.markdown("**Кто «за»:** " + ", ".join(md(n) for n in result["names"]))
        else:
            st.info(f"Порог не набран: нужно было {params['k']} «за». Сколько их было и кто — не узнает никто.")

    elif mech == "match":
        names = {m["id"]: m["name"] for m in members}
        mine = [b if a == me["id"] else a for a, b in result["pairs"] if me["id"] in (a, b)]
        if mine:
            st.success("💚 Взаимно: " + ", ".join(md(names[i]) for i in mine))
            celebrate(env["id"])
        else:
            st.info("Взаимных совпадений нет. Твой выбор останется тайной.")

    elif mech == "slice":
        if result.get("hidden"):
            st.info(f"Ответов меньше {mx.MIN_SLICE} — итог скрыт, иначе по нему можно было бы вычислить, кто как ответил.")
        else:
            for option, count in zip(params["options"], result["counts"]):
                st.markdown(f"**{md(option)}** — {count}")
                st.progress(count / result["answered"])
            st.caption(f"Ответили {result['answered']} из {env['size']}.")

    elif mech == "reveal":
        if not result["rows"]:
            st.info("Конверт вскрыли до того, как кто-то ответил.")
        for name, answer in result["rows"]:
            st.markdown(f"**{md(name)}:** {md(answer)}")
        stats = result.get("stats")
        if stats:
            st.info(f"Меньше всего — {fmt_number(stats['min'])}, больше всего — {fmt_number(stats['max'])}, "
                    f"середина (медиана) — {fmt_number(stats['median'])}.")
            if stats["min"] > 0 and stats["max"] >= 2 * stats["min"]:
                st.caption("Разброс большой — стоит обсудить, почему ответы так различаются.")

    else:  # deal
        if result.get("incomplete"):
            st.info("Конверт вскрыли до того, как ответили обе стороны, — сравнивать нечего.")
        elif result["deal"]:
            st.success("🤝 Зона сделки есть: ваши границы пересекаются.")
            if "mid" in result:
                st.markdown(f"**Середина:** {fmt_number(result['mid'])} {params['unit']}")
            celebrate(env["id"])
        else:
            st.info("Зоны сделки нет: границы не пересеклись. Насколько далеко — не узнает никто.")


def celebrate(env_id):
    if not st.session_state.get(f"celebrated_{env_id}"):
        st.session_state[f"celebrated_{env_id}"] = True
        st.balloons()


# --- Маршрутизация ------------------------------------------------------------


def main():
    env_id = st.query_params.get("e")
    if env_id:
        envelope_page(env_id, st.query_params.get("me", ""))
    else:
        home_page()
