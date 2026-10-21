"""Reusable Unicorn Pro-inspired Clean White & Coral UI Components for CHZZK-Auto-Category."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import (
    QEasingCurve,
     Property,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app_icons import app_icon, icon_pixmap, set_button_icon, validate_icons
from theme import TOKENS


def apply_shadow(
    widget: QWidget,
    blur_radius: int = 24,
    y_offset: int = 4,
    alpha: int = 16,
) -> QGraphicsDropShadowEffect:
    """Attach a soft Unicorn Pro card drop shadow to a widget."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur_radius)
    shadow.setOffset(0, y_offset)
    shadow.setColor(QColor(15, 23, 42, alpha))
    widget.setGraphicsEffect(shadow)
    return shadow


def label(
    text: str = '',
    style_class: str | None = None,
    object_name: str | None = None,
    word_wrap: bool = True,
) -> QLabel:
    """Factory for styled QLabel widgets."""
    lbl = QLabel(str(text))
    lbl.setWordWrap(word_wrap)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    target_name = object_name or style_class
    if target_name:
        lbl.setObjectName(target_name)
    if style_class:
        lbl.setProperty('role', style_class)
    return lbl


def action(
    title: str,
    slot: Callable | None = None,
    icon_name: str | None = None,
    primary: bool = False,
    danger: bool = False,
    outline_accent: bool = False,
    text_link: bool = False,
    parent: QWidget | None = None,
) -> QPushButton:
    """Factory for styled QPushButton controls."""
    btn = QPushButton(title, parent)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        btn.setObjectName('primary')
    elif danger:
        btn.setObjectName('dangerButton')
    elif outline_accent:
        btn.setObjectName('outlineAccentButton')
    elif text_link:
        btn.setObjectName('textAccentButton')

    if icon_name:
        icon_color = (
            '#FFFFFF'
            if primary
            else (
                TOKENS.get('error', '#E11D48')
                if danger
                else (
                    TOKENS.get('accent', '#F0564A')
                    if (outline_accent or text_link)
                    else TOKENS.get('text', '#1E2024')
                )
            )
        )
        try:
            set_button_icon(btn, icon_name, icon_color)
        except Exception:
            btn.setIcon(app_icon(icon_name, icon_color))

    if slot is not None:
        btn.clicked.connect(slot)
    return btn


def card(
    title: str | None = None,
    subtitle: str | None = None,
    vertical: bool = True,
    object_name: str = 'panelCard',
    margin: int = 20,
    spacing: int = 12,
) -> tuple[QFrame, QVBoxLayout | QHBoxLayout]:
    """Construct a clean white bordered card container with optional header."""
    frame = QFrame()
    frame.setObjectName(object_name)
    layout: QVBoxLayout | QHBoxLayout = (
        QVBoxLayout(frame) if vertical else QHBoxLayout(frame)
    )
    layout.setContentsMargins(margin, margin, margin, margin)
    layout.setSpacing(spacing)
    if title:
        title_lbl = label(title, object_name='sectionTitle')
        layout.addWidget(title_lbl)
    if subtitle:
        sub_lbl = label(subtitle, object_name='sectionInfo')
        layout.addWidget(sub_lbl)
    apply_shadow(frame, blur_radius=20, y_offset=4, alpha=12)
    return frame, layout


