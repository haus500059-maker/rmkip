# -*- coding: utf-8 -*-
import math
import bisect

VERIFICATION_POINTS = [0, 25, 50, 75, 100]

# --- СПРАВОЧНИКИ СРЕД ДЛЯ РАСЧЁТА ДИАФРАГМЫ ---
DENSITIES = {
    "вода": 998.2,          # кг/м³ при ~20°C
    "пар (насыщ.)": 0.6,     # примерная плотность насыщенного пара при низком давлении
    "воздух": 1.204,        # кг/м³ при 20°C, 1 атм
    "азот": 1.165,
    "кислород": 1.331,
}

# mu — динамическая вязкость, Па·с; kappa — показатель адиабаты;
# gas=True — сжимаемая среда (нужны p1 и κ для коэффициента расширения ε)
ORIFICE_MEDIA = {
    "вода":         {"rho": 998.2, "mu": 0.001002,  "kappa": None,  "gas": False},
    "пар (насыщ.)": {"rho": 0.6,   "mu": 1.1e-5,    "kappa": 1.30, "gas": True},
    "воздух":       {"rho": 1.204, "mu": 1.825e-5,  "kappa": 1.40, "gas": True},
    "азот":         {"rho": 1.165, "mu": 1.76e-5,   "kappa": 1.40, "gas": True},
    "кислород":     {"rho": 1.331, "mu": 2.06e-5,   "kappa": 1.40, "gas": True},
}


def calc_flow_orifice_gost(delta_p_pa, d_m, D_m, rho_kg_m3, mu_pa_s,
                           kappa=None, p1_abs_pa=None):
    """
    Расчёт расхода через диафрагму по ГОСТ 8.586.2-2005 / ISO 5167-1
    (угловой способ отбора давления, НСХ для несжимаемых и сжимаемых сред).

    Параметры:
        delta_p_pa — перепад давления, Па;
        d_m        — диаметр отверстия диафрагмы, м;
        D_m        — внутренний диаметр трубопровода, м;
        rho_kg_m3  — плотность среды при рабочих условиях, кг/м³;
        mu_pa_s    — динамическая вязкость среды, Па·с;
        kappa      — показатель адиабаты (для газов/пара), иначе None (жидкость);
        p1_abs_pa  — абсолютное давление до диафрагмы, Па (для газов/пара).

    Возвращает dict: qm_kg_s, qv_m3_s, c, eps, re, beta, velocity_m_s,
                     velocity_orif_m_s, warnings.
    """
    import math
    warnings = []

    if rho_kg_m3 <= 0:
        raise ValueError("Плотность должна быть > 0")
    if d_m <= 0 or D_m <= 0:
        raise ValueError("Диаметры должны быть > 0")
    if d_m >= D_m:
        raise ValueError("Диаметр диафрагмы d должен быть меньше диаметра трубы D")
    if delta_p_pa < 0:
        raise ValueError("Перепад давления не может быть отрицательным")
    if mu_pa_s <= 0:
        raise ValueError("Вязкость должна быть > 0")

    beta = d_m / D_m
    area = math.pi * (d_m ** 2) / 4.0

    if beta < 0.1 or beta > 0.75:
        warnings.append(f"β={beta:.3f} вне диапазона применимости ГОСТ 8.586 (0.10–0.75).")

    is_gas = (kappa is not None and kappa > 1.0)
    if is_gas:
        if p1_abs_pa is None or p1_abs_pa <= 0:
            raise ValueError("Для газа/пара укажите абсолютное давление до диафрагмы p1")
        if delta_p_pa >= p1_abs_pa:
            raise ValueError("Перепад ΔP должен быть меньше абсолютного давления p1 (p2 > 0)")
        if kappa > 1.7:
            warnings.append("Показатель адиабаты κ вне обычного диапазона (1.1–1.7).")

    def _coeff_c(beta_v, re_v):
        """Коэффициент расхода C по ISO 5167-1 (угловой отбор)"""
        a_v = (19000.0 * beta_v / re_v) ** 0.8
        return (0.5961 + 0.0261 * beta_v ** 2 - 0.216 * beta_v ** 8
                + 0.000521 * (1e6 * beta_v / re_v) ** 0.7
                + (0.0188 + 0.0063 * a_v) * beta_v ** 3.5 * (1e6 / re_v) ** 0.3)

    def _exp_factor(beta_v, dp, p1, k):
        """Коэффициент расширения ε (ISO 5167)"""
        if dp < 0 or dp >= p1:
            return None
        ratio = (p1 - dp) / p1
        return 1.0 - (0.351 + 0.256 * beta_v ** 4 + 0.93 * beta_v ** 8) * (1.0 - ratio ** (1.0 / k))

    def _assemble(qm, c_v, eps_v, re_v):
        return {
            "qm_kg_s": qm, "qv_m3_s": qm / rho_kg_m3, "c": c_v, "eps": eps_v,
            "re": re_v, "beta": beta,
            "velocity_m_s": 4.0 * (qm / rho_kg_m3) / (math.pi * D_m ** 2),
            "velocity_orif_m_s": (qm / rho_kg_m3) / area,
            "warnings": warnings,
        }

    if delta_p_pa == 0.0:
        c = _coeff_c(beta, 1e6)
        eps = _exp_factor(beta, 0.0, p1_abs_pa, kappa) if is_gas else 1.0
        return _assemble(0.0, c, eps, 0.0)

    # Итерация: C, ε и Re взаимозависимы
    re = 1e6
    c = _coeff_c(beta, re)
    eps = _exp_factor(beta, delta_p_pa, p1_abs_pa, kappa) if is_gas else 1.0
    qm_kg_s = 0.0
    for _ in range(50):
        qm_new = (c * eps * area * math.sqrt(2.0 * delta_p_pa * rho_kg_m3)
                  / math.sqrt(1.0 - beta ** 4))
        re_new = 4.0 * qm_new / (math.pi * D_m * mu_pa_s) if qm_new > 0 else 0.0
        c_new = _coeff_c(beta, re_new)
        eps_new = _exp_factor(beta, delta_p_pa, p1_abs_pa, kappa) if is_gas else 1.0
        if abs(qm_new - qm_kg_s) <= 1e-12 * max(1.0, abs(qm_new)):
            qm_kg_s, c, eps, re = qm_new, c_new, eps_new, re_new
            break
        qm_kg_s, c, eps, re = qm_new, c_new, eps_new, re_new

    if re < 4000:
        warnings.append(f"Re={re:.0f} < 4000 — ниже границы применимости формулы C (ГОСТ 8.586.2).")
    if (qm_kg_s / rho_kg_m3) / area > 500.0:
        warnings.append("Скорость в диафрагме > 500 м/с. Возможен режим запирания потока; "
                        "реальный расход может быть ниже расчётного.")
    if is_gas and eps is not None and eps < 0.5:
        warnings.append("Коэффициент расширения ε < 0.5 — режим близок к критическому перепаду.")

    return _assemble(qm_kg_s, c, eps, re)


