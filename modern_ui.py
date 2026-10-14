"""Six persistent pages over the existing app controller and worker signals."""
import copy
from collections import deque
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSize
from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout,
    QGridLayout, QScrollArea, QTabWidget, QListWidgetItem, QComboBox, QLineEdit,
    QCheckBox, QTableView, QHeaderView, QAbstractItemView, QPushButton, QDialog,
    QFormLayout, QTextEdit, QApplication)
from app_icons import app_icon, set_button_icon
from core import Rule
from normalization import normalized_name, alias_conflicts
from scheduling import HOUR_OPTIONS
from storage import save_config
from theme import TOKENS
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
    """Offline diagnostic used by Windows CI, including bundled icon fonts."""
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
            native = [name for name in ('main', 'modern_ui', 'app_icons', 'theme', 'automation', 'worker')
                      if getattr(sys.modules.get(name), '__file__', '').endswith(('.pyd', '.so'))]
            if getattr(sys, 'frozen', False):
                assert len(native) == 6, 'A first-party native module was replaced with source'
            (destination / 'packaged-checks.json').write_text(json.dumps(
                {'icons': True, 'pages': 6, 'native_modules': native, 'frozen': bool(getattr(sys, 'frozen', False))},
                indent=2), encoding='utf-8')
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


def scroll_page(widget):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(widget)
    return scroll


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
            self.nav.addItem(QListWidgetItem(app_icon(name, '#D4D0C6'), title))
        self.nav.blockSignals(False)
        self.ui_ready = True
        self.nav.setCurrentRow(0)
        self.switch_page(0)
        self.refresh_table()
        self.refresh_connection_page()
        self.refresh_dashboard()
        # Keep shell/buttons responsive at every logical DPI size.
        for widget in self.findChildren(QPushButton):
            widget.setAccessibleName(widget.text() or widget.toolTip() or '작업')
        self.log.document().setMaximumBlockCount(1000)
        for note in old[4].findChildren(QLabel):
            if '200줄' in note.text():
                note.setText('최근 1,000줄 표시 · 상세 로그는 최대 4MB 순환 저장')
        self.log_filter = QComboBox()
        self.log_filter.addItems(['전체', '게임 감지', '카테고리 검색', '자동 매칭', '카테고리 변경',
                                 '치지직 연결', '확장프로그램 통신', '업데이트', '오류'])
        old[4].layout().itemAt(0).layout().insertWidget(0, self.log_filter)
        self.log_filter.currentTextChanged.connect(self.render_logs)
        self.log_entries = deque(maxlen=1000)

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
        layout = QGridLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)
        self.dashboard_values = {}
        hero, box = card('현재 실행 중인 게임')
        self.dashboard_game = label('현재 실행 중인 게임이 없습니다.', 'heroGame')
        self.dashboard_game_meta = label('게임을 실행하면 자동으로 감지하여 방송 카테고리를 검색합니다.')
        box.addStretch(1)
        box.addWidget(self.dashboard_game)
        box.addWidget(self.dashboard_game_meta)
        box.addStretch(1)
        box.addWidget(action('게임 목록 관리', lambda: self.nav.setCurrentRow(1), 'games'))
        layout.addWidget(hero, 0, 0, 2, 2)
        positions = {'extension': (0, 2), 'automation': (1, 2), 'game': (2, 0), 'category': (2, 1)}
        for key, title in (('automation', '자동화 상태'), ('game', '감지 및 매칭'),
                           ('category', '치지직 카테고리'), ('extension', '브라우저 확장프로그램')):
            c, dot, value, meta = self._make_status_card(title, '확인 전', '')
            self.dashboard_values[key] = (value, meta, dot)
            layout.addWidget(c, *positions[key])
        activity, box = card('최근 활동')
        self.dashboard_activity = label('아직 기록된 활동이 없습니다.')
        box.addWidget(self.dashboard_activity)
        box.addStretch(1)
        box.addWidget(action('전체 로그 보기', lambda: self.nav.setCurrentRow(5), 'logs'))
        layout.addWidget(activity, 2, 2)
        for i in range(3):
            layout.setColumnStretch(i, 1)
        layout.setRowStretch(0, 1)
        layout.setRowStretch(1, 1)
        layout.setRowStretch(2, 2)
        return scroll_page(page)

    def representative_game(self):
        active = [g for g in self.runtime_games.values() if g.get('running')]
        chosen = [g for g in active if g.get('representative')]
        return chosen[0] if len(chosen) == 1 else active[0] if len(active) == 1 else None

    def refresh_dashboard(self):
        if not getattr(self, 'ui_ready', False):
            return
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
        self.dashboard_values['game'][0].setText(g.get('game_name') or g.get('process') if g else '감지된 게임 없음')
        self.dashboard_values['game'][1].setText(g.get('stage', '감지됨') if g else '게임 실행을 기다립니다')
        if g:
            self.dashboard_game.setText(g.get('game_name') or g.get('process') or '')
            self.dashboard_game_meta.setText('\n'.join([
                '실행 파일: ' + g.get('process', ''), '카테고리: ' + g.get('category_name', '확인 중'),
                '감지 방식: Discord 공개 게임 목록 + 실행 파일 이름', '매칭 상태: ' + g.get('stage', '감지됨')]))
        else:
            self.dashboard_game.setText('현재 실행 중인 게임이 없습니다.' if not any(x.get('running') for x in self.runtime_games.values())
                                        else '여러 게임이 실행 중입니다. 대표 게임을 선택해 주세요.')
            self.dashboard_game_meta.setText('게임을 실행하면 자동으로 감지하여 방송 카테고리를 검색합니다.')
        self.dashboard_values['category'][0].setText((self.last_category or '아직 확인하지 않음') if self.connection_verified else '확인할 수 없음' if self.last_category else '아직 확인하지 않음')
        self.dashboard_values['category'][1].setText('마지막 적용: ' + (self.last_applied_at or '없음') + (' · 마지막 확인: ' + self.last_category if self.last_category and not self.connection_verified else ''))
        info = self.bridge.extension_status()
        self.dashboard_values['extension'][0].setText(info['state'])
        self.dashboard_values['extension'][1].setText('버전: ' + (info.get('version') or '확인할 수 없음'))
        for key, (value, meta, dot) in self.dashboard_values.items():
            success = value.text() in ('실행 중', '정상 연결') or key == 'category' and bool(self.last_category)
            dot.setPixmap(app_icon('success' if success else 'clock', TOKENS['success'] if success else TOKENS['muted']).pixmap(16, 16))
        self.dashboard_activity.setText('\n'.join(self.recent_activity) or '아직 기록된 활동이 없습니다.')

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
        self.table.verticalHeader().setDefaultSectionSize(50)
        h = self.table.horizontalHeader()
        for i in (0, 1, 2):
            h.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        for i in (3, 4, 5):
            h.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self.update_rule_selection_info())
        self.table.clicked.connect(lambda *_: self.show_game_details())
        self.table.doubleClicked.connect(lambda *_: self.show_game_details())
        layout.addWidget(self.table, 1)
        self.rule_empty = label('등록된 게임이 없습니다. 게임을 실행하거나 게임 추가를 선택해 주세요.', 'emptyRules')
        self.rule_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.rule_empty)
        self.rule_selection_info = label('게임을 선택하면 연결과 상세 정보를 관리할 수 있습니다.')
        layout.addWidget(self.rule_selection_info)
        row = QHBoxLayout()
        row.addWidget(action('수정', self.edit_rule, 'edit'))
        row.addWidget(action('자세히', self.show_game_details, 'details'))
        row.addWidget(action('삭제', self.remove_rule, 'delete'))
        row.addStretch()
        row.addWidget(action('위로', lambda: self.move_rule(-1), 'up'))
        row.addWidget(action('아래로', lambda: self.move_rule(1), 'down'))
        layout.addLayout(row)
        self.pages.addWidget(page)

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
        self.table.setVisible(bool(rows))
        self.rule_stats_text.setText(f'연결 {len(self.rules) + len(self.auto_rules)}개 · 미확정 {len(self.auto_pending)}개')
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
        self.rule_selection_info.setText(f"{row['game']} · {row['process']} → {row['category']} · {row['state']}" if row
                                         else '게임을 선택하면 연결과 상세 정보를 관리할 수 있습니다.')

    def edit_rule(self, _checked=False, new=False):
        if new:
            return super().edit_rule(new=True)
        row = self.selected_game()
        if not row:
            return
        if row['kind'] == 'pending':
            return self.resolve_pending()
        if row['kind'] == 'auto':
            self.convert_rule('manual')
        return super().edit_rule()

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

    def show_game_details(self, *_):
        row = self.selected_game()
        if not row:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(row['game'] + ' · 게임 상세')
        dlg.resize(620, 720)
        layout = QVBoxLayout(dlg)
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
        layout.addWidget(scroll_page(body))
        message = label('별칭을 저장하면 이후 검색에 사용합니다. 실행 파일만으로 TFT를 추측하지 않습니다.')
        layout.addWidget(message)

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
        layout.addLayout(tools)
        tools = QHBoxLayout()
        tools.addWidget(action('수동 연결', lambda: (self.convert_rule('manual', row['process']), dlg.accept()), 'edit'))
        tools.addWidget(action('자동 연결', lambda: (self.convert_rule('auto', row['process']), dlg.accept()), 'automation'))
        tools.addWidget(action('감지 기록', lambda: (dlg.accept(), self.nav.setCurrentRow(5)), 'logs'))
        tools.addWidget(action('저장', save_details, 'success', True))
        layout.addLayout(tools)
        dlg.exec()
        dlg.deleteLater()

    def choose_representative(self, process):
        self.config['preferred_process'] = process
        self.persist()

    def build_options(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(14)

        def check(name, text, key, description, parent_layout):
            widget = QCheckBox(text)
            widget.setChecked(self.config.get(key, True))
            setattr(self, name, widget)
            parent_layout.addWidget(widget)
            parent_layout.addWidget(label(description))
            return widget

        c, box = card('게임 감지')
        check('auto_detect', 'Discord 목록 기반 자동 감지', 'auto_detect', '계정 로그인 없이 실행 파일 이름을 공개 게임 목록과 대조합니다.', box)
        self.interval = QComboBox()
        for sec in (3, 5, 10, 15, 30, 60):
            self.interval.addItem(f'{sec}초', sec)
        self.interval.setCurrentIndex(max(0, self.interval.findData(self.config.get('interval', 5))))
        form = QFormLayout()
        form.addRow('게임 감지 주기', self.interval)
        box.addLayout(form)
        box.addWidget(label('보조 프로세스 통합 · 게임 종료 확인 · 안전한 대표 게임 선택은 항상 적용됩니다.'))
        self.auto_aggressive = QCheckBox('자동 선택 강화 · 필수')
        self.auto_aggressive.setChecked(True)
        self.auto_aggressive.setEnabled(False)
        box.addWidget(self.auto_aggressive)
        layout.addWidget(c)
        c, box = card('카테고리 자동 변경')
        check('auto_start_change', '연결되면 자동 변경 시작', 'auto_start_change', '게임이 바뀌면 안정화 후 반영합니다. 같은 카테고리는 반복 요청하지 않습니다.', box)
        check('only_when_live', '방송 중일 때만 적용', 'only_when_live', '실제 방송 상태를 확인할 수 없으면 적용을 보류합니다.', box)
        box.addWidget(label('수동 규칙 우선 · 낮은 신뢰도는 확인 필요로 분리 · 실패 시 제한된 백오프 재시도'))
        layout.addWidget(c)
        c, box = card('카테고리 검색')
        check('chzzk_open_enabled', '공식 API 보조 검색', 'chzzk_open_enabled', '빌드 인증 정보가 있을 때 사용하며 기존 공개 API와 Studio 검색 경로를 유지합니다.', box)
        self.chzzk_open_status = label('연결 확인 전', 'inlineStatus')
        box.addWidget(self.chzzk_open_status)
        box.addWidget(action('공식 API 연결 확인', self.test_chzzk_open_connection, 'connections'))
        self.category_sync = QComboBox()
        for hour in HOUR_OPTIONS:
            self.category_sync.addItem(f'{hour}시간', hour)
        self.category_sync.setCurrentIndex(max(0, self.category_sync.findData(self.config.get('category_sync_hours', 6))))
        form = QFormLayout()
        form.addRow('카테고리 정기 동기화', self.category_sync)
        box.addLayout(form)
        box.addWidget(label('기본 6시간 · 새로운 게임은 즉시 개별 검색합니다. 검증된 캐시는 오프라인에서도 재사용합니다.'))
        layout.addWidget(c)
        advanced = QPushButton('고급 설정 펼치기')
        set_button_icon(advanced, 'settings')
        layout.addWidget(advanced)
        c, box = card('Discord 데이터 갱신')
        self.discord_refresh = QComboBox()
        for hour in (1, 6, 12, 24, 72, 168):
            self.discord_refresh.addItem(f'{hour}시간', hour)
        self.discord_refresh.setCurrentIndex(max(0, self.discord_refresh.findData(self.config.get('discord_refresh_hours', 24))))
        box.addWidget(self.discord_refresh)
        c.hide()
        advanced.clicked.connect(lambda: (c.setVisible(not c.isVisible()), advanced.setText('고급 설정 접기' if c.isVisible() else '고급 설정 펼치기')))
        layout.addWidget(c)
        layout.addWidget(action('설정 저장', self.save_options, 'success', True))
        layout.addStretch()
        self.pages.addWidget(scroll_page(page))
        # Existing save_options reads these even before program settings are composed.
        for name, key in (('notify', 'notify'), ('pending_sound', 'pending_sound'), ('start_hidden', 'start_hidden'),
                          ('autostart', 'autostart'), ('auto_update', 'auto_update'), ('update_notify', 'update_notify')):
            widget = QCheckBox()
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
        c, box = card('백그라운드 및 알림')
        texts = (('autostart', 'Windows 로그인 시 백그라운드 실행', '메인 창을 열지 않고 트레이에서 실행합니다.'),
                 ('start_hidden', '직접 실행할 때도 트레이로 시작', '첫 설정 안내가 완료된 뒤 적용합니다.'),
                 ('notify', '카테고리 변경 알림', '변경 확인이 완료되면 알립니다.'),
                 ('pending_sound', '확인 필요한 새 게임 알림음', '같은 게임의 반복 감지는 알리지 않습니다.'),
                 ('update_notify', '새 버전 알림', '같은 버전은 반복 알림하지 않습니다.'))
        for name, text, hint in texts:
            w = getattr(self, name)
            w.setText(text)
            box.addWidget(w)
            box.addWidget(label(hint))
        self.close_to_tray = QCheckBox('창 닫기 시 트레이 유지')
        self.close_to_tray.setChecked(self.config.get('close_to_tray', True))
        self.minimize_to_tray = QCheckBox('최소화 시 트레이 이동')
        self.minimize_to_tray.setChecked(self.config.get('minimize_to_tray', True))
        self.detailed_logs = QCheckBox('상세 로그 순환 저장')
        self.detailed_logs.setChecked(self.config.get('detailed_logs', True))
        for w in (self.close_to_tray, self.minimize_to_tray, self.detailed_logs):
            box.addWidget(w)
        layout.addWidget(c)
        c, box = card('프로그램 업데이트')
        self.auto_update.setText('새 릴리스 자동 확인')
        box.addWidget(self.auto_update)
        form = QFormLayout()
        form.addRow('자동 확인 주기', self.update_check_interval)
        box.addLayout(form)
        box.addWidget(label('최소 1시간 · 기본 3시간 · 마지막 확인 시각을 기준으로 예약합니다. 게임 감지 주기와 별개입니다.'))
        self.allow_prerelease = QCheckBox('베타(사전 릴리스)도 확인')
        self.allow_prerelease.setChecked(self.config.get('allow_prerelease', False))
        box.addWidget(self.allow_prerelease)
        box.addWidget(action('지금 확인', self.check_for_updates_manual, 'refresh'))
        layout.addWidget(c)
        layout.addWidget(action('설정 저장', self.save_options, 'success', True))
        layout.addStretch()
        return scroll_page(page)

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

    def append_log(self, text):
        from diagnostics import log_kind, redact
        text = redact(str(text))
        stamp = datetime.now().strftime('%H:%M:%S')
        if hasattr(self, 'log_entries'):
            self.log_entries.append((stamp, log_kind(text), text))
        super().append_log(text)
        if hasattr(self, 'log_filter') and self.log_filter.currentIndex() != 0:
            self.render_logs()
        if hasattr(self, 'recent_activity'):
            self.recent_activity.append(stamp + ' — ' + text)
        self.refresh_dashboard()
        if not self.preview and self.config.get('detailed_logs', True):
            from diagnostics import record_log
            record_log(text)

    def render_logs(self):
        selected = self.log_filter.currentText()
        self.log.setPlainText('\n'.join(f'{t}  [{k}] {s}' for t, k, s in self.log_entries if selected == '전체' or k == selected))

    def on_event(self, event):
        # Existing tests/controller clients may call the method on a minimal host.
        from main import ExistingWindow
        kind = event['kind']
        if kind == 'pipeline_remove' and hasattr(self, 'runtime_games'):
            self.runtime_games.pop(event.get('key'), None)
            return
        if kind == 'pipeline_state' and hasattr(self, 'runtime_games'):
            self.runtime_games[event['data']['key']] = event['data']
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