def scroll_page(child_widget: QWidget) -> QScrollArea:
    """Wrap a page widget inside a borderless, responsive QScrollArea."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(child_widget)
    return area


class ModernCard(QFrame):
    """Reusable clean white card frame."""

    def __init__(self, parent: QWidget | None = None, hoverable: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName('panelCard')
        self._hoverable = hoverable
        apply_shadow(self, blur_radius=20, y_offset=4, alpha=14)


class SectionHeader(QWidget):
    """Clean section header with title and optional subtitle."""

    def __init__(
        self,
        title: str,
        subtitle: str | None = None,
        icon: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 6)
        layout.setSpacing(4)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        if icon:
            icon_lbl = QLabel()
            icon_lbl.setPixmap(icon_pixmap(icon, 18, TOKENS.get('accent', '#F0564A')))
            top.addWidget(icon_lbl, 0)
        title_lbl = label(title, object_name='sectionTitle', word_wrap=False)
        top.addWidget(title_lbl, 1)
        layout.addLayout(top)
        if subtitle:
            layout.addWidget(label(subtitle, object_name='sectionInfo'))


class ToggleSwitch(QCheckBox):
    """Unicorn Pro pill-shaped toggle switch with coral-red active state."""

    def __init__(self, title: str = '', parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        self._position: float = 1.0 if self.isChecked() else 0.0
        self._anim = QPropertyAnimation(self, b'position', self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if title:
            self.setAccessibleName(title)
        self.setFixedSize(44, 24)
        self.toggled.connect(self._animate_to_state)

    def _get_position(self) -> float:
        return self._position

    def _set_position(self, value: float) -> None:
        self._position = float(value)
        self.update()

    position = Property(float, _get_position, _set_position)

    def _animate_to_state(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._position)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()
        self._position = 1.0 if checked else 0.0
        self.update()

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        super().setChecked(bool(checked))
        self._position = 1.0 if self.isChecked() else 0.0
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(44, 24)

    def hitButton(self, pos: QPoint) -> bool:  # noqa: N802
        return self.rect().contains(pos)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        radius = rect.height() / 2.0

        accent = QColor(TOKENS.get('accent', '#F0564A'))
        off_color = QColor('#D5D8DF')
        if not self.isEnabled():
            accent.setAlpha(115)
            off_color.setAlpha(120)

        # Interpolate track color
        t = max(0.0, min(1.0, self._position))
        r = int(off_color.red() + (accent.red() - off_color.red()) * t)
        g = int(off_color.green() + (accent.green() - off_color.green()) * t)
        b = int(off_color.blue() + (accent.blue() - off_color.blue()) * t)
        a = int(off_color.alpha() + (accent.alpha() - off_color.alpha()) * t)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(r, g, b, a))
        painter.drawRoundedRect(rect, radius, radius)

        # White circular thumb
        thumb_diameter = rect.height() - 6.0
        min_x = rect.left() + 3.0
        max_x = rect.right() - 3.0 - thumb_diameter
        thumb_x = min_x + (max_x - min_x) * t
        thumb_rect = QRectF(thumb_x, rect.top() + 3.0, thumb_diameter, thumb_diameter)

        painter.setBrush(QColor('#FFFFFF'))
        painter.drawEllipse(thumb_rect)

        if self.hasFocus():
            focus_pen = QPen(accent, 1.5)
            painter.setPen(focus_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        painter.end()


class CircularStatusRing(QWidget):
    """Unicorn Pro Dashboard centerpiece: concentric status ring with soft glow and checkmark."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None, size: int = 164) -> None:
        super().__init__(parent)
        self._state: str = 'active'  # 'active' | 'paused' | 'waiting' | 'error'
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip('클릭하여 자동 카테고리 감지를 켜거나 끕니다.')

    def set_state(self, state: str) -> None:
        if state not in ('active', 'paused', 'waiting', 'error'):
            state = 'active'
        if self._state != state:
            self._state = state
            self.update()

    def state(self) -> str:
        return self._state

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        cx, cy = w / 2.0, h / 2.0
        outer_radius = min(w, h) / 2.0 - 8.0

        color_map = {
            'active': QColor(TOKENS.get('accent', '#F0564A')),
            'paused': QColor('#C6CBD4'),
            'waiting': QColor(TOKENS.get('warning', '#F59E0B')),
            'error': QColor(TOKENS.get('error', '#E11D48')),
        }
        ring_color = color_map.get(self._state, QColor(TOKENS.get('accent', '#F0564A')))

        # 1. Soft radial glow around the ring (matches Screenshot 1)
        glow = QRadialGradient(QPointF(cx, cy), outer_radius + 8.0)
        glow_start = QColor(ring_color)
        glow_start.setAlpha(42 if self._state != 'paused' else 18)
        glow_end = QColor(ring_color)
        glow_end.setAlpha(0)
        glow.setColorAt(0.68, glow_start)
        glow.setColorAt(1.0, glow_end)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(cx, cy), outer_radius + 7.0, outer_radius + 7.0)

        # 2. Outer colored ring
        ring_width = 9.0
        ring_rect = QRectF(
            cx - outer_radius + ring_width / 2.0,
            cy - outer_radius + ring_width / 2.0,
            (outer_radius - ring_width / 2.0) * 2.0,
            (outer_radius - ring_width / 2.0) * 2.0,
        )
        painter.setBrush(QColor('#FFFFFF'))
        painter.setPen(QPen(ring_color, ring_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawEllipse(ring_rect)

        # 3. Subtle inner disk shadow ring
        inner_radius = outer_radius - ring_width - 10.0
        inner_shadow_pen = QPen(QColor(15, 23, 42, 14), 2.0)
        painter.setPen(inner_shadow_pen)
        painter.setBrush(QColor('#FFFFFF'))
        painter.drawEllipse(QPointF(cx, cy), inner_radius, inner_radius)

        # 4. Center icon (Checkmark when active/waiting, pause bars when paused, exclamation when error)
        icon_pen = QPen(
            ring_color,
            2.6,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        painter.setPen(icon_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if self._state == 'paused':
            painter.drawLine(QPointF(cx - 6.0, cy - 9.0), QPointF(cx - 6.0, cy + 9.0))
            painter.drawLine(QPointF(cx + 6.0, cy - 9.0), QPointF(cx + 6.0, cy + 9.0))
        elif self._state == 'error':
            painter.drawLine(QPointF(cx, cy - 9.0), QPointF(cx, cy + 3.0))
            painter.drawPoint(QPointF(cx, cy + 9.0))
        else:
            path = QPainterPath()
            path.moveTo(cx - 10.0, cy + 0.5)
            path.lineTo(cx - 3.0, cy + 7.5)
            path.lineTo(cx + 11.0, cy - 6.5)
            painter.drawPath(path)

        painter.end()


class StatusMetricCard(QFrame):
    """Unicorn Pro Dashboard bottom metric card (Icon top-left, muted title, bold value)."""

    def __init__(
        self,
        title: str,
        default_value: str = '0',
        default_meta: str = '',
        icon_name: str = 'dashboard',
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName('metricCard')
        self.setProperty('dashboardCard', True)
        self.setMinimumHeight(112)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        self.icon_label = QLabel()
        self.icon_label.setPixmap(
            icon_pixmap(icon_name, 20, TOKENS.get('accent', '#F0564A'))
        )
        top_row.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignLeft)
        top_row.addStretch(1)

        self.dot = QLabel('●')
        self.dot.setStyleSheet(f"color: {TOKENS.get('accent', '#F0564A')}; font-size: 9px;")
        self.dot.setVisible(False)
        top_row.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(top_row)

        layout.addStretch(1)

        self.title_label = label(title, object_name='metricLabel', word_wrap=False)
        layout.addWidget(self.title_label)

        self.value_label = label(default_value, object_name='metricValue', word_wrap=False)
        layout.addWidget(self.value_label)

        self.meta_label = label(default_meta, object_name='softHint', word_wrap=False)
        self.meta_label.setVisible(bool(default_meta))
        layout.addWidget(self.meta_label)

        apply_shadow(self, blur_radius=22, y_offset=4, alpha=14)


class StatusPillBadge(QLabel):
    """Outlined Coral Pill Badge ('상태 : 사용가능' / '상태 : 연결됨') from Screenshot 3."""

    def __init__(self, text: str = '상태 : 사용가능', parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName('statusPillBadge')
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class SettingsComboBox(QComboBox):
    """Minimal styled QComboBox with clean white popup view."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        view = QListView(self)
        view.setSpacing(2)
        self.setView(view)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(32)


class FramelessDialog(QDialog):
    """Clean white frameless dialog window with header drag support and close button."""

    def __init__(self, parent: QWidget | None = None, title: str = '') -> None:
        if isinstance(parent, str) and not title:
            title, parent = parent, None
        super().__init__(parent)
        self._drag_offset: QPoint | None = None
        self.setObjectName('subDialog')
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        if title:
            self.setWindowTitle(title)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # Ensure at least one close button exists for keyboard/test accessibility
        has_close = any('닫기' in b.text() or '취소' in b.text() for b in self.findChildren(QPushButton))
        if not has_close and self.layout() is not None:
            close_btn = QPushButton('닫기', self)
            close_btn.setObjectName('windowButton')
            close_btn.clicked.connect(self.reject)
            self.layout().addWidget(close_btn)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class AppDialog(FramelessDialog):
    """Unicorn Pro clean white alert & confirmation dialog."""

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        message: str,
        *,
        tone: str = 'info',
        confirm_text: str = '확인',
        cancel_text: str | None = None,
        danger: bool = False,
    ) -> None:
        super().__init__(parent, title=title)
        self.setMinimumWidth(400)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # Header row with title & top-right close button
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title_lbl = label(title, object_name='pageTitle', word_wrap=False)
        header.addWidget(title_lbl, 1)

        close_x = QPushButton('✕', self)
        close_x.setObjectName('windowButton')
        close_x.setToolTip('닫기')
        close_x.clicked.connect(self.reject)
        header.addWidget(close_x, 0)
        root.addLayout(header)

        # Message box
        msg_frame = QFrame(self)
        msg_frame.setObjectName('panelCard')
        msg_layout = QVBoxLayout(msg_frame)
        msg_layout.setContentsMargins(16, 14, 16, 14)
        body_lbl = label(message, object_name='sectionInfo', word_wrap=True)
        body_lbl.setStyleSheet(f"color: {TOKENS.get('text', '#1E2024')}; font-size: 13px;")
        msg_layout.addWidget(body_lbl)
        root.addWidget(msg_frame)

        # Action buttons row
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)
        btn_row.setSpacing(8)
        btn_row.addStretch(1)

        if cancel_text:
            cancel_btn = action(cancel_text, self.reject)
            btn_row.addWidget(cancel_btn)
        else:
            close_btn = action('닫기', self.reject)
            close_btn.setVisible(False)
            btn_row.addWidget(close_btn)

        confirm_btn = action(
            confirm_text,
            self.accept,
            primary=not danger,
            danger=danger,
        )
        btn_row.addWidget(confirm_btn)
        root.addLayout(btn_row)


def create_dialog(
    parent: QWidget | None,
    title: str,
    message: str,
    tone: str = 'info',
    confirm_text: str = '확인',
    cancel_text: str | None = None,
    danger: bool = False,
) -> AppDialog:
    return AppDialog(
        parent,
        title,
        message,
        tone=tone,
        confirm_text=confirm_text,
        cancel_text=cancel_text,
        danger=danger,
    )


def show_info(parent: QWidget | None, title: str, message: str) -> None:
    dlg = AppDialog(parent, title, message, tone='info', confirm_text='확인')
    dlg.exec()


def show_warning(parent: QWidget | None, title: str, message: str) -> None:
    dlg = AppDialog(parent, title, message, tone='warning', confirm_text='확인')
    dlg.exec()


def show_error(parent: QWidget | None, title: str, message: str) -> None:
    dlg = AppDialog(parent, title, message, tone='error', confirm_text='확인', danger=True)
    dlg.exec()


def confirm(
    parent: QWidget | None,
    title: str,
    message: str,
    *,
    confirm_text: str = '확인',
    cancel_text: str = '취소',
    danger: bool = False,
) -> bool:
    dlg = AppDialog(
        parent,
        title,
        message,
        tone='warning' if danger else 'info',
        confirm_text=confirm_text,
        cancel_text=cancel_text,
        danger=danger,
    )
    return dlg.exec() == QDialog.DialogCode.Accepted


def choose_executable(
    parent: QWidget | None = None,
    title: str = '실행 파일 선택',
    initial_dir: str = '',
) -> str:
    """Open a non-native, frameless QFileDialog for selecting a game .exe file."""
    dlg = QFileDialog(parent, title, initial_dir or str(Path.home()))
    dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dlg.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
    dlg.setNameFilter('실행 파일 (*.exe);;모든 파일 (*)')
    if dlg.exec() == QDialog.DialogCode.Accepted:
        files = dlg.selectedFiles()
        return files[0] if files else ''
    return ''


def toast_icon():
    return app_icon('dashboard', TOKENS.get('accent', '#F0564A'))


# Backward-compatible aliases used across main.py, modern_ui.py, and tests
information = show_info
warning = show_warning
error = show_error
critical = show_error
question = confirm
ask_confirmation = confirm
