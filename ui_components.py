from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from theme import TOKENS
from app_icons import app_icon
ACCENT = TOKENS['accent']
ACCENT_HOVER = TOKENS['hover']
SURFACE = TOKENS['background']
CARD = TOKENS['card']
BORDER = TOKENS['border']
TEXT = TOKENS['text']
MUTED = TOKENS['muted']
WARNING = '#FFF4DD'
DANGER = '#B94A59'

_DIALOG_STYLE = f'''
QDialog {{ background: transparent; }}
QFrame#dialogShell {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 22px;
}}
QFrame#dialogIconInfo {{ background: #E4F8F0; border: 1px solid #C4E8DC; border-radius: 20px; }}
QFrame#dialogIconWarning {{ background: #FFF4DD; border: 1px solid #EAD8B4; border-radius: 20px; }}
QFrame#dialogIconError {{ background: #FCECF0; border: 1px solid #EBCBD1; border-radius: 20px; }}
QFrame#dialogIconQuestion {{ background: #E4F8F0; border: 1px solid #C4E8DC; border-radius: 20px; }}
QLabel#dialogGlyph {{ color: {TEXT}; font-size: 18px; font-weight: 900; }}
QLabel#dialogTitle {{ color: {TEXT}; font-size: 19px; font-weight: 850; }}
QLabel#dialogMessage {{ color: #6D8490; font-size: 13px; line-height: 1.5; }}
QPushButton {{
    min-height: 42px;
    border-radius: 13px;
    padding: 0 18px;
    background: #FFFFFF;
    border: 1px solid #E3EBEE;
    color: {TEXT};
    font-weight: 700;
}}
QPushButton:hover {{ background: #EDF9F4; border-color: #A8D9CF; }}
QPushButton#dialogPrimary {{ background: {ACCENT}; color: #071911; border: none; }}
QPushButton#dialogPrimary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#dialogDanger {{ background: {DANGER}; color: #1f0710; border: none; }}
QPushButton#dialogDanger:hover {{ background: #ff8495; }}
QPushButton#dialogClose {{
    min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px;
    border-radius: 9px; padding: 0; background: transparent; border: 1px solid transparent;
    color: #8f9aac;
}}
QPushButton#dialogClose:hover {{ background: #EDF9F4; border-color: #E3EBEE; color: #17313C; }}
'''


class AppDialog(QDialog):
    def __init__(
        self,
        parent,
        title: str,
        message: str,
        *,
        tone: str = 'info',
        confirm_text: str = '확인',
        cancel_text: str | None = None,
        danger: bool = False,
    ):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumWidth(450)
        self.setMaximumWidth(560)
        self.setStyleSheet(_DIALOG_STYLE)
        self._drag_offset = QPoint()
        self._fade = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 22, 22, 22)

        shell = QFrame()
        shell.setObjectName('dialogShell')
        shadow = QGraphicsDropShadowEffect(shell)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 14)
        shadow.setColor(QColor(0, 0, 0, 180))
        shell.setGraphicsEffect(shadow)
        outer.addWidget(shell)

        layout = QVBoxLayout(shell)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(12)

        icon_frame = QFrame()
        icon_frame.setFixedSize(40, 40)
        icon_frame.setObjectName({
            'warning': 'dialogIconWarning',
            'error': 'dialogIconError',
            'question': 'dialogIconQuestion',
        }.get(tone, 'dialogIconInfo'))
        icon_layout = QVBoxLayout(icon_frame)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        glyph = QLabel()
        glyph.setPixmap(app_icon('warning' if tone in ('warning', 'error') else 'info').pixmap(20, 20))
        glyph.setObjectName('dialogGlyph')
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_layout.addWidget(glyph)
        header.addWidget(icon_frame, 0, Qt.AlignmentFlag.AlignTop)

        titles = QVBoxLayout()
        titles.setSpacing(4)
        title_label = QLabel(title)
        title_label.setObjectName('dialogTitle')
        title_label.setWordWrap(True)
        message_label = QLabel(message)
        message_label.setObjectName('dialogMessage')
        message_label.setWordWrap(True)
        message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        titles.addWidget(title_label)
        titles.addWidget(message_label)
        header.addLayout(titles, 1)

        close_button = QPushButton('')
        close_button.setIcon(app_icon('close'))
        close_button.setAccessibleName('닫기')
        close_button.setObjectName('dialogClose')
        close_button.clicked.connect(self.reject)
        header.addWidget(close_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch()
        if cancel_text:
            cancel = QPushButton(cancel_text)
            cancel.clicked.connect(self.reject)
            buttons.addWidget(cancel)
        confirm = QPushButton(confirm_text)
        confirm.setObjectName('dialogDanger' if danger else 'dialogPrimary')
        confirm.clicked.connect(self.accept)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)

    def showEvent(self, event):
        super().showEvent(event)
        self.setWindowOpacity(0.0)
        self._fade = QPropertyAnimation(self, b'windowOpacity', self)
        self._fade.setDuration(180)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)


def information(parent, title: str, message: str) -> None:
    AppDialog(parent, title, message, tone='info').exec()


def warning(parent, title: str, message: str) -> None:
    AppDialog(parent, title, message, tone='warning').exec()


def error(parent, title: str, message: str) -> None:
    AppDialog(parent, title, message, tone='error', confirm_text='닫기', danger=True).exec()


def confirm(
    parent,
    title: str,
    message: str,
    *,
    confirm_text: str = '확인',
    cancel_text: str = '취소',
    danger: bool = False,
) -> bool:
    dialog = AppDialog(
        parent,
        title,
        message,
        tone='question',
        confirm_text=confirm_text,
        cancel_text=cancel_text,
        danger=danger,
    )
    return dialog.exec() == QDialog.DialogCode.Accepted