# --- ХАРАКТЕРИСТИКИ ТЕРМОМЕТРОВ (НСХ) ---
THERMOMETERS = {
    "50П":   {"R0": 50.0, "type": "Pt",  "coeffs": (3.9083e-3, -5.775e-7, -4.183e-12)},
    "100П":  {"R0": 100.0, "type": "Pt", "coeffs": (3.9083e-3, -5.775e-7, -4.183e-12)},
    "Pt50":  {"R0": 50.0, "type": "Pt",  "coeffs": (3.9083e-3, -5.775e-7, -4.183e-12)},
    "Pt100": {"R0": 100.0, "type": "Pt", "coeffs": (3.9083e-3, -5.775e-7, -4.183e-12)},
    "Pt1000":{"R0": 1000.0,"type": "Pt", "coeffs": (3.9083e-3, -5.775e-7, -4.183e-12)},
    "50М":   {"R0": 50.0,  "type": "Cu",  "coeffs": (4.28e-3, 0, 0)},
    "100М":  {"R0": 100.0, "type": "Cu",  "coeffs": (4.28e-3, 0, 0)},
    "Cu50":  {"R0": 50.0,  "type": "Cu",  "coeffs": (4.28e-3, 0, 0)},
    "Cu100": {"R0": 100.0, "type": "Cu",  "coeffs": (4.28e-3, 0, 0)},
}

THERMO_DISPLAY_LIST = list(THERMOMETERS.keys())

# --- ФУНКЦИИ РАСЧЁТА (Формулы) ---


