# -*- coding: utf-8 -*-
"""Расчётный модуль КИПиА — мобильная версия (Kivy).
Соответствует настольной программе converter.py (v3): конвертация давления,
квадратичная зависимость расхода, диагностика датчика, термометры НСХ,
термопары НСХ, расход через диафрагму (ГОСТ 8.586.2 / ISO 5167).
"""
import math
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.core.clipboard import Clipboard

import core

# ----------------------------------------------------------------------
# Палитра (RGB 0..1)
# ----------------------------------------------------------------------
PRIMARY = (0.145, 0.388, 0.922, 1)      # #2563eb
PRIMARY_DARK = (0.118, 0.251, 0.686, 1) # #1e40af
SUCCESS = (0.086, 0.647, 0.29, 1)       # #16a34a
DANGER = (0.863, 0.149, 0.149, 1)       # #dc2626
WARNING = (0.851, 0.466, 0.024, 1)      # #d97706
BG = (0.957, 0.965, 0.976, 1)           # #f4f6f9
PANEL = (1, 1, 1, 1)
TEXT = (0.122, 0.161, 0.216, 1)         # #1f2937
MUTED = (0.42, 0.447, 0.502, 1)         # #6b7280
BORDER = (0.796, 0.835, 0.882, 1)       # #cbd5e1

FONT_NAME = "Roboto"


def _num(text):
    return float(str(text).replace(",", ".").strip())


def num_filter(text, from_undo):
    return "".join(ch for ch in text if ch in "-.,0123456789")


# ----------------------------------------------------------------------
# Утилиты
# ----------------------------------------------------------------------
def make_label(text, size=17, bold=False, color=TEXT, halign="left",
               valign="middle", wrap=None, height=40):
    if wrap is None:
        wrap = max(120, len(str(text)) * (size + 6))
    return Label(
        text=text, font_size=size, bold=bold, color=color,
        halign=halign, valign=valign,
        text_size=(wrap, None),
        size_hint_y=None, height=height,
    )


def make_input(hint="", multiline=False, font_size=17, height=48):
    ti = TextInput(
        hint_text=hint, multiline=multiline, font_size=font_size,
        input_filter=num_filter,
        size_hint_y=None, height=height,
        background_color=(1, 1, 1, 1), foreground_color=TEXT,
        cursor_color=PRIMARY,
    )
    return ti


def make_text(hint="", multiline=False, font_size=17):
    ti = TextInput(
        hint_text=hint, multiline=multiline, font_size=font_size,
        size_hint_y=None, height=48,
        background_color=(1, 1, 1, 1), foreground_color=TEXT,
        cursor_color=PRIMARY,
    )
    return ti


def make_button(text, on_press=None, bg=PRIMARY, fg=(1, 1, 1, 1),
                bold=True, size=17, height=52):
    kwargs = dict(
        text=text, font_size=size, bold=bold, background_color=bg,
        color=fg, size_hint_y=None, height=height,
    )
    if on_press is not None:
        kwargs["on_press"] = on_press
    return Button(**kwargs)


def make_spinner(values, index=0, size=17, height=48):
    sp = Spinner(
        text=values[index], values=values, font_size=size,
        size_hint_y=None, height=height,
        background_color=(1, 1, 1, 1), color=TEXT,
    )
    return sp


def make_row(height=None):
    return BoxLayout(orientation="horizontal", spacing=8, padding=(0, 2))


def as_scroll(widget):
    sv = ScrollView()
    sv.add_widget(widget)
    return sv


def new_scroll(width_hint=None, height=None):
    content = BoxLayout(orientation="vertical", size_hint_y=None, padding=14, spacing=10)
    content.bind(minimum_height=content.setter("height"))
    return content


def field(content, caption, input_widget=None, hint=""):
    box = BoxLayout(orientation="vertical", size_hint_y=None, height=76, spacing=2)
    box.add_widget(make_label(caption, size=14, color=MUTED))
    box.add_widget(input_widget if input_widget is not None else make_input(hint))
    content.add_widget(box)


def popup(title, msg, kind="info"):
    cl = {"info": PRIMARY, "ok": SUCCESS, "error": DANGER, "warn": WARNING}.get(kind, PRIMARY)
    content = BoxLayout(orientation="vertical", padding=18, spacing=10)
    lbl = make_label(str(msg), size=16, wrap=420, halign="left")
    content.add_widget(lbl)
    btn = make_button("ОК", bg=cl, height=48)
    content.add_widget(btn)
    p = Popup(title=f"[b]{title}[/b]", content=content,
              size_hint=(0.86, None), height=320, auto_dismiss=True, title_color=PRIMARY)
    btn.bind(on_press=p.dismiss)
    p.open()


def copy_text(text):
    Clipboard.copy(text)
    popup("Скопировано", "Текст помещён в буфер обмена.", "ok")


# ----------------------------------------------------------------------
# Хелпер: карточка входа (модуль с таблицей результатов)
# ----------------------------------------------------------------------
def make_result_area(content):
    return make_label("", size=16, color=TEXT, halign="left", wrap=520)


