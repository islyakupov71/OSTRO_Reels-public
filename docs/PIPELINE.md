# Манифест и воспроизводимость

За основу нового выпуска возьмите `episodes/demo/episode.json`.
Каждый выпуск должен иметь свой ID и отдельную папку.

`actors` задаёт ID участника, ключ персонажа из `registry/characters.json`
и позицию `[x,y,z]`. `lines` содержит ID реплики, speaker и text.
`spoken_text` может отличаться от экранного text. `scenes` содержит
template (studio, conference, arena) и anchor (opening или ID реплики).
`camera` содержит position, look_at и scale. Настройки вывода — fps,
width и height; паузы — opening_silence, ending_silence и gap_after.

Собственная готовая запись задаётся явным `cached_audio` относительно корня
проекта. `cached_alignment` может ссылаться на JSON с characters,
character_start_times_seconds и character_end_times_seconds внутри alignment.
Не добавляйте частные записи в Git. В демо тишина создаётся setup_demo.py.

Настройки собственного голоса храните в `.local/voices.json`:

```json
{
  "demo-host": {
    "name": "Local voice",
    "voice_id": "",
    "status": "not_configured",
    "samples_dir": "voices/inbox/demo-host",
    "method": "not_configured"
  }
}
```

Заполните voice_id только локально и установите status=ready, когда права
на голос подтверждены. Публичный registry содержит только пустую заглушку.
Команда voices clone требует явного подтверждения согласия владельца и
ссылки на локальную запись согласия; результат записывается только в .local.
Повтор после сетевого таймаута делайте после проверки аккаунта, чтобы
не создавать дубликат голоса. Демо ничего не клонирует.

Таймлайн — `build/<id>/timeline.json`, метрики этапов — run.json.
Аудиокеш использует SHA-256 запроса и ID голоса и хранится в .local.
Состояние объектов вычисляется из t. Для проверки перемотки запустите Blender
с сохранённой сценой и `--python tools/check_determinism.py`.
Не запускайте одновременно две сборки одного ID.

GLB-робот генерируется локально. Сцены .blend содержат пути текущей машины,
поэтому они, build, .local, reports и voices исключены из Git и не входят
в публичный исходный код. Не переносите туда производственные эпизоды.