def resistance_to_temp(R, R0, coeffs):
    A, B, C = coeffs
    if R <= 0:
        return None

    t = (R / R0 - 1) / A

    for _ in range(20):
        if t < 0:
            # Отрицательные температуры (t < 0): полная формула с членом C (IEC 60751)
            Rt = R0 * (1 + A*t + B*t**2 + C*(t - 100)*t**3)
            dRdt = R0 * (A + 2*B*t + C*((t - 100)*3*t**2 + t**3))
        else:
            # t >= 0: член C не применяется
            Rt = R0 * (1 + A*t + B*t**2)
            dRdt = R0 * (A + 2*B*t)

        if abs(dRdt) < 1e-9:
            break

        t_new = t - (Rt - R) / dRdt
        if abs(t_new - t) < 0.001:
            t = t_new
            break
        t = t_new

    return t

def temp_to_resistance(t, R0, coeffs):
    A, B, C = coeffs
    if B == 0 and C == 0:  # Медь
        return R0 * (1 + A * t)
    elif t < 0:  # Платина, t < 0: полная формула
        return R0 * (1 + A*t + B*t**2 + C*(t - 100)*t**3)
    else:  # Платина, t >= 0: без члена C
        return R0 * (1 + A*t + B*t**2)


def r_derivative(t, R0, coeffs):
    """Производная dR/dt (Ом/°C) в заданной точке — для пересчёта ΔR ↔ Δt"""
    A, B, C = coeffs
    if B == 0 and C == 0:
        return R0 * A
    if t < 0:
        return R0 * (A + 2*B*t + C*((t - 100)*3*t**2 + t**3))
    return R0 * (A + 2*B*t)


def get_thermo_user(key, r0s, a_s, b_s, c_s):
    """Справочные данные термометра или пользовательская НСХ (строки → float)."""
    if key == "Пользовательская":
        def _f(s):
            val = str(s).strip()
            if not val:
                raise ValueError("Заполните все поля пользовательской НСХ")
            return float(val.replace(",", "."))
        r0 = _f(r0s)
        a = _f(a_s)
        b = _f(b_s)
        c = _f(c_s)
        if r0 <= 0:
            raise ValueError("R0 должен быть больше 0")
        typ = "Cu" if (b == 0 and c == 0) else "Pt"
        return {"R0": r0, "coeffs": (a, b, c), "type": typ}
    if key not in THERMOMETERS:
        raise ValueError("Выберите тип термометра")
    return THERMOMETERS[key]



