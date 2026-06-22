"""Shared types — import-safe."""
from __future__ import annotations

from enum import Enum


class Platform(Enum):
    """Supported messaging platforms."""
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    CLI = "cli"
    SMS = "sms"
    WEB = "web"
    FEISHU = "feishu"
    LARK = "lark"
    WHATSAPP = "whatsapp"
    SIGNAL = "signal"
    IRC = "irc"
    MATTERMOST = "mattermost"
    TEAMS = "teams"
    GOOGLE_CHAT = "google_chat"


__all__ = ["Platform"]
