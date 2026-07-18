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
- **Multi-Client Support:** Поддержка нескольких клиентов с уникальными UUID в режиме `multi`.

### 2. `checker.py` (Скрапер и монитор здоровья)
- **Скрапинг:** Загружает актуальные VLESS-ключи с GitHub.
- **Проверка доступности ресурсов:** Проверяет работу критически важных сервисов (Telegram, Google и т.д.), чтобы отличить проблемы локальной сети от падения VLESS-узлов.
- **Сортировка по задержке:** Ранжирует рабочие ключи по времени отклика.

---

## 🛠️ Установка и настройка (Installation & Setup)

### 1. Установка Xray-core
На вашем VPS (Ubuntu/Debian):
```bash
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
```

### 2. Конфигурация

#### Способ 1: Одиночный ключ (Single Mode - по умолчанию)
1. Убедитесь, что в `docs/keys.json` есть рабочие VLESS-ключи.
2. Настройте `.env` (пароль для Shadowsocks, порты и т.д.).
3. Запустите менеджер: `python3 gateway_manager.py`. Он автоматически создаст `xray_config.json`.

#### Способ 2: Мульти-клиент (Multi Mode)
Для одновременной работы нескольких клиентов с уникальными UUID:

1. Создайте `.env` файл со следующими настройками:
```env
GATEWAY_MODE=multi
CLIENT_UUIDS=uuid1,uuid2,uuid3
CLIENT_KEYS=key1,key2,key3
```

2. Сгенерируйте UUID для каждого клиента:
```bash
python3 -c "import uuid; print(uuid.uuid4())"
```

3. Поместите рабочие VLESS-ключи в `CLIENT_KEYS` (количество должно совпадать с UUID).

4. Запустите менеджер: `python3 gateway_manager.py`.

**Особенности Multi Mode:**
- Все клиенты подключены одновременно
- Каждый клиент имеет свой уникальный UUID
- Xray использует routing rules для маршрутизации трафика
- Нет ротации ключей (все узлы работают параллельно)

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
| `XRAY_CONFIG_PATH` | Путь к генерируемому конфигу Xray | `/usr/local/etc/xray/config.json` |
| `CHECK_TIMEOUT` | Таймаут проверки узла (сек) | `5.0` |
| `CHECK_INTERVAL` | Интервал проверки (сек) | `10.0` |
| `SS_INBOUND_PORT` | Порт для Shadowsocks-2022 | `8388` |
| `SS_PASSWORD` | Пароль для Shadowsocks-2022 | `secure_password_123` |
| `SS_METHOD` | Метод шифрования SS | `2022-blake3-aes-128-gcm` |
| `GATEWAY_MODE` | Режим работы: `single` или `multi` | `single` |
| `XRAY_OUTBOUND_NETWORK` | Тип сети для outbound: `tcp`, `xhttp`, `ws` | `tcp` |
| `XRAY_SECURITY` | Тип безопасности: `tls`, `reality`, `none` | `tls` |
| `CLIENT_UUIDS` | UUID клиентов (через запятую) | - |
| `CLIENT_KEYS` | VLESS ключи клиентов (через запятую) | - |

### Multi-Client Настройка

| Переменная | Описание | Пример |
| :--- | :--- | :--- |
| `GATEWAY_MODE` | Режим multi-клиента | `multi` |
| `CLIENT_UUIDS` | UUID через запятую | `uuid1,uuid2,uuid3` |
| `CLIENT_KEYS` | VLESS ключи через запятую | `key1,key2,key3` |

**Примечание:** Количество UUID должно совпадать с количеством ключей!

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
| **Multi mode не подключаются клиенты** | **Несовпадение UUID и ключей** | Проверьте, что количество UUID в `CLIENT_UUIDS` совпадает с количеством ключей в `CLIENT_KEYS`. |
| **Множество "rotation failed"** | **Все ключи мертвы** | Проверьте доступность ключей через `checker.py` или обновите `docs/keys.json`. |

---

## 🔴 Утечка IP-адреса (IP Leak) - Цепочка VLESS

### Проблема утечки IP при цепочке

Если вы используете **цепочку VLESS** (Клиент → VPS в Нидерландах → Второй VLESS), ваш реальный IP может утечь из-за:

1. **IPv6 трафика** - Трафик по IPv6 идет в обход VPN
2. **Некорректная маршрутизация** - Трафик сбрасывается в `freedom` вместо цепочки
3. **DNS утечка** - DNS-запросы идут локальному провайдеру