THERMOCOUPLES = {
    "ТХА (K)": {
        "title": "ТХА (хромель-алюмель, тип K)",
        "t_range": (-200.0, 1372.0),
        "e_range": (-5.891, 54.886),
        "fwd": [
            (0.0, [0.0, 3.94501280250e-2, 2.36223735980e-5, -3.28589067840e-7,
                   -4.99048287770e-9, -6.75090591730e-11, -5.74103274280e-13,
                   -3.10888728940e-15, -1.04516093650e-17, -1.98988668780e-20,
                   -1.63226974860e-23]),
            (1372.0, [-1.7600413686e-2, 3.89212049750e-2, 1.85587700320e-5,
                      -9.94575928740e-8, 3.18409457190e-10, -5.60728448890e-13,
                      5.60750590590e-16, -3.20207200030e-19, 9.71511471520e-23,
                      -1.21047212750e-26]),
        ],
        "fwd_exp": (0.1185976, -0.0001183432, 126.9686),
        "inv": [
            (0.0, [0.0, 2.5173462e1, -1.1662878, -1.0833638, -8.9773540e-1,
                   -3.7342377e-1, -8.6632643e-2, -1.0450598e-2, -5.1920577e-4, 0.0]),
            (20.644, [0.0, 2.508355e1, 7.860106e-2, -2.503131e-1, 8.315270e-2,
                      -1.228034e-2, 9.804036e-4, -4.413030e-5, 1.057734e-6,
                      -1.052755e-8]),
            (54.886, [-1.318058e2, 4.830222e1, -1.646031, 5.464731e-2,
                      -9.650715e-4, 8.802193e-6, -3.110810e-8, 0.0, 0.0, 0.0]),
        ],
    },
    "ТХК (L)": {
        "title": "ТХК (хромель-копель, тип L)",
        "t_range": (-200.0, 800.0),
        "e_range": (-9.488, 66.466),
        "table": [
            (-200, -9.488), (-190, -9.203), (-180, -8.894), (-170, -8.562),
            (-160, -8.207), (-150, -7.831), (-140, -7.433), (-130, -7.014),
            (-120, -6.575), (-110, -6.118), (-100, -5.641), (-90, -5.147),
            (-80, -4.636), (-70, -4.108), (-60, -3.564), (-50, -3.005),
            (-40, -2.431), (-30, -1.843), (-20, -1.242), (-10, -0.627),
            (0, 0.0), (10, 0.639), (20, 1.290), (30, 1.951), (40, 2.624),
            (50, 3.306), (60, 3.999), (70, 4.701), (80, 5.413), (90, 6.133),
            (100, 6.862), (110, 7.599), (120, 8.344), (130, 9.096),
            (140, 9.857), (150, 10.624), (160, 11.398), (170, 12.179),
            (180, 12.967), (190, 13.761), (200, 14.560), (210, 15.366),
            (220, 16.177), (230, 16.994), (240, 17.818), (250, 18.642),
            (260, 19.474), (270, 20.310), (280, 21.150), (290, 21.995),
            (300, 22.843), (310, 23.695), (320, 24.550), (330, 25.409),
            (340, 26.271), (350, 27.135), (360, 28.002), (370, 28.872),
            (380, 29.743), (390, 30.617), (400, 31.492), (410, 32.369),
            (420, 33.247), (430, 34.126), (440, 35.007), (450, 35.888),
            (460, 36.769), (470, 37.652), (480, 38.534), (490, 39.417),
            (500, 40.299), (510, 41.182), (520, 42.064), (530, 42.946),
            (540, 43.828), (550, 44.709), (560, 45.590), (570, 46.471),
            (580, 47.350), (590, 48.230), (600, 49.108), (610, 49.986),
            (620, 50.864), (630, 51.740), (640, 52.617), (650, 53.492),
            (660, 54.367), (670, 55.241), (680, 56.114), (690, 56.987),
            (700, 57.859), (710, 58.729), (720, 59.599), (730, 60.467),
            (740, 61.333), (750, 62.197), (760, 63.058), (770, 63.917),
            (780, 64.771), (790, 65.621), (800, 66.466),
        ],
    },
    "ТПП (S)": {
        "title": "ТПП (платина-родий/платина, тип S)",
        "t_range": (-50.0, 1768.1),
        "e_range": (-0.235, 18.693),
        "fwd": [
            (1064.18, [0.0, 0.540313308631e-2, 0.125934289740e-4, -0.232477968689e-7,
                       0.322028823036e-10, -0.331465196389e-13, 0.255744251786e-16,
                       -0.125068871393e-19, 0.271443176145e-23]),
            (1664.5, [0.132900444085e1, 0.334509311344e-2, 0.654805192818e-5,
                      -0.164856259209e-8, 0.129989605174e-13]),
            (1768.1, [0.146628232636e3, -0.258430516752e0, 0.163693574641e-3,
                      -0.330439046987e-7, -0.943223690612e-14]),
        ],
        "fwd_exp": None,
        "inv": [
            (1.874, [0.0, 1.84949460e2, -8.00504062e1, 1.02237430e2, -1.52248592e2,
                     1.88821343e2, -1.59085941e2, 8.23027880e1, -2.34181944e1,
                     2.79786260e0]),
            (10.332, [1.291507177e1, 1.466298863e2, -1.534713402e1, 3.145945973e0,
                      -4.163257839e-1, 3.187963771e-2, -1.291637500e-3,
                      2.183475087e-5, -1.447379511e-7, 8.211272125e-9]),
            (17.536, [-8.087801117e1, 1.621573104e2, -8.536869453e0, 4.719686976e-1,
                      -1.441693666e-2, 2.081618890e-4]),
            (18.693, [5.333875126e4, -1.235892298e4, 1.092657613e3, -4.265693686e1,
                      6.247205420e-1]),
        ],
    },
}

THERMOCOUPLE_DISPLAY_LIST = list(THERMOCOUPLES.keys())

def tc_poly_eval(coeffs, x):
    """Вычисление полинома sum(c_i * x^i) по схеме Горнера"""
    r = 0.0
    for c in reversed(coeffs):
        r = r * x + c
    return r