def wrap_screen(scr, title, content):
    """Добавляет в экран верхнюю панель с кнопкой «Назад» и прокручиваемый контент."""
    outer = BoxLayout(orientation="vertical")
    bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=52,
                    padding=(10, 6), spacing=10)
    back = Button(text="‹ Меню", font_size=16, background_color=PRIMARY,
                  size_hint_x=None, width=120)
    back.bind(on_press=lambda *_a: setattr(scr.manager, "current", "menu"))
    bar.add_widget(back)
    bar.add_widget(make_label(title, size=17, bold=True, color=PRIMARY))
    outer.add_widget(bar)
    outer.add_widget(as_scroll(content))
    scr.add_widget(outer)


# ----------------------------------------------------------------------
# ЭКРАН 1. Конвертация и погрешность
# ----------------------------------------------------------------------
class ConvScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        content = new_scroll()

        self.e_value = make_input()
        field(content, "Значение:", self.e_value)
        r_units = make_row()
        r_units.add_widget(make_label("Из единицы:", size=14, color=MUTED))
        self.s_from = make_spinner(list(core.UNITS_DISPLAY.keys()), index=8)  # МПа
        r_units.add_widget(self.s_from)
        r_units.add_widget(make_label("→ В:", size=14, color=MUTED))
        self.s_to = make_spinner(list(core.UNITS_DISPLAY.keys()), index=7)    # кгс/см²
        r_units.add_widget(self.s_to)
        content.add_widget(r_units)
        self.e_span = make_input()
        field(content, "ВПИ (для погрешности):", self.e_span)
        self.e_acc = make_input()
        field(content, "Класс точности, %:", self.e_acc)

        btn = make_button("КОНВЕРТИРОВАТЬ", self.on_convert)
        content.add_widget(btn)
        self.l_res = make_result_area(content)
        content.add_widget(self.l_res)
        b2 = make_button("Копировать результат", lambda *_: copy_text(self.l_res.text),
                         bg=(0.42, 0.447, 0.502, 1), height=46)
        content.add_widget(b2)

        wrap_screen(self, "Конвертация и погрешность", content)

    def on_convert(self, *_):
        try:
            v = _num(self.e_value.text)
        except ValueError:
            popup("Ошибка ввода", "Введите корректное число в поле значения.", "error")
            return
        fk = core.UNITS_DISPLAY[self.s_from.text]
        tk = core.UNITS_DISPLAY[self.s_to.text]
        res = core.convert(v, fk, tk)
        fr = core.get_form(res, tk)
        txt = f"{v:.6f} {core.get_form(v, fk)} = {res:.6f} {fr}"

        if self.e_span.text.strip() and self.e_acc.text.strip():
            try:
                span = _num(self.e_span.text)
                acc = _num(self.e_acc.text)
                err = core.calculate_error(v, span, acc, fk, tk)
                if err:
                    txt += "\n" + err
                else:
                    txt += "\nРасчёт погрешности невозможен: проверьте ВПИ и класс точности"
            except ValueError:
                txt += "\nОшибка: в полях ВПИ или класса точности должны быть числа"
        self.l_res.text = txt


