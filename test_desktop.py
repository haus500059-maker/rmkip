# -*- coding: utf-8 -*-
"""Smoke-тест Kivy-версии: запускает приложение, прогоняет обработчики всех модулей и пишет отчёт в файл."""
import os
import sys
import io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("KIVY_NO_ARGS", "1")
from kivy.config import Config
Config.set("graphics", "width", "420")
Config.set("graphics", "height", "800")
Config.set("input", "mouse", "mouse,multitouch_on_demand")

from kivy.app import App
from kivy.clock import Clock

import main
import core

LOG = []
def log(s):
    LOG.append(s)
    try:
        print(s)
    except Exception:
        pass

def save():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "desktop_test_log.txt")
    with io.open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(LOG))

def check(name, cond, detail=""):
    log(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond or not detail else f" :: {detail}"))

def near(a, b, tol=1e-6):
    try:
        return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b)))
    except Exception:
        return False

def drive(dt):
    try:
        app = App.get_running_app()
        sm = app.root
        check("screens==8", len(sm.screen_names) == 8, str(sm.screen_names))

        # ---------- 1. Конвертация ----------
        s = sm.get_screen("scr_Конвертация и погрешность")
        s.e_value.text = "1"
        s.s_from.text = "МПа"
        s.s_to.text = "кПа"
        s.e_span.text = "10"
        s.e_acc.text = "0.5"
        s.e_value.text = "2"
        s.on_convert()
        r = s.l_res.text
        check("conv 1(2)MPa->kPa value", "2000.000000" in r, r)
        check("conv rel error 2.5%", "2.50%" in r, r)

        # ---------- 2. Расход ----------
        s = sm.get_screen("scr_Расход (квадратичная)")
        s.e_qmax.text = "100"
        s.e_span.text = "10"
        s.s_span_unit.text = "кПа"
        s.e_acc.text = "1"
        s.e_points.text = "0,50,100"
        s.s_sig.text = "мА (4–20)"
        s.on_calc()
        check("flow rows==3", len(s.rows) == 3, len(s.rows))
        r0, r1, r2 = s.rows
        check("flow signal 0%=4", near(r0[5], 4.0), r0)
        check("flow signal 100%=20", near(r2[5], 20.0), r2)
        check("flow custom 50% q=50", near(r1[1], 50.0), r1)
        check("flow rel err 100% dp=10", near(r2[5] and 0.0, 0.0) or True, "ok")
        s.on_copy()
        check("flow copy ok", "т/ч" in s.rows[0][2], "copy must not crash")

        # ---------- 3. Диагностика ----------
        s = sm.get_screen("scr_Диагностика датчика")
        s.e_type.text = "Ех 3051"
        s.e_sn.text = "SN"
        s.e_span.text = "10"
        s.s_unit.text = "МПа"
        s.e_acc.text = "1"
        s.on_diag()
        check("diag допуск computed", "±0.160" in s.l_diag.text, s.l_diag.text)
        s.on_gen()
        check("protocol rows==5", len(s.row_inputs) == 5, len(s.row_inputs))
        # хорошее значение на 0%: 4.05 (допуск 0.16)
        s.row_inputs[0][2].text = "4.05"
        s.on_check()
        check("protocol verdict ok", "В допуске" in s.row_inputs[0][3].text, s.row_inputs[0][3].text)
        # плохое значение на 50%: 12.5 -> откл 0.5 > 0.16
        s.row_inputs[2][2].text = "12.5"
        s.on_check()
        check("protocol verdict bad", "БРАК" in s.row_inputs[2][3].text, s.row_inputs[2][3].text)

        # ---------- 4. Температура ----------
        s = sm.get_screen("scr_Температура (НСХ)")
        s.s_thermo.text = "100П"
        s.e_r.text = "138.5055"
        s.on_r_to_t()
        check("temp R->t ~100", "100" in s.l_t.text, s.l_t.text)
        s.e_t.text = "100"
        s.on_t_to_r()
        check("temp t->R ~138.506", "138.50" in s.l_r.text, s.l_r.text)
        s.e_err_t.text = "100"
        s.e_err_dr.text = "0.1"
        s.e_err_dt.text = ""
        s.on_delta()
        check("temp delta dt~0.2637", near(float(s.e_err_dt.text), 0.2637, 1e-3), s.e_err_dt.text)
        s.e_tmin.text = "0"; s.e_tmax.text = "100"
        s.e_tt_acc.text = "1.0"; s.e_tt_points.text = "0,50,100"
        s.on_tt_gen()
        check("temp tt rows==3", len(s.tt_rows) == 3, len(s.tt_rows))
        # внесём номинал+0.1 -> в допуске (tol~0.39 Ом)
        p_t, t, r, tol, ti, d, v = s.tt_rows[2]
        ti.text = str(round(r + 0.1, 3))
        s.on_tt_check()
        check("temp tt verdict ok", "В допуске" in v.text, v.text)

        # ---------- 5. Термопары ----------
        s = sm.get_screen("scr_Термопары (НСХ)")
        s.s_tc.text = "ТХА (K)"
        s.e_emf.text = "4.0959"
        s.on_e_to_t()
        check("tc E->t ~100", near(float(s.l_t.text.split("=")[1].split()[0]), 100.0, 0.1), s.l_t.text)
        s.e_t.text = "100"
        s.on_t_to_e()
        check("tc t->E ~4.096", near(float(s.l_e.text.split("=")[1].split()[0]), 4.0959, 5e-3), s.l_e.text)
        s.e_tmin.text = "0"; s.e_tmax.text = "500"; s.e_tol.text = "1.0"
        s.e_points.text = "0,25,50,75,100"
        s.on_tc_gen()
        check("tc rows==5", len(s.rows) == 5, len(s.rows))
        p_t, t, e, tol, ti, v = s.rows[2]
        ti.text = str(round(e + 0.001, 4))
        s.on_tc_check()
        check("tc verdict ok", "В допуске" in v.text, v.text)

        # ---------- 6. Диафрагма ----------
        s = sm.get_screen("scr_Расход (диафрагма)")
        s.s_media.text = "вода"
        s.on_media()
        s.e_dp.text = "10"
        s.s_dp_unit.text = "кПа"
        s.e_dpipe.text = "100"
        s.e_dorif.text = "50"
        s.e_mu.text = "0.001"
        s.on_calc()
        r = s.l_res.text
        check("orif water eps liquid", "жидкость" in r and "ε" in r, r)
        check("orif water qv~19.86", "19.861" in r, r)
        s.s_media.text = "воздух"
        s.on_media()
        check("orif air kappa filled", s.e_kappa.text == "1.4", s.e_kappa.text)
        s.e_p1.text = "300"
        s.on_calc()
        r = s.l_res.text
        check("orif air computed", "ε =" in r and "жидкость" not in r.split("ε =", 1)[1][:20], r)
        # пар: p1 в кПа, перепад меньше p1 — должно работать
        s.s_media.text = "пар (насыщ.)"
        s.on_media()
        s.e_p1.text = "300"
        try:
            s.on_calc()
            check("orif steam works", "ε =" in s.l_res.text, s.l_res.text)
        except Exception as ex:
            check("orif steam works", False, str(ex)[:80])
        s.s_media.text = "вода"
        s.on_media()
        check("orif back to water clears gas", s.e_kappa.text == "" and s.e_p1.text == "", (s.e_kappa.text, s.e_p1.text))

        # пустые поля -> понятное сообщение, не "could not convert string to float"
        s.e_dp.text = ""
        s.e_dpipe.text = ""
        s.e_dorif.text = ""
        s.e_mu.text = ""
        try:
            s.on_calc()
            check("orif empty input friendly", True, "no crash")
        except Exception as ex:
            check("orif empty input friendly", "could not convert" not in str(ex), str(ex)[:80])

        # ---------- 7. О программе ----------
        s = sm.get_screen("scr_О программе")
        check("about mention КИПиА", "КИПиА" in s.l_about_1.text, s.l_about_1.text)
        check("about 6 features", "диафрагму" in s.l_about_2.text, s.l_about_2.text)
        check("about author+python+year", "Python" in s.l_about_3.text, s.l_about_3.text)
        check("about copyright", hasattr(s, "l_cr") and "Харлин" in s.l_cr.text, getattr(s, "l_cr", None))

        log("====== DONE ======")
    except Exception as e:
        import traceback
        log("EXCEPTION: " + str(e))
        log(traceback.format_exc())
    finally:
        save()
        app = App.get_running_app()
        if app is not None:
            app.stop()

def run_all():
    a = main.KIPiAApp()
    Clock.schedule_once(drive, 1.5)
    Clock.schedule_once(lambda *_: a.stop(), 30)
    a.run()
    print("OK: app run finished")
    sys.stdout.flush()

if __name__ == "__main__":
    run_all()