def tc_get_spec(key):
    if key not in THERMOCOUPLES:
        raise ValueError("Выберите тип термопары")
    return THERMOCOUPLES[key]


def tc_temp_to_emf(key, t_c):
    """t °C → ЭДС, мВ (НСХ при 0 °C). None — вне диапазона."""
    spec = tc_get_spec(key)
    tmin, tmax = spec["t_range"]
    if t_c < tmin or t_c > tmax:
        return None

    table = spec.get("table")
    if table:
        temps = [p[0] for p in table]
        emfs = [p[1] for p in table]
        if t_c <= temps[0]:
            return emfs[0]
        if t_c >= temps[-1]:
            return emfs[-1]
        i = bisect.bisect_right(temps, t_c) - 1
        t0, e0 = temps[i], emfs[i]
        t1, e1 = temps[i + 1], emfs[i + 1]
        return e0 + (e1 - e0) * (t_c - t0) / (t1 - t0)

    for upper, coeffs in spec["fwd"]:
        if t_c <= upper:
            e = tc_poly_eval(coeffs, t_c)
            exp_terms = spec.get("fwd_exp")
            if exp_terms and upper == tmax:
                a0, a1, a2 = exp_terms
                e += a0 * math.exp(a1 * (t_c - a2) ** 2)
            return e
    return None


def tc_emf_to_temp(key, e_mv):
    """ЭДС, мВ → t °C (НСХ при 0 °C). None — вне диапазона."""
    spec = tc_get_spec(key)
    emin, emax = spec["e_range"]
    if e_mv < emin or e_mv > emax:
        return None

    table = spec.get("table")
    if table:
        temps = [p[0] for p in table]
        emfs = [p[1] for p in table]
        if e_mv <= emfs[0]:
            return temps[0]
        if e_mv >= emfs[-1]:
            return temps[-1]
        i = bisect.bisect_right(emfs, e_mv) - 1
        e0, t0 = emfs[i], temps[i]
        e1, t1 = emfs[i + 1], temps[i + 1]
        return t0 + (t1 - t0) * (e_mv - e0) / (e1 - e0)

    for upper, coeffs in spec["inv"]:
        if e_mv <= upper:
            return tc_poly_eval(coeffs, e_mv)
    return None


def tc_sensitivity(key, t_c):
    """dE/dt, мВ/°C в заданной точке (центральная разность). None — вне диапазона."""
    h = 1.0
    e_hi = tc_temp_to_emf(key, t_c + h)
    e_lo = tc_temp_to_emf(key, t_c - h)
    if e_hi is None or e_lo is None:
        return None
    return (e_hi - e_lo) / (2.0 * h)



UNITS_CALC = {
    'pa': 1, 'kpa': 1000, 'mpa': 1_000_000,
    'bar': 100_000, 'mbar': 100, 'hpa': 100,
    'atm': 101_325, 'kgf_cm2': 98_066.5,
    'kgf_m2': 9.80665, 'mmhg': 133.322,
    'cmhg': 1333.22, 'mh2o': 9_806.65,
    'psi': 6894.76,
}

UNITS_DISPLAY = {
    'Па': 'pa', 'кПа': 'kpa', 'МПа': 'mpa',
    'бар': 'bar', 'мбар': 'mbar', 'гПа': 'hpa',
    'атм': 'atm', 'кгс/см²': 'kgf_cm2',
    'кгс/м²': 'kgf_m2', 'мм рт. ст.': 'mmhg',
    'см рт. ст.': 'cmhg', 'м вод. ст.': 'mh2o',
    'psi': 'psi',
}

UNITS_FULL_NOM = {
    'pa': 'паскаль', 'kpa': 'килопаскаль', 'mpa': 'мегапаскаль',
    'bar': 'бар', 'mbar': 'миллибар', 'hpa': 'гектопаскаль',
    'atm': 'атмосфера', 'kgf_cm2': 'килограмм-сила на квадратный сантиметр',
    'kgf_m2': 'килограмм-сила на квадратный метр', 'mmhg': 'миллиметр ртутного столба',
    'cmhg': 'сантиметр ртутного столба', 'mh2o': 'метр водяного столба',
    'psi': 'фунт-сила на квадратный дюйм',
}


