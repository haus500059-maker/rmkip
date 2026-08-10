[app]

# Название APK и отображаемое имя приложения
title = РМ: КИПиА

package.name = kipiacalc
package.domain = org.kipia

source.dir = .
source.include_exts = py,png,kv,atlas,txt
source.include_globs =

version = 1.0

requirements = python3,kivy==2.3.1

# Порядок экранов: только книжная ориентация — экраны спроектированы вертикально
orientation = portrait
# Полноэкранный режим: приложение рисует на весь экран, системные панели скрыты.
# Безопасные отступы под вырез камеры и жесты добавляются в main.py.
fullscreen = 1

# Иконка приложения (512x512 PNG)
icon.filename = %(source.dir)s/appicon.png

# Android
android.permissions =
# Только arm64-v8a: повторное использование venv между двумя arch ломает pip
# (баг python-for-android #3339), второй проход падал с ImportError в pip.
android.archs = arm64-v8a
android.accept_sdk_license = True
android.ndk = 25b
android.minapi = 21
android.api = 33
# Разрешить приложению рисовать в область выреза дисплея (камера/отверстие) на API 28+
android.display_cutout = shortEdges

# Логика приложения не хранит данные на диске, внешний storage не требуется
android.allow_backup = True

# Формат release-сборки: APK (подписанный) — подходит для RuStore и прямой
# установки. Для Google Play при необходимости меняйте на aab.
android.release_artifact = apk

# iOS (не используется)
ios.codesign.debug = automatic

[buildozer]

# Многопоточная загрузка SDK/NDK и выходных файлов
log_level = 2
# В контейнере сборка идёт под root — отключаем интерактивный вопрос,
# который падал с EOFError (нет stdin)
warn_on_root = 0