### Решение 1: Блокировка IPv6

Включите блокировку IPv6 в вашем `.env` файле:

```env
ENABLE_IPV6_BLOCK=true
```

Это направит весь IPv6 трафик в черную дыру (`blackhole`), предотвращая утечку.

### Решение 2: Цепочковая маршрутизация

Настройте **Chain VLESS** в вашем `.env` файле:

```env
# Входящий VLESS ключ (от клиента к вашему VPS)
CLIENT_KEYS=vless://...your_vless_key...

# Цепочковый VLESS ключ (от вашего VPS к второму серверу)
CHAIN_VLESS_KEY=vless://...your_chain_vless_key...
CHAIN_OUTBOUND_TAG=chain-vless-out
```

Это создаст явное правило маршрутизации: весь входящий трафик направляется в цепочку.

### Решение 3: Cloudflare WARP для ChatGPT

Установите Cloudflare WARP на VPS и настройте прокси:

```bash
warp-cli mode proxy
warp-cli connect
```

Затем в `.env` добавьте:

```env
WARP_SOCKS_PORT=40000
WARP_DOMAINS=openai.com,chatgpt.com,ai.com
```

Трафик к ChatGPT будет идти через WARP, скрывая IP VPS.

### Проверка утечек

Проверьте свой IP на [ipleak.net](https://ipleak.net):

- Если видите IPv6 - включите `ENABLE_IPV6_BLOCK=true`
- Если видите ваш реальный IP - проверьте настройки `CHAIN_VLESS_KEY`

---

## 📂 Структура проекта (Project Structure)

## 📂 Структура проекта (Project Structure)
- `gateway_manager.py` - Основной сервис ротации и мониторинга.
- `checker.py` - Скрипт скрапинга и проверки доступности сервисов.
- `docs/keys.json` - База данных узлов.
- `.env.example` - Шаблон переменных окружения.
- `.env` - (Создается) Переменные окружения для конфигурации.
- `xray_config.json` - (Генерируется) Активный конфиг Xray.
- `vless-gateway.service` - Systemd service для запуска.
- `vless-checker.timer` - Systemd timer для обновления ключей.

---

## 🔐 Безопасность (Security)

1. **Храните `.env` в секрете:** Не публикуйте файл `.env` в репозитории.
2. **Используйте UUID4 для клиентов:** Генерируйте уникальные UUID для каждого клиента.
3. **Периодическая смена паролей:** Обновляйте пароли Shadowsocks регулярно.
4. **Проверка целостности:** Используйте `checker.py` для регулярной проверки рабочих ключей.

---

## 📡 Генерация ключей Outline (Outline Key Generation)

### Использование функции `generate_shadowsocks_key()`

В [`gateway_manager.py`](gateway_manager.py:1) есть две функции для генерации Shadowsocks ссылок:

#### 1. `generate_shadowsocks_key(ss_method=None, ss_password=None)`
Генерирует ключ, используя параметры из `.env` файла.

#### 2. `generate_shadowsocks_key_with_params(ss_method, ss_password, vps_ip, ss_port)`
Генерирует ключ с пользовательскими параметрами.

### Пример использования

```python
from gateway_manager import generate_shadowsocks_key, generate_shadowsocks_key_with_params

# Используя параметры из .env
ss_link = generate_shadowsocks_key()
print(ss_link)
# Вывод: ss://YWVzLTI1Ni1nY206c2VjdXJlX3Bhc3N3b3Jk@123.456.789.0:443#MyVLESSRotator

# С пользовательскими параметрами
ss_link = generate_shadowsocks_key_with_params(
    ss_method="aes-256-gcm",
    ss_password="my_strong_password",
    vps_ip="192.168.1.100",
    ss_port=443
)
print(ss_link)
# Вывод: ss://YWVzLTI1Ni1nY206bXlfc3Ryb25nX3Bhc3N3b3Jk@192.168.1.100:443#MyVLESSRotator
```

### Ручная генерация (для справки)

Outline принимает конфигурацию в виде специальной ссылки, которая кодируется в формат Base64.

1. **Объедините метод и пароль:**
   ```
   aes-256-gcm:your_strong_password
   ```

2. **Закодируйте в Base64:**
   ```bash
   echo -n "aes-256-gcm:your_strong_password" | base64
   # Вывод: YWVzLTI1Ni1nY206eW91cl9zdHJvbmdfcGFzc3dvcmQ=
   ```

3. **Сформируйте ссылку:**
   ```
   ss://YWVzLTI1Ni1nY206eW91cl9zdHJvbmdfcGFzc3dvcmQ=@192.168.1.100:443#MyVLESSRotator
   ```

### Настройка в `.env`

Для автоматической генерации добавьте в `.env`:

```env
SS_VPS_IP=ВАШ_VPS_IP_АДРЕС
SS_OUTBOUND_PORT=443
SS_PASSWORD=ваш_пароль
SS_METHOD=aes-256-gcm
```

> **Важно:** `SS_VPS_IP` должен быть вашим реальным публичным IP-адресом VPS.

---

## � Примеры конфигурации

### Пример 1: Single Mode (один ключ)
```env
KEYS_JSON_PATH=docs/keys.json
SS_INBOUND_PORT=8388
SS_PASSWORD=secure_password_123
```

### Пример 2: Multi Mode (несколько клиентов)
```env
GATEWAY_MODE=multi
SS_INBOUND_PORT=8388
SS_PASSWORD=secure_password_123
CLIENT_UUIDS=4b056394-2f40-11f1-bffe-46c4782ac1a7,58be4691-5430-417a-96e3-02736d151490
CLIENT_KEYS=vless://4b056394-2f40-11f1-bffe-46c4782ac1a7@77.233.215.78:443?security=tls&encryption=none&flow=xtls-rprx-vision&sni=example.com,vless://58be4691-5430-417a-96e3-02736d151490@77.233.215.78:443?security=tls&encryption=none&flow=xtls-rprx-vision&sni=example.com
```

### Пример 3: With Reality Protocol
```env
GATEWAY_MODE=single
XRAY_SECURITY=reality
XRAY_OUTBOUND_NETWORK=tcp
CLIENT_UUIDS=
CLIENT_KEYS=
```

### Пример 4: Single Mode с сервером 77.233.215.78
```env
SS_INBOUND_PORT=8388
SS_PASSWORD=secure_password_123
CLIENT_KEYS=vless://4b056394-2f40-11f1-bffe-46c4782ac1a7@77.233.215.78:443?security=tls&encryption=none&flow=xtls-rprx-vision&sni=example.com
```

### Пример 5: Chain VLESS с блокировкой IPv6
Для настройки **цепочки VLESS** (Клиент → VPS в Нидерландах → Второй VLESS):

```env
# Входящий VLESS ключ (от клиента к вашему VPS)
CLIENT_KEYS=vless://4b056394-2f40-11f1-bffe-46c4782ac1a7@77.233.215.78:443?security=tls&encryption=none&flow=xtls-rprx-vision&sni=example.com

# Цепочковый VLESS ключ (от вашего VPS к второму серверу)
CHAIN_VLESS_KEY=vless://58be4691-5430-417a-96e3-02736d151490@de1.linkto.sbs:443?security=tls&encryption=none&flow=xtls-rprx-vision&sni=de1.linkto.sbs

# Блокировка IPv6 для предотвращения утечек
ENABLE_IPV6_BLOCK=true

# Тег outbound для цепочки
CHAIN_OUTBOUND_TAG=chain-vless-out
```

### Пример 6: Chain VLESS с WARP для ChatGPT
Настройка цепочки + WARP прокси для доступа к ChatGPT:

```env
# Входящий VLESS ключ
CLIENT_KEYS=vless://4b056394-2f40-11f1-bffe-46c4782ac1a7@77.233.215.78:443?security=tls&encryption=none&flow=xtls-rprx-vision&sni=example.com

# Цепочковый VLESS ключ
CHAIN_VLESS_KEY=vless://58be4691-5430-417a-96e3-02736d151490@de1.linkto.sbs:443?security=tls&encryption=none&flow=xtls-rprx-vision&sni=de1.linkto.sbs

# Блокировка IPv6
ENABLE_IPV6_BLOCK=true

# WARP прокси для ChatGPT
WARP_SOCKS_PORT=40000
WARP_DOMAINS=openai.com,chatgpt.com,ai.com
```

> **Важно:** WARP должен быть запущен на VPS в режиме прокси (`warp-cli mode proxy`) перед использованием.

---

## 🆘 Поддержка (Support)

Если у вас возникли проблемы с проектом:
1. Проверьте логи: `journalctl -u vless-gateway -f`
2. Проверьте конфигурацию в `xray_config.json`
3. Убедитесь, что ключи работают через `checker.py`
4. Проверьте права доступа к файлам

---

*Последнее обновление: 2026-07-15*