UNITS_FULL_NOM = {
    'pa': 'паскаль', 'kpa': 'килопаскаль', 'mpa': 'мегапаскаль',
    'bar': 'бар', 'mbar': 'миллибар', 'hpa': 'гектопаскаль',
    'atm': 'атмосфера', 'kgf_cm2': 'килограмм-сила на квадратный сантиметр',
    'kgf_m2': 'килограмм-сила на квадратный метр', 'mmhg': 'миллиметр ртутного столба',
    'cmhg': 'сантиметр ртутного столба', 'mh2o': 'метр водяного столба',
    'psi': 'фунт-сила на квадратный дюйм',
}

UNITS_FULL_GEN = {
    'pa': ('паскаля', 'паскалей'), 'kpa': ('килопаскаля', 'килопаскалей'),
    'mpa': ('мегапаскаля', 'мегапаскалей'), 'bar': ('бара', 'баров'),
    'mbar': ('миллибара', 'миллибаров'), 'hpa': ('гектопаскаля', 'гектопаскалей'),
    'atm': ('атмосферы', 'атмосфер'), 'kgf_cm2': ('килограмм-силы на квадратный сантиметр', 'килограмм-сил на квадратный сантиметр'),
    'kgf_m2': ('килограмм-силы на квадратный метр', 'килограмм-сил на квадратный метр'),
    'mmhg': ('миллиметра ртутного столба', 'миллиметров ртутного столба'),
    'cmhg': ('сантиметра ртутного столба', 'сантиметров ртутного столба'),
    'mh2o': ('метра водяного столба', 'метров водяного столба'),
    'psi': ('фунт-силы на квадратный дюйм', 'фунт-сил на квадратный дюйм'),
}


def get_form(value, key):
    n = int(abs(value)) % 100
    if 11 <= n <= 19:
        return UNITS_FULL_GEN[key][1]
    last = n % 10
    if last == 1:
        return UNITS_FULL_GEN[key][0]
    elif 2 <= last <= 4:
        return UNITS_FULL_GEN[key][0]
    else:
        return UNITS_FULL_GEN[key][1]

# --- Конвертация единиц ---
def convert(value, from_u_key, to_u_key):
    pa = value * UNITS_CALC[from_u_key]
    return pa / UNITS_CALC[to_u_key]

# --- Расчёт погрешности ---
def calculate_error(value, span_val, accuracy_val, from_key, to_key):
    try:
        if span_val <= 0 or accuracy_val < 0:
            return None
        abs_error_input = (accuracy_val * span_val) / 100.0
        abs_error_output = convert(abs_error_input, from_key, to_key)
        rel_error = (abs_error_input / value) * 100.0 if value > 0 else 0.0

        from_text_err = f"{abs_error_input:.6f} {get_form(abs_error_input, from_key)}"
        to_text_err = f"{abs_error_output:.6f} {get_form(abs_error_output, to_key)}"

        from_unit_name = [k for k, v in UNITS_DISPLAY.items() if v == from_key][0]

        return (f"\nДиапазон: 0–{span_val:.2f} {from_unit_name}, "
                f"класс точности: {accuracy_val:.2f}%\n"
                f"Допускаемая погрешность: ±{from_text_err} (±{to_text_err})\n"
                f"Относительная погрешность при этом значении: ±{rel_error:.2f}%")
    except Exception:
        return None


# --- Квадратичная зависимость (расход) ---
def calc_quad_flow(flow_pct, flow_max, signal_type, signal_min=4, signal_max=20):
    """
    flow_pct: процент от диапазона (0..100)
    signal_type: 'ma', 'v', '%'
    Возвращает: (расход, перепад, сигнал)
    """
    q = flow_max * (flow_pct / 100.0)
    dp = (q / flow_max) ** 2  # относительный перепад (0..1)

    # сигнал: линейная шкала от min до max
    sig = signal_min + (signal_max - signal_min) * (flow_pct / 100.0)

    return q, dp, sig


