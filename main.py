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
from kivy.uix.image import Image
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window

import core

# Дизайн-ширина макета в dp: всё масштабируется под фактическую ширину экрана.
DESIGN_WIDTH_DP = 360.0


def sc(v):
    """dp → px с учётом реальной ширины экрана (резиновая вёрстка)."""
    try:
        w = Window.width
    except Exception:
        w = 0
    if not w:
        return float(v)
    return float(v) * (w / DESIGN_WIDTH_DP)


def safe_insets_px():
    """Высоты системных зон (верх/низ) в px на Android; вне Android — (0, 0).
    Нужны в полноэкранном режиме, чтобы контент не прятался под вырезом
    камеры (сверху) и под зоной жестов/кнопок навигации (снизу)."""
    top = bottom = 0
    try:
        from kivy.utils import platform
        if platform != "android":
            return 0, 0
        from jnius import autoclass
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        resources = activity.getResources()
        def _dimen(name):
            ident = resources.getIdentifier(name, "dimen", "android")
            return resources.getDimensionPixelSize(ident) if ident else 0
        top = _dimen("status_bar_height")
        bottom = _dimen("navigation_bar_height")
    except Exception:
        top = bottom = 0
    return top, bottom


def add_safe_spacers(outer, top=True, bottom=True):
    """Вставляет в вертикальный BoxLayout пустые «прокладки» под системные зоны,
    чтобы контент не заходил под камеру (вырез) сверху и под зону жестов снизу."""
    t, b = safe_insets_px()
    if top and t:
        outer.add_widget(BoxLayout(size_hint_y=None, height=t), index=0)
    if bottom and b:
        outer.add_widget(BoxLayout(size_hint_y=None, height=b))

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
SPIN_BG = (0.859, 0.902, 0.973, 1)       # #dbe6f8 — светлый голубой для полей выбора единиц

FONT_NAME = "Roboto"


class InputError(ValueError):
    """Ошибка ввода: число не удалось прочитать из поля."""


def _num(text):
    try:
        return float(str(text).replace(",", ".").strip())
    except (ValueError, TypeError):
        raise InputError("Поле должно содержать число (например, 10 или 5,5).")


def num_filter(text, from_undo):
    return "".join(ch for ch in text if ch in "-.,0123456789")


from kivy.graphics import Color, RoundedRectangle

# ----------------------------------------------------------------------
# Утилиты
# ----------------------------------------------------------------------
def paint_bg(widget, color, radius=0.0):
    """Рисует скруглённую подложку позади виджета (фон экрана / карточки)."""
    with widget.canvas.before:
        Color(*color)
        widget._bg_panel = RoundedRectangle(pos=widget.pos, size=widget.size,
                                            radius=[radius] * 4)
    def _upd(*_a):
        widget._bg_panel.pos = widget.pos
        widget._bg_panel.size = widget.size
    widget.bind(pos=_upd, size=_upd)
    return widget


def cap_label(text, size=13, color=MUTED, height=22):
    """Малая подпись над полем: переносится по своей ширине, авто-высота."""
    lbl = Label(text=text, font_size=sc(size), color=color, bold=False,
                halign="left", valign="middle", size_hint=(1, None), height=sc(height))
    lbl.bind(width=lambda *_a: setattr(lbl, "text_size", (lbl.width - sc(4), None)))
    def _fit_h(*_a):
        lbl.height = max(sc(height), lbl.texture_size[1] + sc(4))
    lbl.bind(texture_size=_fit_h)
    return lbl


def cell_label(text="", size=13, color=TEXT, bold=False):
    """Ячейка таблицы: по центру, перенос/высота по фактической ширине колонки."""
    lbl = Label(text=text, font_size=sc(size), color=color, bold=bold,
                halign="center", valign="middle", size_hint=(1, None))
    lbl.bind(width=lambda *_a: setattr(lbl, "text_size", (lbl.width - sc(6), None)))
    def _fit_h(*_a):
        lbl.height = max(sc(42), lbl.texture_size[1] + sc(12))
    lbl.bind(texture_size=_fit_h)
    return lbl


def auto_area(text="", size=15, color=TEXT):
    """Многострочный блок результата: высота по содержимому, перенос по ширине."""
    lbl = Label(text=text, font_size=sc(size), color=color,
                halign="left", valign="top", size_hint=(1, None))
    lbl.bind(width=lambda *_a: setattr(lbl, "text_size", (lbl.width - sc(8), None)))
    def _fit_h(*_a):
        lbl.height = lbl.texture_size[1] or sc(40)
    lbl.bind(texture_size=_fit_h)
    return lbl


def make_label(text, size=17, bold=False, color=TEXT, halign="left",
               valign="middle", wrap=None, height=40):
    if wrap is None:
        wrap = max(120, len(str(text)) * (size + 6))
        lbl = Label(
            text=text, font_size=sc(size), bold=bold, color=color,
            halign=halign, valign=valign,
            size_hint_y=None, height=sc(height),
        )
        # Привязка переноса к фактической ширине виджета: текст не вылезает за края.
        def _fit(_w=None, _h=None):
            lbl.text_size = (lbl.width, None)
        lbl.bind(width=_fit)
        lbl.text_size = (lbl.width, None)
        return lbl
    return Label(
        text=text, font_size=sc(size), bold=bold, color=color,
        halign=halign, valign=valign,
        text_size=(sc(wrap), None),
        size_hint_y=None, height=sc(height),
    )


def make_input(hint="", multiline=False, font_size=17, height=48):
    ti = TextInput(
        hint_text=hint, multiline=multiline, font_size=sc(font_size),
        input_filter=num_filter,
        size_hint_y=None, height=sc(height),
        padding=(sc(12), sc(7), sc(12), sc(7)),
        background_color=(1, 1, 1, 1), foreground_color=TEXT,
        cursor_color=PRIMARY,
    )
    return ti


def make_cell_input(hint="", font_size=15):
    """Компактное поле ввода для ячейки таблицы: высота = высоте ячеек,
    текст по центру — поле получается ровно напротив значений соседних колонок."""
    ti = TextInput(
        hint_text=hint, multiline=False, font_size=sc(font_size),
        input_filter=num_filter,
        size_hint_y=None, height=sc(44),
        padding=(sc(8), sc(2), sc(8), sc(2)),
        halign="center",
        background_color=(1, 1, 1, 1), foreground_color=TEXT,
        cursor_color=PRIMARY,
    )
    return ti


def make_text(hint="", multiline=False, font_size=17):
    ti = TextInput(
        hint_text=hint, multiline=multiline, font_size=sc(font_size),
        size_hint_y=None, height=sc(48),
        padding=(sc(12), sc(7), sc(12), sc(7)),
        background_color=(1, 1, 1, 1), foreground_color=TEXT,
        cursor_color=PRIMARY,
    )
    return ti


def make_button(text, on_press=None, bg=PRIMARY, fg=(1, 1, 1, 1),
                bold=True, size=17, height=52):
    kwargs = dict(
        text=text, font_size=sc(size), bold=bold, background_color=bg,
        color=fg, size_hint_y=None, height=sc(height),
    )
    if on_press is not None:
        kwargs["on_press"] = on_press
    return Button(**kwargs)


def make_spinner(values, index=0, size=17, height=48):
    sp = Spinner(
        text=values[index], values=values, font_size=sc(size),
        size_hint_y=None, height=sc(height),
        background_normal="", background_down="",
        background_color=SPIN_BG, color=TEXT, bold=True,
    )
    _style_spinner(sp)
    return sp


