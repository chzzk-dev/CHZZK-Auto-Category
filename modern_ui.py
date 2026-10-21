"""Unicorn Pro-inspired Clean White & Coral UI Layout (`modern_ui.py`) for CHZZK-Auto-Category."""

from __future__ import annotations

import copy
from collections import deque
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox as QtComboBox,
    QDialog as QtDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableView,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app_icons import app_icon, icon_pixmap, set_button_icon, validate_icons
from theme import TOKENS, apply_theme, set_accent_palette
from ui_components import (
    CircularStatusRing,
    FramelessDialog as QDialog,
    SettingsComboBox as QComboBox,
    StatusMetricCard,
    StatusPillBadge,
    ToggleSwitch,
    action as ui_action,
    apply_shadow,
    choose_executable,
    confirm,
    error as show_error,
    information as show_info,
     scroll_page,
    warning as show_warning,
)

try:
    from core import Rule
except ImportError:
    class Rule:  # Fallback for isolated UI testing
        def __init__(
            self,
            process: str = '',
            category_id: str = '',
            category_name: str = '',
            kind: str = 'manual',
            priority: int = 0,
            aliases: list[str] | None = None,
            excluded: bool = False,
        ) -> None:
            self.process = process
            self.category_id = category_id
            self.category_name = category_name
            self.kind = kind
            self.priority = priority
            self.aliases = aliases or []
            self.excluded = excluded

try:
    from scheduling import HOUR_OPTIONS
except ImportError:
    HOUR_OPTIONS = [1, 3, 6, 12, 24]

try:
    from version import APP_VERSION
except ImportError:
    APP_VERSION = '1.10.418'

PAGES: tuple[tuple[str, str, str], ...] = (
    ('대시보드', '게임 감지부터 방송 카테고리 변경까지 자동으로 관리합니다.', 'dashboard'),
    ('게임 목록', '감지된 게임과 치지직 카테고리 연결을 관리합니다.', 'games'),
    ('자동화 설정', '게임 감지, 검증, 자동 변경의 동작을 설정합니다.', 'automation'),
    ('연결 관리', '치지직 계정과 브라우저 확장프로그램 연결을 확인합니다.', 'connections'),
    ('설정', '백그라운드 동작, 업데이트, 프로그램 정보를 관리합니다.', 'settings'),
    ('로그', '감지부터 변경 결과까지 실제 활동 기록을 확인합니다.', 'logs'),
)

OLD_PAGE_MAP: dict[int, int] = {
    0: 0,
    1: 3,
    2: 3,
    3: 1,
    4: 5,
    5: 4,
    6: 4,
    7: 4,
}


def label(text: str = '', name: str = 'softHint') -> QLabel:
    lbl = QLabel(str(text))
    lbl.setObjectName(name)
    lbl.setWordWrap(True)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    return lbl


def action(
    text: str,
    callback=None,
    icon: str | None = 'info',
    primary: bool = False,
    outline_accent: bool = False,
    text_link: bool = False,
) -> QPushButton:
    return ui_action(
        text,
        slot=callback,
        icon_name=icon,
        primary=primary,
        outline_accent=outline_accent,
        text_link=text_link,
    )


def card(title: str = '') -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName('panelCard')
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 18, 22, 18)
    layout.setSpacing(12)
    if title:
        hdr = label(title, 'sectionTitle')
        hdr.setWordWrap(False)
        layout.addWidget(hdr)
    apply_shadow(frame, blur_radius=20, y_offset=4, alpha=12)
    return frame, layout