# ----------------------------------------------------------------------
# ЭКРАН 2. Расход (квадратичная зависимость)
# ----------------------------------------------------------------------
class FlowScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        content = new_scroll()

        self.e_qmax = make_input()
        field(content, "Макс. расход:", self.e_qmax)
        r0 = make_row()
        r0.add_widget(make_label("Ед. расхода:", size=14, color=MUTED))
        self.s_unit = make_spinner(["т/ч", "м³/ч"])
        r0.add_widget(self.s_unit)
        content.add_widget(r0)

        self.e_span = make_input()
        field(content, "ВПИ перепада (значение):", self.e_span)
        r1 = make_row()
        r1.add_widget(make_label("Ед. перепада:", size=14, color=MUTED))
        self.s_span_unit = make_spinner(["Па", "кПа", "МПа", "бар", "кгс/см²", "кгс/м²"])
        r1.add_widget(self.s_span_unit)
        content.add_widget(r1)

        self.e_acc = make_input()
        field(content, "Класс точности, %:", self.e_acc)
        r2 = make_row()
        r2.add_widget(make_label("Сигнал:", size=14, color=MUTED))
        self.s_sig = make_spinner(["мА (4–20)", "В (0–10)", "%"])
        r2.add_widget(self.s_sig)
        content.add_widget(r2)
        self.e_points = make_input()
        field(content, "Точки шкалы (через запятую; пусто — 0..100):", self.e_points)

        btn = make_button("РАССЧИТАТЬ ТАБЛИЦУ", self.on_calc)
        content.add_widget(btn)

        # таблица результатов
        self.tbl_title = make_label("", size=15, bold=True, color=PRIMARY)
        content.add_widget(self.tbl_title)
        self.tbl = GridLayout(cols=5, size_hint_y=None, spacing=4)
        self.tbl.bind(minimum_height=self.tbl.setter("height"))
        content.add_widget(self.tbl)
        b2 = make_button("Скопировать таблицу", self.on_copy,
                         bg=(0.42, 0.447, 0.502, 1), height=46)
        content.add_widget(b2)
        self.rows = []

        wrap_screen(self, "Расход (квадратичная)", content)

    def on_calc(self, *_):
        try:
            qmax = _num(self.e_qmax.text)
            span = _num(self.e_span.text)
            acc = _num(self.e_acc.text)
        except ValueError:
            popup("Ошибка ввода", "Заполните Макс. расход, ВПИ перепада и Класс точности.", "error")
            return
        if qmax <= 0 or span <= 0 or acc < 0:
            popup("Ошибка", "Макс. расход > 0, ВПИ > 0, Класс точности >= 0.", "error")
            return
        u2pa = {"Па": 1, "кПа": 1000, "МПа": 1e6, "бар": 1e5,
                "кгс/см²": 98066.5, "кгс/м²": 9.80665}
        factor = u2pa[self.s_span_unit.text]
        span_pa = span * factor

        pts_txt = self.e_points.text.strip()
        if pts_txt:
            try:
                custom = sorted(set(_num(x) for x in pts_txt.replace(",", " ").split()))
            except ValueError:
                popup("Ошибка", "Точки шкалы — числа через запятую.", "error")
                return
            # кастомные точки интерпретируются как значения расхода (для КСД2 и т.п.)
            is_custom = True
        else:
            custom = list(range(0, 101, 10))
            is_custom = False

        self.tbl.clear_widgets()
        self.rows = []
        head = ["%", "Расход", "Перепад", "Отн. погр., %", "Сигнал"]
        for h in head:
            self.tbl.add_widget(make_label(h, size=13, bold=True, color=PRIMARY,
                                           halign="center"))
        for p in custom:
            if is_custom:
                q = p
                pct = (q / qmax) * 100.0
                if pct > 100:
                    pct = 100.0
                    q = qmax
                dp_pa = span_pa * (q / qmax) ** 2
            else:
                pct = p
                q = qmax * (pct / 100.0) ** 0.5
                dp_pa = span_pa * (pct / 100.0)
            abs_err = span_pa * acc / 100.0
            rel = (abs_err / dp_pa * 100.0) if dp_pa > 0 else 0.0
            dp_dis = dp_pa / factor
            if self.s_sig.text.startswith("мА"):
                sig = 4 + 16 * pct / 100.0
            elif self.s_sig.text.startswith("В"):
                sig = 10 * pct / 100.0
            else:
                sig = pct
            self.tbl.add_widget(make_label(f"{pct:.1f}%", size=14, halign="center"))
            self.tbl.add_widget(make_label(f"{q:.2f}", size=14, halign="center"))
            self.tbl.add_widget(make_label(f"{dp_dis:.2f}", size=14, halign="center"))
            self.tbl.add_widget(make_label(f"{rel:.2f}", size=14, halign="center"))
            self.tbl.add_widget(make_label(f"{sig:.2f}", size=14, halign="center"))
            self.rows.append((pct, q, self.s_unit.text, dp_dis, rel, sig))

    def on_copy(self, *_):
        if not self.rows:
            popup("Инфо", "Сначала выполните расчёт.", "info")
            return
        lines = ["%\tРасход\tЕд.\tПерепад\tОтн.погр.,%\tСигнал"]
        for r in self.rows:
            lines.append("\t".join(f"{x:.2f}" for x in r))
        copy_text("\n".join(lines))


# ----------------------------------------------------------------------
# ЭКРАН 3. Диагностика датчика
# ----------------------------------------------------------------------
VERIF_POINTS = core.VERIFICATION_POINTS  # [0,25,50,75,100]


class DiagScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        content = new_scroll()

        self.e_type = make_text()
        field(content, "Тип датчика:", self.e_type)
        self.e_sn = make_text()
        field(content, "Зав. №:", self.e_sn)
        self.e_span = make_input()
        field(content, "ВПИ (диапазон):", self.e_span)
        r0 = make_row()
        r0.add_widget(make_label("Ед. ВПИ:", size=14, color=MUTED))
        self.s_unit = make_spinner(list(core.UNITS_DISPLAY.keys()), index=8)
        r0.add_widget(self.s_unit)
        content.add_widget(r0)
        self.e_acc = make_input()
        field(content, "Класс точности, %:", self.e_acc)

        b1 = make_button("ВЫПОЛНИТЬ ДИАГНОСТИКУ", self.on_diag)
        content.add_widget(b1)
        self.l_diag = make_result_area(content)
        content.add_widget(self.l_diag)
        b2 = make_button("Копировать фрагмент акта", lambda *_: copy_text(self.l_diag.text),
                         bg=(0.42, 0.447, 0.502, 1), height=46)
        content.add_widget(b2)

        # ---- мини-протокол поверки ----
        content.add_widget(make_label("Мини-протокол поверки (по точкам)", size=18,
                                      bold=True, color=PRIMARY))
        b3 = make_button("Сформировать протокол", self.on_gen)
        content.add_widget(b3)
        self.tbl = GridLayout(cols=4, size_hint_y=None, spacing=4)
        self.tbl.bind(minimum_height=self.tbl.setter("height"))
        content.add_widget(self.tbl)
        b4 = make_button("Проверить точки", self.on_check, bg=SUCCESS)
        content.add_widget(b4)
        self.row_inputs = []   # (exp, tol, TextInput, verdict_label)

        wrap_screen(self, "Диагностика датчика", content)

    def on_diag(self, *_):
        try:
            span_v = _num(self.e_span.text)
            acc = _num(self.e_acc.text)
        except ValueError:
            popup("Ошибка ввода", "Заполните ВПИ и Класс точности.", "error")
            return
        if span_v <= 0 or acc < 0:
            popup("Ошибка", "ВПИ > 0, Класс точности >= 0.", "error")
            return
        tol = acc / 100.0 * 16.0
        self.l_diag.text = (f"Тип: {self.e_type.text or 'Не указан'}\n"
                            f"Зав. №: {self.e_sn.text or '-'}\n"
                            f"ВПИ: {span_v:.2f} {self.s_unit.text}\n"
                            f"Класс точности: {acc:.1f}%\n"
                            f"Допуск (шкала 4–20 мА): ±{tol:.3f} мА\n\n"
                            f"Для поточечной проверки нажмите «Сформировать протокол», "
                            f"внесите измеренные мА и «Проверить точки».")

    def on_gen(self, *_):
        try:
            span_v = _num(self.e_span.text)
            acc = _num(self.e_acc.text)
        except ValueError:
            popup("Ошибка ввода", "Заполните ВПИ и Класс точности.", "error")
            return
        span_pa = span_v * core.UNITS_CALC[core.UNITS_DISPLAY[self.s_unit.text]]
        tol = acc / 100.0 * 16.0
        self.tbl.clear_widgets()
        self.row_inputs = []
        for h in ["Точка", "Давление", "Ож. ток, мА", ""]:
            self.tbl.add_widget(make_label(h, size=13, bold=True, color=PRIMARY, halign="center"))
        for pct in VERIF_POINTS:
            pv = pct / 100.0 * span_v
            exp = 4.0 + 16.0 * pct / 100.0
            ti = make_input(hint="изм. мА", font_size=15)
            v_lbl = make_label("", size=13, color=MUTED, halign="center")
            self.tbl.add_widget(make_label(f"{pct}%", size=14, halign="center"))
            self.tbl.add_widget(make_label(f"{pv:,.1f}", size=14, halign="center"))
            self.tbl.add_widget(make_label(f"{exp:.3f}", size=14, halign="center"))
            self.tbl.add_widget(ti)
            self.row_inputs.append((exp, tol, ti, v_lbl))
        popup("Протокол готов", "Введите измеренные мА и нажмите «Проверить точки».", "ok")

    def on_check(self, *_):
        if not self.row_inputs:
            popup("Инфо", "Сначала сформируйте протокол.", "info")
            return
        checked = 0
        for exp, tol, ti, v_lbl in self.row_inputs:
            raw = ti.text.strip()
            if not raw:
                continue
            try:
                m = _num(raw)
            except ValueError:
                continue
            d = m - exp
            ok = abs(d) <= tol
            v_lbl.text = f"✓ В допуске" if ok else f"✗ Брак\n(d={d:+.3f})"
            v_lbl.color = SUCCESS if ok else DANGER
            v_lbl.height = 44
            checked += 1
        if checked:
            popup("Готово", f"Проверено точек: {checked}. Вердикт — в зелёном столбце.", "ok")
        else:
            popup("Инфо", "Нет данных для проверки (заполните измеренные мА).", "info")


