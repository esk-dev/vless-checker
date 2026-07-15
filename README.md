# 🛡️ VLESS Self-Healing Gateway & Checker

This project provides a professional-grade solution for maintaining a stable, high-availability VLESS proxy gateway. It is designed to automatically monitor connectivity, rotate "dead" VLESS nodes, and ensure intelligent traffic routing to prevent IP leaks.

---

## 🛠️ Установка и настройка (Installation & Setup)

### 1. Установка Xray-core
Для работы шлюза на вашем VPS необходимо установить ядро Xray.

**Для Ubuntu/Debian:**
```bash
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
```

### 2. Настройка базовых ключей
Скрипт `gateway_manager.py` полностью берет на себя генерацию конфига. Вам нужно только:
1. Убедиться, что в `docs/keys.json` есть рабочие ключи.
2. Настроить `.env` (пароль для Shadowsocks и т.д.).
3. Запустить `gateway_manager.py`. Он сам создаст `xray_config.json`.

### 3. Как составить ключ подключения (Connection Strings)

Для подключения ваших клиентов используйте следующие форматы:

#### **Shadowsocks-2022 (Рекомендуется)**
Если вы используете Shadowsocks-inbound, ключ будет выглядеть так:
`ss://method:password@IP:PORT#Name`
*Пример:* `ss://2022-blake3-aes-128-gcm:your_password@1.2.3.4:8388#MyGateway`

#### **VLESS (через шлюз)**
Вы можете использовать любые VLESS ключи из вашего пула, но помните, что шлюз работает как прокси. Если вы хотите подключиться к самому шлюзу, используйте его SOCKS5 порт:
`socks5://127.0.0.1:1080` (для локальных тестов).

---

## ⚠️ Решение типичных проблем (Troubleshooting)

| Проблема | Причина | Решение |
| :--- | :--- | :--- |
| **Не работает подключение (Timeout)** | **Блокировка DPI** (Deep Packet Inspection) | Используйте протоколы с маскировкой, такие как `VLESS + Reality` или `Shadowsocks-2022`. Убедитесь, что в `gateway_manager.py` включен `xtls-rprx-vision`. |
| **Низкая скорость / Задержки** | **Проблема MTU** | Если пакеты дропаются, попробуйте уменьшить MTU в настройках сетевого интерфейса клиента (например, до `1280` или `1350`). |
| **Порт занят (Address already in use)** | **Конфликт портов** | Проверьте, не запущен ли другой Xray или сервис на порту `1080` или `8388`. Используйте `sudo netstat -tulpn | grep LISTEN`. |
| **Сайты РФ открываются через VPN** | **Ошибка маршрутизации** | Проверьте, что в `xray_config.json` правила `geoip:ru` и `geosite:ru` стоят **выше** общего правила `proxy`. |
| **Порт закрыт провайдером** | **Блокировка портов** | Попробуйте сменить стандартный порт `8388` на какой-нибудь нестандартный (например, в диапазоне `40000-50000`). |

---

## 🚀 Core Components

### 1. `gateway_manager.py` (The Self-Healing Engine)
This is the main service that keeps your connection alive 24/7.

**Key Features:**
- **Asynchronous Monitoring:** Uses `asyncio` to check the current VLESS outbound every 10 seconds with a strict 5s timeout.
- **Automatic Rotation:** If the current node fails (timeout or connection refused), the system immediately selects the next best node from the pool.
- **Dynamic Xray Config:** Automatically rewrites `xray_config.json` with the new node's credentials.
- **Intelligent Routing (Split-Tunneling):** 
  - **Russian Traffic:** Uses `geoip:ru` and `geosite:ru` to route traffic **directly**, ensuring Russian services see your local IP.
  - **International Traffic:** Routes everything else through the **VLESS proxy**, hiding your original IP.
- **Shadowsocks-2022 Inbound:** Provides a high-security Shadowsocks-2022 entry point (default port `8388`) for your clients.

### 2. `checker.py` (The Scraper & Health Monitor)
A utility to find new VLESS keys and verify the general health of the internet environment.

**Key Features:**
- **Scraping:** Fetches the latest VLESS keys from GitHub.
- **Resource Health Check:** Before checking keys, it verifies the availability of critical services (Telegram, Google, Instagram, Microsoft, etc.) to distinguish between a local network issue and a VLESS node failure.
- **Latency Sorting:** Sorts working keys by response time for optimal performance.

---

## 🛠️ Installation & Setup

### Prerequisites
- Python 3.8+
- [Xray-core](https://github.com/XTLS/Xray-core) installed on your system.
- `systemd` (for running as a service).

### 1. Clone & Install
```bash
git clone <your-repo-url>
cd vless-checker
pip install requests python-dotenv
```

### 2. Configuration
Copy the example environment file and edit it:
```bash
cp .env.example .env
```
Edit `.env` to set your preferred Shadowsocks password and ports.

### 3. Running the Gateway
For testing:
```bash
python3 gateway_manager.py
```

**For Production (Systemd):**
Create a file `/etc/systemd/system/vless-gateway.service`:
```ini
[Unit]
Description=VLESS Self-Healing Gateway
After=network.target

[Service]
User=root
WorkingDirectory=/home/user/vless-checker
ExecStart=/usr/bin/python3 gateway_manager.py
Restart=always

[Install]
WantedBy=multi-user.target
```
Then run:
```bash
sudo systemctl enable --now vless-gateway
```

---

## 📡 Client Connection

Once the gateway is running, you can connect using:

| Protocol | Address | Port | Auth/Password |
| :--- | :--- | :--- | :--- |
| **SOCKS5** | `127.0.0.1` | `1080` | None |
| **Shadowsocks-2022** | `127.0.0.1` | `8388` | (From your `.env`) |

---

## 📂 Project Structure
- `gateway_manager.py` - The core monitoring and rotation service.
- `checker.py` - Scraper and connectivity health check tool.
- `docs/keys.json` - The database of available VLESS nodes.
- `.env.example` - Template for environment variables.
- `xray_config.json` - (Generated) The active Xray configuration.
- `gateway_manager.log` - Logs for the gateway service.
