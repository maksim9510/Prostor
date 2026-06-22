# Prostor Plugin API

> 📌 Руководство для разработчиков плагинов.

## 🧩 Что такое плагин?

Плагин Prostor — это Python-пакет в `plugins/`, который расширяет функциональность агента. Плагины могут:

- Добавлять **платформы** (Telegram, Discord, Slack, ...)
- Добавлять **инструменты** (image gen, video gen, web search, ...)
- Добавлять **память** (Honcho, Hindsight, OpenViking, ...)
- Регистрировать **hooks** (вызываются при событиях агента)
- Добавлять **CLI-команды**

## 📁 Структура плагина

```
plugins/my-plugin/
├── __init__.py           # точка входа (обязательно)
├── adapter.py            # логика плагина
├── plugin.yaml           # метаданные (опционально)
└── requirements.txt      # зависимости (опционально)
```

### `__init__.py`

```python
"""My Plugin for Prostor Agent."""

from typing import Any, Dict, List

# Метаданные плагина
PLUGIN_NAME = "my-plugin"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Does something cool"

# Hook-функции (вызываются агентом)
def on_message(message: str, context: Dict[str, Any]) -> None:
    """Вызывается при каждом сообщении пользователя."""
    pass

def on_tool_result(tool_name: str, result: Any) -> None:
    """Вызывается после каждого tool call."""
    pass

def get_tools() -> List[Dict[str, Any]]:
    """Возвращает список инструментов плагина."""
    return [
        {
            "name": "my_tool",
            "description": "Does something",
            "parameters": {...},
        }
    ]
```

### `plugin.yaml`

```yaml
name: my-plugin
version: 1.0.0
description: Does something cool
author: Your Name
license: MIT

# Зависимости (lazy install через tools/lazy_deps.py)
dependencies:
  - anthropic>=0.40.0
  - httpx>=0.28.0

# Hooks (какие функции вызывать)
hooks:
  - on_message
  - on_tool_result

# Инструменты
tools:
  - my_tool
```

## 🔌 Регистрация плагина

Плагины обнаруживаются **автоматически** при старте через `prostor_cli.plugins.discover_plugins()`:

```python
# prostor_cli/plugins.py:1806
def discover_plugins(force: bool = False) -> None:
    """Сканирует plugins/ и регистрирует найденные плагины."""
```

### Ручная регистрация

```python
from prostor_cli.plugins import invoke_hook

# Вызвать hook во всех плагинах
results = invoke_hook("on_message", message="Hello", context={})
```

## 🪝 Hooks

| Hook | Когда вызывается | Параметры |
|---|---|---|
| `on_start` | При старте агента | `config: dict` |
| `on_message` | При сообщении пользователя | `message: str, context: dict` |
| `on_tool_call` | Перед tool call | `tool_name: str, args: dict` |
| `on_tool_result` | После tool call | `tool_name: str, result: Any` |
| `on_session_start` | При новой сессии | `session_id: str` |
| `on_session_end` | При завершении сессии | `session_id: str` |

## 📦 Платформенные плагины

Платформенные плагины живут в `plugins/platforms/` и реализуют `BasePlatformAdapter`:

```python
# plugins/platforms/my_platform/adapter.py
from gateway.platforms.base import BasePlatformAdapter, PlatformConfig

class MyPlatformAdapter(BasePlatformAdapter):
    async def connect(self) -> None:
        """Подключение к платформе."""
        ...

    async def send_message(self, chat_id: str, text: str) -> None:
        """Отправка сообщения."""
        ...

    async def receive_message(self) -> Any:
        """Получение сообщения."""
        ...

    async def disconnect(self) -> None:
        """Отключение."""
        ...
```

## 🔧 Инструментальные плагины

Инструментальные плагины регистрируют tools, доступные агенту:

```python
# plugins/my_plugin/__init__.py
def get_tools():
    return [{
        "name": "search_web",
        "description": "Search the web",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        }
    }]

def execute_tool(name: str, args: dict) -> str:
    if name == "search_web":
        # Ваша логика
        return f"Results for: {args['query']}"
```

## 🧠 Память плагины

Плагины памяти (`plugins/memory/`) предоставляют провайдеры для хранения контекста:

- **Honcho** — диалектическое моделирование пользователя
- **Hindsight** — эпизодическая память
- **OpenViking** — семантический поиск

## 📊 Текущие плагины (18)

| Плагин | Тип | Описание |
|---|---|---|
| `platforms/telegram` | Platform | Telegram-бот |
| `platforms/discord` | Platform | Discord-бот |
| `platforms/slack` | Platform | Slack-бот |
| `platforms/whatsapp` | Platform | WhatsApp (через webhook) |
| `platforms/signal` | Platform | Signal-бот |
| `platforms/matrix` | Platform | Matrix-бот (E2EE) |
| `platforms/feishu` | Platform | Feishu/Lark |
| `platforms/wecom` | Platform | WeCom (WeChat Work) |
| `platforms/dingtalk` | Platform | DingTalk |
| `platforms/line` | Platform | LINE |
| `platforms/google_chat` | Platform | Google Chat |
| `platforms/photon` | Platform | Photon |
| `platforms/qqbot` | Platform | QQ Bot |
| `platforms/teams` | Platform | MS Teams |
| `platforms/yuanbao` | Platform | Yuanbao (元宝) |
| `memory/honcho` | Memory | Динамическое моделирование |
| `memory/hindsight` | Memory | Эпизодическая память |
| `memory/openviking` | Memory | Семантический поиск |
| `kanban` | Tool | Kanban-доска для задач |
| `spotify` | Tool | Управление музыкой |
| `image_gen` | Tool | Генерация изображений (FAL) |
| `video_gen` | Tool | Генерация видео (FAL) |
| `web` | Tool | Веб-поиск (Exa, Firecrawl) |
| `security-guidance` | Tool | Security analysis |
| `google_meet` | Tool | Google Meet pipeline |
| `teams_pipeline` | Tool | Teams meeting summary |
| `cron` | Tool | Cron-планировщик |
| `disk-cleanup` | Tool | Очистка диска |
| `browser` | Tool | Browser automation |
| `model-providers` | Core | Custom model providers |
| `observability` | Core | Метрики и трейсинг |
| `dashboard_auth` | Core | OAuth для dashboard |
| `prostor-achievements` | Gamification | Достижения |
| `context_engine` | Core | Context enhancement |

## 🚀 Создание нового плагина

```bash
# 1. Создать директорию
mkdir plugins/my-plugin

# 2. Создать __init__.py
cat > plugins/my-plugin/__init__.py << 'EOF'
PLUGIN_NAME = "my-plugin"
PLUGIN_VERSION = "1.0.0"

def on_message(message, context):
    print(f"My plugin received: {message}")
EOF

# 3. Перезапустить prostor — плагин обнаружится автоматически
prostor
```

## 📝 Best Practices

1. **Lazy imports** — используйте `tools/lazy_deps.ensure()` для тяжёлых зависимостей
2. **Graceful degradation** — если зависимость недоступна, показывайте понятную ошибку
3. **Thread safety** — hooks могут вызываться из разных потоков
4. **No blocking** — hooks не должны блокировать основной цикл агента
5. **Testing** — пишите тесты в `tests/plugins/test_my_plugin.py`

## 🔗 Полезные ссылки

- [AGENTS.md](../AGENTS.md) — гайд для AI-ассистентов
- [CONTRIBUTING.md](../CONTRIBUTING.md) — как контрибьютить
- [ARCHITECTURE.md](../ARCHITECTURE.md) — архитектура проекта
- [tools/lazy_deps.py](../tools/lazy_deps.py) — lazy import система