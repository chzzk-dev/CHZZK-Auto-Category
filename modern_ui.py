"""Six persistent pages over the existing app controller and worker signals."""
import copy
from collections import deque
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSize, QTimer
from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout,
    QGridLayout, QScrollArea, QTabWidget, QListWidgetItem, QComboBox, QLineEdit,
    QCheckBox, QTableView, QHeaderView, QAbstractItemView, QPushButton, QDialog,
    QFormLayout, QTextEdit, QApplication, QToolButton, QLayout, QSizePolicy)
from app_icons import app_icon, set_button_icon
from core import Rule
from normalization import normalized_name, alias_conflicts
from scheduling import HOUR_OPTIONS
from storage import save_config, get_steam_api_key
from theme import TOKENS
from ui_components import ToggleSwitch, SettingsComboBox as QComboBox, FramelessDialog as QDialog
from version import APP_VERSION

PAGES = (
    ('대시보드', '게임 감지부터 방송 카테고리 변경까지 자동으로 관리합니다.', 'dashboard'),
    ('게임 목록', '감지된 게임과 치지직 카테고리 연결을 관리합니다.', 'games'),
    ('자동화 설정', '게임 감지, 검증, 자동 변경의 동작을 설정합니다.', 'automation'),
    ('연결 관리', '치지직 계정과 브라우저 확장프로그램 연결을 확인합니다.', 'connections'),
    ('설정', '백그라운드 동작, 업데이트, 프로그램 정보를 관리합니다.', 'settings'),
    ('로그', '감지부터 변경 결과까지 실제 활동 기록을 확인합니다.', 'logs'),
)


def run_packaged_ui_smoke(destination):
    """UI diagnostic; explicit CI opt-in also verifies the compiled Steam key online."""
    import json
    import os
    import sys
    import tempfile
    from app_icons import validate_icons
    from storage import normalize_config
    from main import Window
    app = QApplication.instance()
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    original = os.environ.get('LOCALAPPDATA')
    with tempfile.TemporaryDirectory(prefix='chzzk-ui-smoke-') as directory:
        os.environ['LOCALAPPDATA'] = directory
        try:
            w = Window(normalize_config({'autostart': False, 'auto_update': False,
                                         'auto_start_change': False}), preview=True)
            w.show()
            app.processEvents()
            assert validate_icons(), 'Bundled QtAwesome fonts are missing'
            assert w.pages.count() == 6
            for i in range(6):
                w.nav.setCurrentRow(i)
                app.processEvents()
                assert w.grab().save(str(destination / f'page-{i}.png'))
            w.connection_tabs.setCurrentIndex(2)
            w.nav.setCurrentRow(3)
            app.processEvents()
            assert not w.findChildren(QLineEdit, 'steamApiKeyInput')
            assert w.grab().save(str(destination / 'steam-connection.png'))
            native = [name for name in ('main', 'modern_ui', 'app_icons', 'theme', 'automation', 'worker', 'steam_lookup', 'storage')
                      if getattr(sys.modules.get(name), '__file__', '').endswith(('.pyd', '.so'))]
            if getattr(sys, 'frozen', False):
                assert len(native) == 8, 'A first-party native module was replaced with source'
            checks = {'icons': True, 'pages': 6, 'native_modules': native,
                      'frozen': bool(getattr(sys, 'frozen', False))}
            if os.environ.get('CHZZK_VERIFY_STEAM_API') == 'true':
                from storage import APP_STEAM_WEB_API_KEY
                from steam_lookup import SteamResolver, valid_key
                probe = SteamResolver('', Path(directory) / 'steam-smoke.json')
                try:
                    assert probe.test_store_connection(), 'Steam public Store connection failed'
                    record = probe.resolve({'id': 'ci-mimesis', 'name': 'MIMESIS', 'aliases': [],
                                            'steam_app_ids': [2827200]}, 'mimesis.exe')
                    assert record and record['appid'] == 2827200 and record['localized_name'] == '미메시스', 'Steam localized lookup failed'
                finally:
                    probe.close()
                checks.update(steam_keyless_lookup=True, steam_api_connected=True, steam_localized_lookup=True)
                if APP_STEAM_WEB_API_KEY:
                    assert valid_key(APP_STEAM_WEB_API_KEY), 'Bundled Steam fallback key is invalid'
                    assert get_steam_api_key() == APP_STEAM_WEB_API_KEY, 'Steam smoke must use the bundled key'
                    probe = SteamResolver(get_steam_api_key(), Path(directory) / 'steam-fallback-smoke.json')
                    try:
                        assert probe.test_connection(), 'Steam fallback API authentication failed'
                    finally:
                        probe.close()
                    checks['steam_builtin_key'] = True
            (destination / 'packaged-checks.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
            w.quitting = True
            w.close()
            w.deleteLater()
            app.processEvents()
        finally:
            if original is None:
                os.environ.pop('LOCALAPPDATA', None)
            else:
                os.environ['LOCALAPPDATA'] = original
    return 0


def label(text, name='softHint'):
    result = QLabel(text)
    result.setObjectName(name)
    result.setWordWrap(True)
    result.setTextFormat(Qt.TextFormat.PlainText)
    return result


def action(text, callback, icon='info', primary=False):
    result = QPushButton(text)
    if primary:
        result.setObjectName('primary')
    set_button_icon(result, icon, '#FFFFFF' if primary else '#252525')
    result.clicked.connect(callback)
    return result


def card(title):
    widget = QFrame()
    widget.setObjectName('panelCard')
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(14)
    layout.addWidget(label(title, 'sectionTitle'))
    return widget, layout


def setting_row(title, description, control):
    row = QFrame()
    row.setObjectName('settingRow')
    row.setMinimumHeight(64)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 9, 0, 9)
    layout.setSpacing(24)
    text = QVBoxLayout()
    text.setSpacing(4)
    text.addWidget(label(title, 'settingTitle'))
    text.addWidget(label(description, 'settingDescription'))
    layout.addLayout(text, 1)
    if isinstance(control, QComboBox):
        control.setMinimumWidth(140)
        control.setMaximumWidth(190)
    control.setAccessibleName(title)
    layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
    return row


def scroll_page(widget):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(widget)
    return scroll


def settings_shell(content, save):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    layout.addWidget(scroll_page(content), 1)
    footer = QHBoxLayout()
    footer.addStretch()
    footer.addWidget(action('설정 저장', save, 'success', True))
    layout.addLayout(footer)
    return page


