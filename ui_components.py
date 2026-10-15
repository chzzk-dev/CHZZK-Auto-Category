from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, Property, QRectF, QSize
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QDialogButtonBox,
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
CARD = '#F5F3ED'
BORDER = TOKENS['border']
TEXT = TOKENS['text']
MUTED = TOKENS['muted']
WARNING = '#E7E3DA'
DANGER = '#B94A59'

_DIALOG_STYLE = f'''
QDialog {{ background: transparent; }}
QFrame#dialogShell {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 22px;
}}
QFrame#dialogIconInfo {{ background: #E7E3DA; border: 1px solid #D4D0C5; border-radius: 20px; }}
QFrame#dialogIconWarning {{ background: #E7E3DA; border: 1px solid #D4D0C5; border-radius: 20px; }}
QFrame#dialogIconError {{ background: #E7E3DA; border: 1px solid #D4D0C5; border-radius: 20px; }}
QFrame#dialogIconQuestion {{ background: #E7E3DA; border: 1px solid #D4D0C5; border-radius: 20px; }}
QLabel#dialogGlyph {{ color: {TEXT}; font-size: 18px; font-weight: 900; }}
QLabel#dialogTitle {{ color: {TEXT}; font-size: 19px; font-weight: 850; }}
QLabel#dialogMessage {{ color: #77756F; font-size: 13px; line-height: 1.5; }}
QPushButton {{
    min-height: 42px;
    border-radius: 13px;
    padding: 0 18px;
    background: #FFFFFF;
    border: 1px solid #D4D0C5;
    color: {TEXT};
    font-weight: 700;
}}
QPushButton:hover {{ background: #DDD8CE; border-color: #BDB7AB; }}
QPushButton#dialogPrimary {{ background: {ACCENT}; color: #252525; border: none; }}
QPushButton#dialogPrimary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#dialogDanger {{ background: {DANGER}; color: #1f0710; border: none; }}
QPushButton#dialogDanger:hover {{ background: #ff8495; }}
QPushButton#dialogClose {{
    min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px;
    border-radius: 9px; padding: 0; background: transparent; border: 1px solid transparent;
    color: #8f9aac;
}}
QPushButton#dialogClose:hover {{ background: #DDD8CE; border-color: #D4D0C5; color: #252525; }}
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


class ToggleSwitch(QCheckBox):
    """Native checkbox semantics with a keyboard-accessible sliding switch."""
    def __init__(self, title='', parent=None):
        super().__init__('', parent)
        self.setAccessibleName(title)
        self.setFixedSize(56, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._position = 0.0
        self._animation = QPropertyAnimation(self, b'position', self)
        self._animation.setDuration(140)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.toggled.connect(self._animate)

    def _animate(self, checked):
        self._animation.stop()
        end = 1.0 if checked else 0.0
        if self.isVisible():
            self._animation.setStartValue(self._position)
            self._animation.setEndValue(end)
            self._animation.start()
        else:
            self._set_position(end)

    def _get_position(self):
        return self._position

    def _set_position(self, value):
        self._position = value
        self.update()

    position = Property(float, _get_position, _set_position)

    def sizeHint(self):
        return QSize(56, 30)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.5)
        painter.setPen(QPen(QColor('#AAA69D' if self.hasFocus() else '#74716A'), 1.5))
        painter.setBrush(QColor('#EDEBE4' if self.isChecked() else '#505050'))
        painter.drawRoundedRect(QRectF(1, 1, 54, 28), 14, 14)
        x = 4 + self._position * 26
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#252525' if self.isChecked() else '#F5F3ED'))
        painter.drawEllipse(QRectF(x, 4, 22, 22))
        painter.setPen(QPen(QColor('#FFFFFF' if self.isChecked() else '#555555'), 1.8))
        if self.isChecked():
            painter.drawLine(QPoint(round(x + 6), 15), QPoint(round(x + 10), 19))
            painter.drawLine(QPoint(round(x + 10), 19), QPoint(round(x + 17), 11))
        else:
            painter.drawLine(QPoint(round(x + 8), 12), QPoint(round(x + 14), 18))
            painter.drawLine(QPoint(round(x + 8), 18), QPoint(round(x + 14), 12))


class SettingsComboBox(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#3E3B35' if self.isEnabled() else '#AAA69D'), 1.8))
        x, y = self.width() - 16, self.height() // 2
        painter.drawLine(QPoint(x - 4, y - 2), QPoint(x, y + 2))
        painter.drawLine(QPoint(x, y + 2), QPoint(x + 4, y - 2))


class FramelessDialog(QDialog):
    """Common borderless subwindow; Escape and an in-window close remain available."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setObjectName('subDialog')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._drag_offset = None

    def showEvent(self, event):
        if not any('닫기' in b.text() or b.toolTip() == '닫기' for b in self.findChildren(QPushButton)):
            close = QPushButton('닫기', self)
            close.setIcon(app_icon('close'))
            close.clicked.connect(self.reject)
            if self.layout() is None:
                QVBoxLayout(self)
            self.layout().addWidget(close)
        super().showEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 48:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)


def choose_executable(parent):
    dialog = QFileDialog(parent, '게임 실행 파일', '', 'Windows 실행 파일 (*.exe)')
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
    dialog.setObjectName('subDialog')
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    dialog.setLabelText(QFileDialog.DialogLabel.Reject, '닫기')
    result = dialog.exec()
    files = dialog.selectedFiles() if result == QDialog.DialogCode.Accepted else []
    dialog.deleteLater()
    return files[0] if files else ''
