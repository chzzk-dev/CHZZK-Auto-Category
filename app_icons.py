"""Offline QtAwesome icons, validated names, one bounded GUI-thread cache."""
from functools import lru_cache
import qtawesome as qta
from PySide6.QtCore import QSize

ICONS = {
    'dashboard': 'gauge-high', 'games': 'gamepad', 'automation': 'sliders',
    'connections': 'link', 'settings': 'gear', 'logs': 'list', 'start': 'play',
    'pause': 'pause', 'add': 'plus', 'edit': 'pen', 'delete': 'trash',
    'search': 'magnifying-glass', 'refresh': 'rotate', 'info': 'circle-info',
    'success': 'check', 'warning': 'triangle-exclamation', 'close': 'xmark',
    'minimize': 'minus', 'maximize': 'window-maximize', 'up': 'arrow-up',
    'down': 'arrow-down', 'download': 'download', 'details': 'eye',
    'notify': 'bell', 'tray': 'desktop', 'clock': 'clock', 'exclude': 'ban',
}


@lru_cache(maxsize=128)
def app_icon(name, color='#17313C'):
    return qta.icon('fa6s.' + ICONS[name], color=color)


def set_button_icon(button, name, color='#17313C'):
    button.setIcon(app_icon(name, color))
    button.setIconSize(QSize(18, 18))
    button.setAccessibleName(button.text() or button.toolTip() or name)


def validate_icons():
    return all(not app_icon(name).pixmap(20, 20).isNull() for name in ICONS)