# --- Вспомогательная функция: расчёт ожидаемого тока и допуска для одной точки ---
def calc_expected_ma(span_pa, acc_val, pressure_pa, signal_min=4, signal_max=20):
    """
    Возвращает: (expected_ma, delta_ma_allowed)
    """
    if span_pa <= 0:
        raise ValueError("ВПИ должен быть больше 0")
    ratio = pressure_pa / span_pa
    ratio_clamped = max(0.0, min(1.0, ratio))
    expected_ma = signal_min + (signal_max - signal_min) * ratio_clamped

    full_span_ma = signal_max - signal_min
    abs_error_allowed_pa = (acc_val / 100.0) * span_pa
    ma_per_pa = full_span_ma / span_pa
    delta_ma_allowed = abs_error_allowed_pa * ma_per_pa

    return expected_ma, delta_ma_allowed


# --------------------------------------------------------------------------
# Уровень по давлению: справочник плотностей жидкостей и расчёт уровня
# --------------------------------------------------------------------------
GRAVITY_M_S2 = 9.80665  # ускорение свободного падения, м/с²

# Плотность воды, кг/м³, при температурах 0..100 °C (опорные точки для интерполяции)
WATER_DENSITY_TABLE = [
    (0, 999.84), (5, 999.97), (10, 999.70), (15, 999.10), (20, 998.21),
    (25, 997.05), (30, 995.65), (35, 994.03), (40, 992.21), (45, 990.21),
    (50, 988.04), (55, 985.69), (60, 983.20), (65, 980.55), (70, 977.76),
    (75, 974.84), (80, 971.80), (85, 968.61), (90, 965.31), (95, 961.89),
    (100, 958.35),
]

# beta — коэффициент объёмного теплового расширения, 1/°C
LIQUIDS = {
    "вода":                 {"kind": "water",  "rho20": 998.21, "beta": 0.0},
    "нефть":                {"kind": "linear", "rho20": 850.0,  "beta": 0.0008},
    "дизельное топливо":    {"kind": "linear", "rho20": 845.0,  "beta": 0.0008},
    "бензин":               {"kind": "linear", "rho20": 750.0,  "beta": 0.0010},
    "керосин":              {"kind": "linear", "rho20": 800.0,  "beta": 0.0009},
    "спирт этиловый":       {"kind": "linear", "rho20": 789.0,  "beta": 0.0011},
    "молоко":               {"kind": "linear", "rho20": 1030.0, "beta": 0.0005},
    "раствор (ρ вручную)":  {"kind": "manual", "rho20": 1100.0, "beta": 0.0},
    "другое":               {"kind": "manual", "rho20": 1000.0, "beta": 0.0},
}
LIQUID_DISPLAY_LIST = list(LIQUIDS.keys())


def water_density(t_c):
    """Плотность воды при температуре t_c, кг/м³ (линейная интерполяция таблицы)."""
    if t_c <= WATER_DENSITY_TABLE[0][0]:
        return WATER_DENSITY_TABLE[0][1]
    if t_c >= WATER_DENSITY_TABLE[-1][0]:
        return WATER_DENSITY_TABLE[-1][1]
    for i in range(1, len(WATER_DENSITY_TABLE)):
        t1, d1 = WATER_DENSITY_TABLE[i - 1]
        t2, d2 = WATER_DENSITY_TABLE[i]
        if t_c <= t2:
            f = (t_c - t1) / (t2 - t1)
            return d1 + (d2 - d1) * f
    return WATER_DENSITY_TABLE[-1][1]


def liquid_density(media, t_c, rho20_manual=None):
    """Плотность жидкости при температуре t_c, кг/м³.

    Для сред «раствор (ρ вручную)»/«другое» можно передать rho20_manual —
    плотность при 20 °C, заданную пользователем.
    """
    spec = LIQUIDS.get(media)
    if not spec:
        raise ValueError("Неизвестная среда: %s" % media)
    rho20 = rho20_manual if (spec["kind"] == "manual" and rho20_manual) else spec["rho20"]
    if spec["kind"] == "water":
        return water_density(t_c)
    beta = spec["beta"]
    if not beta:
        return rho20
    return rho20 / (1.0 + beta * (t_c - 20.0))


def calc_level(p_eff_pa, rho_kg_m3, g=GRAVITY_M_S2):
    """Высота столба жидкости по гидростатическому давлению, м."""
    if rho_kg_m3 <= 0:
        raise ValueError("Плотность должна быть > 0")
    if p_eff_pa < 0:
        raise ValueError("Эффективное давление не может быть отрицательным")
    return p_eff_pa / (rho_kg_m3 * g)