# ----------------------------------------------------------------------
# ЭКРАН 4. Температура (НСХ) — термометры
# ----------------------------------------------------------------------
class TempScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        content = new_scroll()

        content.add_widget(make_label("Термометр (R ↔ t)", size=18, bold=True, color=PRIMARY))
        r0 = make_row()
        r0.add_widget(make_label("Тип:", size=14, color=MUTED))
        self.s_thermo = make_spinner(core.THERMO_DISPLAY_LIST + ["Пользовательская"], index=1)
        r0.add_widget(self.s_thermo)
        content.add_widget(r0)

        # пользовательская НСХ
        self.panel_nsh = BoxLayout(orientation="vertical", size_hint_y=None, spacing=2)
        content.add_widget(self.panel_nsh)
        self.panel_nsh.add_widget(make_label("Пользовательская НСХ (R0, A, B, C)",
                                             size=15, bold=True, color=PRIMARY))
        self.e_r0 = make_input("R0, Ом")
        self.e_a = make_input("A")
        self.e_b = make_input("B")
        self.e_c = make_input("C")
        for w in (self.e_r0, self.e_a, self.e_b, self.e_c):
            self.panel_nsh.add_widget(w)

        # R -> t
        self.e_r = make_input()
        field(content, "Сопротивление, Ом:", self.e_r)
        content.add_widget(make_button("Рассчитать t по R", self.on_r_to_t))
        self.l_t = make_result_area(content)
        content.add_widget(self.l_t)

        # t -> R
        self.e_t = make_input()
        field(content, "Температура, °C:", self.e_t)
        content.add_widget(make_button("Рассчитать R по t", self.on_t_to_r))
        self.l_r = make_result_area(content)
        content.add_widget(self.l_r)

        # ΔR ↔ Δt
        content.add_widget(make_label("Пересчёт погрешности ΔR ↔ Δt", size=16,
                                      bold=True, color=PRIMARY))
        r1 = make_row()
        r1.add_widget(make_label("t, °C:", size=14, color=MUTED))
        self.e_err_t = make_input()
        r1.add_widget(self.e_err_t)
        content.add_widget(r1)
        r2 = make_row()
        r2.add_widget(make_label("δR, Ом:", size=14, color=MUTED))
        self.e_err_dr = make_input()
        r2.add_widget(self.e_err_dr)
        r2.add_widget(make_label("δt, °C:", size=14, color=MUTED))
        self.e_err_dt = make_input()
        r2.add_widget(self.e_err_dt)
        content.add_widget(r2)
        content.add_widget(make_button("ПЕРЕСЧИТАТЬ", self.on_delta))
        self.l_delta = make_result_area(content)
        content.add_widget(self.l_delta)

        # таблица поверки
        content.add_widget(make_label("Таблица поверки (точки → номинал R)", size=16,
                                      bold=True, color=PRIMARY))
        r3 = make_row()
        r3.add_widget(make_label("t min:", size=13, color=MUTED))
        self.e_tmin = make_input(); self.e_tmin.text = "0"
        r3.add_widget(self.e_tmin)
        r3.add_widget(make_label("t max:", size=13, color=MUTED))
        self.e_tmax = make_input(); self.e_tmax.text = "100"
        r3.add_widget(self.e_tmax)
        content.add_widget(r3)
        r4 = make_row()
        r4.add_widget(make_label("Кл.точн., %:", size=13, color=MUTED))
        self.e_tt_acc = make_input(); self.e_tt_acc.text = "1.0"
        r4.add_widget(self.e_tt_acc)
        r4.add_widget(make_label("Точки, %:", size=13, color=MUTED))
        self.e_tt_points = make_input(); self.e_tt_points.text = "0,25,50,75,100"
        r4.add_widget(self.e_tt_points)
        content.add_widget(r4)
        td0 = make_row()
        td0.add_widget(make_button("Сформировать таблицу", self.on_tt_gen, height=46))
        td0.add_widget(make_button("Проверить точки", self.on_tt_check, bg=SUCCESS, height=46))
        content.add_widget(td0)
        self.tt_tbl = GridLayout(cols=6, size_hint_y=None, spacing=4)
        self.tt_tbl.bind(minimum_height=self.tt_tbl.setter("height"))
        content.add_widget(self.tt_tbl)
        self.tt_rows = []

        wrap_screen(self, "Температура (НСХ)", content)

    def get_data(self):
        return core.get_thermo_user(
            self.s_thermo.text,
            self.e_r0.text if hasattr(self, "e_r0") else "",
            self.e_a.text if hasattr(self, "e_a") else "",
            self.e_b.text if hasattr(self, "e_b") else "",
            self.e_c.text if hasattr(self, "e_c") else "",
        )

    def on_r_to_t(self, *_):
        try:
            rv = _num(self.e_r.text)
            data = self.get_data()
        except ValueError:
            popup("Ошибка ввода", "Введите сопротивление.", "error")
            return
        t = core.resistance_to_temp(rv, data["R0"], data["coeffs"])
        if t is None:
            popup("Ошибка", "Некорректное R.", "error")
            return
        rng = (-200, 850) if data["type"] == "Pt" else (-50, 180)
        if rng[0] <= t <= rng[1]:
            self.l_t.text = f"t = {t:.2f} °C"
        else:
            self.l_t.text = f"t = {t:.2f} °C (вне НСХ {rng[0]}..{rng[1]} °C)"

    def on_t_to_r(self, *_):
        try:
            tv = _num(self.e_t.text)
            data = self.get_data()
        except ValueError:
            popup("Ошибка ввода", "Введите температуру.", "error")
            return
        r = core.temp_to_resistance(tv, data["R0"], data["coeffs"])
        self.l_r.text = f"R = {r:.3f} Ом"

    def on_delta(self, *_):
        try:
            tv = _num(self.e_err_t.text)
            data = self.get_data()
        except ValueError:
            popup("Ошибка ввода", "Укажите температуру t.", "error")
            return
        drdt = core.r_derivative(tv, data["R0"], data["coeffs"])
        try:
            dr = _num(self.e_err_dr.text) if self.e_err_dr.text.strip() else None
        except ValueError:
            dr = None
        try:
            dt_ = _num(self.e_err_dt.text) if self.e_err_dt.text.strip() else None
        except ValueError:
            dt_ = None
        if dr is not None and dt_ is None:
            dt_ = dr / drdt
            self.e_err_dt.text = f"{dt_:.4f}"
        elif dt_ is not None and dr is None:
            dr = dt_ * drdt
            self.e_err_dr.text = f"{dr:.4f}"
        else:
            popup("Инфо", "Заполните ОДНО из полей: δR или δt (плюс t).", "warn")
            return
        self.l_delta.text = (f"dR/dt(t={tv:.1f} °C) = {drdt:.4f} Ом/°C\n"
                             f"δR = {dr:.4f} Ом  ↔  δt = {dt_:.4f} °C")

    def on_tt_gen(self, *_):
        try:
            tmin = _num(self.e_tmin.text)
            tmax = _num(self.e_tmax.text)
            acc = _num(self.e_tt_acc.text)
            pts = [_num(x) for x in self.e_tt_points.text.replace(",", " ").split()]
        except ValueError:
            popup("Ошибка ввода", "Проверьте поля таблицы поверки.", "error")
            return
        if tmax <= tmin or acc < 0 or any(not (0 <= p <= 100) for p in pts):
            popup("Ошибка", "t max > t min, кл. точности >= 0, точки 0..100.", "error")
            return
        data = self.get_data()
        span_r = abs(core.temp_to_resistance(tmax, data["R0"], data["coeffs"]) -
                     core.temp_to_resistance(tmin, data["R0"], data["coeffs"]))
        tol = acc / 100.0 * span_r
        self.tt_tbl.clear_widgets()
        self.tt_rows = []
        for h in ["Точка", "t,°C", "Номинал R", "Измер. R", "ΔR", "Вердикт"]:
            self.tt_tbl.add_widget(make_label(h, size=12, bold=True, color=PRIMARY, halign="center"))
        for p in pts:
            t = tmin + p / 100.0 * (tmax - tmin)
            r = core.temp_to_resistance(t, data["R0"], data["coeffs"])
            ti = make_input(font_size=14, height=40)
            self.tt_tbl.add_widget(make_label(f"{p:g}%", size=13, halign="center"))
            self.tt_tbl.add_widget(make_label(f"{t:.1f}", size=13, halign="center"))
            self.tt_tbl.add_widget(make_label(f"{r:.3f}", size=13, halign="center"))
            self.tt_tbl.add_widget(ti)
            v_lbl = make_label("", size=12, color=MUTED, halign="center", height=40)
            self.tt_tbl.add_widget(v_lbl)
            self.tt_rows.append((t, r, tol, ti, v_lbl))
        popup("Готово", "Внесите измеренные R и нажмите «Проверить точки».", "ok")

    def on_tt_check(self, *_):
        if not self.tt_rows:
            popup("Инфо", "Сначала сформируйте таблицу.", "info")
            return
        data = self.get_data()
        checked = 0
        for t, r, tol, ti, v_lbl in self.tt_rows:
            raw = ti.text.strip()
            if not raw:
                continue
            try:
                m = _num(raw)
            except ValueError:
                continue
            d = m - r
            dt_ = d / core.r_derivative(t, data["R0"], data["coeffs"])
            ok = abs(d) <= tol
            v_lbl.text = f"{d:+.3f}  {'В допуске' if ok else 'Брак'}"
            v_lbl.color = SUCCESS if ok else DANGER
            checked += 1
        popup("Готово" if checked else "Инфо",
              f"Проверено точек: {checked}." if checked else "Нет данных для проверки.", "ok")


