# 🛡️ VLESS Self-Healing Gateway & Checker

Этот проект представляет собой профессиональное решение для создания стабильного, отказоустойчивого VLESS-шлюза. Он автоматически отслеживает доступность соединений, ротирует "умирающие" VLESS-узлы и обеспечивает интеллектуальную маршрутизацию трафика для предотвращения утечек IP.

---

## 🚀 Основные компоненты (Core Components)

### 1. `gateway_manager.py` (Движок самовосстановления)
Основной сервис, который обеспечивает работу вашего соединения 24/7.

- **Асинхронный мониторинг:** Использует `asyncio` для проверки текущего VLESS-выхода каждые 10 секунд с таймаутом 5 секунд.
- **Автоматическая ротация:** Если узел перестает отвечать (timeout или отказ в соединении), система немедленно выбирает следующий лучший узел из пула.
- **Динамический конфиг Xray:** На лету перезаписывает `xray_config.json`, подставляя учетные данные активного узла.
- **Интеллектуальная маршрутизация (Split-Tunneling):** 
  - **Российский трафик:** Направляется напрямую (используя `geoip:ru` и `geosite:ru`), чтобы сервисы видели ваш локальный IP.
  - **Зарубежный трафик:** Направляется через **VLESS-прокси** для скрытия вашего реального IP.
- **Shadowsocks-2022 Inbound:** Предоставляет защищенную точку входа (порт по умолчанию `8388`).

### 2. `checker.py` (Скрапер и монитор здоровья)
- **Скрапинг:** Загружает актуальные VLESS-ключи с GitHub.
- **Проверка доступности ресурсов:** Проверяет работу критически важных сервисов (Telegram, Google и т.д.), чтобы отличить проблемы локальной сети от падения VLESS-узлов.
- **Сортировка по задержке:** Ранжирует рабочие ключи по времени отклика.

---

## 🛠️ Установка и настройка (Installation & Setup)

### 1. Установка Xray-core
На вашем VPS (Ubuntu/Deb Debian):
```bash
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
```

### 2. Конфигурация
1. Убедитесь, что в `docs/keys.json` есть рабочие VLESS-ключи.
2. Настройте `.env` (пароль для Shadowsocks, порты и т.д.).
3. Запустите менеджер: `python3 gateway_manager.py`. Он автоматически создаст `xray_config.json`.

### 3. Запуск как сервис (Production)
Чтобы шлюз работал постоянно и автоматически перезапускался при сбоях, используйте `systemd`.

1. Создайте файл `/etc/systemd/system/vless-gateway.service`:
```ini
[Unit]
Description=VLESS Self-Healing Gateway
After=network.target

[Service]
# Укажите пользователя, от которого работает сервис
User=root
# Укажите полный путь к директории проекта
WorkingDirectory=/home/user/vless-checker
# Укажите полный путь к python3 и вашему скрипту
ExecStart=/usr/bin/python3 /home/user/vless-checker/gateway_manager.py
Restart=always

[Install]
WantedBy=multi-user.target
```

2. Включите и запустите сервис:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vless-gateway
```

### 4. Автоматическое обновление ключей (Checker Timer)
Для автоматического обновления базы ключей каждые 30 минут, настройте `systemd timer`:

1. Создайте `/etc/systemd/system/vless-checker.service`:
```ini
[Unit]
Description=VLESS Key Checker Task
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/home/user/vless-checker
ExecStart=/usr/bin/python3 /home/user/vless-checker/checker.py
StandardOutput=journal
StandardError=journal
```

2. Создайте `/etc/systemd/system/vless-checker.timer`:
```ini
[Unit]
Description=Run VLESS Checker every 30 minutes

[Timer]
OnCalendar=*:0/30
Persistent=true

[Install]
WantedBy=timers.target
```

3. Запустите таймер:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vless-checker.timer
```

---

## ⚙️ Настройка переменных окружения (Environment Variables)

Для гибкой настройки используйте файл `.env`. Создайте его на основе `.env.example`.

| Переменная | Описание | Значение по умолчанию |
| :--- | :--- | :--- |
| `KEYS_JSON_PATH` | Путь к `keys.json` | `docs/keys.json` |
| `XRAY_CONFIG_PATH` | Путь к генерируемому конфигу Xray | `xray_config.json` |
| `CHECK_TIMEOUT` | Таймаут проверки узла (сек) | `5.0` |
| `CHECK_INTERVAL` | Интервал проверки (сек) | `10.0` |
| `SS_INBOUND_PORT` | Порт для Shadowsocks-2022 | `8388` |
| `SS_PASSWORD` | Пароль для Shadowsocks-2022 | `secure_password_123` |
| `SS_METHOD` | Метод шифрования SS | `2022-blake3-aes-128-gcm` |

---

## 📡 Руководство по подключению (Connection Guide)

### 1. Генерация надежного пароля Shadowsocks
Для протокола **Shadowsocks-2022** (`2022-blake3-aes-128-gcm`) требуется ключ длиной 16 байт. Сгенерируйте его через терминал:
```bash
openssl rand -base64 16
```
Добавьте результат в ваш `.env` файл: `SS_PASSWORD=ваш_сгенерированный_ключ`.

### 2. Строки подключения (Connection Strings)

| Протокол | Формат / Пример |
| :--- | :--- |
| **Shadowsocks-2022** | `ss://METHOD:PASSWORD@IP:PORT#NAME` <br> *Пример: `ss://2022-blake3-aes-128-gcm:u6Y%2fR8pWp%2fXmG2z9kLq3A%3D%3D@1.2.3.4:8388#MyGateway` |
| **SOCKS5** | `socks5://127.0.0.1:1080` |

> **Примечание:** Если ваш пароль содержит спецсимволы (например, `/`, `+`, `=`), они должны быть **URL-закодированы** в строке подключения (например, `/` $\rightarrow$ `%2F`). Большинство современных клиентов (Nekoray, Shadowrocket) делают это автоматически, если вы просто вставляете "сырой" пароль.

---

## ⚠️ Решение проблем (Troubleshooting)

| Проблема | Вероятная причина | Решение |
| :--- | :--- | :--- |
| **Таймаут соединения** | **Блокировка DPI** | Используйте `VLESS + Reality` или `Shadowsocks-2022` с включенным `xtls-rprx-vision`. |
| **Низкая скорость / Лаги** | **Проблемы с MTU** | Попробуйте уменьшить MTU на клиенте (например, до `1280` или `1350`). |
| **Конфликт портов** | **Порт занят** | Проверьте: `sudo netstat -tulpn \| grep LISTEN`. Измените порты в `.env`. |
| **Сайты РФ через VPN** | **Ошибка маршрутизации** | Убедитесь, что правила `geoip:ru` стоят **выше** общего правила `proxy` в конфиге. |
| **Ошибка Permission Denied в логах** | **Права доступа к файлам** | Мы перешли на логирование через `stdout`. Теперь логи смотрятся через `journalctl -u vless-gateway`. |

---

## 📂 Структура проекта (Project Structure)
- `gateway_manager.py` - Основной сервис ротации и мониторинга.
- `checker.py` - Скрипт скрапинга и проверки доступности сервисов.
- `docs/keys.json` - База данных узлов.
- `.env.example` - Шаблон переменных окружения.
- `xray_config.json` - (Генерируется) Активный конфиг Xray.
