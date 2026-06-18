# Future Live Race Mode

Идея режима:

1. Вход: поток событий гонки или ручные заметки админов.
2. Бот превращает событие в короткий live-комментарий.
3. Для risky-событий бот отправляет черновик в review.
4. Для безопасных low-stakes событий можно включить auto publish.

Примеры входа:

```text
LAP 18: Safety Car, debris in sector 2.
LAP 24: Norris under investigation for track limits.
LAP 42: Rain expected in 8 minutes.
```

Желаемое поведение:

- быстро;
- не длиннее обычного live-поста;
- без уверенного вранья;
- с реакцией, но без истерики на каждый чих.
