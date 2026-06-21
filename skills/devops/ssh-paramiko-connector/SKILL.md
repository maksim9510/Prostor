---
name: ssh-paramiko-connector
description: "Connect to remote hosts via SSH using Paramiko. Supports login/password auth, custom ports, exec and shell modes. Works with Linux/Unix servers and network devices (Eltex, Cisco, etc.)."
version: 1.0.0
author: Prostor
license: MIT
platforms: [linux, macos, windows]
metadata:
  prostor:
    tags: [ssh, paramiko, remote, network, devops, eltex, cisco]
---

# SSH Paramiko Connector

Подключение к удалённым серверам и сетевому оборудованию через SSH с помощью
библиотеки `paramiko`. Поддерживает авторизацию по логину и паролю,
нестандартные порты, два режима работы (exec и shell).

## Предварительные требования

- Python 3.8+
- `paramiko`: `pip install paramiko`

## Параметры

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `hostname` | str | **обязательный** | IP-адрес или домен |
| `port` | int | 22 | Порт SSH (может быть нестандартным) |
| `username` | str | **обязательный** | Логин |
| `password` | str | **обязательный** | Пароль |
| `commands` | list[str] | **обязательный** | Список команд для выполнения |
| `mode` | str | `exec` | `exec` (Linux/Unix) или `shell` (сетевое оборудование) |
| `timeout` | int | 20 | Таймаут подключения в секундах |

## Режимы работы

### exec (по умолчанию)
Для Linux/Unix серверов. Каждая команда выполняется через `exec_command`.
Вывод stdout и stderr раздельно. Подходит для:
- `show run` на ESR (если paging отключён)
- `cat /etc/network/interfaces`
- `systemctl status nginx`

### shell
Для сетевого оборудования (Eltex, Cisco, MikroTik). Открывает интерактивную
shell-сессию через `invoke_shell`. Подходит для:
- `show running-config` с paging
- Команды, требующие enable/privileged mode
- Последовательные команды с зависимостями

## Примеры использования

### Подключение к Linux-серверу на нестандартном порту

```python
from skills.devops.ssh_paramiko_connector import run_ssh_task

result = run_ssh_task(
    hostname="192.168.1.100",
    port=2222,  # нестандартный порт
    username="admin",
    password="secret",
    commands=["uname -a", "df -h", "free -m"],
    mode="exec"
)
```

### Подключение к ESR (сетевое оборудование)

```python
result = run_ssh_task(
    hostname="178.46.134.229",
    port=22,
    username="admin",
    password="password",
    commands=[
        "terminal datadump",  # отключить paging
        "show running-config",
        "show version"
    ],
    mode="shell"  # интерактивный режим для ESR
)
```

### Несколько серверов параллельно

```python
from concurrent.futures import ThreadPoolExecutor

servers = [
    {"hostname": "10.0.0.1", "port": 22, "username": "admin", "password": "pass1"},
    {"hostname": "10.0.0.2", "port": 2222, "username": "root", "password": "pass2"},
    {"hostname": "10.0.0.3", "port": 22, "username": "user", "password": "pass3"},
]

def check_server(srv):
    return run_ssh_task(
        hostname=srv["hostname"],
        port=srv["port"],
        username=srv["username"],
        password=srv["password"],
        commands=["hostname", "uptime", "df -h /"],
        mode="exec"
    )

with ThreadPoolExecutor(max_workers=min(len(servers), 4)) as pool:
    results = list(pool.map(check_server, servers))
```

## Лучшие практики

1. **Сетевое оборудование**: Всегда первой командой отключайте paging
   - Eltex ESR: `terminal datadump`
   - Cisco: `terminal length 0`
   - Juniper: `set cli screen-length 0`

2. **Таймауты**: Увеличьте `timeout` для медленных соединений (спутник, VPN)

3. **Безопасность**: Никогда не хардкодьте credentials в скриптах.
   Передавайте как параметры или читайте из config.yaml / .env

4. **Большие выводы**: Для `show running-config` на сложных устройствах
   увеличьте `time.sleep` в shell-режиме до 5-10 секунд

5. **ANSI-коды**: shell-режим автоматически очищает ANSI escape sequences

## Устранение неполадок

| Ошибка | Решение |
|--------|---------|
| `Authentication failed` | Проверить логин/пароль, убедиться что SSH-доступ разрешён |
| `Connection refused` | Проверить порт, убедиться что SSH-сервер запущен |
| `Connection timed out` | Проверить IP-адрес, firewall, VPN-туннель |
| `Bad host key` | Удалить запись из `~/.ssh/known_hosts` или использовать `AutoAddPolicy` |
| `EOFError` | Устройство закрыло соединение — проверить enable mode |