def _style_spinner(sp):
    """Выделяем Spinner рамкой и стрелкой, чтобы поле выбора не сливалось с фоном."""
    from kivy.graphics import Color as GColor, Line
    def _redraw(*_a):
        sp.canvas.after.clear()
        if not sp.size[0] or not sp.size[1]:
            return
        with sp.canvas.after:
            GColor(*PRIMARY)
            Line(rounded_rectangle=(sp.x + sc(1), sp.y + sc(1),
                                    sp.width - sc(2), sp.height - sc(2),
                                    sc(7)), width=sc(1.5))
            # стрелка вниз справа
            cx = sp.x + sp.width - sc(18)
            cy = sp.y + sp.height / 2.0
            GColor(*PRIMARY)
            Line(points=[cx - sc(5), cy - sc(2), cx, cy + sc(2), cx + sc(5), cy - sc(2)],
                 width=sc(2))
    sp.bind(pos=_redraw, size=_redraw)
    sp.fbind("on_text", _redraw)
    sp.fbind("on_press", _redraw)


def make_row(height=None):
    r = BoxLayout(orientation="horizontal", spacing=sc(8), padding=(0, sc(2)),
                  size_hint_y=None)
    r.bind(minimum_height=r.setter("height"))
    return r


def as_scroll(widget):
    sv = ScrollView()
    sv.add_widget(widget)
    return sv


def new_scroll(width_hint=None, height=None):
    content = BoxLayout(orientation="vertical", size_hint_y=None,
                        padding=sc(14), spacing=sc(12))
    content.bind(minimum_height=content.setter("height"))
    return content


def heading(content, text, size=16, color=PRIMARY):
    """Заголовок секции с отступом сверху."""
    top = BoxLayout(size_hint_y=None, height=sc(6))
    content.add_widget(top)
    lbl = auto_area(text, size=size, color=color)
    lbl.bold = True
    content.add_widget(lbl)


def field(content, caption, input_widget=None, hint="", cap_size=13):
    """Поле с подписью сверху; высота авто-подстраивается под контент."""
    box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=sc(4))
    box.add_widget(cap_label(caption, size=cap_size))
    box.add_widget(input_widget if input_widget is not None else make_input(hint))
    box.bind(minimum_height=box.setter("height"))
    content.add_widget(box)


def pair_grid(content, cols, cells):
    """Сетка из N колонок; в каждой ячейке подпись над контролом (полная ширина).
    Высота ячеек и сетки авто-подстраивается под перенос подписей."""
    g = GridLayout(cols=cols, size_hint_y=None, spacing=sc(10))
    for caption, widget in cells:
        b = BoxLayout(orientation="vertical", size_hint_y=None, spacing=sc(4))
        b.add_widget(cap_label(caption, size=12))
        b.add_widget(widget)
        b.bind(minimum_height=b.setter("height"))
        g.add_widget(b)
    g.bind(minimum_height=g.setter("height"))
    content.add_widget(g)
    return g


def popup(title, msg, kind="info"):
    cl = {"info": PRIMARY, "ok": SUCCESS, "error": DANGER, "warn": WARNING}.get(kind, PRIMARY)
    content = BoxLayout(orientation="vertical", padding=sc(18), spacing=sc(14))
    paint_bg(content, PANEL, radius=sc(12))
    lbl = auto_area(str(msg), size=18, color=(0.05, 0.07, 0.09, 1))
    content.add_widget(lbl)
    btn = make_button("ОК", bg=cl, height=50)
    content.add_widget(btn)
    p = Popup(title=title, content=content,
              size_hint=(0.9, None), height=sc(330), auto_dismiss=True,
              title_size=sc(20), title_align="center", title_color=cl)
    p.background = ""
    p.background_color = (1, 1, 1, 1)
    btn.bind(on_press=p.dismiss)
    p.open()


def copy_text(text):
    Clipboard.copy(text)
    popup("Скопировано", "Текст помещён в буфер обмена.", "ok")


def copy_result(lbl):
    """Копирует текст результата, если он есть; иначе подсказывает выполнить расчёт."""
    if lbl is None or not str(lbl.text).strip():
        popup("Нет результата", "Сначала выполните расчёт, затем копируйте.", "warn")
        return
    copy_text(lbl.text)


def fmt_point(v, sig=4):
    """Точное значение точки поверки (доля ВПИ) без потери от округления.
    Показывает 1.575 вместо 1.6, чтобы оно совпадало с ожидаемым сигналом
    (25% от 6.3 кПа = 1.575, сигнал 8.0 мА; округление до 1.6 давало бы 8.06)."""
    if v == 0:
        return "0"
    dec = sig - int(math.floor(math.log10(abs(v)))) - 1
    dec = max(0, min(dec, 6))
    s = "{:,.{de}f}".format(v, de=dec)
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


# ----------------------------------------------------------------------
# Хелпер: карточка результата
# ----------------------------------------------------------------------
def make_result_area(content):
    lbl = auto_area("", size=15)
    lbl.padding = (sc(12), sc(10))
    paint_bg(lbl, PANEL, radius=sc(10))
    return lbl