# ----------------------------------------------------------------------
# ЭКРАН 5. Термопары (НСХ)
# ----------------------------------------------------------------------
class TCScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        content = new_scroll()

        content.add_widget(make_label("Термопара (мВ ↔ °C)", size=18, bold=True, color=PRIMARY))
        r0 = make_row()
        r0.add_widget(make_label("Тип:", size=14, color=MUTED))
        self.s_tc = make_spinner(core.THERMOCOUPLE_DISPLAY_LIST, index=0)
        r0.add_widget(self.s_tc)
        content.add_widget(r0)

        self.e_emf = make_input()
        field(content, "ЭДС термопары, мВ:", self.e_emf)
        content.add_widget(make_button("Рассчитать t по E", self.on_e_to_t))
        self.l_t = make_result_area(content)
        content.add_widget(self.l_t)

        self.e_t = make_input()
        field(content, "Температура, °C:", self.e_t)
        content.add_widget(make_button("Рассчитать E по t", self.on_t_to_e))
        self.l_e = make_result_area(content)
        content.add_widget(self.l_e)

        # таблица поверки
        content.add_widget(make_label("Таблица поверки (точки → номинал ЭДС)", size=16,
                                      bold=True, color=PRIMARY))
        r1 = make_row()
        r1.add_widget(make_label("t min:", size=13, color=MUTED))
        self.e_tmin = make_input(); self.e_tmin.text = "0"
        r1.add_widget(self.e_tmin)
        r1.add_widget(make_label("t max:", size=13, color=MUTED))
        self.e_tmax = make_input(); self.e_tmax.text = "1000"
        r1.add_widget(self.e_tmax)
        content.add_widget(r1)
        r2 = make_row()
        r2.add_widget(make_label("Допуск, °C:", size=13, color=MUTED))
        self.e_tol = make_input(); self.e_tol.text = "1.5"
        r2.add_widget(self.e_tol)
        r2.add_widget(make_label("Точки, %:", size=13, color=MUTED))
        self.e_points = make_input(); self.e_points.text = "0,25,50,75,100"
        r2.add_widget(self.e_points)
        content.add_widget(r2)
        td = make_row()
        td.add_widget(make_button("Сформировать таблицу", self.on_tc_gen, height=46))
        td.add_widget(make_button("Проверить точки", self.on_tc_check, bg=SUCCESS, height=46))
        content.add_widget(td)
        self.tbl = GridLayout(cols=5, size_hint_y=None, spacing=4)
        self.tbl.bind(minimum_height=self.tbl.setter("height"))
        content.add_widget(self.tbl)
        self.rows = []

        wrap_screen(self, "Термопары (НСХ)", content)

    def on_e_to_t(self, *_):
        try:
            e = _num(self.e_emf.text)
        except ValueError:
            popup("Ошибка ввода", "Введите ЭДС, мВ.", "error")
            return
        key = self.s_tc.text
        t = core.tc_emf_to_temp(key, e)
        if t is None:
            spec = core.THERMOCOUPLES[key]
            popup("Вне диапазона",
                  f"Диапазон НСХ: {spec['e_range'][0]:g}…{spec['e_range'][1]:g} мВ", "warn")
            return
        self.l_t.text = f"t = {t:.2f} °C"

    def on_t_to_e(self, *_):
        try:
            tv = _num(self.e_t.text)
        except ValueError:
            popup("Ошибка ввода", "Введите температуру, °C.", "error")
            return
        key = self.s_tc.text
        e = core.tc_temp_to_emf(key, tv)
        if e is None:
            spec = core.THERMOCOUPLES[key]
            popup("Вне диапазона",
                  f"Диапазон НСХ: {spec['t_range'][0]:g}…{spec['t_range'][1]:g} °C", "warn")
            return
        self.l_e.text = f"E = {e:.4f} мВ"

    def on_tc_gen(self, *_):
        try:
            tmin = _num(self.e_tmin.text)
            tmax = _num(self.e_tmax.text)
            tol_deg = _num(self.e_tol.text)
            pts = [_num(x) for x in self.e_points.text.replace(",", " ").split()]
        except ValueError:
            popup("Ошибка ввода", "Проверьте поля таблицы.", "error")
            return
        key = self.s_tc.text
        spec = core.THERMOCOUPLES[key]
        if tmax <= tmin or tol_deg < 0 or any(not (0 <= p <= 100) for p in pts):
            popup("Ошибка", "t max > t min, допуск >= 0, точки 0..100.", "error")
            return
        if tmin < spec["t_range"][0] or tmax > spec["t_range"][1]:
            popup("Вне НСХ", f"Диапазон: {spec['t_range'][0]:g}…{spec['t_range'][1]:g} °C", "warn")
            return
        self.tbl.clear_widgets()
        self.rows = []
        for h in ["Точка", "t,°C", "Номинал E", "Измер. E", "Вердикт"]:
            self.tbl.add_widget(make_label(h, size=12, bold=True, color=PRIMARY, halign="center"))
        for p in pts:
            t = tmin + p / 100.0 * (tmax - tmin)
            e = core.tc_temp_to_emf(key, t)
            s = core.tc_sensitivity(key, t)
            tol = (tol_deg * s) if s else 0.0
            ti = make_input(font_size=14, height=40)
            v_lbl = make_label("", size=12, color=MUTED, halign="center", height=40)
            self.tbl.add_widget(make_label(f"{p:g}%", size=13, halign="center"))
            self.tbl.add_widget(make_label(f"{t:.1f}", size=13, halign="center"))
            self.tbl.add_widget(make_label(f"{e:.4f}", size=13, halign="center"))
            self.tbl.add_widget(ti)
            self.tbl.add_widget(v_lbl)
            self.rows.append((t, e, tol, ti, v_lbl))
        popup("Готово", "Внесите измеренную ЭДС и нажмите «Проверить точки».", "ok")

    def on_tc_check(self, *_):
        if not self.rows:
            popup("Инфо", "Сначала сформируйте таблицу.", "info")
            return
        key = self.s_tc.text
        checked = 0
        for t, e, tol, ti, v_lbl in self.rows:
            raw = ti.text.strip()
            if not raw:
                continue
            try:
                m = _num(raw)
            except ValueError:
                continue
            d = m - e
            s = core.tc_sensitivity(key, t)
            dt_ = (d / s) if s else 0.0
            ok = abs(d) <= tol
            v_lbl.text = f"{d:+.4f}  {'В допуске' if ok else 'Брак'}"
            v_lbl.color = SUCCESS if ok else DANGER
            checked += 1
        popup("Готово" if checked else "Инфо",
              f"Проверено точек: {checked}." if checked else "Нет данных для проверки.", "ok")