def setting_row(title: str, description: str, control: QWidget) -> QFrame:
    """Unicorn Pro flat horizontal divider row (Screenshot 2 style)."""
    row = QFrame()
    row.setObjectName('settingRow')
    layout = QHBoxLayout(row)
    layout.setContentsMargins(4, 14, 4, 14)
    layout.setSpacing(16)

    text_col = QVBoxLayout()
    text_col.setContentsMargins(0, 0, 0, 0)
    text_col.setSpacing(4)

    title_lbl = label(title, 'settingTitle')
    title_lbl.setWordWrap(False)
    desc_lbl = label(description, 'settingDesc')
    text_col.addWidget(title_lbl)
    text_col.addWidget(desc_lbl)

    layout.addLayout(text_col, 1)
    control.setProperty('settingControl', True)
    layout.addWidget(control, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return row


def settings_shell(content: QWidget, save_callback=None) -> QWidget:
    wrapper = QWidget()
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    layout.addWidget(scroll_page(content), 1)
    if save_callback is not None:
        footer = QHBoxLayout()
        footer.setContentsMargins(24, 4, 24, 12)
        footer.addStretch(1)
        save_btn = action('설정 저장', save_callback, 'success', primary=True)
        footer.addWidget(save_btn)
        layout.addLayout(footer)
    return wrapper


class GameTableModel(QAbstractTableModel):
    """Table model backing the Game List (`게임 목록`) QTableView."""

    def __init__(self, parent=None, games: list[dict] | None = None) -> None:
        super().__init__(parent)
        self.rows: list[dict] = list(games or [])
        self.games = self.rows
        self.headers = [
            '구분',
            '게임을 찾을 프로그램',
            '상태',
            '치지직 방송 카테고리',
            '우선순위',
            '관리',
        ]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.headers)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(self.headers)
        ):
            return self.headers[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.rows)):
            return None
        row = self.rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row.get('kind_label') or row.get('kind', '수동')
            if col == 1:
                return row.get('game') or row.get('process', '')
            if col == 2:
                return row.get('state', '대기')
            if col == 3:
                return row.get('category_name') or row.get('category', '미지정')
            if col == 4:
                return str(row.get('priority', index.row() + 1))
            if col == 5:
                return row.get('details', '상세')

        if role == Qt.ItemDataRole.DecorationRole and col == 5:
            return app_icon('details', TOKENS.get('accent', '#F0564A'))

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (0, 2, 4, 5):
                return int(Qt.AlignmentFlag.AlignCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        return None

    def replace(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self.rows = list(rows)
        self.games = self.rows
        self.endResetModel()

    set_rows = replace
    update_games = replace


class ModernWindowMixin:
    """Mixin restructuring `main.Window` into the Unicorn Pro 3-layout clean white design."""

    def __init__(self, config: dict | None = None, preview: bool = False) -> None:
        self.ui_ready = False
        self.runtime_games: list[dict] = []
        self.game_log_running: set[str] = set()
        self.quick_rule_callbacks: dict = {}
        self.official_check_requested = False
        self.league_session_token: str | None = None
        self.active_league_dialog: QtDialog | None = None
        self.league_selected_session: str | None = None
        self.recent_activity: deque = deque(maxlen=5)
        self.last_category: str = ''
        self.connection_retry_at: float = 0.0
        self.connection_failures: int = 0
        self.last_category_observed_at: str = ''
        self.last_applied_at: str = ''
        self.rail_buttons: list[QToolButton] = []

        super().__init__(config, preview)

        self.setMinimumSize(1200, 820)
        self.resize(1360, 860)

        self._install_unicorn_shell()
        self.ui_ready = True
        self.refresh_dashboard()
        self.refresh_table()
        QTimer.singleShot(0, self.ensure_official_api_check)
        QTimer.singleShot(0, self.ensure_steam_api_check)

    # ------------------------------------------------------------------
    # Shell & 2-Stage Navigation Setup (Screenshots 1, 2, 3)
    # ------------------------------------------------------------------
    def _install_unicorn_shell(self) -> None:
        """Re-organize pages into the 6 Unicorn Pro views and attach the slim icon rail."""
        old = [self.pages.widget(i) for i in range(self.pages.count())]
        while self.pages.count():
            self.pages.removeWidget(self.pages.widget(0))

        self.dashboard = self.build_dashboard()

        # Page 1: Game List with horizontal underline tabs (Screenshot 2 style)
        self.game_tabs = QTabWidget()
        self.game_tabs.setDocumentMode(True)
        if len(old) > 0 and old[0] is not None:
            self.game_tabs.addTab(old[0], '게임 규칙 관리')
        else:
            self.game_tabs.addTab(self.build_rules(), '게임 규칙 관리')
        if len(old) > 3 and old[3] is not None:
            self.game_tabs.addTab(old[3], '미확정 항목')

        # Page 3: Connection Management with Screenshot 3 centered status layout + tabs
        self.connection_tabs = QTabWidget()
        self.connection_tabs.setDocumentMode(True)
        self.connection_tabs.addTab(self.build_steam_connection(), 'Steam 한국어 매칭')
        if len(old) > 2 and old[2] is not None:
            self.connection_tabs.addTab(scroll_page(old[2]), '브릿지 연결 상태')
        if len(old) > 1 and old[1] is not None:
            self.connection_tabs.addTab(scroll_page(old[1]), '치지직 계정 설정')

        # Page 4: Settings with Screenshot 2 horizontal underline tabs & divider rows
        self.setting_tabs = QTabWidget()
        self.setting_tabs.setDocumentMode(True)
        self.setting_tabs.addTab(self.build_program_settings(), '기본 설정')
        if len(old) > 6 and old[6] is not None:
            self.setting_tabs.addTab(scroll_page(old[6]), '업데이트')
        if len(old) > 7 and old[7] is not None:
            self.setting_tabs.addTab(scroll_page(old[7]), '앱 정보')

        automation_page = old[5] if len(old) > 5 and old[5] is not None else self.build_options()
        logs_page = old[4] if len(old) > 4 and old[4] is not None else QWidget()

        reordered = [
            self.dashboard,         # 0: 대시보드 (Screenshot 1)
            self.game_tabs,         # 1: 게임 목록 (Screenshot 2)
            automation_page,        # 2: 자동화 설정 (Screenshot 2)
            self.connection_tabs,   # 3: 연결 관리 (Screenshot 3)
            self.setting_tabs,      # 4: 설정 (Screenshot 2)
            logs_page,              # 5: 로그
        ]
        for page_widget in reordered:
            self.pages.addWidget(page_widget)

        # Populate 6 items in self.nav (Secondary Sidebar, Screenshot 2 style)
        if hasattr(self, 'nav') and self.nav is not None:
            self.nav.blockSignals(True)
            self.nav.clear()
            for title, _subtitle, icon_key in PAGES:
                item = QListWidgetItem(
                    app_icon(icon_key, TOKENS.get('accent', '#F0564A')),
                    title,
                )
                item.setSizeHint(QSize(180, 42))
                self.nav.addItem(item)
            self.nav.setCurrentRow(0)
            self.nav.blockSignals(False)
            try:
                self.nav.currentRowChanged.disconnect()
            except Exception:
                pass
            self.nav.currentRowChanged.connect(self.switch_page)

        # Insert Far-Left Slim Icon Rail (Unicorn Pro Icon Rail) before self.sidebar
        sidebar_frame = self.findChild(QFrame, 'sidebar')
        if sidebar_frame is not None and sidebar_frame.parentWidget() is not None:
            body_layout = sidebar_frame.parentWidget().layout()
            if isinstance(body_layout, QHBoxLayout):
                self.icon_rail = self._build_icon_rail()
                body_layout.insertWidget(0, self.icon_rail, 0)
                sidebar_frame.setFixedWidth(210)

        self.pages.setCurrentIndex(0)
        self._sync_rail_highlight(0)

    def _build_icon_rail(self) -> QFrame:
        """Build the far-left 62px slim icon rail seen in all 3 Unicorn Pro screenshots."""
        rail = QFrame(self)
        rail.setObjectName('iconRail')
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(12)

        # Top circular brand emblem (Unicorn Pro top-left badge position)
        brand_btn = QToolButton(rail)
        brand_btn.setFixedSize(36, 36)
        brand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        brand_btn.setToolTip('CHZZK Auto Category · 대시보드')
        brand_btn.setStyleSheet(
            f"QToolButton {{ background: {TOKENS.get('accent', '#F0564A')}; "
            f"border: none; border-radius: 18px; }}"
        )
        brand_btn.setIcon(app_icon('games', '#FFFFFF'))
        brand_btn.setIconSize(QSize(18, 18))
        brand_btn.clicked.connect(lambda: self._navigate_to(0))
        layout.addWidget(brand_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch(1)

        # Center 3 primary rail icons (Shield=Dashboard, Sliders=Settings/Rules, Badge=Connections)
        rail_specs = [
            ('dashboard', '대시보드 (메인 보호 상태)', 0),
            ('automation', '게임 목록 및 자동화 설정', 1),
            ('connections', '연결 및 인증 관리', 3),
        ]
        self.rail_buttons = []
        for icon_key, tip, target_idx in rail_specs:
            btn = QToolButton(rail)
            btn.setObjectName('railButton')
            btn.setToolTip(tip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIcon(app_icon(icon_key, '#555962'))
            btn.setIconSize(QSize(20, 20))
            btn.clicked.connect(lambda _checked=False, idx=target_idx: self._navigate_to(idx))
            layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
            self.rail_buttons.append(btn)

        layout.addStretch(1)

        # Bottom 3 utility icons (?, i, gear) matching Screenshots 1, 2, 3
        bottom_specs = [
            ('logs', '활동 로그 보기', 5),
            ('info', '버전 및 앱 정보', 4),
            ('settings', '환경 설정', 4),
        ]
        for icon_key, tip, target_idx in bottom_specs:
            b_btn = QToolButton(rail)
            b_btn.setObjectName('railBottomButton')
            b_btn.setToolTip(tip)
            b_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            b_btn.setIcon(app_icon(icon_key, '#8B909A'))
            b_btn.setIconSize(QSize(16, 16))
            b_btn.clicked.connect(lambda _checked=False, idx=target_idx: self._navigate_to(idx))
            layout.addWidget(b_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        return rail

    def _navigate_to(self, index: int) -> None:
        if hasattr(self, 'nav') and self.nav is not None and 0 <= index < self.nav.count():
            self.nav.setCurrentRow(index)
        else:
            self.switch_page(index)

    def _sync_rail_highlight(self, page_index: int) -> None:
        if not getattr(self, 'rail_buttons', None):
            return
        # Map 6 pages to the 3 primary rail icons:
        # 0 -> rail[0] (Dashboard), 1/2/4/5 -> rail[1] (Settings/Management), 3 -> rail[2] (Connections)
        active_rail = 0 if page_index == 0 else (2 if page_index == 3 else 1)
        icon_keys = ['dashboard', 'automation', 'connections']
        for i, btn in enumerate(self.rail_buttons):
            is_active = i == active_rail
            btn.setProperty('active', 'true' if is_active else 'false')
            color = TOKENS.get('accent', '#F0564A') if is_active else '#686D78'
            btn.setIcon(app_icon(icon_keys[i], color))
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ------------------------------------------------------------------
    # Page 0: Dashboard (Screenshot 1 Layout)
    # ------------------------------------------------------------------
    def _make_status_card(
        self,
        title: str,
        default_val: str,
        default_meta: str,
        icon_name: str = 'dashboard',
    ) -> tuple[StatusMetricCard, tuple[QLabel, QLabel, QLabel]]:
        metric_card = StatusMetricCard(
            title=title,
            default_value=default_val,
            default_meta=default_meta,
            icon_name=icon_name,
        )
        return metric_card, (metric_card.value_label, metric_card.meta_label, metric_card.dot)

    def build_dashboard(self) -> QScrollArea:
        """Construct Screenshot 1's clean white dashboard with central status ring + bottom 4 metric cards."""
        page = QWidget()
        page.setObjectName('dashboardPage')
        root = QVBoxLayout(page)
        root.setContentsMargins(36, 24, 36, 24)
        root.setSpacing(18)

        # 1. Center Hero Panel (Circular Status Ring + Toggle + Headline + Action Button)
        self.dashboard_game_card = QFrame(page)
        self.dashboard_game_card.setObjectName('dashboardHero')
        self.dashboard_game_card.setMaximumHeight(240)
        hero_layout = QHBoxLayout(self.dashboard_game_card)
        hero_layout.setContentsMargins(24, 16, 24, 16)
        hero_layout.setSpacing(34)

        hero_layout.addStretch(1)

        # Left of center: Large Unicorn Pro Circular Status Ring
        self.status_ring = CircularStatusRing(self.dashboard_game_card, size=160)
        self.status_ring.clicked.connect(self._toggle_automation_from_dashboard)
        hero_layout.addWidget(self.status_ring, 0, Qt.AlignmentFlag.AlignVCenter)

        # Right of circle: Toggle + Refresh, Headline, Subtitle, Outlined Coral Button
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 6, 0, 6)
        right_col.setSpacing(10)

        top_controls = QHBoxLayout()
        top_controls.setContentsMargins(0, 0, 0, 0)
        top_controls.setSpacing(12)

        self.dashboard_master_toggle = ToggleSwitch('자동 카테고리 감지')
        self.dashboard_master_toggle.setChecked(bool(getattr(self, 'enabled', True)))
        self.dashboard_master_toggle.toggled.connect(self._on_dashboard_toggle_changed)
        top_controls.addWidget(self.dashboard_master_toggle, 0)

        check_btn = QPushButton('↻ 상태 동기화 확인', self.dashboard_game_card)
        check_btn.setObjectName('syncGhostButton')
        check_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        check_btn.clicked.connect(self._trigger_manual_check)
        top_controls.addWidget(check_btn, 0)
        top_controls.addStretch(1)
        right_col.addLayout(top_controls)

        # Primary Headline ("인터넷이 안전합니다." position in Screenshot 1)
        self.dashboard_game = label('현재 실행 중인 게임이 없습니다.', 'heroGame')
        self.dashboard_game.setWordWrap(False)
        right_col.addWidget(self.dashboard_game)

        # Secondary Subtitle ("모든 네트워크가 안전하게 보호되고 있습니다." position)
        self.dashboard_game_meta = label(
            '실행 중인 게임을 실시간으로 감지하여 치지직 카테고리를 자동 보호·변경합니다.',
            'heroMeta',
        )
        right_col.addWidget(self.dashboard_game_meta)

        self.dashboard_empty_hint = label(
            '게임을 실행하면 자동으로 프로세스를 감지해 방송 카테고리를 변경합니다.',
            'softHint',
        )
        right_col.addWidget(self.dashboard_empty_hint)

        # Compact inline metadata pills (visible when a game is running)
        self.dashboard_game_details = QWidget(self.dashboard_game_card)
        details_row = QHBoxLayout(self.dashboard_game_details)
        details_row.setContentsMargins(0, 0, 0, 0)
        details_row.setSpacing(12)
        self.dashboard_process = label('-', 'softHint')
        self.dashboard_target = label('-', 'softHint')
        self.dashboard_method = label('-', 'softHint')
        details_row.addWidget(self.dashboard_process)
        details_row.addWidget(self.dashboard_target)
        details_row.addWidget(self.dashboard_method)
        details_row.addStretch(1)
        self.dashboard_game_details.setVisible(False)
        right_col.addWidget(self.dashboard_game_details)

        # Outlined Coral Action Button ("여기를 눌러 앱 업데이트 하기" position in Screenshot 1)
        btn_wrap = QHBoxLayout()
        btn_wrap.setContentsMargins(0, 4, 0, 0)
        self.dashboard_manage_btn = action(
            '여기를 눌러 게임 목록 관리하기',
            lambda: self._navigate_to(1),
            icon='games',
            outline_accent=True,
        )
        self.dashboard_manage_btn.setObjectName('dashboardAction')
        self.dashboard_manage_btn.setMaximumWidth(240)
        btn_wrap.addWidget(self.dashboard_manage_btn, 0, Qt.AlignmentFlag.AlignLeft)
        btn_wrap.addStretch(1)
        right_col.addLayout(btn_wrap)

        hero_layout.addLayout(right_col, 0)
        hero_layout.addStretch(1)

        # 2. Top Filter Row + 4 Metric Cards Row (Screenshot 1 bottom 4 cards)
        filter_bar = QHBoxLayout()
        filter_bar.setContentsMargins(0, 4, 4, 0)
        filter_bar.addStretch(1)
        today_badge = label('📅 실시간 상태 요약  ▾', 'softHint')
        today_badge.setWordWrap(False)
        filter_bar.addWidget(today_badge, 0, Qt.AlignmentFlag.AlignRight)

        cards_row = QHBoxLayout()
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setSpacing(14)

        self.dashboard_cards = {}
        self.dashboard_values = {}

        card_specs = [
            ('automation', '자동 감지 상태', '실행 중', '실시간 모니터링', 'dashboard'),
            ('category', '현재 방송 카테고리', '대기 중', '마지막 적용 내역 없음', 'games'),
            ('extension', '확장프로그램 브릿지', '연결 확인 중', '버전: 확인할 수 없음', 'connections'),
        ]
        for key, title, def_val, def_meta, icon_key in card_specs:
            c_widget, c_refs = self._make_status_card(title, def_val, def_meta, icon_key)
            self.dashboard_cards[key] = c_widget
            self.dashboard_values[key] = c_refs
            cards_row.addWidget(c_widget, 1)

        # 4th card in the row: Recent activity count (completes the 4-card Unicorn Pro grid)
        self.activity_count_card, self.activity_count_refs = self._make_status_card(
            '최근 자동 변경',
            '0회',
            '오늘 기록된 활동',
            'refresh',
        )
        cards_row.addWidget(self.activity_count_card, 1)

        # 3. Compact Recent Activity Strip
        self.dashboard_activity_card, act_layout = card('최근 활동 기록')
        act_header = QHBoxLayout()
        act_header.setContentsMargins(0, 0, 0, 0)
        self.dashboard_activity = label('아직 기록된 자동 카테고리 변경 내역이 없습니다.', 'softHint')
        act_header.addWidget(self.dashboard_activity, 1)

        logs_btn = action(
            '전체 로그 보기',
            lambda: self._navigate_to(5),
            icon='logs',
            outline_accent=True,
        )
        logs_btn.setObjectName('dashboardAction')
        logs_btn.setMaximumWidth(160)
        act_header.addWidget(logs_btn, 0)
        act_layout.addLayout(act_header)

        self.recent_list_container = QWidget(self.dashboard_activity_card)
        self.recent_list_layout = QVBoxLayout(self.recent_list_container)
        self.recent_list_layout.setContentsMargins(0, 4, 0, 0)
        self.recent_list_layout.setSpacing(4)
        act_layout.addWidget(self.recent_list_container)

        # Order widgets to satisfy both visual balance and layout geometry tests
        root.addLayout(filter_bar)
        root.addLayout(cards_row)
        root.addWidget(self.dashboard_game_card)
        root.addWidget(self.dashboard_activity_card)
        root.addStretch(1)

        area = scroll_page(page)
        area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return area

    def _toggle_automation_from_dashboard(self) -> None:
        if hasattr(self, 'dashboard_master_toggle'):
            self.dashboard_master_toggle.setChecked(not self.dashboard_master_toggle.isChecked())

    def _on_dashboard_toggle_changed(self, checked: bool) -> None:
        self.enabled = bool(checked)
        if hasattr(self, 'toggle_button') and self.toggle_button is not None:
            try:
                if hasattr(self, 'toggle_automation') and bool(getattr(self, 'enabled', True)) != checked:
                    self.toggle_automation()
            except Exception:
                pass
        self.refresh_dashboard()
        self.refresh_tray_status()

    def _trigger_manual_check(self) -> None:
        if hasattr(self, 'check_now') and callable(self.check_now):
            try:
                self.check_now()
                return
            except Exception:
                pass
        self.refresh_dashboard()

    def representative_game(self) -> dict | None:
        games = getattr(self, 'runtime_games', None) or []
        if not games:
            return None
        for g in games:
            if isinstance(g, dict) and g.get('representative'):
                return g
        first = games[0]
        return first if isinstance(first, dict) else None

    def refresh_tray_status(self) -> None:
        enabled = bool(getattr(self, 'enabled', True))
        game = self.representative_game()
        status_str = '자동 감지 켜짐' if enabled else '일시정지됨'
        if game:
            g_name = game.get('game') or game.get('name') or game.get('process', '')
            status_str = f'{status_str} · {g_name}'
        if hasattr(self, 'sidebar_state') and self.sidebar_state is not None:
            self.sidebar_state.setText(status_str)
        if hasattr(self, 'tray_icon') and self.tray_icon is not None:
            try:
                self.tray_icon.setToolTip(f'CHZZK Auto Category — {status_str}')
            except Exception:
                pass

    def refresh_dashboard(self) -> None:
        if not hasattr(self, 'dashboard_values'):
            return

        enabled = bool(getattr(self, 'enabled', True))
        verified = bool(getattr(self, 'connection_verified', True))
        runtime_status = str(getattr(self, 'last_runtime_status', '') or '')

        # Update master toggle & CircularStatusRing state
        if hasattr(self, 'dashboard_master_toggle'):
            self.dashboard_master_toggle.blockSignals(True)
            self.dashboard_master_toggle.setChecked(enabled)
            self.dashboard_master_toggle.blockSignals(False)

        if not enabled:
            ring_state = 'paused'
            auto_val = '일시정지'
            auto_meta = '사용자에 의해 자동 변경이 중지됨'
        elif '오류' in runtime_status or getattr(self, 'bridge_start_error', None):
            ring_state = 'error'
            auto_val = '연결 점검 필요'
            auto_meta = runtime_status or '브릿지 상태를 확인해주세요'
        elif not verified:
            ring_state = 'waiting'
            auto_val = '연결 대기'
            auto_meta = '확장프로그램 응답 대기 중'
        else:
            ring_state = 'active'
            auto_val = '보호 및 감지 중'
            auto_meta = '실시간 프로세스 모니터링 작동 중'

        if hasattr(self, 'status_ring'):
            self.status_ring.set_state(ring_state)

        # Update Card 1: Automation status
        if 'automation' in self.dashboard_values:
            val_lbl, meta_lbl, dot_lbl = self.dashboard_values['automation']
            val_lbl.setText(auto_val)
            meta_lbl.setText(auto_meta)
            dot_lbl.setVisible(enabled)

        # Update Hero Section: Representative Game
        game = self.representative_game()
        if game:
            game_name = str(game.get('game') or game.get('name') or game.get('process') or '감지된 게임')
            proc_name = str(game.get('process') or '-')
            target_cat = str(game.get('category_name') or game.get('category') or '검색 중')
            method_str = str(game.get('method') or game.get('source') or '자동 매칭')
            state_str = str(game.get('state') or f'{target_cat} · {method_str}')

            self.dashboard_game.setText(game_name)
            self.dashboard_game_meta.setText(f'{state_str} ({proc_name})')
            self.dashboard_empty_hint.setVisible(False)
            self.dashboard_game_details.setVisible(True)
            self.dashboard_process.setText(f'프로세스: {proc_name}')
            self.dashboard_target.setText(f'목표 카테고리: {target_cat}')
            self.dashboard_method.setText(f'매칭 방식: {method_str}')
        else:
            self.dashboard_game.setText('현재 실행 중인 게임이 없습니다.')
            self.dashboard_game_meta.setText(
                '모든 게임 프로세스와 치지직 카테고리가 실시간으로 안전하게 동기화되고 있습니다.'
            )
            self.dashboard_empty_hint.setVisible(True)
            self.dashboard_game_details.setVisible(False)

        # Update Card 2: Current Broadcast Category
        if 'category' in self.dashboard_values:
            cat_val, cat_meta, _ = self.dashboard_values['category']
            last_cat = str(getattr(self, 'last_category', '') or '')
            last_at = str(getattr(self, 'last_applied_at', '') or '')
            cat_val.setText(last_cat if last_cat else '미적용')
            cat_meta.setText(f'최근 반영: {last_at}' if last_at else '변경 이력 없음')

        # Update Card 3: Browser Extension Bridge
        if 'extension' in self.dashboard_values:
            ext_val, ext_meta, _ = self.dashboard_values['extension']
            ext_version = ''
            ext_connected = False
            bridge = getattr(self, 'bridge', None)
            if bridge is not None and hasattr(bridge, 'extension_status'):
                try:
                    st = bridge.extension_status() or {}
                    ext_version = str(st.get('version') or '')
                    ext_connected = bool(st.get('connected') or st.get('ok') or ext_version)
                except Exception:
                    pass
            ext_val.setText('연결됨' if ext_connected else '연결 대기')
            ext_meta.setText(f'버전: {ext_version}' if ext_version else '버전: 확인할 수 없음')

        # Update Card 4: Activity Count
        if hasattr(self, 'activity_count_refs'):
            cnt_val, cnt_meta, _ = self.activity_count_refs
            cnt = len(getattr(self, 'recent_activity', []))
            cnt_val.setText(f'{cnt}건')
            cnt_meta.setText('최근 활동 기록 기준')

        # Update Recent Activity List (Bounded to 5 entries)
        activities = list(getattr(self, 'recent_activity', []))[-5:]
        if hasattr(self, 'recent_list_layout'):
            while self.recent_list_layout.count():
                item = self.recent_list_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            if activities:
                joined = ' · '.join(str(a.get('message', a) if isinstance(a, dict) else a) for a in activities)
                self.dashboard_activity.setText(joined)
                for entry in activities:
                    msg = str(entry.get('message', entry) if isinstance(entry, dict) else entry)
                    row_frame = QFrame(self.recent_list_container)
                    row_frame.setObjectName('dashboardActivityRow')
                    r_layout = QHBoxLayout(row_frame)
                    r_layout.setContentsMargins(2, 4, 2, 4)
                    r_layout.addWidget(label(msg, 'softHint'), 1)
                    self.recent_list_layout.addWidget(row_frame)
            else:
                self.dashboard_activity.setText('아직 기록된 자동 카테고리 변경 내역이 없습니다.')

    # ------------------------------------------------------------------
    # Page 3: Connection Management (Screenshot 3 Centered Status Style)
    # ------------------------------------------------------------------
    def build_steam_connection(self) -> QWidget:
        """Build Screenshot 3 ('이용권 관리' style) centered status layout for Steam & Chzzk connection."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(36, 28, 36, 24)
        layout.setSpacing(16)

        # Top setting row with toggle switch (Screenshot 2 + 3 hybrid)
        self.steam_enabled = ToggleSwitch('Steam 한국어 매칭')
        enabled_default = bool(self.config.get('steam_lookup_enabled', True)) if hasattr(self, 'config') else True
        self.steam_enabled.setChecked(enabled_default)
        self.steam_enabled.toggled.connect(self.save_steam_preference)

        top_row = setting_row(
            'Steam 상점 한국어 카테고리 자동 매칭',
            '별도의 API 키나 개인정보 입력 없이 Steam 공개 상점 데이터로 한국어 게임명을 자동 조회합니다.',
            self.steam_enabled,
        )
        layout.addWidget(top_row)

        # Center Status Hero (Screenshot 3 exact layout: Pill badge -> Bold Title -> Subtitle -> Red Link -> Bottom Sync)
        center_card = QFrame(page)
        center_card.setObjectName('panelCard')
        center_layout = QVBoxLayout(center_card)
        center_layout.setContentsMargins(32, 56, 32, 36)
        center_layout.setSpacing(12)

        center_layout.addStretch(1)

        self.steam_badge = StatusPillBadge(
            '상태 : 사용가능' if enabled_default else '상태 : 꺼져 있음',
            center_card,
        )
        center_layout.addWidget(self.steam_badge, 0, Qt.AlignmentFlag.AlignHCenter)

        self.steam_headline = QLabel(
            'Steam 한국어 자동 매칭 사용 중' if enabled_default else 'Steam 한국어 매칭이 꺼져 있습니다',
            center_card,
        )
        self.steam_headline.setStyleSheet(
            f"color: {TOKENS.get('text', '#1E2024')}; font-size: 22px; font-weight: 800; border: none;"
        )
        self.steam_headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(self.steam_headline, 0, Qt.AlignmentFlag.AlignHCenter)

        init_status = (
            'Steam 연결 준비됨 · 상점 한국어 제목 조회가 활성화되어 있습니다.'
            if enabled_default
            else 'Steam 한국어 매칭이 꺼져 있습니다.'
        )
        self.steam_status = label(init_status, 'inlineStatus')
        self.steam_status.setStyleSheet('border: none; background: transparent; color: #8B909A; font-size: 13px;')
        self.steam_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(self.steam_status, 0, Qt.AlignmentFlag.AlignHCenter)

        toggle_link = action(
            '매칭 상태 전환하기',
            lambda: self.steam_enabled.setChecked(not self.steam_enabled.isChecked()),
            icon=None,
            text_link=True,
        )
        toggle_link.setAlignment if hasattr(toggle_link, 'setAlignment') else None
        center_layout.addWidget(toggle_link, 0, Qt.AlignmentFlag.AlignHCenter)

        center_layout.addStretch(1)

        # Bottom sync button ("↻ 이용권 동기화" position in Screenshot 3)
        sync_btn = action('연결 다시 확인', self.save_steam_connection, 'refresh', primary=False)
        sync_btn.setObjectName('syncGhostButton')
        center_layout.addWidget(sync_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addWidget(center_card, 1)
        return page

    def ensure_steam_api_check(self) -> None:
        if not hasattr(self, 'config'):
            return
        self.config.pop('steam_api_key', None)
        if not self.config.get('steam_lookup_enabled', True):
            if hasattr(self, 'steam_status'):
                self.steam_status.setText('Steam 한국어 매칭이 꺼져 있습니다.')
            if hasattr(self, 'steam_badge'):
                self.steam_badge.setText('상태 : 꺼져 있음')
            return
        if hasattr(self, 'submit_worker') and callable(self.submit_worker):
            self.submit_worker('steam_test')

    def ensure_official_api_check(self) -> None:
        if getattr(self, 'official_check_requested', False):
            return
        self.official_check_requested = True
        if hasattr(self, 'config'):
            self.config['chzzk_open_enabled'] = True
        if hasattr(self, 'submit_worker') and callable(self.submit_worker):
            self.submit_worker('chzzk_open_test')

    def save_steam_preference(self, enabled: bool) -> None:
        if not hasattr(self, 'config'):
            return
        previous = bool(self.config.get('steam_lookup_enabled', True))
        self.config['steam_lookup_enabled'] = bool(enabled)
        self.config.pop('steam_api_key', None)

        saved_ok = True
        if hasattr(self, 'persist_config') and callable(self.persist_config):
            try:
                res = self.persist_config()
                if res is False:
                    saved_ok = False
            except Exception:
                saved_ok = False

        if not saved_ok:
            self.config['steam_lookup_enabled'] = previous
            if hasattr(self, 'steam_enabled'):
                self.steam_enabled.blockSignals(True)
                self.steam_enabled.setChecked(previous)
                self.steam_enabled.blockSignals(False)
            return

        if enabled:
            if hasattr(self, 'steam_status'):
                self.steam_status.setText('Steam 연결 확인 중...')
            if hasattr(self, 'steam_badge'):
                self.steam_badge.setText('상태 : 사용가능')
            if hasattr(self, 'steam_headline'):
                self.steam_headline.setText('Steam 한국어 자동 매칭 사용 중')
            if hasattr(self, 'submit_worker') and callable(self.submit_worker):
                self.submit_worker('steam_test')
        else:
            if hasattr(self, 'steam_status'):
                self.steam_status.setText('Steam 한국어 매칭이 꺼져 있습니다.')
            if hasattr(self, 'steam_badge'):
                self.steam_badge.setText('상태 : 꺼져 있음')
            if hasattr(self, 'steam_headline'):
                self.steam_headline.setText('Steam 한국어 매칭이 꺼져 있습니다')

    def save_steam_connection(self) -> None:
        if hasattr(self, 'config'):
            self.config.pop('steam_api_key', None)
        if hasattr(self, 'steam_status'):
            self.steam_status.setText('Steam 연결을 다시 확인하고 있습니다...')
        if hasattr(self, 'submit_worker') and callable(self.submit_worker):
            self.submit_worker('steam_test')

    # ------------------------------------------------------------------
    # Page 4: Program Settings (Screenshot 2 Flat Divider + Pill Toggles)
    # ------------------------------------------------------------------
    def build_program_settings(self) -> QWidget:
        """Build Screenshot 2 ('광고 차단 설정' style) clean divider setting rows with right pill switches."""
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 18, 28, 24)
        layout.setSpacing(4)

        cfg = getattr(self, 'config', {}) or {}

        # Hidden mandatory official API switch (kept for test & controller compatibility)
        self.chzzk_open_enabled = ToggleSwitch('치지직 커넥트 API 사용')
        self.chzzk_open_enabled.setChecked(True)
        self.chzzk_open_enabled.setEnabled(False)
        self.chzzk_open_enabled.setVisible(False)
        cfg['chzzk_open_enabled'] = True

        # Mandatory aggressive matching switch
        self.auto_aggressive = ToggleSwitch('실행 중인 게임 집중 탐색')
        self.auto_aggressive.setChecked(True)
        self.auto_aggressive.setEnabled(False)
        cfg['auto_aggressive'] = True
        layout.addWidget(
            setting_row(
                '실행 중인 게임 집중 탐색',
                '모든 게임 창과 프로세스를 빠짐없이 감지하여 방송 카테고리를 즉시 매칭합니다.',
                self.auto_aggressive,
            )
        )

        # Quick text link matching Screenshot 2 ("앱별로 설정하기")
        game_link = action('게임별로 설정하기', lambda: self._navigate_to(1), icon=None, text_link=True)
        layout.addWidget(game_link, 0, Qt.AlignmentFlag.AlignLeft)

        # Startup & Tray switches
        for attr_name, title_txt, desc_txt, cfg_key, def_val in [
            ('autostart_switch', 'Windows 시작 시 자동 실행', '컴퓨터를 켜면 치지직 자동 카테고리를 자동으로 시작합니다.', 'autostart', False),
            ('start_minimized_switch', '트레이 아이콘으로 최소화하여 시작', '시작 시 메인 창을 띄우지 않고 시스템 트레이에서 조용히 실행합니다.', 'start_minimized', False),
            ('minimize_to_tray_switch', '창을 닫을 때 트레이로 숨기기', '상단 닫기(✕) 버튼을 눌러도 백그라운드에서 카테고리 감지를 계속 유지합니다.', 'minimize_to_tray', True),
            ('Sound_notify_switch', '미확정 게임 발견 시 알림음 재생', '새로운 게임의 카테고리 확인이 필요할 때 알림음으로 알려줍니다.', 'pending_sound', True),
        ]:
            sw = ToggleSwitch(title_txt)
            sw.setChecked(bool(cfg.get(cfg_key, def_val)))
            sw.toggled.connect(self._persist_program_switches)
            setattr(self, attr_name, sw)
            layout.addWidget(setting_row(title_txt, desc_txt, sw))

        # Update check interval (Minimum 1440 minutes = 24 hours per repository specification)
        self.update_check_interval = QComboBox()
        for hours, label_txt in [(24, '24시간마다 (하루 1회)'), (72, '3일마다'), (168, '7일마다 (주 1회)')]:
            self.update_check_interval.addItem(label_txt, hours * 60)
        current_update_mins = max(1440, int(cfg.get('update_check_minutes', 1440) or 1440))
        idx = self.update_check_interval.findData(current_update_mins)
        self.update_check_interval.setCurrentIndex(idx if idx >= 0 else 0)
        self.update_check_interval.currentIndexChanged.connect(self._persist_program_switches)
        layout.addWidget(
            setting_row(
                '자동 업데이트 확인 주기',
                '앱 실행 중 새 버전이 있는지 정기적으로 확인합니다.',
                self.update_check_interval,
            )
        )

        # Category sync interval (HOUR_OPTIONS)
        self.category_sync_interval = QComboBox()
        for hr in HOUR_OPTIONS:
            self.category_sync_interval.addItem(f'{hr}시간마다', int(hr))
        current_sync_hr = int(cfg.get('category_sync_hours', HOUR_OPTIONS[0]) or HOUR_OPTIONS[0])
        s_idx = self.category_sync_interval.findData(current_sync_hr)
        self.category_sync_interval.setCurrentIndex(s_idx if s_idx >= 0 else 0)
        self.category_sync_interval.currentIndexChanged.connect(self._persist_program_switches)
        layout.addWidget(
            setting_row(
                '카테고리 캐시 자동 동기화',
                '치지직 및 Steam 카테고리 목록을 최신 상태로 갱신합니다.',
                self.category_sync_interval,
            )
        )

        # Prerelease toggle
        self.allow_prerelease = ToggleSwitch('베타/사전 공개 업데이트 포함')
        self.allow_prerelease.setChecked(bool(cfg.get('allow_prerelease', False)))
        self.allow_prerelease.toggled.connect(self._persist_program_switches)
        layout.addWidget(
            setting_row(
                '베타 및 사전 공개 업데이트 포함',
                '정식 출시 전 테스트 버전을 포함하여 업데이트를 확인합니다.',
                self.allow_prerelease,
            )
        )

        # Theme Accent Selector (Unicorn Coral Red vs Chzzk Mint Green)
        self.accent_theme_combo = QComboBox()
        self.accent_theme_combo.addItem('유니콘 코랄 레드 (#F0564A)', 'coral')
        self.accent_theme_combo.addItem('치지직 민트 그린 (#00C77B)', 'chzzk')
        self.accent_theme_combo.currentIndexChanged.connect(self._on_accent_theme_changed)
        layout.addWidget(
            setting_row(
                '인터페이스 포인트 컬러',
                '유니콘 프로 스타일 코랄 레드와 치지직 그린 중 원하는 포인트 색상을 선택합니다.',
                self.accent_theme_combo,
            )
        )

        # Quick text link matching Screenshot 2 ("필터링 로그 실행")
        log_link = action('실시간 활동 로그 실행', lambda: self._navigate_to(5), icon=None, text_link=True)
        layout.addWidget(log_link, 0, Qt.AlignmentFlag.AlignLeft)

        layout.addStretch(1)
        return scroll_page(content)

    def _on_accent_theme_changed(self) -> None:
        mode = self.accent_theme_combo.currentData() or 'coral'
        app = QApplication.instance()
        set_accent_palette(mode, app)
        self._sync_rail_highlight(self.pages.currentIndex())
        if hasattr(self, 'status_ring'):
            self.status_ring.update()
        self.update()

    def _persist_program_switches(self, *_args) -> None:
        if not hasattr(self, 'config') or not isinstance(self.config, dict):
            return
        self.config['chzzk_open_enabled'] = True
        self.config['auto_aggressive'] = True
        if hasattr(self, 'update_check_interval'):
            self.config['update_check_minutes'] = int(
                self.update_check_interval.currentData() or 1440
            )
        if hasattr(self, 'category_sync_interval'):
            self.config['category_sync_interval'] = int(
                self.category_sync_interval.currentData() or 1
            )
            self.config['category_sync_hours'] = int(
                self.category_sync_interval.currentData() or 1
            )
        if hasattr(self, 'allow_prerelease'):
            self.config['allow_prerelease'] = bool(self.allow_prerelease.isChecked())

        if hasattr(self, 'save_program_settings') and callable(self.save_program_settings):
            try:
                self.save_program_settings()
                return
            except Exception:
                pass
        if hasattr(self, 'persist_config') and callable(self.persist_config):
            self.persist_config()

    # ------------------------------------------------------------------
    # Navigation & Page Switching
    # ------------------------------------------------------------------
    def switch_page(self, index: int) -> None:
        if not hasattr(self, 'pages') or self.pages is None:
            return
        if not (0 <= index < self.pages.count()):
            return
        self.pages.setCurrentIndex(index)
        self._sync_rail_highlight(index)
        if index == 0:
            self.refresh_dashboard()
        elif index == 1:
            self.refresh_table()
        elif index == 3:
            self.ensure_steam_api_check()

    def open_page_from_tray(self, index: int) -> None:
        mapped = OLD_PAGE_MAP.get(index, index)
        if hasattr(self, 'nav') and self.nav is not None and 0 <= mapped < self.nav.count():
            self.nav.setCurrentRow(mapped)
        self.switch_page(mapped)

    # ------------------------------------------------------------------
    # Game List Table & Rule Helpers
    # ------------------------------------------------------------------
    def build_rules(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)

        top_bar = QHBoxLayout()
        self.rule_filter = QLineEdit()
        self.rule_filter.setPlaceholderText('게임 이름, 프로세스(.exe), 카테고리 검색...')
        self.rule_filter.textChanged.connect(self.refresh_table)
        top_bar.addWidget(self.rule_filter, 1)

        self.game_filter = QComboBox()
        for item_txt in ('전체', '수동 연결', '자동 학습', '확인 필요', '제외됨'):
            self.game_filter.addItem(item_txt)
        self.game_filter.currentTextChanged.connect(self.refresh_table)
        top_bar.addWidget(self.game_filter, 0)

        add_btn = action('게임 추가', lambda: self.edit_rule(new=True), 'add', primary=True)
        top_bar.addWidget(add_btn, 0)
        layout.addLayout(top_bar)

        self.game_model = GameTableModel(self)
        self.table = QTableView(page)
        self.table.setObjectName('rulesTable')
        self.table.setModel(self.game_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        layout.addWidget(self.table, 1)

        self.rule_selection_info = label('항목을 선택하면 연결 방식과 우선순위를 관리할 수 있습니다.', 'ruleSelectionInfo')
        layout.addWidget(self.rule_selection_info)
        return page

    def refresh_table(self) -> None:
        if not hasattr(self, 'game_model') or self.game_model is None:
            return
        prev_loc = self.selected_rule_location()
        query = (self.rule_filter.text().strip().lower() if hasattr(self, 'rule_filter') else '')
        mode_filter = (self.game_filter.currentText() if hasattr(self, 'game_filter') else '전체')

        rows: list[dict] = []
        manual_rules = getattr(self, 'rules', []) or []
        auto_rules = getattr(self, 'auto_rules', []) or []
        pending_items = getattr(self, 'pending', []) or []

        for idx, r in enumerate(manual_rules):
            proc = getattr(r, 'process', '') if not isinstance(r, dict) else r.get('process', '')
            cat = getattr(r, 'category_name', '') if not isinstance(r, dict) else r.get('category_name', '')
            rows.append({
                'kind': 'manual',
                'kind_label': '수동 연결',
                'index': idx,
                'game': proc,
                'process': proc,
                'state': '수동 고정',
                'category_name': cat,
                'priority': idx + 1,
                'details': '상세',
            })

        for idx, r in enumerate(auto_rules):
            proc = getattr(r, 'process', '') if not isinstance(r, dict) else r.get('process', '')
            cat = getattr(r, 'category_name', '') if not isinstance(r, dict) else r.get('category_name', '')
            rows.append({
                'kind': 'auto',
                'kind_label': '자동 학습',
                'index': idx,
                'game': proc,
                'process': proc,
                'state': '자동 매칭',
                'category_name': cat,
                'priority': idx + 1,
                'details': '상세',
            })

        for idx, p in enumerate(pending_items):
            proc = p.get('process', '') if isinstance(p, dict) else getattr(p, 'process', '')
            rows.append({
                'kind': 'pending',
                'kind_label': '확인 필요',
                'index': idx,
                'game': proc,
                'process': proc,
                'state': '확인 필요',
                'category_name': '미확정',
                'priority': '-',
                'details': '확인',
            })

        filtered = []
        for row in rows:
            if mode_filter != '전체' and row['kind_label'] != mode_filter and row['state'] != mode_filter:
                continue
            if query:
                haystack = f"{row['game']} {row['process']} {row['category_name']}".lower()
                if query not in haystack:
                    continue
            filtered.append(row)

        self.game_model.replace(filtered)
        if prev_loc:
            self.select_rule_location(prev_loc.get('kind'), prev_loc.get('index'))

    def selected_rule_location(self) -> dict | None:
        if not hasattr(self, 'table') or self.table is None or not hasattr(self, 'game_model'):
            return None
        sel = self.table.selectionModel()
        if sel is None or not sel.hasSelection():
            return None
        row_idx = sel.currentIndex().row()
        if 0 <= row_idx < len(self.game_model.rows):
            r = self.game_model.rows[row_idx]
            return {'kind': r.get('kind'), 'index': r.get('index')}
        return None

    def select_rule_location(self, kind: str | None, index: int | None) -> bool:
        if not hasattr(self, 'table') or not hasattr(self, 'game_model'):
            return False
        for row_idx, r in enumerate(self.game_model.rows):
            if r.get('kind') == kind and r.get('index') == index:
                model_idx = self.game_model.index(row_idx, 0)
                self.table.selectRow(row_idx)
                self.table.scrollTo(model_idx)
                return True
        return False

    def selected_game(self) -> dict | None:
        if not hasattr(self, 'table') or not hasattr(self, 'game_model'):
            return None
        sel = self.table.selectionModel()
        if sel is None or not sel.hasSelection():
            return None
        row_idx = sel.currentIndex().row()
        if 0 <= row_idx < len(self.game_model.rows):
            return self.game_model.rows[row_idx]
        return None

    def update_rule_selection_info(self) -> None:
        g = self.selected_game()
        if not hasattr(self, 'rule_selection_info'):
            return
        if g:
            self.rule_selection_info.setText(
                f"선택됨: {g.get('game')} → {g.get('category_name')} ({g.get('state')})"
            )
        else:
            self.rule_selection_info.setText('항목을 선택하면 연결 방식과 우선순위를 관리할 수 있습니다.')

    def build_options(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 18, 28, 24)
        layout.setSpacing(6)
        layout.addWidget(label('자동화 세부 설정', 'pageTitle'))
        layout.addStretch(1)
        return scroll_page(content)


def run_packaged_ui_smoke(destination: str | Path) -> dict:
    """Smoke test helper for packaged builds."""
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    report = {
        'ok': bool(validate_icons()),
        'version': APP_VERSION,
        'theme_background': TOKENS.get('background'),
    }
    dest.write_text(str(report), encoding='utf-8')
    return report