def wrap_screen(scr, title, content):
    """Добавляет в экран верхнюю панель с кнопкой «Назад» и прокручиваемый контент."""
    outer = BoxLayout(orientation="vertical")
    paint_bg(outer, BG)
    add_safe_spacers(outer, top=True, bottom=False)
    bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=sc(64),
                    padding=(sc(6), sc(6)), spacing=sc(8))
    paint_bg(bar, PANEL)
    back = Button(text="‹  Меню", font_size=sc(16), background_color=PRIMARY,
                  size_hint_x=None, padding=(sc(8), sc(6)), halign="center")
    back.bind(texture_size=lambda _w, _s: setattr(back, "width", back.texture_size[0] + sc(16)))
    back.bind(on_press=lambda *_a: setattr(scr.manager, "current", "menu"))
    bar.add_widget(back)
    tl = auto_area(title, size=17, color=PRIMARY)
    tl.bold = True
    tl.halign = "center"
    tl.valign = "middle"
    bar.add_widget(tl)
    outer.add_widget(bar)
    outer.add_widget(as_scroll(content))
    add_safe_spacers(outer, top=False, bottom=True)
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
        self.s_from = make_spinner(list(core.UNITS_DISPLAY.keys()), index=8)  # МПа
        self.s_to = make_spinner(list(core.UNITS_DISPLAY.keys()), index=7)    # кгс/см²
        pair_grid(content, 2, [("Из единицы:", self.s_from), ("В единицу:", self.s_to)])
        self.e_span = make_input()
        field(content, "ВПИ (для погрешности):", self.e_span)
        self.e_acc = make_input()
        field(content, "Класс точности, %:", self.e_acc)

        btn = make_button("КОНВЕРТИРОВАТЬ", self.on_convert)
        content.add_widget(btn)
        self.l_res = make_result_area(content)
        content.add_widget(self.l_res)
        b2 = make_button("Копировать результат", lambda *_: copy_result(self.l_res),
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
        self.s_unit = make_spinner(["т/ч", "м³/ч"])
        field(content, "Ед. расхода:", self.s_unit)

        self.e_span = make_input()
        field(content, "ВПИ перепада (значение):", self.e_span)
        self.s_span_unit = make_spinner(["Па", "кПа", "МПа", "бар", "кгс/см²", "кгс/м²"])
        field(content, "Ед. перепада:", self.s_span_unit)

        self.e_acc = make_input()
        field(content, "Класс точности, %:", self.e_acc)
        self.s_sig = make_spinner(["мА (4–20)", "В (0–10)", "%"])
        field(content, "Сигнал:", self.s_sig)
        self.e_points = make_input()
        field(content, "Точки шкалы (через запятую; пусто — 0..100):", self.e_points)

        btn = make_button("РАССЧИТАТЬ ТАБЛИЦУ", self.on_calc)
        content.add_widget(btn)

        # таблица результатов
        self.tbl_title = make_label("", size=15, bold=True, color=PRIMARY)
        content.add_widget(self.tbl_title)
        self.tbl = GridLayout(cols=5, size_hint_y=None, spacing=sc(4))
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
            self.tbl.add_widget(cell_label(h, size=12, bold=True, color=PRIMARY))
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
            self.tbl.add_widget(cell_label(f"{pct:.1f}%", size=13))
            self.tbl.add_widget(cell_label(f"{q:.2f}", size=13))
            self.tbl.add_widget(cell_label(f"{dp_dis:.2f}", size=13))
            self.tbl.add_widget(cell_label(f"{rel:.2f}", size=13))
            self.tbl.add_widget(cell_label(f"{sig:.2f}", size=13))
            self.rows.append((pct, q, self.s_unit.text, dp_dis, rel, sig))

    def on_copy(self, *_):
        if not self.rows:
            popup("Инфо", "Сначала выполните расчёт.", "info")
            return
        lines = ["%\tРасход\tЕд.\tПерепад\tОтн.погр.,%\tСигнал"]
        for pct, q, unit, dp_dis, rel, sig in self.rows:
            lines.append(f"{pct:.2f}\t{q:.2f}\t{unit}\t{dp_dis:.2f}\t{rel:.2f}\t{sig:.2f}")
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
        self.s_unit = make_spinner(list(core.UNITS_DISPLAY.keys()), index=8)
        field(content, "Ед. ВПИ:", self.s_unit)
        self.e_acc = make_input()
        field(content, "Класс точности, %:", self.e_acc)

        b1 = make_button("ВЫПОЛНИТЬ ДИАГНОСТИКУ", self.on_diag)
        content.add_widget(b1)
        self.l_diag = make_result_area(content)
        content.add_widget(self.l_diag)
        b2 = make_button("Копировать фрагмент акта", lambda *_: copy_result(self.l_diag),
                         bg=(0.42, 0.447, 0.502, 1), height=46)
        content.add_widget(b2)

        # ---- мини-протокол поверки ----
        heading(content, "Мини-протокол поверки (по точкам)")
        b3 = make_button("Сформировать протокол", self.on_gen)
        content.add_widget(b3)
        self.tbl = GridLayout(cols=5, size_hint_y=None, spacing=sc(4))
        self.tbl.bind(minimum_height=self.tbl.setter("height"))
        content.add_widget(self.tbl)
        b4 = make_button("Проверить точки", self.on_check, bg=SUCCESS)
        content.add_widget(b4)
        b5 = make_button("Копировать протокол", self.on_proto_copy, height=46)
        content.add_widget(b5)
        self.row_inputs = []   # (pct, pv, exp, tol, TextInput, verdict_label)

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
        for h in ["Точка", "Давление", "Ож. ток, мА", "Измер. мА", "Результат"]:
            self.tbl.add_widget(cell_label(h, size=12, bold=True, color=PRIMARY))
        for pct in VERIF_POINTS:
            pv = pct / 100.0 * span_v
            exp = 4.0 + 16.0 * pct / 100.0
            ti = make_cell_input(hint="мА", font_size=15)
            v_lbl = cell_label("", size=12, color=MUTED)
            self.tbl.add_widget(cell_label(f"{pct}%", size=13))
            self.tbl.add_widget(cell_label(fmt_point(pv), size=13))
            self.tbl.add_widget(cell_label(f"{exp:.3f}", size=13))
            self.tbl.add_widget(ti)
            self.tbl.add_widget(v_lbl)
            self.row_inputs.append((pct, pv, exp, tol, ti, v_lbl))
        popup("Протокол готов", "Введите измеренные мА и нажмите «Проверить точки».", "ok")

    def on_check(self, *_):
        if not self.row_inputs:
            popup("Инфо", "Сначала сформируйте протокол.", "info")
            return
        checked = 0
        for pct, pv, exp, tol, ti, v_lbl in self.row_inputs:
            raw = ti.text.strip()
            if not raw:
                continue
            try:
                m = _num(raw)
            except ValueError:
                continue
            d = m - exp
            ok = abs(d) <= tol
            v_lbl.text = f"{d:+.3f} мА  {'В допуске' if ok else 'БРАК'}"
            v_lbl.color = SUCCESS if ok else DANGER
            checked += 1
        if checked:
            popup("Готово", f"Проверено точек: {checked}. Вердикт — в зелёном столбце.", "ok")
        else:
            popup("Инфо", "Нет данных для проверки (заполните измеренные мА).", "info")

    def on_proto_copy(self, *_):
        if not self.row_inputs:
            popup("Инфо", "Сначала сформируйте протокол.", "info")
            return
        try:
            span_v = _num(self.e_span.text)
            acc = _num(self.e_acc.text)
        except ValueError:
            span_v = acc = 0.0
        line_span = f"ВПИ: {fmt_point(span_v)} {self.s_unit.text}" if span_v else "ВПИ: —"
        line_acc = f"Класс точности: {acc:g}%" if acc else "Класс точности: —"
        lines = [
            f"Тип: {self.e_type.text.strip() or 'Не указан'}",
            f"Зав. №: {self.e_sn.text.strip() or '-'}",
            line_span,
            line_acc,
            "",
            "Точка\tДавление, " + self.s_unit.text + "\tОж. ток, мА\tИзмер. мА\tРезультат",
        ]
        for pct, pv, exp, tol, ti, v_lbl in self.row_inputs:
            lines.append(f"{pct}%\t{fmt_point(pv)}\t{exp:.3f}"
                         f"\t{ti.text.strip() or '—'}\t{v_lbl.text.strip() or '—'}")
        copy_text("\n".join(lines))


# ----------------------------------------------------------------------
# ЭКРАН 4. Температура (НСХ) — термометры
# ----------------------------------------------------------------------
class TempScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        content = new_scroll()

        heading(content, "Термометр (R и t)")
        self.s_thermo = make_spinner(core.THERMO_DISPLAY_LIST + ["Пользовательская"], index=1)
        field(content, "Тип термометра:", self.s_thermo, cap_size=13)

        # пользовательская НСХ
        self.panel_nsh = BoxLayout(orientation="vertical", size_hint_y=None, spacing=sc(6))
        self.panel_nsh.bind(minimum_height=self.panel_nsh.setter("height"))
        content.add_widget(self.panel_nsh)
        self.panel_nsh.add_widget(cap_label("Пользовательская НСХ (R0, A, B, C):", size=13))
        self.e_r0 = make_input("R0, Ом")
        self.e_a = make_input("A")
        self.e_b = make_input("B")
        self.e_c = make_input("C")
        pair_grid(self.panel_nsh, 2, [("R0, Ом", self.e_r0), ("A", self.e_a),
                                      ("B", self.e_b), ("C", self.e_c)])

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
        heading(content, "Пересчёт погрешности ΔR / Δt")
        self.e_err_t = make_input()
        field(content, "t, °C:", self.e_err_t)
        self.e_err_dr = make_input()
        self.e_err_dt = make_input()
        pair_grid(content, 2, [("δR, Ом (пусто — расчёт по δt)", self.e_err_dr),
                               ("δt, °C (пусто — расчёт по δR)", self.e_err_dt)])
        content.add_widget(make_button("ПЕРЕСЧИТАТЬ", self.on_delta))
        self.l_delta = make_result_area(content)
        content.add_widget(self.l_delta)

        # таблица поверки
        heading(content, "Таблица поверки (точки в номинал R)")
        self.e_tmin = make_input(); self.e_tmin.text = "0"
        self.e_tmax = make_input(); self.e_tmax.text = "100"
        pair_grid(content, 2, [("t min, °C", self.e_tmin), ("t max, °C", self.e_tmax)])
        self.e_tt_acc = make_input(); self.e_tt_acc.text = "1.0"
        self.e_tt_points = make_input(); self.e_tt_points.text = "0,25,50,75,100"
        pair_grid(content, 2, [("Кл. точности, %", self.e_tt_acc),
                               ("Точки, % (через запятую)", self.e_tt_points)])
        content.add_widget(make_button("Сформировать таблицу", self.on_tt_gen, height=46))
        content.add_widget(make_button("Проверить точки", self.on_tt_check, bg=SUCCESS, height=46))
        self.tt_tbl = GridLayout(cols=6, size_hint_y=None, spacing=sc(4))
        self.tt_tbl.bind(minimum_height=self.tt_tbl.setter("height"))
        content.add_widget(self.tt_tbl)
        content.add_widget(make_button("Скопировать таблицу", self.on_tt_copy,
                                       bg=(0.42, 0.447, 0.502, 1), height=46))
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
                             f"δR = {dr:.4f} Ом  /  δt = {dt_:.4f} °C")

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
        for h in ["Точка", "t, °C", "Номинал R", "Измер. R", "ΔR", "Вердикт"]:
            self.tt_tbl.add_widget(cell_label(h, size=11, bold=True, color=PRIMARY))
        for p in pts:
            t = tmin + p / 100.0 * (tmax - tmin)
            r = core.temp_to_resistance(t, data["R0"], data["coeffs"])
            ti = make_input(font_size=14, height=40)
            d_lbl = cell_label("", size=11, color=TEXT)
            v_lbl = cell_label("", size=11, color=MUTED)
            self.tt_tbl.add_widget(cell_label(f"{p:g}%", size=12))
            self.tt_tbl.add_widget(cell_label(f"{t:.1f}", size=12))
            self.tt_tbl.add_widget(cell_label(f"{r:.3f}", size=12))
            self.tt_tbl.add_widget(ti)
            self.tt_tbl.add_widget(d_lbl)
            self.tt_tbl.add_widget(v_lbl)
            self.tt_rows.append((p, t, r, tol, ti, d_lbl, v_lbl))
        popup("Готово", "Внесите измеренные R и нажмите «Проверить точки».", "ok")

    def on_tt_check(self, *_):
        if not self.tt_rows:
            popup("Инфо", "Сначала сформируйте таблицу.", "info")
            return
        data = self.get_data()
        checked = 0
        for p, t, r, tol, ti, d_lbl, v_lbl in self.tt_rows:
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
            d_lbl.text = f"{d:+.3f}"
            d_lbl.color = SUCCESS if ok else DANGER
            v_lbl.text = "В допуске" if ok else "Брак"
            v_lbl.color = SUCCESS if ok else DANGER
            checked += 1
        popup("Готово" if checked else "Инфо",
              f"Проверено точек: {checked}." if checked else "Нет данных для проверки.", "ok")

    def on_tt_copy(self, *_):
        if not self.tt_rows:
            popup("Инфо", "Сначала сформируйте таблицу.", "info")
            return
        lines = ["Точка\tt, °C\tНоминал R\tИзмер. R\tΔR\tВердикт"]
        for p, t, r, tol, ti, d_lbl, v_lbl in self.tt_rows:
            lines.append(f"{p:g}%\t{t:.1f}\t{r:.3f}"
                         f"\t{ti.text.strip()}\t{d_lbl.text.strip()}\t{v_lbl.text.strip()}")
        copy_text("\n".join(lines))