# ----------------------------------------------------------------------
# ЭКРАН 6. Расход через диафрагму
# ----------------------------------------------------------------------
class OrifScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        content = new_scroll()

        content.add_widget(make_label("Расход через диафрагму (ГОСТ 8.586.2)", size=17,
                                      bold=True, color=PRIMARY))
        self.e_dp = make_input()
        field(content, "Перепад ΔP:", self.e_dp)
        r0 = make_row()
        r0.add_widget(make_label("Ед. перепада:", size=14, color=MUTED))
        self.s_dp_unit = make_spinner(list(core.UNITS_DISPLAY.keys()), index=1)  # кПа
        r0.add_widget(self.s_dp_unit)
        content.add_widget(r0)

        self.e_dpipe = make_input()
        field(content, "Диаметр трубы D, мм:", self.e_dpipe)
        self.e_dorif = make_input()
        field(content, "Диаметр диафрагмы d, мм:", self.e_dorif)

        r1 = make_row()
        r1.add_widget(make_label("Среда:", size=14, color=MUTED))
        self.s_media = make_spinner(["вода", "пар (насыщ.)", "воздух", "азот",
                                     "кислород", "другое"])
        r1.add_widget(self.s_media)
        content.add_widget(r1)
        self.l_manual = make_label("Плотность, кг/м³ (для «другое»):", size=14, color=MUTED)
        content.add_widget(self.l_manual)
        self.e_rho_manual = make_input()
        content.add_widget(self.e_rho_manual)

        self.e_mu = make_input()
        field(content, "Вязкость μ, Па·с:", self.e_mu)
        self.l_kappa = make_label("Адиабата κ (для газа/пара):", size=14, color=MUTED)
        content.add_widget(self.l_kappa)
        self.e_kappa = make_input()
        content.add_widget(self.e_kappa)
        self.l_p1 = make_label("Абс. давление p1, Па (для газа/пара):", size=14, color=MUTED)
        content.add_widget(self.l_p1)
        self.e_p1 = make_input()
        content.add_widget(self.e_p1)

        self.s_media.bind(text=self.on_media)
        self.on_media()

        content.add_widget(make_button("РАССЧИТАТЬ РАСХОД", self.on_calc))
        self.l_res = make_result_area(content)
        content.add_widget(self.l_res)
        content.add_widget(make_button("Копировать результат", lambda *_: copy_text(self.l_res.text),
                                       bg=(0.42, 0.447, 0.502, 1), height=46))

        wrap_screen(self, "Расход (диафрагма)", content)

    def on_media(self, *_):
        key = self.s_media.text
        self.on_kappa_state = True
        if key == "другое":
            self.l_manual.text = "Плотность, кг/м³:"
            self.e_rho_manual.disabled = False
            self.e_kappa.disabled = False
            self.e_p1.disabled = False
            return
        med = core.ORIFICE_MEDIA.get(key)
        if not med:
            return
        self.e_rho_manual.disabled = True
        if med["gas"]:
            self.e_kappa.disabled = False
            self.e_p1.disabled = False
            self.e_kappa.text = f"{med['kappa']:g}"
            self.e_p1.text = ""
        else:
            self.e_kappa.disabled = True
            self.e_p1.disabled = True
            self.e_kappa.text = ""
            self.e_p1.text = ""
        self.e_mu.text = f"{med['mu']:g}"

    def on_calc(self, *_):
        try:
            dp_dis = _num(self.e_dp.text)
            dp_unit = core.UNITS_DISPLAY[self.s_dp_unit.text]
            dp_pa = dp_dis * core.UNITS_CALC[dp_unit]
            d_pipe_m = _num(self.e_dpipe.text) / 1000.0
            d_orif_m = _num(self.e_dorif.text) / 1000.0

            key = self.s_media.text
            med = core.ORIFICE_MEDIA.get(key)
            if key == "другое":
                rho = _num(self.e_rho_manual.text)
                is_gas = bool(self.e_kappa.text.strip())
                kappa = _num(self.e_kappa.text) if self.e_kappa.text.strip() else None
            else:
                rho = core.DENSITIES[key]
                is_gas = bool(med and med["gas"])
                kappa = _num(self.e_kappa.text) if self.e_kappa.text.strip() else (med and med["kappa"])

            mu = _num(self.e_mu.text)

            p1 = None
            if is_gas:
                if kappa is None or kappa <= 1.0:
                    raise ValueError("Показатель адиабаты κ должен быть > 1")
                if not self.e_p1.text.strip():
                    raise ValueError("Для газа/пара укажите p1 (Па)")
                p1 = _num(self.e_p1.text)
                if p1 <= 0:
                    raise ValueError("p1 должно быть положительным")
                if dp_pa >= p1:
                    raise ValueError("ΔP должно быть меньше p1 (p2 > 0)")
            if rho <= 0 or mu <= 0 or d_pipe_m <= 0 or d_orif_m <= 0:
                raise ValueError("Значения должны быть положительными")
            if d_orif_m >= d_pipe_m:
                raise ValueError("d должно быть меньше D")
            if dp_pa < 0:
                raise ValueError("Перепад не может быть отрицательным")
        except ValueError as e:
            popup("Ошибка ввода", str(e), "error")
            return
        try:
            res = core.calc_flow_orifice_gost(dp_pa, d_orif_m, d_pipe_m, rho, mu,
                                              kappa=kappa, p1_abs_pa=p1)
        except ValueError as e:
            popup("Ошибка", str(e), "error")
            return
        eps_s = f"{res['eps']:.4f}" if res["eps"] is not None else "1.000"
        if res["eps"] is None or res["eps"] == 1.0:
            eps_s = "1.000 (жидкость)"
        lines = [
            f"β = {res['beta']:.4f}    C = {res['c']:.5f}",
            f"ε = {eps_s}",
            f"Re = {res['re']:.0f}",
            f"Объёмный расход: {res['qv_m3_s']*3600:.3f} м³/ч",
            f"Массовый расход: {res['qm_kg_s']*3600/1000:.3f} т/ч",
            f"Скорость в трубе: {res['velocity_m_s']:.2f} м/с",
            f"Скорость в диафрагме: {res['velocity_orif_m_s']:.2f} м/с",
        ]
        for w in res.get("warnings", []):
            lines.append("⚠ " + w)
        self.l_res.text = "\n".join(lines)


