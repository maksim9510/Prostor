#!/usr/bin/env python3
"""
SSH Paramiko Connector — подключение к удалённым хостам через SSH.

Поддержка:
- Логин/пароль авторизация
- Нестандартные порты (не только 22)
- exec режим (Linux/Unix — раздельный stdout/stderr)
- shell режим (сетевое оборудование — Eltex, Cisco, MikroTik)
- ANSI cleanup для shell-вывода
- Параллельное подключение к нескольким хостам
"""

import logging
import re
import time
from typing import Any

logger = logging.getLogger(__name__)


def clean_ansi(text: str) -> str:
    """Удаляет ANSI escape sequences из вывода shell."""
    return re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', text)


def run_ssh_task(
    hostname: str,
    port: int = 22,
    username: str = "",
    password: str = "",
    commands: list[str] = None,
    mode: str = "exec",
    timeout: int = 20,
    shell_wait: float = 3.0,
) -> list[dict[str, Any]] | str:
    """Выполнить команды на удалённом хосте через SSH.

    Args:
        hostname: IP-адрес или домен
        port: SSH порт (по умолчанию 22, может быть нестандартным)
        username: Логин
        password: Пароль
        commands: Список команд для выполнения
        mode: 'exec' (Linux/Unix) или 'shell' (сетевое оборудование)
        timeout: Таймаут подключения в секундах
        shell_wait: Время ожидания вывода в shell-режиме (секунды)

    Returns:
        Список словарей {cmd, out, err} при успехе,
        или строку с ошибкой при неудаче.
    """
    if commands is None:
        commands = []

    try:
        import paramiko
    except ImportError:
        return "Error: paramiko not installed. Run: pip install paramiko"

    if not hostname or not username or not password:
        return "Error: hostname, username, and password are required"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        logger.info(
            "SSH connecting: %s@%s:%d (mode=%s, timeout=%ds)",
            username, hostname, int(port), mode, timeout,
        )
        client.connect(
            hostname=hostname,
            port=int(port),
            username=username,
            password=password,
            timeout=timeout,
            allow_agent=False,
            look_for_keys=False,
        )

        output_data: list[dict[str, Any]] = []

        if mode == "exec":
            for cmd in commands:
                stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
                out = stdout.read().decode("utf-8", errors="ignore")
                err = stderr.read().decode("utf-8", errors="ignore")
                output_data.append({
                    "cmd": cmd,
                    "out": out,
                    "err": err,
                })
        elif mode == "shell":
            shell = client.invoke_shell()
            time.sleep(2)
            # Clear initial buffer (banner, MOTD)
            try:
                shell.recv(10000)
            except Exception:
                pass

            for cmd in commands:
                shell.send(cmd + "\n")
                time.sleep(shell_wait)
                chunk = ""
                # Read all available data
                while shell.recv_ready():
                    chunk += shell.recv(10000).decode("utf-8", errors="ignore")
                    time.sleep(0.5)
                # Also check if more data is coming
                if not chunk:
                    time.sleep(shell_wait)
                    while shell.recv_ready():
                        chunk += shell.recv(10000).decode("utf-8", errors="ignore")
                        time.sleep(0.5)
                output_data.append({
                    "cmd": cmd,
                    "out": clean_ansi(chunk),
                    "err": "",
                })
        else:
            return f"Error: unknown mode '{mode}'. Use 'exec' or 'shell'."

        client.close()
        logger.info("SSH task completed: %d commands on %s:%d", len(output_data), hostname, port)
        return output_data

    except paramiko.AuthenticationException:
        return f"Error: Authentication failed for {username}@{hostname}:{port}"
    except paramiko.SSHException as e:
        return f"SSH Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"


def run_ssh_batch(
    hosts: list[dict[str, Any]],
    max_workers: int = 4,
) -> list[dict[str, Any]]:
    """Параллельное SSH-подключение к нескольким хостам.

    Args:
        hosts: Список конфигураций хостов, каждый с:
            - hostname (str, required)
            - port (int, default 22)
            - username (str, required)
            - password (str, required)
            - commands (list[str], required)
            - mode (str, default 'exec')
            - timeout (int, default 20)
        max_workers: Максимальное количество параллельных подключений

    Returns:
        Список результатов: {host, success, data/error}
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _execute(host_config: dict[str, Any]) -> dict[str, Any]:
        hostname = host_config.get("hostname", "")
        try:
            result = run_ssh_task(
                hostname=hostname,
                port=host_config.get("port", 22),
                username=host_config.get("username", ""),
                password=host_config.get("password", ""),
                commands=host_config.get("commands", []),
                mode=host_config.get("mode", "exec"),
                timeout=host_config.get("timeout", 20),
                shell_wait=host_config.get("shell_wait", 3.0),
            )
            if isinstance(result, str) and result.startswith("Error"):
                return {"host": hostname, "success": False, "error": result}
            return {"host": hostname, "success": True, "data": result}
        except Exception as e:
            return {"host": hostname, "success": False, "error": str(e)}

    # Auto-detect workers based on host count
    workers = min(max_workers, len(hosts), 4)  # cap at 4 parallel SSH
    results: list[dict[str, Any]] = [None] * len(hosts)

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ssh_batch") as executor:
        future_to_idx = {
            executor.submit(_execute, host): i
            for i, host in enumerate(hosts)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                results[idx] = {
                    "host": hosts[idx].get("hostname", ""),
                    "success": False,
                    "error": str(e),
                }

    return results


__all__ = [
    "run_ssh_task",
    "run_ssh_batch",
    "clean_ansi",
]
