# -*- coding: utf-8 -*-
"""Генерация тематического логотипа (манометр) для меню приложения."""
from PIL import Image, ImageDraw, ImageFont
import math

S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

cx, cy = S / 2.0, S / 2.0
R = 236

# внешнее синее кольцо (#2563eb) с белой окантовкой
d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=(37, 99, 235, 255))
d.ellipse([cx - R + 8, cy - R + 8, cx + R - 8, cy + R - 8], fill=(255, 255, 255, 255))

# циферблат
Rd = R - 40
d.ellipse([cx - Rd, cy - Rd, cx + Rd, cy + Rd],
          fill=(247, 249, 252, 255), outline=(203, 213, 225, 255), width=3)

# деления шкалы: -90..+90 град (манометр, 0..100%)
for i in range(41):
    ang = -90 + i * 4.5
    rad = math.radians(ang)
    long_tick = i % 10 == 0
    h1 = Rd - (34 if long_tick else 22)
    h2 = Rd - (22 if long_tick else 15)
    w = 6 if long_tick else 3
    d.line([cx + h1 * math.cos(rad), cy + h1 * math.sin(rad),
            cx + h2 * math.cos(rad), cy + h2 * math.sin(rad)],
           fill=(51, 65, 85, 255), width=w)

# красная зона 80..100% (дуга-сектор у края циферблата)
for i in range(16, 21):
    a0 = math.radians(-90 + i * 4.5)
    a1 = math.radians(-90 + (i + 1) * 4.5)
    pts = []
    r0 = Rd - 14
    for t in range(0, 11):
        ang = a0 + (a1 - a0) * t / 10.0
        pts.append((cx + r0 * math.cos(ang), cy + r0 * math.sin(ang)))
    for t in range(10, -1, -1):
        ang = a0 + (a1 - a0) * t / 10.0
        pts.append((cx + (Rd - 46) * math.cos(ang), cy + (Rd - 46) * math.sin(ang)))
    d.polygon(pts, fill=(220, 38, 38, 255))

# центральная ось и стрелка (на ~40%)
needle_ang = math.radians(-90 + 40.5)
nl = Rd - 70
d.line([cx, cy, cx + nl * math.cos(needle_ang), cy + nl * math.sin(needle_ang)],
       fill=(217, 119, 6, 255), width=10)
d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14],
          fill=(37, 99, 235, 255), outline=(255, 255, 255, 255), width=4)

# текст внизу: КИПиА
try:
    f = ImageFont.truetype("arialbd.ttf", 62)
except Exception:
    f = ImageFont.load_default()
txt = "КИПиА"
d.text((cx, cy + R - 62), txt, font=f, fill=(23, 37, 84, 255), anchor="mm")

img.save("logo_gauge.png")
print("saved logo_gauge.png", img.size)