# ----------------------------------------------------------------------
# Главный экран — меню модулей
# ----------------------------------------------------------------------
MENU_ITEMS = [
    ("Конвертация и погрешность", ConvScreen),
    ("Расход (квадратичная)", FlowScreen),
    ("Диагностика датчика", DiagScreen),
    ("Температура (НСХ)", TempScreen),
    ("Термопары (НСХ)", TCScreen),
    ("Расход (диафрагма)", OrifScreen),
]


class MenuScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        content = new_scroll()
        content.add_widget(make_label("Расчётный модуль КИПиА", size=24, bold=True,
                                      color=PRIMARY))
        content.add_widget(make_label("Выберите раздел:", size=16, color=MUTED))
        for name, _cls in MENU_ITEMS:
            b = make_button(name, bg=PRIMARY_DARK if False else PRIMARY, height=58)
            b.bind(on_press=lambda _wdt, n=name: self.goto(n))
            content.add_widget(b)
        self.add_widget(as_scroll(content))

    def goto(self, name):
        for n, _cls in MENU_ITEMS:
            if n == name:
                self.manager.current = f"scr_{n}"
                return


class KIPiAApp(App):
    title = "Расчётный модуль КИПиА"

    def build(self):
        sm = ScreenManager()
        sm.add_widget(MenuScreen(name="menu"))
        for name, cls in MENU_ITEMS:
            sm.add_widget(cls(name=f"scr_{name}"))
        return sm

    def on_pause(self):
        return True


if __name__ == "__main__":
    KIPiAApp().run()