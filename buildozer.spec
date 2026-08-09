[app]

# Название APK и отображаемое имя приложения
title = КИПиА Калькулятор

package.name = kipiacalc
package.domain = org.kipia

source.dir = .
source.include_exts = py,png,kv,atlas,txt
source.include_globs =

version = 1.0

requirements = python3,kivy==2.3.1

# Порядок экранов: только книжная ориентация — экраны спроектированы вертикально
orientation = portrait
fullscreen = 0

# Иконка приложения (512x512 PNG)
icon.filename = %(source.dir)s/appicon.png

# Android
android.permissions =
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True
android.ndk = 25b
android.minapi = 21
android.api = 33

# Логика приложения не хранит данные на диске, внешний storage не требуется
android.allow_backup = True

# iOS (не используется)
ios.codesign.debug = automatic

[buildozer]

# Многопоточная загрузка SDK/NDK и выходных файлов
log_level = 2
# В контейнере сборка идёт под root — отключаем интерактивный вопрос,
# который падал с EOFError (нет stdin)
warn_on_root = 0