# ----------------------------------------------------------------------
# ЭКРАН 5. Термопары (НСХ)
# ----------------------------------------------------------------------
class TCScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        content = new_scroll()

        heading(content, "Термопара (мВ и °C)")
        self.s_tc = make_spinner(core.THERMOCOUPLE_DISPLAY_LIST, index=0)
        field(content, "Тип:", self.s_tc, cap_size=13)

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
        heading(content, "Таблица поверки (точки в номинал ЭДС)")
        self.e_tmin = make_input(); self.e_tmin.text = "0"
        self.e_tmax = make_input(); self.e_tmax.text = "1000"
        pair_grid(content, 2, [("t min, °C", self.e_tmin), ("t max, °C", self.e_tmax)])
        self.e_tol = make_input(); self.e_tol.text = "1.5"
        self.e_points = make_input(); self.e_points.text = "0,25,50,75,100"
        pair_grid(content, 2, [("Допуск, °C", self.e_tol),
                               ("Точки, % (через запятую)", self.e_points)])
        content.add_widget(make_button("Сформировать таблицу", self.on_tc_gen, height=46))
        content.add_widget(make_button("Проверить точки", self.on_tc_check, bg=SUCCESS, height=46))
        self.tbl = GridLayout(cols=5, size_hint_y=None, spacing=sc(4))
        self.tbl.bind(minimum_height=self.tbl.setter("height"))
        content.add_widget(self.tbl)
        content.add_widget(make_button("Скопировать таблицу", self.on_tc_copy,
                                       bg=(0.42, 0.447, 0.502, 1), height=46))
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
        for h in ["Точка", "t, °C", "Номинал E", "Измер. E", "Вердикт"]:
            self.tbl.add_widget(cell_label(h, size=11, bold=True, color=PRIMARY))
        for p in pts:
            t = tmin + p / 100.0 * (tmax - tmin)
            e = core.tc_temp_to_emf(key, t)
            s = core.tc_sensitivity(key, t)
            tol = (tol_deg * s) if s else 0.0
            ti = make_input(font_size=14, height=40)
            v_lbl = cell_label("", size=11, color=MUTED)
            self.tbl.add_widget(cell_label(f"{p:g}%", size=12))
            self.tbl.add_widget(cell_label(f"{t:.1f}", size=12))
            self.tbl.add_widget(cell_label(f"{e:.4f}", size=12))
            self.tbl.add_widget(ti)
            self.tbl.add_widget(v_lbl)
            self.rows.append((p, t, e, tol, ti, v_lbl))
        popup("Готово", "Внесите измеренную ЭДС и нажмите «Проверить точки».", "ok")

    def on_tc_check(self, *_):
        if not self.rows:
            popup("Инфо", "Сначала сформируйте таблицу.", "info")
            return
        key = self.s_tc.text
        checked = 0
        for p, t, e, tol, ti, v_lbl in self.rows:
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

    def on_tc_copy(self, *_):
        if not self.rows:
            popup("Инфо", "Сначала сформируйте таблицу.", "info")
            return
        lines = ["Точка\tt, °C\tНоминал E\tИзмер. E\tВердикт"]
        for p, t, e, tol, ti, v_lbl in self.rows:
            lines.append(f"{p:g}%\t{t:.1f}\t{e:.4f}"
                         f"\t{ti.text.strip()}\t{v_lbl.text.strip()}")
        copy_text("\n".join(lines))


