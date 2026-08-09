# Сборка APK через GitHub Actions

Приложение собирается автоматически на GitHub Actions (buildozer не работает на Windows).

## 1. Создать пустой репозиторий

На https://github.com/new: имя любое (например `kipiacalc`), **не** добавлять README/`.gitignore`/лицензию,
нажать **Create repository**.

## 2. Загрузить код

Откройте `kivy_app` как корень репозитория и запушьте его содержимое
(`main.py`, `core.py`, `buildozer.spec`, `appicon.png`, `.github/`, `.gitignore`).

```bash
cd kivy_app
git init
git add .
git commit -m "KIPiA Kalkulyator - Kivy app"
git branch -M main
git remote add origin https://github.com/<USER>/<REPO>.git
git push -u origin main
```

При push Windows спросит логин/пароль GitHub — подойдёт Personal Access Token
(Settings → Developer settings → Tokens → галочки `repo` и `workflow`).

## 3. Запустить сборку

- **Автоматически**: после `push` в ветку `main` workflow `Build APK` запустится сам.
- **Вручную**: вкладка **Actions → Build APK → Run workflow**.

Сборка занимает ~1 час (первый раз — загрузка Android SDK/NDK).

## 4. Скачать APK

**Actions → Build APK → последний запуск → Artifacts → `kipiacalc-debug-apk`**.
Выгрузите `bin/*.apk` и установите на телефон (включите «Установка из неизвестных источников»).

## Важно

- APK подписан debug-ключом — для Google Play нужна release-сборка (см. `android.release_artifacts` в buildozer.spec).
- Проверка работоспособности перед каждым коммитом:
  `python test_desktop.py` → в `desktop_test_log.txt` должно быть 25 × `PASS` и `DONE`.