class GameTableModel(QAbstractTableModel):
    headers = ('게임', '실행 파일', '치지직 카테고리', '연결 방식', '상태', '작업')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        row = self.rows[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return row
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            values = (row['game'], row['process'], row.get('category', '미확정'),
                      row['mode'], row['state'], '자세히')
            return values[index.column()]
        if role == Qt.ItemDataRole.DecorationRole and index.column() == 5:
            return app_icon('details', '#C7C4BC')

    def replace(self, rows):
        if rows == self.rows:
            return
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()


class ModernWindowMixin:
    def __init__(self, config, preview=False):
        self.ui_ready = False
        self.runtime_games = {}
        self.game_log_running = {}
        self.quick_rule_callbacks = {}
        self.official_check_requested = False
        self.league_session_token = None
        self.active_league_dialog = None
        self.league_selected_session = None
        self.recent_activity = deque(maxlen=5)
        self.last_category = None
        self.connection_retry_at = 0
        self.connection_failures = 0
        self.last_category_observed_at = 0
        self.last_applied_at = None
        super().__init__(config, preview)
        # Reparent existing functional pages, keeping controller fields/signals alive.
        old = [self.pages.widget(i) for i in range(self.pages.count())]
        for page in old:
            self.pages.removeWidget(page)
        self.dashboard = self.build_dashboard()
        self.game_tabs = QTabWidget()
        self.game_tabs.addTab(old[0], '연결 관리')
        self.game_tabs.addTab(old[3], '미확정 항목')
        self.connection_tabs = QTabWidget()
        self.connection_tabs.addTab(scroll_page(old[2]), '연결 상태')
        self.connection_tabs.addTab(scroll_page(old[1]), '계정 설정')
        self.connection_tabs.addTab(self.build_steam_connection(), 'Steam 한국어 매칭')
        self.setting_tabs = QTabWidget()
        self.setting_tabs.addTab(self.build_program_settings(), '일반')
        self.setting_tabs.addTab(scroll_page(old[6]), '업데이트')
        self.setting_tabs.addTab(scroll_page(old[7]), '정보')
        for page in (self.dashboard, self.game_tabs, old[5], self.connection_tabs, self.setting_tabs, old[4]):
            self.pages.addWidget(page)
        self.nav.blockSignals(True)
        self.nav.clear()
        self.nav.setIconSize(QSize(19, 19))
        for title, _, name in PAGES:
            self.nav.addItem(QListWidgetItem(app_icon(name, TOKENS['muted']), title))
        self.nav.blockSignals(False)
        self.install_icon_rail()
        self.ui_ready = True
        self.nav.setCurrentRow(0)
        self.switch_page(0)
        self.refresh_table()
        self.refresh_connection_page()
        self.refresh_dashboard()
        # Keep shell/buttons responsive at every logical DPI size.
        for widget in self.findChildren(QPushButton):
            widget.setAccessibleName(widget.text() or widget.toolTip() or '작업')
        self.log.document().setMaximumBlockCount(0)  # The row buffer, not HTML cell blocks, bounds memory.
        for note in old[4].findChildren(QLabel):
            if '200줄' in note.text():
                note.setText('주요 활동 · 최대 1,000건')
                note.setToolTip('중간 과정은 세부 과정 표시로 확인합니다. 상세 파일 로그는 최대 4MB 순환 저장합니다.')
        self.log_filter = QComboBox()
        self.log_filter.addItems(['전체', '게임 감지', '카테고리 검색', '자동 매칭', '카테고리 변경',
                                 '치지직 연결', '확장프로그램 통신', '업데이트', '오류'])
        old[4].layout().itemAt(0).layout().insertWidget(0, self.log_filter)
        self.log_filter.currentTextChanged.connect(self.render_logs)
        self.log_entries = deque(maxlen=1000)
        self.log_detail_entries = deque(maxlen=1000)
        self.log_sequence = 0
        self.last_summary_log = None
        self.log_details = QCheckBox('세부 과정 표시')
        self.log_details.setAccessibleName('분석·검색·검증 중간 과정 표시')
        old[4].layout().itemAt(0).layout().insertWidget(1, self.log_details)
        self.log_details.toggled.connect(self.render_logs)
        self.render_logs()
        QTimer.singleShot(0, self.ensure_official_api_check)
        self.steam_check_requested = False
        QTimer.singleShot(0, self.ensure_steam_api_check)

    def install_icon_rail(self):
        sidebar = self.findChild(QFrame, 'sidebar')
        body = sidebar.parentWidget().layout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        sidebar.setFixedWidth(188)
        sidebar.layout().setContentsMargins(0, 24, 0, 16)
        self.findChild(QLabel, 'brandIcon').hide()
        self.findChild(QLabel, 'brandSub').hide()
        self.findChild(QLabel, 'brandTitle').setText('CHZZK 설정')
        self.findChild(QLabel, 'navSection').setText('방송 카테고리 자동화')
        self.icon_rail = QFrame()
        self.icon_rail.setObjectName('iconRail')
        rail = QVBoxLayout(self.icon_rail)
        rail.setContentsMargins(8, 14, 8, 14)
        rail.setSpacing(14)
        brand = QToolButton()
        brand.setObjectName('railBrand')
        brand.setIcon(app_icon('games', TOKENS['accent']))
        brand.setIconSize(QSize(23, 23))
        brand.setToolTip('대시보드')
        brand.setAccessibleName('대시보드')
        brand.clicked.connect(lambda: self.nav.setCurrentRow(0))
        rail.addWidget(brand, 0, Qt.AlignmentFlag.AlignHCenter)
        rail.addStretch()
        self.rail_buttons = {}
        for page, name, title in ((0, 'dashboard', '대시보드'), (1, 'games', '게임 관리'),
                                  (3, 'connections', '연결 관리')):
            button = QToolButton()
            button.setObjectName('railButton')
            button.setToolTip(title)
            button.setAccessibleName(title)
            button.setIconSize(QSize(19, 19))
            button.clicked.connect(lambda checked=False, target=page: self.nav.setCurrentRow(target))
            rail.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            self.rail_buttons[page] = (button, name)
        rail.addStretch()
        for page, name, title in ((5, 'logs', '로그'), (4, 'settings', '설정')):
            button = QToolButton()
            button.setObjectName('railButton')
            button.setToolTip(title)
            button.setAccessibleName(title)
            button.setIconSize(QSize(17, 17))
            button.clicked.connect(lambda checked=False, target=page: self.nav.setCurrentRow(target))
            rail.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            self.rail_buttons[page] = (button, name)
        body.insertWidget(0, self.icon_rail)
        self.nav.currentRowChanged.connect(self.sync_navigation_icons)
        self.sync_navigation_icons(0)

    def sync_navigation_icons(self, current):
        for i, (_, _, name) in enumerate(PAGES):
            self.nav.item(i).setIcon(app_icon(name, TOKENS['accent'] if i == current else TOKENS['muted']))
        active = 1 if current == 2 else current
        for page, (button, name) in self.rail_buttons.items():
            button.setProperty('active', page == active)
            button.setIcon(app_icon(name, TOKENS['accent'] if page == active else TOKENS['muted']))
            button.style().unpolish(button)
            button.style().polish(button)

    def ensure_steam_api_check(self):
        if (self.preview or self.steam_check_requested
                or not self.config.get('steam_lookup_enabled', True)):
            return
        self.steam_check_requested = True
        self.steam_status.setText('Steam 연결을 자동 확인하고 있습니다…')
        self.worker.submit('steam_test')

    def ensure_official_api_check(self):
        if self.preview or self.official_check_requested:
            return
        self.official_check_requested = True
        self.chzzk_open_status.setText('공식 API 연결을 자동 확인하고 있습니다…')
        self.worker.submit('chzzk_open_test')

    def build_steam_connection(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addStretch(1)
        panel, box = card('Steam 한국어 게임 이름')
        panel.setObjectName('connectionCenter')
        panel.setMinimumWidth(540)
        panel.setMinimumHeight(300)
        panel.setMaximumWidth(600)
        box.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        box.addWidget(label('게임 감지 → 한국어 이름 조회 → 치지직 카테고리 연결'))
        self.steam_enabled = ToggleSwitch('Steam 한국어 매칭')
        self.steam_enabled.setChecked(self.config.get('steam_lookup_enabled', True))
        box.addWidget(setting_row('Steam 한국어 매칭', 'Steam에 없는 게임은 기존 방식으로 매칭합니다.', self.steam_enabled))
        box.addWidget(label('별도의 로그인이나 키 입력 없이 자동으로 연결합니다.'))
        status = '키 없이 자동 연결 · 연결 확인 대기'
        if not self.steam_enabled.isChecked():
            status = 'Steam 한국어 매칭이 꺼져 있습니다.'
        self.steam_status = label(status, 'inlineStatus')
        box.addWidget(self.steam_status)
        row = QHBoxLayout()
        reconnect = action('연결 다시 확인', self.save_steam_connection, 'refresh')
        reconnect.setObjectName('textAccentButton')
        row.addStretch()
        row.addWidget(reconnect)
        row.addStretch()
        box.addLayout(row)
        self.steam_enabled.toggled.connect(self.save_steam_preference)
        layout.addWidget(panel, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        return scroll_page(page)

    def save_steam_preference(self, enabled):
        previous = self.config.get('steam_lookup_enabled', True)
        self.config['steam_lookup_enabled'] = bool(enabled)
        if not self.persist():
            self.config['steam_lookup_enabled'] = previous
            self.steam_enabled.blockSignals(True)
            self.steam_enabled.setChecked(previous)
            self.steam_enabled.blockSignals(False)
            return
        if enabled:
            self.steam_check_requested = False
            self.ensure_steam_api_check()
        else:
            self.steam_status.setText('Steam 한국어 매칭이 꺼져 있습니다.')

    def save_steam_connection(self):
        if not self.config.get('steam_lookup_enabled', True):
            self.steam_status.setText('Steam 한국어 매칭이 꺼져 있습니다.')
            return
        self.steam_status.setText('Steam 연결을 확인하고 있습니다…')
        self.worker.submit('steam_test')

    def switch_page(self, index):
        if not getattr(self, 'ui_ready', False):
            return super().switch_page(index)
        if not 0 <= index < len(PAGES):
            return
        self.pages.setCurrentIndex(index)
        self.page_title.setText(PAGES[index][0])
        self.page_sub.setText(PAGES[index][1])
        for i, (_, _, name) in enumerate(PAGES):
            self.nav.item(i).setIcon(app_icon(name, '#252525' if i == index else '#D4D0C6'))
        if index in (0, 3):
            self.refresh_connection_page()
        if index == 4:
            self.refresh_update_page()

    def open_page_from_tray(self, index):
        self.show_main()
        self.nav.setCurrentRow({0: 1, 1: 3, 2: 3, 3: 1, 4: 5, 5: 4, 6: 4, 7: 4}.get(index, 0))
        if index == 3:
            self.game_tabs.setCurrentIndex(1)
        if index == 6:
            self.setting_tabs.setCurrentIndex(1)

    def build_dashboard(self):
        page = QWidget()
        page.setObjectName('dashboardPage')
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(12)
        self.dashboard_values = {}
        self.dashboard_summary_cards = []
        summary = QGridLayout()
        summary.setSpacing(12)
        for column, (key, title) in enumerate((('automation', '자동화 상태'),
                ('category', '치지직 카테고리'), ('extension', '브라우저 확장프로그램'))):
            c, dot, value, meta = self._make_status_card(title, '확인 전', '')
            c.setProperty('dashboardCard', True)
            c.layout().setContentsMargins(18, 16, 18, 16)
            c.layout().setSpacing(8)
            self.dashboard_values[key] = (value, meta, dot)
            self.dashboard_summary_cards.append(c)
            summary.addWidget(c, 0, column)
            summary.setColumnStretch(column, 1)
        layout.addLayout(summary)

        detail = QGridLayout()
        detail.setSpacing(12)
        detail.setColumnStretch(0, 1)
        hero, box = card('현재 실행 중인 게임')
        hero.setProperty('dashboardCard', True)
        self.dashboard_game_card = hero
        self.dashboard_game_dot = QLabel()
        self.dashboard_game_dot.setFixedSize(16, 16)
        title = box.takeAt(0).widget()
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(self.dashboard_game_dot)
        header.addWidget(title, 1)
        manage = action('게임 관리', lambda: self.nav.setCurrentRow(1), 'games')
        manage.setObjectName('dashboardAction')
        header.addWidget(manage)
        box.addLayout(header)
        self.dashboard_game = label('현재 실행 중인 게임이 없습니다.', 'heroGame')
        box.addWidget(self.dashboard_game)
        self.dashboard_empty_hint = label('게임을 실행하면 자동으로 감지하여 방송 카테고리를 검색합니다.')
        box.addWidget(self.dashboard_empty_hint)
        self.dashboard_game_details = QWidget()
        fields = QGridLayout(self.dashboard_game_details)
        fields.setContentsMargins(0, 8, 0, 0)
        fields.setHorizontalSpacing(18)
        fields.setVerticalSpacing(16)
        self.dashboard_process = label('', 'dashboardDetailValue')
        self.dashboard_target = label('', 'dashboardDetailValue')
        self.dashboard_method = label('Discord 게임 목록', 'dashboardDetailValue')
        self.dashboard_game_meta = label('', 'dashboardDetailValue')
        for i, (text, value) in enumerate((('실행 파일', self.dashboard_process),
                ('연결 카테고리', self.dashboard_target), ('감지 방식', self.dashboard_method),
                ('감지 및 매칭', self.dashboard_game_meta))):
            field = QVBoxLayout()
            field.setSpacing(5)
            field.addWidget(label(text, 'statusCardTitle'))
            field.addWidget(value)
            fields.addLayout(field, 0, i)
            fields.setColumnStretch(i, 1)
        box.addWidget(self.dashboard_game_details)
        box.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.dashboard_values['game'] = (self.dashboard_game, self.dashboard_game_meta,
                                         self.dashboard_game_dot)
        detail.addWidget(hero, 0, 0)
        activity, box = card('최근 활동')
        activity.setProperty('dashboardCard', True)
        self.dashboard_activity_card = activity
        title = box.takeAt(0).widget()
        header = QHBoxLayout()
        header.addWidget(title, 1)
        logs = action('전체 로그', lambda: self.nav.setCurrentRow(5), 'logs')
        logs.setObjectName('dashboardAction')
        header.addWidget(logs)
        box.addLayout(header)
        self.dashboard_activity = label('아직 기록된 활동이 없습니다.')
        box.addWidget(self.dashboard_activity)
        self.dashboard_activity_rows = []
        for _ in range(5):
            row = QFrame()
            row.setObjectName('dashboardActivityRow')
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 8, 0, 8)
            row_layout.setSpacing(10)
            stamp = label('', 'dashboardTime')
            stamp.setFixedWidth(54)
            message = label('', 'dashboardActivityText')
            row_layout.addWidget(stamp, 0, Qt.AlignmentFlag.AlignTop)
            row_layout.addWidget(message, 1)
            box.addWidget(row)
            self.dashboard_activity_rows.append((row, stamp, message))
        box.setSpacing(0)
        box.setAlignment(Qt.AlignmentFlag.AlignTop)
        detail.addWidget(activity, 1, 0)
        layout.addLayout(detail)
        layout.addStretch(1)
        return scroll_page(page)

    def representative_game(self):
        active = [g for g in self.runtime_games.values() if g.get('running')]
        chosen = [g for g in active if g.get('representative')]
        return chosen[0] if len(chosen) == 1 else active[0] if len(active) == 1 else None

    def refresh_tray_status(self):
        popup = getattr(self, 'tray_popup', None)
        if popup is not None:
            runtime, _ = popup.game_status()
            self.tray.setToolTip('치지직 자동 카테고리\n' + runtime)
            if popup.isVisible():
                popup.refresh()

    def refresh_dashboard(self):
        if not getattr(self, 'ui_ready', False):
            return
        self.refresh_tray_status()
        state = '일시정지' if not self.enabled else '실행 중' if self.connection_verified else '연결 대기'
        if not self.enabled and self.auto_start_armed and self.config.get('auto_start_change', True):
            state = '연결 대기'
        if self.enabled and ('실패' in self.last_runtime_status or '오류' in self.last_runtime_status):
            state = '오류'
        self.dashboard_values['automation'][0].setText(state)
        self.dashboard_values['automation'][1].setText('안전한 자동 선택 · 항상 적용')
        self.sidebar_auto_state.setText(state)
        set_button_icon(self.toggle_button, 'pause' if self.enabled else 'start', '#FFFFFF')
        g = self.representative_game()
        self.dashboard_game_details.setVisible(bool(g))
        self.dashboard_empty_hint.setVisible(not g)
        if g:
            self.dashboard_game.setText(g.get('localized_name') or g.get('game_name') or g.get('process') or '')
            self.dashboard_process.setText(g.get('process') or '확인 중')
            self.dashboard_process.setToolTip(g.get('process') or '')
            self.dashboard_target.setText(g.get('category_name') or '확인 중')
            self.dashboard_game_meta.setText(g.get('stage', '감지됨'))
            self.dashboard_method.setText(g.get('detection_source') or 'Discord 게임 목록')
        else:
            self.dashboard_game.setText('현재 실행 중인 게임이 없습니다.' if not any(x.get('running') for x in self.runtime_games.values())
                                        else '여러 게임이 실행 중입니다. 대표 게임을 선택해 주세요.')
            self.dashboard_game_meta.setText('게임 실행을 기다립니다')
        self.dashboard_values['category'][0].setText((self.last_category or '아직 확인하지 않음') if self.connection_verified else '확인할 수 없음' if self.last_category else '아직 확인하지 않음')
        self.dashboard_values['category'][1].setText('마지막 적용: ' + (self.last_applied_at or '없음') + (' · 마지막 확인: ' + self.last_category if self.last_category and not self.connection_verified else ''))
        info = self.bridge.extension_status()
        self.dashboard_values['extension'][0].setText(info['state'])
        self.dashboard_values['extension'][1].setText('버전: ' + (info.get('version') or '확인할 수 없음'))
        for key, (value, meta, dot) in self.dashboard_values.items():
            success = value.text() in ('실행 중', '정상 연결') or key == 'category' and bool(self.last_category)
            dot.setPixmap(app_icon('success' if success else 'clock', TOKENS['success'] if success else TOKENS['muted']).pixmap(16, 16))
        self.dashboard_activity.setVisible(not self.recent_activity)
        for index, (row, stamp, message) in enumerate(self.dashboard_activity_rows):
            visible = index < len(self.recent_activity)
            row.setVisible(visible)
            if visible:
                time, _, text = self.recent_activity[index].partition(' — ')
                stamp.setText(time)
                message.setText(text)
                message.setToolTip(text)

    def build_rules(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        row = QHBoxLayout()
        self.rule_filter = QLineEdit()
        self.rule_filter.setPlaceholderText('게임 · 실행 파일 · 카테고리 검색')
        self.rule_filter.setClearButtonEnabled(True)
        self.rule_filter.textChanged.connect(self.refresh_table)
        self.game_filter = QComboBox()
        self.game_filter.addItems(['전체', '자동 연결', '수동 연결', '미확정', '감지된 게임'])
        self.game_filter.currentTextChanged.connect(self.refresh_table)
        row.addWidget(self.rule_filter, 1)
        row.addWidget(self.game_filter)
        row.addWidget(action('게임 추가', lambda: self.edit_rule(new=True), 'add', True))
        row.addWidget(action('동기화', lambda: self.worker.submit('sync_auto'), 'refresh'))
        layout.addLayout(row)
        self.rule_stats_text = label('')
        layout.addWidget(self.rule_stats_text)
        self.game_model = GameTableModel(self)
        self.table = QTableView()
        self.table.setObjectName('rulesTable')
        self.table.setModel(self.game_model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(48)
        h = self.table.horizontalHeader()
        for i in (0, 1, 2):
            h.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        for i, width in ((3, 80), (4, 104), (5, 84)):
            h.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            h.resizeSection(i, width)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self.update_rule_selection_info())
        self.table.clicked.connect(lambda index: self.show_game_details() if index.column() == 5 else None)
        self.table.doubleClicked.connect(lambda *_: self.show_game_details())
        layout.addWidget(self.table, 1)
        empty_layout = QVBoxLayout(self.table.viewport())
        empty_layout.setContentsMargins(24, 24, 24, 24)
        empty_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        empty_layout.addStretch()
        self.rule_empty = QFrame()
        self.rule_empty.setObjectName('gameEmptyState')
        self.rule_empty.setMinimumWidth(320)
        self.rule_empty.setMaximumWidth(420)
        empty_box = QVBoxLayout(self.rule_empty)
        empty_box.setContentsMargins(12, 12, 12, 12)
        empty_box.setSpacing(10)
        empty_icon = QLabel()
        empty_icon.setObjectName('gameEmptyIcon')
        empty_icon.setFixedSize(48, 48)
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon.setPixmap(app_icon('games', '#A6ABB3').pixmap(26, 26))
        empty_box.addWidget(empty_icon, 0, Qt.AlignmentFlag.AlignHCenter)
        self.rule_empty_title = label('등록된 게임이 없습니다', 'gameEmptyTitle')
        self.rule_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_box.addWidget(self.rule_empty_title)
        self.rule_empty_description = label('게임을 실행해 자동 감지하거나\n게임 추가로 직접 등록해 주세요.', 'gameEmptyDescription')
        self.rule_empty_description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_box.addWidget(self.rule_empty_description)
        self.rule_empty_action = action('게임 추가', self.handle_empty_rules_action, 'add', True)
        empty_box.addWidget(self.rule_empty_action, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addWidget(self.rule_empty, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addStretch()
        self.rule_selection_info = label('게임을 선택하면 연결과 상세 정보를 관리할 수 있습니다.', 'ruleSelectionInfo')
        self.rule_selection_info.setWordWrap(False)
        self.rule_selection_info.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        # Mixed Korean/Latin fallback glyphs must not change the table height.
        self.rule_selection_info.setFixedHeight(24)
        layout.addWidget(self.rule_selection_info)
        row = QHBoxLayout()
        self.rule_edit_button = action('수정', self.edit_rule, 'edit')
        self.rule_details_button = action('간편 설정', self.show_game_details, 'details')
        self.rule_delete_button = action('삭제', self.remove_rule, 'delete')
        for button in (self.rule_edit_button, self.rule_details_button, self.rule_delete_button):
            row.addWidget(button)
        row.addStretch()
        self.rule_move_up_button = action('위로', lambda: self.move_rule(-1), 'up')
        self.rule_move_down_button = action('아래로', lambda: self.move_rule(1), 'down')
        row.addWidget(self.rule_move_up_button)
        row.addWidget(self.rule_move_down_button)
        layout.addLayout(row)
        self.update_rule_selection_info()
        self.pages.addWidget(page)

    def handle_empty_rules_action(self):
        if self.rule_filter.text().strip() or self.game_filter.currentIndex() != 0:
            self.rule_filter.clear()
            self.game_filter.setCurrentIndex(0)
        else:
            self.edit_rule(new=True)

    def refresh_table(self):
        if not hasattr(self, 'game_model'):
            return
        selected = self.selected_rule_location()
        rows, represented = [], set()
        for kind, rules in (('manual', self.rules), ('auto', self.auto_rules)):
            for i, r in enumerate(rules):
                runtime = next((g for g in self.runtime_games.values()
                                if r.process.casefold() in [p.casefold() for p in g.get('processes', [g.get('process', '')])]), {})
                represented.update(p.casefold() for p in r.processes)
                rows.append(dict(kind=kind, index=i, game=r.game_name or Path(r.process).stem,
                                 process=r.process, category=r.category_name, mode='수동' if kind == 'manual' else '자동',
                                 state=runtime.get('stage', '저장된 연결'), running=runtime.get('running', False), rule=r))
        for i, p in enumerate(self.auto_pending):
            process = str(p.get('process') or '')
            if not process or process.casefold() in represented:
                continue
            represented.add(process.casefold())
            rows.append(dict(kind='pending', index=i, game=p.get('game_name') or ', '.join(p.get('games') or []) or process,
                             process=process, category='미확정', mode='미확정', state='확인 필요', running=True))
        for g in self.runtime_games.values():
            if not g.get('running') or g.get('process', '').casefold() in represented:
                continue
            rows.append(dict(kind='runtime', index=-1, game=g.get('game_name') or g.get('process'),
                             process=g.get('process', ''), category=g.get('category_name', '미확정'),
                             mode='감지', state=g.get('stage', '감지됨'), running=True))
        q = self.rule_filter.text().strip().casefold()
        f = self.game_filter.currentText()
        rows = [r for r in rows if (not q or q in ' '.join(str(r.get(k, '')) for k in ('game', 'process', 'category')).casefold())
                and (f == '전체' or f == '자동 연결' and r['kind'] == 'auto'
                     or f == '수동 연결' and r['kind'] == 'manual' or f == '미확정' and r['state'] in ('확인 필요', '오류')
                     or f == '감지된 게임' and r['running'])]
        self.game_model.replace(rows)
        if selected:
            self.select_rule_location(selected['kind'], selected['index'])
        self.rule_empty.setVisible(not rows)
        filtered = bool(q or f != '전체')
        self.rule_empty_title.setText('검색 결과가 없습니다' if q else '조건에 맞는 게임이 없습니다' if filtered else '등록된 게임이 없습니다')
        self.rule_empty_description.setText('검색어나 필터를 초기화하면\n전체 게임을 다시 볼 수 있습니다.' if filtered
                                            else '게임을 실행해 자동 감지하거나\n게임 추가로 직접 등록해 주세요.')
        self.rule_empty_action.setText('조건 초기화' if filtered else '게임 추가')
        set_button_icon(self.rule_empty_action, 'refresh' if filtered else 'add', '#FFFFFF')
        self.rule_stats_text.setText(f'연결 {len(self.rules) + len(self.auto_rules)}개 · 미확정 {len(self.auto_pending)}개')
        self.update_rule_selection_info()
        if hasattr(self, 'pending_table'):
            self.refresh_pending_page()

    def selected_rule_location(self):
        index = self.table.currentIndex()
        if not index.isValid() or index.row() >= len(self.game_model.rows):
            return None
        row = self.game_model.rows[index.row()]
        return {'kind': row['kind'], 'index': row['index']}

    def select_rule_location(self, kind, index):
        for i, row in enumerate(self.game_model.rows):
            if row['kind'] == kind and row['index'] == index:
                self.table.selectRow(i)
                return

    def selected_game(self):
        index = self.table.currentIndex()
        return self.game_model.rows[index.row()] if index.isValid() and index.row() < len(self.game_model.rows) else None

    def update_rule_selection_info(self):
        if not hasattr(self, 'rule_selection_info'):
            return
        row = self.selected_game()
        text = (f"{row['game']} · {row['process']} → {row['category']} · {row['state']}" if row
                else '게임을 선택하면 연결과 상세 정보를 관리할 수 있습니다.')
        self.rule_selection_info.setText(text)
        self.rule_selection_info.setToolTip(text if row else '')
        self.rule_edit_button.setEnabled(bool(row and row['kind'] in ('manual', 'auto', 'pending')))
        self.rule_details_button.setEnabled(bool(row))
        self.rule_delete_button.setEnabled(bool(row and row['kind'] in ('manual', 'auto')))
        manual = row and row['kind'] == 'manual'
        self.rule_move_up_button.setEnabled(bool(manual and row['index'] > 0))
        self.rule_move_down_button.setEnabled(bool(manual and row['index'] < len(self.rules) - 1))

    def confirm_league_selection(self, rule):
        if self.league_session_token and rule and any(p.casefold() in ('leagueclient.exe', 'league of legends.exe') for p in rule.processes):
            self.league_selected_session = self.league_session_token
            self.worker.submit('confirm_league_mode', {'session': self.league_session_token, 'rule': asdict(rule)})

    def edit_rule(self, _checked=False, new=False):
        if new:
            result = super().edit_rule(new=True)
        else:
            row = self.selected_game()
            if not row:
                return
            if row['kind'] == 'pending':
                return self.resolve_pending()
            if row['kind'] == 'auto':
                self.convert_rule('manual')
            result = super().edit_rule()
        if isinstance(result, Rule):
            self.confirm_league_selection(result)
        return result

    def resolve_pending(self):
        from main import RuleDialog
        row = self.selected_game()
        if row and row['kind'] in ('pending', 'runtime'):
            process, game = row['process'], row['game']
        elif self.auto_pending:
            idx = self.pending_table.currentRow()
            item = self.auto_pending[idx if 0 <= idx < len(self.auto_pending) else 0]
            process = str(item.get('process') or '')
            game = item.get('game_name') or ', '.join(item.get('games') or [])
        else:
            return
        dlg = RuleDialog(self)
        dlg.process.setEditText(process)
        dlg.note.setText('이 게임의 카테고리를 직접 선택해 주세요: ' + game)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            before = (list(self.rules), list(self.auto_rules), list(self.auto_pending))
            occupied = {p.casefold() for p in dlg.result_rule.processes}
            self.rules = [r for r in self.rules if not occupied.intersection(p.casefold() for p in r.processes)]
            self.auto_rules = [r for r in self.auto_rules if not occupied.intersection(p.casefold() for p in r.processes)]
            self.rules.append(dlg.result_rule)
            self.auto_pending = [x for x in self.auto_pending if str(x.get('process', '')).casefold() not in occupied]
            if not self.persist():
                self.rules, self.auto_rules, self.auto_pending = before
            else:
                self.confirm_league_selection(dlg.result_rule)
            self.refresh_table()
        dlg.deleteLater()

    def convert_rule(self, kind, process=None):
        row = self.selected_game()
        if process:
            row = next((r for r in self.game_model.rows if r['process'].casefold() == process.casefold()), None)
        if not row or row['kind'] not in ('auto', 'manual') or row['kind'] == kind:
            return
        before = (list(self.rules), list(self.auto_rules))
        source = self.rules if row['kind'] == 'manual' else self.auto_rules
        r = source.pop(row['index'])
        target = self.rules if kind == 'manual' else self.auto_rules
        target.append(r)
        if not self.persist():
            self.rules, self.auto_rules = before
        self.refresh_table()
        self.select_rule_location(kind, len(target) - 1)

    def prompt_league_mode(self, event):
        if self.league_session_token != event['session'] or self.league_selected_session == event['session']:
            return
        if self.active_league_dialog is not None:
            return
        if QApplication.activeModalWidget() is not None:
            QTimer.singleShot(250, lambda: self.prompt_league_mode(event))
            return
        self.show_game_details(prompt_event=event)

    def show_game_details(self, *_, prompt_event=None):
        row = self.selected_game()
        if prompt_event:
            row = next((r for r in self.game_model.rows if r['process'].casefold() in ('leagueclient.exe', 'league of legends.exe')), None)
            if row is None:
                row = {'game': '롤 / 롤토체스', 'process': prompt_event['process'], 'category': '선택 전',
                       'kind': 'runtime', 'running': True}
        if not row:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle('어떤 게임을 할까요?' if prompt_event else row['game'] + ' · 간편 설정')
        if prompt_event:
            self.active_league_dialog = dlg
            dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        dlg.resize(560, 380)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        summary, summary_box = card('어떤 게임을 할까요?' if prompt_event else row['game'])
        if not prompt_event:
            summary_box.addWidget(label('방송 카테고리: ' + row['category'], 'statusCardValue'))
        summary_box.addWidget(label('이번에 플레이할 게임을 선택하면 방송 카테고리를 연결합니다.' if prompt_event else '선택한 게임에 맞춰 방송 카테고리를 자동 변경합니다.'))
        layout.addWidget(summary)
        quick_message = label('')
        quick_message.setObjectName('quickMessage')
        layout.addWidget(quick_message)
        quick_tokens = []
        quick_buttons = []

        def choose_mode(canonical):
            import uuid
            token = uuid.uuid4().hex
            session = prompt_event['session'] if prompt_event else self.league_session_token
            quick_tokens.append(token)
            quick_message.setText('카테고리를 확인하고 있습니다…')
            for button in quick_buttons:
                button.setEnabled(False)

            def complete(event):
                for button in quick_buttons:
                    button.setEnabled(True)
                if event['kind'] == 'quick_rule_error':
                    quick_message.setText(event['text'])
                    return
                if session and session != self.league_session_token:
                    quick_message.setText('게임 실행이 종료되었습니다. 다시 실행한 뒤 선택해 주세요.')
                    return
                rule = Rule(**event['data'])
                before = (list(self.rules), list(self.auto_rules), list(self.auto_pending))
                occupied = {p.casefold() for p in rule.processes}
                self.rules = [r for r in self.rules if not occupied.intersection(p.casefold() for p in r.processes)]
                self.auto_rules = [r for r in self.auto_rules if not occupied.intersection(p.casefold() for p in r.processes)]
                self.auto_pending = [item for item in self.auto_pending if str(item.get('process', '')).casefold() not in occupied]
                self.rules.append(rule)
                if self.persist():
                    self.confirm_league_selection(rule)
                    self.refresh_table()
                    dlg.accept()
                else:
                    self.rules, self.auto_rules, self.auto_pending = before
                    quick_message.setText('저장하지 못했습니다. 다시 시도해 주세요.')
            self.quick_rule_callbacks[token] = complete
            self.worker.submit('quick_game_mode', {'token': token, 'process': row['process'], 'game': canonical, 'session': session})

        league = row['process'].casefold() in ('leagueclient.exe', 'league of legends.exe')
        if league:
            layout.addWidget(label('게임을 실행할 때마다 한 번 선택합니다. 닫으면 이번 실행의 자동 변경을 보류합니다.'))
            choices = QHBoxLayout()
            for title, canonical in (('롤', 'League of Legends'), ('롤토체스', 'Teamfight Tactics')):
                button = action(title, lambda _checked=False, name=canonical: choose_mode(name), 'games', True)
                quick_buttons.append(button)
                choices.addWidget(button)
            layout.addLayout(choices)
        else:
            def use_category():
                if row.get('rule'):
                    self.convert_rule('manual', row['process'])
                    dlg.accept()
                else:
                    dlg.accept()
                    self.edit_rule()
            layout.addWidget(action('이 카테고리로 사용' if row.get('rule') else '카테고리 찾기', use_category, 'success', True))
        other_category = action('다른 카테고리 선택', lambda: (dlg.accept(), self.edit_rule()), 'search')
        layout.addWidget(other_category)
        other_category.setVisible(not bool(prompt_event))
        advanced_toggle = QPushButton('고급 설정 보기')
        advanced_toggle.setCheckable(True)
        layout.addWidget(advanced_toggle)
        advanced_toggle.setVisible(not bool(prompt_event))
        body = QWidget()
        form = QFormLayout(body)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        r = row.get('rule')
        g = next((x for x in self.runtime_games.values() if x.get('process', '').casefold() == row['process'].casefold()), {})
        fields = [('게임', row['game']), ('Discord 원본 이름', g.get('discord_name') or '확인할 수 없음'),
                  ('실행 파일', ', '.join(r.processes) if r else row['process']),
                  ('실행 파일 경로', '조회하지 않음 · 이름 기반 감지'), ('감지 방식', 'Discord 공개 목록 + 프로세스 이름'),
                  ('현재 실행', '실행 중' if row['running'] else '종료됨'), ('마지막 감지', g.get('last_detected_at', '아직 확인하지 않음')),
                  ('한국어 카테고리', row['category']), ('카테고리 ID', r.category_id if r else '미확정'),
                  ('영문 이름', r.game_name if r else row['game']), ('매칭 출처', r.match_source if r else '검색 중'),
                  ('신뢰도', g.get('confidence_label', '아직 검증하지 않음')), ('마지막 검증', g.get('verified_at', '아직 검증하지 않음'))]
        for name, value in fields:
            form.addRow(name, label(str(value), ''))
        aliases = QLineEdit(', '.join(self.config.get('game_aliases', {}).get(row['game'], [])))
        aliases.setPlaceholderText('쉼표로 구분한 한국어/영문 별칭')
        form.addRow('게임 별칭', aliases)
        process_aliases = QLineEdit(', '.join(r.process_aliases) if r else '')
        process_aliases.setPlaceholderText('같은 게임의 보조 실행 파일 · 쉼표로 구분')
        form.addRow('보조 실행 파일', process_aliases)
        excluded = QCheckBox('자동 감지에서 제외')
        excluded.setChecked(row['process'].casefold() in {p.casefold() for p in self.config.get('excluded_processes', [])})
        form.addRow(excluded)
        advanced = QWidget()
        advanced_layout = QVBoxLayout(advanced)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.addWidget(scroll_page(body))
        message = label('별칭과 실행 파일은 필요한 경우에만 변경하세요.')
        advanced_layout.addWidget(message)
        layout.addWidget(advanced)
        advanced.hide()
        def toggle_advanced(opened):
            advanced.setVisible(opened)
            advanced_toggle.setText('고급 설정 접기' if opened else '고급 설정 보기')
            dlg.resize(680, 820) if opened else dlg.resize(560, 380)
        advanced_toggle.toggled.connect(toggle_advanced)

        def save_details():
            book = copy.deepcopy(self.config.get('game_aliases', {}))
            book[row['game']] = list(dict.fromkeys(a.strip() for a in aliases.text().split(',') if a.strip()))
            if alias_conflicts(book):
                message.setText('다른 게임과 같은 별칭이 있습니다. 충돌한 별칭을 제거해 주세요.')
                return
            if r:
                try:
                    from dataclasses import replace
                    changed = replace(r, process_aliases=tuple(p.strip() for p in process_aliases.text().split(',') if p.strip()))
                    others = [rule for rule in self.rules + self.auto_rules if rule is not r]
                    if any({p.casefold() for p in changed.processes} & {p.casefold() for p in other.processes} for other in others):
                        message.setText('다른 게임 규칙에서 사용하는 실행 파일이 있습니다.')
                        return
                    target_rules = self.rules if row['kind'] == 'manual' else self.auto_rules
                    position = next((i for i, item in enumerate(target_rules) if item == r), None)
                    if position is None:
                        message.setText('게임 연결이 변경되었습니다. 상세 창을 다시 열어 주세요.')
                        return
                    target_rules[position] = changed
                except ValueError:
                    message.setText('실행 파일 형식을 확인해 주세요.')
                    return
            self.config['game_aliases'] = book
            excluded_names = {p.casefold(): p for p in self.config.get('excluded_processes', [])}
            if excluded.isChecked():
                excluded_names[row['process'].casefold()] = row['process']
            else:
                excluded_names.pop(row['process'].casefold(), None)
            self.config['excluded_processes'] = list(excluded_names.values())
            if self.persist():
                dlg.accept()

        tools = QHBoxLayout()
        tools.addWidget(action('재검색', lambda: self.worker.submit('research_game', row['process']), 'refresh'))
        tools.addWidget(action('직접 선택', lambda: (dlg.accept(), self.edit_rule()), 'search'))
        tools.addWidget(action('대표 게임', lambda: (self.choose_representative(row['process']), dlg.accept()), 'games'))
        advanced_layout.addLayout(tools)
        tools = QHBoxLayout()
        tools.addWidget(action('수동 연결', lambda: (self.convert_rule('manual', row['process']), dlg.accept()), 'edit'))
        tools.addWidget(action('자동 연결', lambda: (self.convert_rule('auto', row['process']), dlg.accept()), 'automation'))
        tools.addWidget(action('감지 기록', lambda: (dlg.accept(), self.nav.setCurrentRow(5)), 'logs'))
        tools.addWidget(action('저장', save_details, 'success', True))
        advanced_layout.addLayout(tools)
        layout.addWidget(action('닫기', dlg.reject, 'close'))
        def clean_callbacks(*_):
            for token in quick_tokens:
                self.quick_rule_callbacks.pop(token, None)
        dlg.finished.connect(clean_callbacks)
        if prompt_event:
            QTimer.singleShot(0, dlg.raise_)
            QTimer.singleShot(0, dlg.activateWindow)
        dlg.exec()
        if self.active_league_dialog is dlg:
            self.active_league_dialog = None
        dlg.deleteLater()

    def choose_representative(self, process):
        self.config['preferred_process'] = process
        self.persist()

    def build_options(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(18)
        grid = QGridLayout()
        grid.setSpacing(16)
        def toggle(name, title, key, hint, box):
            control = ToggleSwitch(title)
            control.setChecked(self.config.get(key, True))
            setattr(self, name, control)
            box.addWidget(setting_row(title, hint, control))
            return control
        c, box = card('게임 감지')
        box.setSpacing(4)
        toggle('auto_detect', '게임 자동 감지', 'auto_detect', '게임을 실행하면 자동으로 찾습니다. Discord 로그인은 필요하지 않습니다.', box)
        self.interval = QComboBox()
        for sec in (3, 5, 10, 15, 30, 60):
            self.interval.addItem(f'{sec}초', sec)
        self.interval.setCurrentIndex(max(0, self.interval.findData(self.config.get('interval', 5))))
        box.addWidget(setting_row('감지 주기', '기본 5초 · 게임 실행과 종료를 확인합니다.', self.interval))
        self.auto_aggressive = QCheckBox()
        self.auto_aggressive.setChecked(True)
        self.auto_aggressive.setEnabled(False)
        box.addWidget(label('중복 게임 통합과 안전한 자동 선택은 기본으로 적용됩니다.'))
        grid.addWidget(c, 0, 0)
        c, box = card('카테고리 자동 변경')
        box.setSpacing(4)
        toggle('auto_start_change', '연결되면 자동 시작', 'auto_start_change', '연결을 확인하면 자동 변경을 시작합니다.', box)
        toggle('only_when_live', '방송 중에만 변경', 'only_when_live', '방송 중인 것으로 확인될 때만 적용합니다.', box)
        box.addWidget(label('수동 연결을 우선하며 같은 카테고리는 반복 변경하지 않습니다.'))
        grid.addWidget(c, 0, 1)
        c, box = card('카테고리 검색 및 연결')
        box.setSpacing(4)
        self.chzzk_open_enabled = QCheckBox()
        self.chzzk_open_enabled.setChecked(True)
        self.chzzk_open_enabled.setEnabled(False)
        box.addWidget(label('공식 API · 필수 자동 연결', 'settingTitle'))
        box.addWidget(label('설치 프로그램에 포함된 인증 정보를 자동 사용합니다. 별도 입력이나 켜기 설정이 필요 없습니다.'))
        self.chzzk_open_status = label('앱을 시작하면 공식 API 상태를 자동 확인합니다.', 'inlineStatus')
        box.addWidget(self.chzzk_open_status)
        self.category_sync = QComboBox()
        for hour in HOUR_OPTIONS:
            self.category_sync.addItem(f'{hour}시간', hour)
        self.category_sync.setCurrentIndex(max(0, self.category_sync.findData(self.config.get('category_sync_hours', 6))))
        box.addWidget(setting_row('카테고리 정보 갱신', '새 게임은 대기 없이 바로 검색합니다.', self.category_sync))
        grid.addWidget(c, 1, 0, 1, 2)
        for col in (0, 1):
            grid.setColumnStretch(col, 1)
        layout.addLayout(grid)
        advanced = QPushButton('고급 설정 보기')
        advanced.setCheckable(True)
        set_button_icon(advanced, 'settings')
        layout.addWidget(advanced)
        c, box = card('고급 연결 설정')
        box.setSpacing(4)
        self.discord_refresh = QComboBox()
        for hour in (1, 6, 12, 24, 72, 168):
            self.discord_refresh.addItem(f'{hour}시간', hour)
        self.discord_refresh.setCurrentIndex(max(0, self.discord_refresh.findData(self.config.get('discord_refresh_hours', 24))))
        box.addWidget(setting_row('Discord 게임 목록 갱신', '게임 감지 주기와 별개의 데이터 갱신 주기입니다.', self.discord_refresh))
        box.addWidget(action('공식 API 다시 확인', self.test_chzzk_open_connection, 'refresh'))
        c.hide()
        advanced.toggled.connect(c.setVisible)
        layout.addWidget(c)
        layout.addStretch()
        self.pages.addWidget(settings_shell(page, self.save_options))
        for name, key in (('notify', 'notify'), ('pending_sound', 'pending_sound'), ('start_hidden', 'start_hidden'),
                          ('autostart', 'autostart'), ('auto_update', 'auto_update'), ('update_notify', 'update_notify')):
            widget = ToggleSwitch(name)
            widget.setChecked(self.config.get(key, True))
            setattr(self, name, widget)
        self.update_check_interval = QComboBox()
        for hour in HOUR_OPTIONS:
            self.update_check_interval.addItem(f'{hour}시간', hour * 60)
        minutes = self.config.get('update_check_minutes', 180)
        if self.update_check_interval.findData(minutes) < 0:
            self.update_check_interval.addItem(f'{minutes}분 · 기존 설정', minutes)
        self.update_check_interval.setCurrentIndex(self.update_check_interval.findData(minutes))

    def build_program_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 0, 18)
        layout.setSpacing(0)
        startup_box = notification_box = layout
        rows = (
            ('autostart', 'Windows 시작 시 실행', '로그인하면 백그라운드에서 시작합니다.', startup_box),
            ('start_hidden', '트레이로 시작', '처음 설정을 마친 뒤 메인 창을 숨겨 시작합니다.', startup_box),
            ('notify', '카테고리 변경 알림', '변경이 완료되면 알립니다.', notification_box),
            ('pending_sound', '새 게임 확인 알림음', '확인이 필요한 게임을 처음 발견하면 소리로 알립니다.', notification_box),
            ('update_notify', '새 버전 알림', '같은 버전은 반복해서 알리지 않습니다.', notification_box))
        for name, title, hint, box in rows:
            box.addWidget(setting_row(title, hint, getattr(self, name)))
        for name, title, hint, key, box in (
            ('close_to_tray', '닫아도 백그라운드 유지', '창을 닫아도 게임 감지를 유지합니다.', 'close_to_tray', startup_box),
            ('minimize_to_tray', '최소화 시 트레이로 이동', '작업 표시줄 대신 트레이에 표시합니다.', 'minimize_to_tray', startup_box),
            ('detailed_logs', '상세 로그 저장', '기록을 제한된 크기로 순환 저장합니다.', 'detailed_logs', notification_box)):
            switch = ToggleSwitch(title)
            switch.setChecked(self.config.get(key, True))
            setattr(self, name, switch)
            box.addWidget(setting_row(title, hint, switch))
        layout.addSpacing(24)
        layout.addWidget(label('프로그램 업데이트', 'sectionTitle'))
        box = layout
        box.addWidget(setting_row('새 버전 자동 확인', '설정한 간격으로 새 정식 버전을 확인합니다.', self.auto_update))
        box.addWidget(setting_row('자동 확인 주기', '최소 1시간 · 기본 3시간', self.update_check_interval))
        self.allow_prerelease = ToggleSwitch('베타 버전도 확인')
        self.allow_prerelease.setChecked(self.config.get('allow_prerelease', False))
        box.addWidget(setting_row('베타 버전도 확인', '사전 릴리스를 업데이트 확인 대상에 포함합니다.', self.allow_prerelease))
        actions = QHBoxLayout()
        actions.addWidget(action('지금 확인', self.check_for_updates_manual, 'refresh'))
        actions.addStretch()
        box.addLayout(actions)
        layout.addStretch()
        return settings_shell(page, self.save_options)

    def save_options(self):
        self.config.update(only_when_live=self.only_when_live.isChecked(),
                           category_sync_hours=self.category_sync.currentData(), auto_aggressive=True)
        if hasattr(self, 'allow_prerelease'):
            self.config.update(allow_prerelease=self.allow_prerelease.isChecked(), close_to_tray=self.close_to_tray.isChecked(),
                               minimize_to_tray=self.minimize_to_tray.isChecked(), detailed_logs=self.detailed_logs.isChecked())
        return super().save_options()

    def connection_tick(self, force=False):
        import time
        if not force and time.monotonic() < self.connection_retry_at:
            self.refresh_connection_page()
            return
        if not force and self.connection_verified and time.monotonic() - self.last_category_observed_at >= 60:
            force = True
        return super().connection_tick(force)

    def refresh_connection_page(self):
        super().refresh_connection_page()
        info = self.bridge.extension_status()
        if hasattr(self, 'extension_status_meta'):
            self.extension_status_value.setText(info['state'])
            self.extension_status_meta.setText(f"버전: {info.get('version') or '확인할 수 없음'} · {info.get('compatibility', '확인 불가')}\n"
                                               f"브라우저: {info.get('browser') or '확인 불가'} · 마지막 응답: {info.get('last_response') or '없음'}")
        if hasattr(self, 'update_extension_label'):
            self.update_extension_label.setText('Chrome 확장  ' + (info.get('version') or '확인할 수 없음'))
        for dot, good in ((self.bridge_status_dot, bool(self.bridge.server)), (self.extension_status_dot, info['state'] == '정상 연결'),
                          (self.account_status_dot, self.connection_verified), (self.automation_status_dot, self.enabled)):
            dot.setPixmap(app_icon('success' if good else 'clock', TOKENS['success'] if good else TOKENS['muted']).pixmap(16, 16))
        self.refresh_dashboard()

    def append_log(self, text, detail=False):
        from diagnostics import activity_parts, redact
        text = redact(str(text))
        stamp = datetime.now().strftime('%H:%M:%S')
        duplicate = not detail and text == getattr(self, 'last_summary_log', None)
        detail = bool(detail or duplicate)
        kind, message = activity_parts(text)
        if hasattr(self, 'log_entries'):
            self.log_sequence += 1
            target = self.log_detail_entries if detail else self.log_entries
            target.append((stamp, kind, message, self.log_sequence))
        if not self.preview and getattr(self, 'bridge', None):
            self.bridge.add_log(text)
        if hasattr(self, 'log_details') and (not detail or self.log_details.isChecked()):
            self.render_logs()
        if not detail and hasattr(self, 'recent_activity'):
            self.last_summary_log = text
            self.recent_activity.append(stamp + ' — ' + text)
            self.refresh_dashboard()
        if not self.preview and self.config.get('detailed_logs', True):
            from diagnostics import record_log
            record_log(text)

    def visible_log_entries(self):
        selected = self.log_filter.currentText()
        entries = list(self.log_entries)
        if self.log_details.isChecked():
            entries = sorted([*entries, *self.log_detail_entries], key=lambda entry: entry[3])[-1000:]
        return [(t, k, s) for t, k, s, sequence in entries if selected == '전체' or k == selected]

    def copy_logs(self):
        if not hasattr(self, 'log_entries'):
            return super().copy_logs()
        QApplication.clipboard().setText('\n'.join(f'{t}  [{k}] {s}' for t, k, s in self.visible_log_entries()))

    def render_logs(self):
        from html import escape
        rows = self.visible_log_entries()
        scrollbar = self.log.verticalScrollBar()
        position = scrollbar.value()
        at_bottom = position >= scrollbar.maximum() - 4
        if rows:
            body = ''.join(
                '<tr><td width="110" valign="top"><font color="#8B909A">'+escape(t)+'</font></td>'
                '<td width="150" valign="top"><b><font color="'+(TOKENS['error'] if k == '오류' else TOKENS['accent'])+'">'
                +escape(k)+'</font></b></td><td valign="top">'+escape(s).replace('\n', '<br>')+'</td></tr>'
                for t, k, s in rows)
            content = ('<table width="100%" cellspacing="0" cellpadding="9">'
                       '<tr><th align="left" width="110">시간</th><th align="left" width="150">유형</th>'
                       '<th align="left">내용</th></tr>'+body+'</table>')
        else:
            content = '<p style="color:#8B909A">표시할 주요 활동이 없습니다. 세부 과정은 위 옵션에서 확인할 수 있습니다.</p>'
        self.log.setHtml('<div style="font-size:14px; color:#1E2024">'+content+'</div>')
        scrollbar.setValue(scrollbar.maximum() if at_bottom else position)

    def clear_logs(self):
        if not hasattr(self, 'log_entries'):
            return super().clear_logs()
        self.log_entries.clear()
        self.log_detail_entries.clear()
        self.log_sequence = 0
        self.last_summary_log = None
        self.recent_activity.clear()
        self.render_logs()
        self.refresh_dashboard()

    def on_event(self, event):
        # Existing tests/controller clients may call the method on a minimal host.
        from main import ExistingWindow
        kind = event['kind']
        if kind == 'steam_status':
            if hasattr(self, 'steam_status'):
                self.steam_status.setText(event.get('text', 'Steam 연결 확인 대기'))
            return
        if kind == 'league_mode_required':
            self.league_session_token = event['session']
            self.league_selected_session = None
            QTimer.singleShot(0, lambda: self.prompt_league_mode(event))
            return
        if kind == 'league_session_ended':
            if event['session'] == self.league_session_token:
                self.league_session_token = None
                self.league_selected_session = None
                if self.active_league_dialog is not None:
                    self.active_league_dialog.reject()
            return
        if kind in ('quick_rule_ready', 'quick_rule_error'):
            callback = self.quick_rule_callbacks.pop(event.get('token'), None)
            if callback:
                callback(event)
            return
        if kind == 'pipeline_remove' and hasattr(self, 'runtime_games'):
            self.runtime_games.pop(event.get('key'), None)
            self.game_log_running.pop(event.get('key'), None)
            self.refresh_table()
            self.refresh_dashboard()
            return
        if kind == 'pipeline_state' and hasattr(self, 'runtime_games'):
            data = event['data']
            previous_running = self.game_log_running.get(data['key'], False)
            if data.get('running') and not previous_running:
                self.append_log('[게임 감지] ' + str(data.get('localized_name') or data.get('game_name') or data.get('process')) + ' 실행 감지')
            elif previous_running and not data.get('running'):
                self.append_log('[게임 감지] ' + str(data.get('localized_name') or data.get('game_name') or data.get('process')) + ' 종료')
            self.game_log_running[data['key']] = bool(data.get('running'))
            self.runtime_games[data['key']] = dict(data)
            self.refresh_table()
            self.refresh_dashboard()
            return
        if kind == 'detected_games' and hasattr(self, 'runtime_games'):
            active = {p.casefold() for p in event.get('data', [])}
            for process, details in event.get('game_details', {}).items():
                existing = next((x for x in self.runtime_games.values() if x.get('process', '').casefold() == process), None)
                if existing is None:
                    key = normalized_name(details.get('name')) or process
                    self.runtime_games.setdefault(key, {'key': key, 'process': process, 'game_name': details.get('name'), 'stage': '감지됨', 'running': True})
            for g in self.runtime_games.values():
                g['running'] = bool(active & {p.casefold() for p in g.get('processes', [g.get('process', '')])})
            self.refresh_table()
            self.refresh_dashboard()
            return
        ExistingWindow.on_event(self, event)
        if hasattr(self, 'runtime_games'):
            if kind == 'error' and event.get('operation') == 'check':
                import time
                self.connection_failures += 1
                self.connection_retry_at = time.monotonic() + min(300, 5 * 2 ** min(6, self.connection_failures))
                self.account_status.setText('치지직 연결을 확인하지 못했습니다. 스튜디오 로그인 후 다시 연결해 주세요.')
            if kind == 'checked':
                self.ensure_official_api_check()
                import time
                self.last_category_observed_at = time.monotonic()
                self.connection_retry_at = 0
                self.connection_failures = 0
                self.last_category = event.get('category_name') or event.get('text', '').replace('연결 성공 · ', '')
            if kind == 'applied':
                import time
                self.last_category_observed_at = time.monotonic()
                self.connection_verified = True
                self.last_category = event.get('category_name') or event.get('text', '').split(' → ')[-1]
                self.last_applied_at = datetime.now().strftime('%H:%M:%S')
            self.refresh_dashboard()

    def closeEvent(self, event):
        if not self.config.get('close_to_tray', True):
            event.ignore()
            self.quit_app()
            return
        super().closeEvent(event)

    def changeEvent(self, event):
        if self.config.get('minimize_to_tray', True):
            super().changeEvent(event)
        else:
            from PySide6.QtWidgets import QMainWindow
            QMainWindow.changeEvent(self, event)