# ----------------------------------------------------------------------
# ЭКРАН 6. Расход через диафрагму
# ----------------------------------------------------------------------
class OrifScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        content = new_scroll()

        heading(content, "Расход через диафрагму (ГОСТ 8.586.2)")
        self.e_dp = make_input()
        field(content, "Перепад ΔP:", self.e_dp)
        self.s_dp_unit = make_spinner(list(core.UNITS_DISPLAY.keys()), index=1)  # кПа
        field(content, "Ед. перепада:", self.s_dp_unit)

        self.e_dpipe = make_input()
        field(content, "Диаметр трубы D, мм:", self.e_dpipe)
        self.e_dorif = make_input()
        field(content, "Диаметр диафрагмы d, мм:", self.e_dorif)

        self.s_media = make_spinner(["вода", "пар (насыщ.)", "воздух", "азот",
                                     "кислород", "другое"])
        field(content, "Среда:", self.s_media)
        self.l_manual = cap_label("Плотность, кг/м³ (для «другое»):")
        content.add_widget(self.l_manual)
        self.e_rho_manual = make_input()
        content.add_widget(self.e_rho_manual)

        self.e_mu = make_input()
        field(content, "Вязкость μ, Па·с:", self.e_mu)
        self.l_kappa = cap_label("Адиабата κ (для газа/пара):")
        content.add_widget(self.l_kappa)
        self.e_kappa = make_input()
        content.add_widget(self.e_kappa)
        self.l_p1 = cap_label("Абс. давление p1, кПа (для газа/пара, напр. 300):")
        content.add_widget(self.l_p1)
        self.e_p1 = make_input()
        content.add_widget(self.e_p1)

        self.s_media.bind(text=self.on_media)
        self.on_media()

        content.add_widget(make_button("РАССЧИТАТЬ РАСХОД", self.on_calc))
        self.l_res = make_result_area(content)
        content.add_widget(self.l_res)
        content.add_widget(make_button("Копировать результат", lambda *_: copy_result(self.l_res),
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
                    raise ValueError("Для газа/пара укажите p1 (кПа)")
                p1 = _num(self.e_p1.text) * 1000.0
                if p1 <= 0:
                    raise ValueError("p1 должно быть положительным числом (кПа)")
                if dp_pa >= p1:
                    raise ValueError("Перепад ΔP должен быть меньше давления p1 "
                                     f"(введено ΔP={dp_dis:g} {core.UNITS_DISPLAY[self.s_dp_unit.text]}, "
                                     f"p1={self.e_p1.text} кПа)")
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
# ЭКРАН 7. Уровень по давлению
# ----------------------------------------------------------------------
class LevelScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        content = new_scroll()

        heading(content, "Уровень по давлению")
        content.add_widget(make_label(
            "Пересчёт показаний дифманометра/датчика давления в уровень "
            "жидкости в резервуаре. Плотность подставляется автоматически "
            "по среде и температуре.",
            size=14, color=MUTED, height=56))

        self.s_media = make_spinner(core.LIQUID_DISPLAY_LIST, index=0)
        field(content, "Среда:", self.s_media)

        self.e_temp = make_input()
        field(content, "Температура, °C (пусто = 20):", self.e_temp)

        # ручной ввод плотности (для «раствор (ρ вручную)» / «другое»)
        self.l_rho_manual = cap_label("Плотность при 20°C, кг/м³:")
        content.add_widget(self.l_rho_manual)
        self.e_rho_manual = make_input()
        content.add_widget(self.e_rho_manual)

        self.l_rho = cap_label("", size=13, color=PRIMARY)
        content.add_widget(self.l_rho)

        self.e_p = make_input()
        field(content, "Показание датчика P:", self.e_p)
        self.s_p_unit = make_spinner(list(core.UNITS_DISPLAY.keys()), index=1)  # кПа
        field(content, "Ед. давления:", self.s_p_unit)

        self.e_vent = make_input()
        field(content, "Наддув P0 (пусто = 0):", self.e_vent)
        self.s_vent_unit = make_spinner(list(core.UNITS_DISPLAY.keys()), index=1)
        field(content, "Ед. наддува:", self.s_vent_unit)

        self.s_media.bind(text=self.update_rho)
        self.e_temp.bind(text=self.update_rho)
        self.e_rho_manual.bind(text=self.update_rho)
        self.update_rho()

        content.add_widget(make_button("РАССЧИТАТЬ УРОВЕНЬ", self.on_calc))
        self.l_res = make_result_area(content)
        content.add_widget(self.l_res)
        content.add_widget(make_button("Копировать результат", lambda *_: copy_result(self.l_res),
                                       bg=(0.42, 0.447, 0.502, 1), height=46))

        wrap_screen(self, "Уровень по давлению", content)

    def _manual_mode(self):
        spec = core.LIQUIDS.get(self.s_media.text)
        return bool(spec and spec["kind"] == "manual")

    def _temp(self):
        if self.e_temp.text.strip():
            return _num(self.e_temp.text)
        return 20.0

    def _density(self):
        rho20 = None
        if self._manual_mode() and self.e_rho_manual.text.strip():
            rho20 = _num(self.e_rho_manual.text)
        return core.liquid_density(self.s_media.text, self._temp(), rho20)

    def update_rho(self, *_):
        manual = self._manual_mode()
        # показываем/скрываем поле ручной плотности
        if manual:
            self.l_rho_manual.height = sc(22)
            self.e_rho_manual.height = sc(48)
            self.e_rho_manual.disabled = False
        else:
            self.l_rho_manual.height = 0
            self.e_rho_manual.height = 0
            self.e_rho_manual.disabled = True
        try:
            rho = self._density()
            self.l_rho.text = (f"Плотность при {self._temp():g}°C: "
                               f"{rho:.2f} кг/м³")
        except Exception:
            self.l_rho.text = "Плотность: —"

    def on_calc(self, *_):
        try:
            p_val = _num(self.e_p.text)
            p_pa = p_val * core.UNITS_CALC[core.UNITS_DISPLAY[self.s_p_unit.text]]
            if p_val < 0:
                raise ValueError("Показание датчика не может быть отрицательным")

            vent_pa = 0.0
            vent_txt = "0 (не задан)"
            if self.e_vent.text.strip():
                v = _num(self.e_vent.text)
                vent_pa = v * core.UNITS_CALC[core.UNITS_DISPLAY[self.s_vent_unit.text]]
                vent_txt = f"{v:g} {self.s_vent_unit.text}"
            p_eff = p_pa - vent_pa
            if p_eff < 0:
                raise ValueError("Давление наддува больше показания датчика — уровень не определяется")

            rho = self._density()
            if rho <= 0:
                raise ValueError("Плотность должна быть > 0")

            h_m = core.calc_level(p_eff, rho)
            h_cm = h_m * 100.0

            lines = [
                f"Среда: {self.s_media.text}",
                f"Плотность при {self._temp():g}°C: {rho:.2f} кг/м³",
                f"P датчика: {p_val:g} {self.s_p_unit.text} = {p_pa:.1f} Па",
                f"Наддув P0: {vent_txt} (вычитается)",
                f"Эффективное P: {p_eff:.1f} Па",
                "",
                f"УРОВЕНЬ: {h_m:.3f} м  =  {h_cm:.1f} см",
            ]
            self.l_res.text = "\n".join(lines)
        except InputError as e:
            self.l_res.text = f"Ошибка ввода: {e}"
            popup("Ошибка ввода", str(e), "error")
        except ValueError as e:
            self.l_res.text = f"Ошибка: {e}"
            popup("Ошибка ввода", str(e), "error")


# ----------------------------------------------------------------------
# ЭКРАН 7. Расчёт импульсных линий и конденсата
# ----------------------------------------------------------------------
class CondScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        content = new_scroll()

        heading(content, "Импульсные линии (конденсат)")
        content.add_widget(make_label(
            "Оценка объёма и массы конденсата в импульсной линии, перепада "
            "ΔP = ρ·g·h и времени накопления. Плотность конденсата — по "
            "таблице воды при заданной температуре.",
            size=14, color=MUTED, height=76))

        self.s_media = make_spinner(core.COND_MEDIA_LIST, index=0)
        field(content, "Рабочая среда:", self.s_media)

        self.e_L = make_input()
        self.e_L.text = "10"
        field(content, "Длина линии L, м:", self.e_L)

        tube_names = [t[0] for t in core.COND_TUBES] + ["вручную"]
        self.s_tube = make_spinner(tube_names, index=1)  # 14×2
        field(content, "Труба:", self.s_tube)

        # ручной ввод диаметра (скрыт по умолчанию)
        self.l_d_outer = cap_label("D нар, мм:")
        content.add_widget(self.l_d_outer)
        self.e_d_outer = make_input()
        self.e_d_outer.text = "14"
        content.add_widget(self.e_d_outer)
        self.l_t_wall = cap_label("t стенки, мм:")
        content.add_widget(self.l_t_wall)
        self.e_t_wall = make_input()
        self.e_t_wall.text = "2"
        content.add_widget(self.e_t_wall)

        self.e_slope = make_input()
        self.e_slope.text = "5"
        field(content, "Уклон линии, ‰ (0 = горизонтальная):", self.e_slope)

        self.e_temp = make_input()
        self.e_temp.text = "20"
        field(content, "Температура среды, °C:", self.e_temp)

        self.e_q = make_input()
        field(content, "Скорость конденсации Q, мл/ч:", self.e_q)

        # Режим конденсации: постепенная / быстрое остывание
        self.btn_mode = make_button("Режим: постепенная конденсация",
                                    self.toggle_mode, bg=SPIN_BG, fg=TEXT, height=48)
        content.add_widget(self.btn_mode)
        self._fast = False

        self.l_cool = cap_label("Время остывания, ч (после продувки/остановки):")
        content.add_widget(self.l_cool)
        self.e_cool = make_input()
        self.e_cool.text = "2"
        content.add_widget(self.e_cool)
        self._apply_cool_visible()

        self.e_purge = make_input()
        field(content, "Периодичность продувки, ч (опц.):", self.e_purge)

        self.e_fill = make_input()
        self.e_fill.text = "50"
        field(content, "Заполнение конденсатом, %:", self.e_fill)

        # Вторая линия (дифманометр) — переключатель
        self.btn_second = make_button("Дифманометр: вторая линия — ВЫКЛ",
                                      self.toggle_second, bg=SPIN_BG, fg=TEXT, height=48)
        content.add_widget(self.btn_second)
        self._second_on = False

        self.l_L2 = cap_label("Линия 2 — длина L2, м:")
        content.add_widget(self.l_L2)
        self.e_L2 = make_input()
        self.e_L2.text = "10"
        content.add_widget(self.e_L2)
        self.l_slope2 = cap_label("Линия 2 — уклон, ‰:")
        content.add_widget(self.l_slope2)
        self.e_slope2 = make_input()
        self.e_slope2.text = "5"
        content.add_widget(self.e_slope2)
        self.l_fill2 = cap_label("Линия 2 — заполнение, %:")
        content.add_widget(self.l_fill2)
        self.e_fill2 = make_input()
        self.e_fill2.text = "0"
        content.add_widget(self.e_fill2)
        self._apply_second_visible()

        self.s_media.bind(text=self.update_q)
        self.e_L.bind(text=self.update_q)
        self.s_tube.bind(text=self.update_tube)
        self.update_q()
        self.update_tube()

        content.add_widget(make_button("РАССЧИТАТЬ", self.on_calc))
        self.l_res = make_result_area(content)
        content.add_widget(self.l_res)
        content.add_widget(make_button("Копировать результат", lambda *_: copy_result(self.l_res),
                                       bg=(0.42, 0.447, 0.502, 1), height=46))
        content.add_widget(make_button("Сформировать запись в акт", self.on_act,
                                       bg=SUCCESS, height=46))

        wrap_screen(self, "Импульсные линии", content)

    # --- переключатель второй линии ---
    def toggle_second(self, *_):
        self._second_on = not self._second_on
        self.btn_second.text = ("Дифманометр: вторая линия — ВКЛ" if self._second_on
                                else "Дифманометр: вторая линия — ВЫКЛ")
        self.btn_second.background_color = SUCCESS if self._second_on else SPIN_BG
        self.btn_second.color = (1, 1, 1, 1) if self._second_on else TEXT
        self._apply_second_visible()

    def _apply_second_visible(self):
        for lbl, ent in ((self.l_L2, self.e_L2), (self.l_slope2, self.e_slope2),
                         (self.l_fill2, self.e_fill2)):
            self._field_visible(lbl, self._second_on, 22)
            self._field_visible(ent, self._second_on, 48)

    # --- переключатель режима конденсации ---
    def toggle_mode(self, *_):
        self._fast = not self._fast
        self.btn_mode.text = ("Режим: быстрое остывание"
                              if self._fast else "Режим: постепенная")
        self.btn_mode.background_color = SUCCESS if self._fast else SPIN_BG
        self.btn_mode.color = (1, 1, 1, 1) if self._fast else TEXT
        self._apply_cool_visible()
        if self._fast:
            if self.e_fill.text.strip() == "50":
                self.e_fill.text = "100"
        self.e_q.disabled = self._fast

    def _apply_cool_visible(self):
        self._field_visible(self.l_cool, self._fast, 22)
        self._field_visible(self.e_cool, self._fast, 48)

    def _field_visible(self, w, show, height):
        w.disabled = not show
        w.height = sc(height) if show else 0

    # --- труба: показать ручной ввод при «вручную» ---
    def update_tube(self, *_):
        manual = self.s_tube.text == "вручную"
        self._field_visible(self.l_d_outer, manual, 22)
        self._field_visible(self.e_d_outer, manual, 48)
        self._field_visible(self.l_t_wall, manual, 22)
        self._field_visible(self.e_t_wall, manual, 48)

    # --- скорость конденсации по умолчанию ---
    def _q_default(self):
        media = self.s_media.text
        L = 10.0
        if self.e_L.text.strip():
            try:
                L = _num(self.e_L.text)
            except InputError:
                L = 10.0
        if "пар" in media:
            return 7.0 * L / 10.0
        return 0.0

    def update_q(self, *_):
        if self._fast:
            return
        default = self._q_default()
        if not self.e_q.text.strip() and default:
            self.e_q.text = f"{default:g}"
        elif self.s_media.text != "пар/газ с конденсацией" and not self.e_q.text.strip():
            self.e_q.text = ""

    def _num_or(self, widget, default):
        if not widget.text.strip():
            return default
        return _num(widget.text)

    def on_calc(self, *_):
        try:
            L = self._num_or(self.e_L, 0.0)
            if L <= 0:
                raise ValueError("Длина линии должна быть больше 0")
            if self.s_tube.text == "вручную":
                d_in = core.cond_d_inner_mm("вручную",
                                            _num(self.e_d_outer.text),
                                            _num(self.e_t_wall.text))
            else:
                d_in = core.cond_d_inner_mm(self.s_tube.text)
            if d_in <= 0:
                raise ValueError("Внутренний диаметр должен быть больше 0")
            slope = self._num_or(self.e_slope, 0.0)
            fill = self._num_or(self.e_fill, 50.0)
            t_c = self._num_or(self.e_temp, 20.0)

            l1 = core.cond_line_geometry(L, slope, fill, d_in, t_c)
            lines = [
                f"Труба: {self.s_tube.text} (d вн = {d_in:.1f} мм)",
                f"Среда: {self.s_media.text}, ρ = {l1['rho']:.1f} кг/м³ (при {t_c:g}°C)",
                f"Объём линии: {l1['V_ml']:.0f} мл  ·  Конденсат: {l1['V_cond']:.0f} мл",
                f"Масса конденсата: {l1['m_g']:.0f} г",
                f"Столб h = {l1['h_mm']:.1f} мм",
                f"Перепад ΔP: {l1['dp_pa']:.0f} Па ≈ {l1['dp_mmh2o']:.1f} мм вод. ст.",
            ]
            if self._fast:
                lines.insert(0, f"Режим: быстрое остывание — весь пар в объёме "
                                f"линии сконденсируется за ~{self._num_or(self.e_cool, 2.0):g} ч")
            else:
                lines.insert(0, "Режим: постепенная конденсация (по скорости Q)")

            dp_eff_pa = l1["dp_pa"]
            if self._second_on:
                L2 = self._num_or(self.e_L2, L)
                slope2 = self._num_or(self.e_slope2, 0.0)
                fill2 = self._num_or(self.e_fill2, 0.0)
                l2 = core.cond_line_geometry(L2, slope2, fill2, d_in, t_c)
                dh_mm = abs(l1["h_mm"] - l2["h_mm"])
                dp_eff_pa = dh_mm / 1000.0 * l1["rho"] * core.GRAVITY_M_S2
                lines.append(f"Δh = |h1 − h2| = {dh_mm:.1f} мм  →  ΔP = "
                             f"{dp_eff_pa:.0f} Па ≈ {dp_eff_pa / 9.80665:.1f} мм вод. ст.")

            Q = self._num_or(self.e_q, 0.0)
            if self._fast:
                t_cool_h = max(0.1, self._num_or(self.e_cool, 2.0))
                lines.append(f"\nВремя до полного заполнения: ~{t_cool_h:g} ч "
                             f"(равно времени остывания; Q не используется)")
                t_full_h = t_cool_h
            elif Q > 0:
                lines.append(f"\nВремя до полного заполнения: {l1['V_ml'] / Q:.0f} ч"
                             f" (до текущего: {l1['V_cond'] / Q:.0f} ч)")
                t_full_h = l1["V_ml"] / Q
            else:
                lines.append("\nВремя накопления: не задано (Q = 0)")
                t_full_h = None

            kind, status = core.cond_status(dp_eff_pa, fast_cool=self._fast)
            purge_h = self._num_or(self.e_purge, 0.0)
            recs = core.cond_recommendations(
                slope, fill, dp_eff_pa, purge_h or None, t_full_h,
                fast_cool=self._fast,
                t_cool_h=(self._num_or(self.e_cool, 2.0) if self._fast else None))
            lines.append(f"\nСТАТУС: {status}")
            lines.append("Рекомендации:")
            lines.extend(f"• {r}" for r in recs)
            self.l_res.text = "\n".join(lines)
        except InputError as e:
            self.l_res.text = f"Ошибка ввода: {e}"
            popup("Ошибка ввода", str(e), "error")
        except ValueError as e:
            self.l_res.text = f"Ошибка: {e}"
            popup("Ошибка ввода", str(e), "error")

    def on_act(self, *_):
        """Формирует запись в акт и копирует в буфер."""
        try:
            L = self._num_or(self.e_L, 0.0)
            if L <= 0:
                raise ValueError("Длина линии должна быть больше 0")
            if self.s_tube.text == "вручную":
                d_in = core.cond_d_inner_mm("вручную",
                                            _num(self.e_d_outer.text),
                                            _num(self.e_t_wall.text))
            else:
                d_in = core.cond_d_inner_mm(self.s_tube.text)
            slope = self._num_or(self.e_slope, 0.0)
            fill = self._num_or(self.e_fill, 50.0)
            t_c = self._num_or(self.e_temp, 20.0)
            l1 = core.cond_line_geometry(L, slope, fill, d_in, t_c)
            dp_pa = l1["dp_pa"]
            if self._second_on:
                L2 = self._num_or(self.e_L2, L)
                slope2 = self._num_or(self.e_slope2, 0.0)
                fill2 = self._num_or(self.e_fill2, 0.0)
                l2 = core.cond_line_geometry(L2, slope2, fill2, d_in, t_c)
                dp_pa = abs(l1["h_mm"] - l2["h_mm"]) / 1000.0 * l1["rho"] * core.GRAVITY_M_S2

            tube_name = self.s_tube.text
            if tube_name == "вручную":
                tube_name = (f"Ø{_num(self.e_d_outer.text):g}×"
                             f"{_num(self.e_t_wall.text):g}")
            act_text = (
                f"При осмотре выявлено скопление конденсата в импульсной линии "
                f"длиной {L:g} м (труба {tube_name}, среда — {self.s_media.text}). "
                f"Расчётный объём конденсата — {l1['V_cond']:.0f} мл, расчётный "
                f"перепад из-за конденсата — {dp_pa / 9.80665:.1f} мм вод. ст. "
                f"Выполнена продувка. Показания стабилизированы."
            )
            if self._fast:
                act_text = (
                    act_text[:-1] +
                    f" Линия была продута/остановлена: при остывании весь пар "
                    f"в объёме трубы сконденсируется за "
                    f"~{max(0.1, self._num_or(self.e_cool, 2.0)):g} ч."
                )
            copy_text(act_text)
        except InputError as e:
            popup("Ошибка ввода", str(e), "error")
        except ValueError as e:
            popup("Ошибка ввода", str(e), "error")


# ----------------------------------------------------------------------
# ЭКРАН 8. 4–20 мА ⇄ Величина
# ----------------------------------------------------------------------
MA_UNITS = ["бар", "кПа", "МПа", "мбар", "атм", "пси",
            "°C", "°F", "K",
            "м³/ч", "л/с", "л/мин", "кг/ч", "т/ч",
            "м", "мм", "см", "%"]

MA_PRESETS = [
    "Пользовательский",
    "Давление 0–10 бар",
    "Давление 0–16 бар",
    "Давление 0–25 бар",
    "Давление 0–100 кПа",
    "Давление 0–1 МПа",
    "Температура –50…+150 °C",
    "Температура 0–200 °C",
    "Температура 0–500 °C",
    "Расход 0–100 м³/ч",
    "Расход 0–500 л/с",
    "Уровень 0–10 м",
    "Уровень 0–100 %",
]

MA_PRESET_DATA = {
    "Давление 0–10 бар": (4, 20, 0, 10, "бар"),
    "Давление 0–16 бар": (4, 20, 0, 16, "бар"),
    "Давление 0–25 бар": (4, 20, 0, 25, "бар"),
    "Давление 0–100 кПа": (4, 20, 0, 100, "кПа"),
    "Давление 0–1 МПа": (4, 20, 0, 1, "МПа"),
    "Температура –50…+150 °C": (4, 20, -50, 150, "°C"),
    "Температура 0–200 °C": (4, 20, 0, 200, "°C"),
    "Температура 0–500 °C": (4, 20, 0, 500, "°C"),
    "Расход 0–100 м³/ч": (4, 20, 0, 100, "м³/ч"),
    "Расход 0–500 л/с": (4, 20, 0, 500, "л/с"),
    "Уровень 0–10 м": (4, 20, 0, 10, "м"),
    "Уровень 0–100 %": (4, 20, 0, 100, "%"),
}


class MaScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        content = new_scroll()

        heading(content, "4–20 мА ⇄ Величина")
        content.add_widget(make_label(
            "Универсальный пересчёт сигнала 4–20 мА в физическую величину и обратно.",
            size=14, color=MUTED, height=56))

        self.s_preset = make_spinner(MA_PRESETS, index=0)
        field(content, "Типовой прибор:", self.s_preset)
        self.s_preset.bind(text=self.on_preset)

        self.btn_dir = make_button("Направление: мА → Величина",
                                   self.toggle_dir, bg=SPIN_BG, fg=TEXT, height=48)
        content.add_widget(self.btn_dir)
        self._ma2val = True

        self.e_ma_min = make_input()
        self.e_ma_min.text = "4"
        field(content, "Сигнал от, мА:", self.e_ma_min)
        self.e_ma_max = make_input()
        self.e_ma_max.text = "20"
        field(content, "Сигнал до, мА:", self.e_ma_max)

        self.e_val_min = make_input()
        self.e_val_min.text = "0"
        field(content, "Величина от:", self.e_val_min)
        self.e_val_max = make_input()
        self.e_val_max.text = "10"
        field(content, "Величина до:", self.e_val_max)

        self.s_unit = make_spinner(MA_UNITS, index=0)
        field(content, "Ед. изм.:", self.s_unit)

        self.e_input = make_input()
        self.e_input.text = "12"
        field(content, "Входное значение:", self.e_input)

        content.add_widget(make_button("РАССЧИТАТЬ", self.on_calc))
        self.l_res = make_result_area(content)
        content.add_widget(self.l_res)
        content.add_widget(make_button("Копировать результат", lambda *_: copy_result(self.l_res),
                                       bg=(0.42, 0.447, 0.502, 1), height=46))

        wrap_screen(self, "4–20 мА ⇄ Величина", content)

    def on_preset(self, *_):
        name = self.s_preset.text
        data = MA_PRESET_DATA.get(name)
        if data:
            self.e_ma_min.text = str(data[0])
            self.e_ma_max.text = str(data[1])
            self.e_val_min.text = str(data[2])
            self.e_val_max.text = str(data[3])
            self.s_unit.text = data[4]

    def toggle_dir(self, *_):
        self._ma2val = not self._ma2val
        self.btn_dir.text = ("Направление: Величина → мА"
                             if self._ma2val else "Направление: мА → Величина")
        self.btn_dir.background_color = SUCCESS if not self._ma2val else SPIN_BG
        self.btn_dir.color = (1, 1, 1, 1) if not self._ma2val else TEXT

    def on_calc(self, *_):
        try:
            ma_min = _num(self.e_ma_min.text)
            ma_max = _num(self.e_ma_max.text)
            val_min = _num(self.e_val_min.text)
            val_max = _num(self.e_val_max.text)
            inp = _num(self.e_input.text)
            if ma_max <= ma_min or val_max <= val_min:
                raise ValueError("Максимум должен быть больше минимума")
            unit = self.s_unit.text
            if self._ma2val:
                pct = (inp - ma_min) / (ma_max - ma_min) * 100
                val = val_min + (inp - ma_min) / (ma_max - ma_min) * (val_max - val_min)
                out_of = ""
                if inp < ma_min or inp > ma_max:
                    out_of = " [!] ВНЕ ДИАПАЗОНА"
                self.l_res.text = f"{val:.3f} {unit}  ({pct:.1f}%){out_of}"
            else:
                pct = (inp - val_min) / (val_max - val_min) * 100
                ma = ma_min + (inp - val_min) / (val_max - val_min) * (ma_max - ma_min)
                out_of = ""
                if inp < val_min or inp > val_max:
                    out_of = " [!] ВНЕ ДИАПАЗОНА"
                self.l_res.text = f"{ma:.3f} мА  ({pct:.1f}%){out_of}"
        except InputError as e:
            self.l_res.text = f"Ошибка ввода: {e}"
            popup("Ошибка ввода", str(e), "error")
        except ValueError as e:
            self.l_res.text = f"Ошибка: {e}"
            popup("Ошибка ввода", str(e), "error")


# ----------------------------------------------------------------------
# ЭКРАН 9. О программе
# ----------------------------------------------------------------------
class AboutScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        content = new_scroll()

        content.add_widget(make_label("Расчётный модуль КИПиА", size=22, bold=True,
                                      color=PRIMARY))
        content.add_widget(make_label("Версия 1.2", size=14, color=MUTED))

        self.l_about_1 = make_result_area(content)
        content.add_widget(self.l_about_1)
        self.l_about_1.text = (
            "Программа предназначена для специалистов КИПиА, метрологов и инженеров, "
            "которым ежедневно приходится выполнять быстрые и точные расчёты при поверке, "
            "диагностике и эксплуатации средств измерений.")

        heading(content, "Возможности")
        self.l_about_2 = make_result_area(content)
        content.add_widget(self.l_about_2)
        self.l_about_2.text = (
            "• Конвертация единиц давления и расчёт погрешности\n"
            "• Пересчёт сигнала 4–20 мА ↔ физическая величина (пресеты приборов)\n"
            "• Расход по квадратичной зависимости (шкала и сигнал)\n"
            "• Диагностика датчиков и мини-протокол поверки\n"
            "• Термометры сопротивления: НСХ, R и t, таблицы поверки\n"
            "• Термопары: НСХ, ЭДС и t, таблицы поверки\n"
            "• Расход через диафрагму по ГОСТ 8.586.2 / ISO 5167\n"
            "• Уровень по давлению (дифманометр, плотность по среде)\n"
            "• Импульсные линии: объём и масса конденсата, перепад ΔP = ρ·g·h")

        self.l_about_3 = make_result_area(content)
        content.add_widget(self.l_about_3)
        self.l_about_3.text = (
            "Приложение написано на языке Python (фреймворк Kivy).")

        heading(content, "Что нового в версии 1.2")
        self.l_about_new = make_result_area(content)
        content.add_widget(self.l_about_new)
        self.l_about_new.text = (
            "Версия 1.2: добавлен расчёт конденсата в импульсных линиях — "
            "объём, масса, перепад ΔP = ρ·g·h, время накопления\n"
            "• Рекомендации по уклону, дренажу и периодичности продувки "
            "с цветовым статусом\n"
            "• Формирование записи в акт одним нажатием\n"
            "• Уровень по давлению: плотность подставляется автоматически "
            "по среде и температуре\n"
            "• Пересчёт 4–20 мА ↔ величина: 13 пресетов типовых приборов, "
            "18 единиц измерения, направление в обе стороны")

        self.l_cr = make_label("© Евгений Харлин, 2026 г.", size=18, bold=True,
                               color=PRIMARY, halign="center")
        content.add_widget(self.l_cr)

        wrap_screen(self, "О программе", content)


# ----------------------------------------------------------------------
# Главный экран — меню модулей
# ----------------------------------------------------------------------
MENU_ITEMS = [
    ("Конвертация и погрешность", ConvScreen),
    ("4–20 мА ⇄ Величина", MaScreen),
    ("Диагностика датчика", DiagScreen),
    ("Расход (квадратичная)", FlowScreen),
    ("Расход (диафрагма)", OrifScreen),
    ("Уровень по давлению", LevelScreen),
    ("Импульсные линии (конденсат)", CondScreen),
    ("Температура (НСХ)", TempScreen),
    ("Термопары (НСХ)", TCScreen),
    ("О программе", AboutScreen),
]


class MenuScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        content = new_scroll()
        paint_bg(self, BG)
        outer = BoxLayout(orientation="vertical")
        paint_bg(outer, BG)
        add_safe_spacers(outer, top=True, bottom=False)
        t = auto_area("Расчётный модуль КИПиА", size=25, color=PRIMARY)
        t.bold = True
        t.halign = "center"
        content.add_widget(t)
        logo = Image(source="logo_gauge.png", size_hint=(None, None),
                     size=(sc(160), sc(160)))
        logo.pos_hint = {"center_x": 0.5}
        content.add_widget(logo)
        content.add_widget(make_label("Выберите раздел:", size=16, color=MUTED))
        for name, _cls in MENU_ITEMS:
            b = make_button(name, bg=PRIMARY, height=58)
            b.bind(on_press=lambda _wdt, n=name: self.goto(n))
            content.add_widget(b)
        outer.add_widget(as_scroll(content))
        add_safe_spacers(outer, top=False, bottom=True)
        self.add_widget(outer)

    def goto(self, name):
        for n, _cls in MENU_ITEMS:
            if n == name:
                self.manager.current = f"scr_{n}"
                return


class KIPiAApp(App):
    title = "РМ: КИПиА"

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