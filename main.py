import copy
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import sys
import uuid
from PySide6.QtCore import Qt, QLockFile, QTimer, QEvent, QEasingCurve, QPropertyAnimation, QParallelAnimationGroup, QSize, QPoint
from PySide6.QtGui import (QAction, QColor, QCursor, QFont, QIcon, QPainter, QPalette, QPixmap,
                           QLinearGradient)
from PySide6.QtWidgets import (QApplication, QAbstractItemView, QCheckBox, QComboBox,
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem, QMainWindow,
    QPushButton, QSpinBox, QStyle, QSystemTrayIcon, QStackedWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget, QFrame, QGraphicsOpacityEffect, QScrollArea, QGridLayout, QSizeGrip, QGraphicsDropShadowEffect)
from ui_components import SettingsComboBox as QComboBox, FramelessDialog as QDialog, choose_executable
from core import Rule, channel_id
from storage import (data_dir, load_config, save_config, set_windows_autostart,
                     ensure_start_menu_shortcut)
from bridge import LocalExtensionBridge, BridgeError
from autodetect import (cleanup_auto_mappings, serialize_rules, is_ignored_process,
                        category_choice_process_key)
from worker import Worker
from version import APP_VERSION
from onboarding import FirstRunSetup, needs_setup
from updater import UpdateCheckWorker, AutoUpdateWindow
from ui_components import information as show_info, warning as show_warning, error as show_error


def play_pending_alert():
    """Play a short notification without blocking game detection or the UI."""
    if sys.platform == 'win32':
        try:
            import winsound
            winsound.PlaySound('SystemExclamation', winsound.SND_ALIAS | winsound.SND_ASYNC)
            return
        except (ImportError, OSError, RuntimeError):
            pass
    QApplication.beep()


from theme import STYLE, apply_theme as apply_light_theme
from app_icons import app_icon, set_button_icon

def _resource_path(name):
    """Return a bundled resource path for source and PyInstaller builds."""
    roots = []
    bundle = getattr(sys, '_MEIPASS', None)
    if bundle:
        roots.append(Path(bundle))
    roots.append(Path(sys.executable).resolve().parent)
    roots.append(Path(__file__).resolve().parent)

    for root in roots:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return roots[-1] / name


def icon():
    icon_path = _resource_path('chzzk_auto_category.ico')
    loaded = QIcon(str(icon_path))
    if not loaded.isNull():
        return loaded

    # Fallback icon only if the packaged resource is unexpectedly missing.
    p = QPixmap(64, 64)
    p.fill(Qt.GlobalColor.transparent)
    painter = QPainter(p)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#24272a'))
    painter.drawRoundedRect(3, 3, 58, 58, 17, 17)
    painter.setPen(QColor('#ffffff'))
    painter.setFont(QFont('Segoe UI', 31, QFont.Weight.Bold))
    painter.drawText(p.rect().adjusted(0, 0, 0, -1), Qt.AlignmentFlag.AlignCenter, 'C')
    painter.end()
    return QIcon(p)


def button(text, callback, primary=False):
    result = QPushButton(text)
    if primary:
        result.setObjectName('primary')
    set_button_icon(result, next((name for key, name in (('닫기', 'close'), ('취소', 'close'), ('삭제', 'delete'), ('지우기', 'delete'), ('수정', 'edit'), ('검색', 'search'), ('확인', 'refresh'), ('설정', 'settings'), ('저장', 'success'), ('연결', 'connections'), ('트레이', 'tray'), ('로그', 'logs'), ('위로', 'up'), ('아래로', 'down'), ('업데이트', 'download')) if key in text), 'info'), '#FFFFFF' if primary else '#252525')
    result.clicked.connect(callback)
    return result


class CustomTitleBar(QFrame):
    def __init__(self, window):
        super().__init__(window)
        self.host = window
        self._drag_offset = QPoint()
        self._dragging = False
        self.setObjectName('titleBar')
        self.setFixedHeight(46)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 7, 9, 7)
        layout.setSpacing(8)

        app_icon = QLabel()
        app_icon.setPixmap(icon().pixmap(20, 20))
        app_icon.setFixedSize(22, 22)
        layout.addWidget(app_icon)

        title = QLabel('CHZZK Auto Category')
        title.setObjectName('titleBarApp')
        layout.addWidget(title)
        version = QLabel(f'v{APP_VERSION}')
        version.setObjectName('titleBarVersion')
        layout.addWidget(version)
        layout.addStretch(1)

        minimize = QPushButton('')
        minimize.setObjectName('windowButton')
        minimize.setToolTip('최소화')
        set_button_icon(minimize, 'minimize')
        minimize.clicked.connect(window.showMinimized)
        layout.addWidget(minimize)

        self.maximize = QPushButton('')
        self.maximize.setObjectName('windowButton')
        self.maximize.setToolTip('최대화 / 복원')
        set_button_icon(self.maximize, 'maximize')
        self.maximize.clicked.connect(self.toggle_maximize)
        layout.addWidget(self.maximize)

        close = QPushButton('')
        close.setObjectName('windowClose')
        close.setProperty('class', 'windowClose')
        close.setStyleSheet('QPushButton { background: transparent; border: none; border-radius: 6px; min-width:34px; max-width:34px; min-height:28px; max-height:28px; padding:0; color:#a9b0b7; font-size:16px; } QPushButton:hover { background:#d94b56; color:white; }')
        close.setToolTip('트레이로 숨기기')
        set_button_icon(close, 'close')
        close.clicked.connect(window.close)
        layout.addWidget(close)

    def toggle_maximize(self):
        if self.host.isMaximized():
            self.host.showNormal()
            self.maximize.setText('')
        else:
            self.host.showMaximized()
            self.maximize.setText('')
        QTimer.singleShot(0, self.host._sync_window_frame)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.host.isMaximized():
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.host.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and (event.buttons() & Qt.MouseButton.LeftButton) and not self.host.isMaximized():
            self.host.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        super().mouseReleaseEvent(event)


class TrayPopup(QWidget):
    # Custom tray dashboard shown instead of the native QMenu.
    def __init__(self, host):
        super().__init__(None)
        self.host = host
        self.setObjectName('trayPopupWindow')
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(380)
        self._show_anim = None
        self._target_pos = QPoint()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)

        panel = QFrame()
        panel.setObjectName('trayPanel')
        shadow = QGraphicsDropShadowEffect(panel)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 170))
        panel.setGraphicsEffect(shadow)
        outer.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 17, 18, 16)
        layout.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(10)
        app_icon = QLabel()
        app_icon.setObjectName('trayAppIcon')
        app_icon.setPixmap(icon().pixmap(32, 32))
        app_icon.setFixedSize(34, 34)
        head.addWidget(app_icon)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel('CHZZK Auto Category')
        title.setObjectName('trayTitle')
        version = QLabel('Windows 앱 ' + APP_VERSION)
        version.setObjectName('trayCaption')
        titles.addWidget(title)
        titles.addWidget(version)
        head.addLayout(titles, 1)
        layout.addLayout(head)

        self.status_card = QFrame()
        self.status_card.setObjectName('trayStatusCard')
        status_layout = QVBoxLayout(self.status_card)
        status_layout.setContentsMargins(14, 12, 14, 12)
        status_layout.setSpacing(4)
        self.status_title = QLabel('자동 변경 일시정지')
        self.status_title.setObjectName('trayStatusTitle')
        self.status_text = QLabel('등록된 게임 실행을 기다립니다.')
        self.status_text.setObjectName('trayCaption')
        self.status_text.setWordWrap(True)
        status_layout.addWidget(self.status_title)
        status_layout.addWidget(self.status_text)
        layout.addWidget(self.status_card)

        self.open_button = self._button('앱 열기', primary=True)
        self.open_button.clicked.connect(lambda: self._invoke(self.host.show_main))
        layout.addWidget(self.open_button)

        self.toggle_button = self._button('자동 변경 시작')
        self.toggle_button.clicked.connect(lambda: self._invoke(self.host.toggle))
        layout.addWidget(self.toggle_button)

        divider = QFrame()
        divider.setObjectName('trayDivider')
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        section = QLabel('빠른 이동')
        section.setObjectName('traySection')
        layout.addWidget(section)

        quick = QHBoxLayout()
        quick.setSpacing(8)
        connection = self._button('연결 상태')
        logs = self._button('로그')
        settings = self._button('설정')
        connection.clicked.connect(lambda: self._invoke(lambda: self.host.open_page_from_tray(2)))
        logs.clicked.connect(lambda: self._invoke(lambda: self.host.open_page_from_tray(4)))
        settings.clicked.connect(lambda: self._invoke(lambda: self.host.open_page_from_tray(5)))
        quick.addWidget(connection)
        quick.addWidget(logs)
        quick.addWidget(settings)
        layout.addLayout(quick)

        self.info_card = QFrame()
        self.info_card.setObjectName('trayInfoCard')
        info_layout = QVBoxLayout(self.info_card)
        info_layout.setContentsMargins(14, 12, 14, 12)
        info_layout.setSpacing(7)
        self.bridge_line = QLabel('로컬 브리지 · 확인 중')
        self.extension_line = QLabel('Chrome 확장 · 연결 대기')
        self.account_line = QLabel('치지직 계정 · 확인 전')
        self.last_line = QLabel('최근 적용 · 없음')
        for label in (self.bridge_line, self.extension_line, self.account_line, self.last_line):
            label.setObjectName('trayInfoText')
            label.setWordWrap(True)
            info_layout.addWidget(label)
        layout.addWidget(self.info_card)

        self.update_button = self._button('업데이트 설치')
        self.update_button.clicked.connect(lambda: self._invoke(self.host.open_pending_update))
        self.update_button.hide()
        layout.addWidget(self.update_button)

        divider2 = QFrame()
        divider2.setObjectName('trayDivider')
        divider2.setFixedHeight(1)
        layout.addWidget(divider2)

        quit_button = self._button('앱 종료', danger=True)
        quit_button.clicked.connect(lambda: self._invoke(self.host.quit_app))
        layout.addWidget(quit_button)

        self.setStyleSheet(r'''
            QWidget#trayPopupWindow { background: transparent; }
            QFrame#trayPanel {
                background: #F3F1EB;
                border: 1px solid #D7D3C9;
                border-radius: 20px;
            }
            QLabel#trayAppIcon { background: transparent; border: none; }
            QLabel#trayTitle { color: #252525; font-size: 14px; font-weight: 800; }
            QLabel#trayCaption { color: #77756F; font-size: 11px; }
            QFrame#trayStatusCard, QFrame#trayInfoCard {
                background: #FFFFFF;
                border: 1px solid #D7D3C9;
                border-radius: 14px;
            }
            QLabel#trayStatusTitle { color: #252525; font-size: 13px; font-weight: 750; }
            QLabel#trayInfoText { color: #77756F; font-size: 11px; }
            QLabel#traySection { color: #77756F; font-size: 10px; font-weight: 700; padding: 2px 2px 0 2px; }
            QFrame#trayDivider { background: #D7D3C9; border: none; }
            QPushButton#trayButton {
                text-align: left;
                background: #FFFFFF;
                color: #252525;
                border: 1px solid #D7D3C9;
                border-radius: 13px;
                min-height: 22px;
                padding: 10px 13px;
                font-weight: 650;
            }
            QPushButton#trayButton:hover { background: #E3DFD5; border-color: #BDB7AB; }
            QPushButton#trayPrimary {
                text-align: left;
                background: #252525;
                color: #FFFFFF;
                border: 1px solid #252525;
                border-radius: 13px;
                min-height: 22px;
                padding: 10px 13px;
                font-weight: 800;
            }
            QPushButton#trayPrimary:hover { background: #484848; border-color: #484848; }
            QPushButton#trayDanger {
                text-align: left;
                background: #FFFFFF;
                color: #B94A59;
                border: 1px solid #EBCBD1;
                border-radius: 13px;
                min-height: 22px;
                padding: 10px 13px;
                font-weight: 650;
            }
            QPushButton#trayDanger:hover { background: #FCECF0; border-color: #EBCBD1; }
        ''')

    def _button(self, text, primary=False, danger=False):
        result = QPushButton(text)
        set_button_icon(result, 'close' if danger else 'start' if primary else 'info', '#FFFFFF' if primary else '#252525')
        result.setCursor(Qt.CursorShape.PointingHandCursor)
        result.setObjectName('trayPrimary' if primary else ('trayDanger' if danger else 'trayButton'))
        return result

    def _invoke(self, callback):
        self.hide()
        QTimer.singleShot(0, callback)

    def showEvent(self, event):
        super().showEvent(event)
        target = self.pos()
        start = QPoint(target.x(), target.y() + 10)
        self.move(start)
        self.setWindowOpacity(0.0)
        group = QParallelAnimationGroup(self)
        fade = QPropertyAnimation(self, b'windowOpacity', group)
        fade.setDuration(180)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        slide = QPropertyAnimation(self, b'pos', group)
        slide.setDuration(210)
        slide.setStartValue(start)
        slide.setEndValue(target)
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.addAnimation(fade)
        group.addAnimation(slide)
        self._show_anim = group
        group.start()

    def refresh(self):
        running = bool(self.host.enabled)
        self.status_title.setText('자동 변경 실행 중' if running else '자동 변경 일시정지')
        self.toggle_button.setText('자동 변경 일시정지' if running else '자동 변경 시작')
        runtime = str(getattr(self.host, 'last_runtime_status', '') or '').strip()
        self.status_text.setText(runtime or ('게임을 감지하고 있습니다.' if running else '자동 변경을 시작하면 게임을 감지합니다.'))

        bridge_ok = not bool(getattr(self.host, 'bridge_start_error', ''))
        extension_ok = bool(getattr(getattr(self.host, 'bridge', None), 'connected', False))
        account_ok = bool(getattr(self.host, 'connection_verified', False))
        self.bridge_line.setText('로컬 브리지 · ' + ('정상' if bridge_ok else '오류'))
        self.extension_line.setText('Chrome 확장 · ' + ('연결됨' if extension_ok else '연결 대기'))
        self.account_line.setText('치지직 계정 · ' + ('연결 확인됨' if account_ok else '확인 전'))
        self.last_line.setText('최근 적용 · ' + str(getattr(self.host, 'last_applied_text', '없음') or '없음'))

        release = getattr(self.host, 'pending_update_release', None)
        if isinstance(release, dict):
            version = str(release.get('version') or '?')
            self.update_button.setText(f'업데이트 {version} 설치')
            self.update_button.show()
        else:
            self.update_button.hide()
        self.adjustSize()


class RuleDialog(QDialog):
    def __init__(self, parent, existing=None):
        super().__init__(parent)
        self.existing_rule = existing
        self.setWindowTitle('게임과 카테고리 연결')
        self.resize(680, 610)
        self.worker = parent.worker
        self.request_id = None
        self.selected = None
        self.result_rule = None
        self._process_user_edited = False
        self._game_details = {}
        self._keyword_user_edited = False
        self._existing_process = bool(existing)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(QLabel('1. 게임 실행 파일을 선택하거나 이름을 직접 입력해 주세요.'))
        row = QHBoxLayout()
        self.process = QComboBox()
        self.process.setView(QListView(self.process))
        self.process.setEditable(True)
        self.process.setMinimumWidth(260)
        self.process.lineEdit().setPlaceholderText('실행 중인 게임 확인 중…')
        self.process.lineEdit().textEdited.connect(self._mark_process_user_edited)
        row.addWidget(self.process, 1)
        row.addWidget(button('파일 선택', self.browse))
        row.addWidget(button('새로고침', lambda: self.worker.submit('processes')))
        layout.addLayout(row)
        search_title = QLabel('2. 게임 이름을 검색하고 치지직 카테고리를 선택해 주세요.')
        layout.addWidget(search_title)
        search_flow = QLabel(
            '영문 게임명도 입력할 수 있습니다. Discord 게임명/별칭을 CHZZK 카테고리 ID와 비교해 '
            '한국어 카테고리 후보를 만들고, 공식 Open API와 스튜디오 검색 결과를 함께 점수화합니다.'
        )
        search_flow.setObjectName('softHint')
        search_flow.setWordWrap(True)
        layout.addWidget(search_flow)
        row = QHBoxLayout()
        self.keyword = QLineEdit()
        self.keyword.setPlaceholderText('예: VRChat, Minecraft, 오버워치 2')
        self.keyword.textEdited.connect(self._mark_keyword_user_edited)
        self.process.activated.connect(lambda _index: self.prefill_keyword_from_process(self.process.currentText()))
        self.search_button = button('검색', self.search)
        row.addWidget(self.keyword, 1)
        row.addWidget(self.search_button)
        layout.addLayout(row)
        self.results = QListWidget()
        self.results.setSpacing(3)
        self.results.currentItemChanged.connect(self.choose)
        layout.addWidget(self.results, 1)
        self.note = QLabel('검색 흐름: Discord/입력명 → CHZZK 공식·비공식 API → 한국어 후보 → Studio 검증 → categoryId')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        controls.button(QDialogButtonBox.StandardButton.Save).setText('규칙 저장')
        controls.button(QDialogButtonBox.StandardButton.Cancel).setText('닫기')
        set_button_icon(controls.button(QDialogButtonBox.StandardButton.Cancel), 'close')
        controls.accepted.connect(self.save)
        controls.rejected.connect(self.reject)
        layout.addWidget(controls)
        self.keyword.returnPressed.connect(self.search)
        self.worker.event.connect(self.on_event)
        self.finished.connect(self.detach)
        if existing:
            self.process.setEditText(existing.process)
            self.selected = {'categoryId': existing.category_id, 'categoryValue': existing.category_name,
                             'categoryType': existing.category_type}
            detail = existing.game_name or existing.process
            self.note.setText(f'현재 연결: {detail} → {existing.category_name}')
        self.worker.submit('processes')

    def _mark_process_user_edited(self, _text):
        self._process_user_edited = True

    def detach(self, *_):
        self.worker.event.disconnect(self.on_event)

    def browse(self):
        path = choose_executable(self)
        if path:
            self.process.setEditText(Path(path).name)
            self.prefill_keyword_from_process(Path(path).name)

    def _mark_keyword_user_edited(self, _text):
        self._keyword_user_edited = True

    def prefill_keyword_from_process(self, value):
        if self._keyword_user_edited and self.keyword.text().strip():
            return
        process = str(value or '').strip()
        details = self._game_details.get(process.casefold(), {})
        name = str(details.get('keyword') or details.get('name') or Path(process).stem).strip()
        if name:
            self.keyword.setText(name)

    def search(self):
        keyword = self.keyword.text().strip()
        if not keyword:
            return
        self.request_id = uuid.uuid4().hex
        self.search_button.setEnabled(False)
        self.note.setText('검색 중…')
        self.worker.submit('search', {'keyword': keyword, 'request': self.request_id})

    def choose(self, current, _previous):
        if current:
            self.selected = current.data(Qt.ItemDataRole.UserRole)
            source = str(self.selected.get('_matchSource') or 'CHZZK')
            self.note.setText('선택: ' + self.selected['categoryValue'] + ' · ' + source)

    def on_event(self, event):
        if event['kind'] == 'processes':
            self._game_details = event.get('game_details') or {}
            text = self.process.currentText().strip()
            games = [str(value).strip() for value in event.get('data', []) if str(value).strip()]
            game_keys = {value.casefold() for value in games}
            # Preserve only a genuine user/manual entry, an existing saved rule, or a
            # value that is still present in the filtered running-game list. This
            # prevents stale values such as cl.exe from surviving a refresh.
            preserve = text if (
                self._process_user_edited
                or self._existing_process
                or text.casefold() in game_keys
            ) else ''

            self.process.blockSignals(True)
            self.process.clear()
            self.process.addItems(games)
            if preserve:
                self.process.setEditText(preserve)
            elif games:
                self.process.setCurrentIndex(0)
            else:
                self.process.setEditText('')
            self.process.blockSignals(False)

            if games:
                self.prefill_keyword_from_process(self.process.currentText())
            if not games and not preserve:
                self.process.lineEdit().setPlaceholderText('감지 목록과 일치하는 실행 중 게임이 없습니다')
            else:
                self.process.lineEdit().setPlaceholderText('현재 실행 중인 게임 또는 직접 입력')
            warning = str(event.get('warning') or '').strip()
            if warning:
                self.note.setText('Discord 목록 갱신 실패 · 저장 목록과 내장 호환 목록으로 감지합니다. 활동 기록을 확인해 주세요.')
            elif not games and self.request_id is None:
                self.note.setText('일치하는 게임을 찾지 못했습니다. 파일 선택으로 실행 파일을 지정하거나 게임 이름을 직접 검색해 주세요.')
        elif event['kind'] == 'search' and event['request'] == self.request_id:
            self.search_button.setEnabled(True)
            self.results.clear()
            self.selected = None
            for c in event['data']:
                category = str(c.get('categoryValue') or '')
                source = str(c.get('_matchSource') or 'CHZZK')
                matched_keyword = str(c.get('_matchedKeyword') or '')
                korean_name = str(c.get('_koreanCandidate') or '')
                detail_parts = [source]
                if matched_keyword and matched_keyword != category:
                    detail_parts.append('감지명: ' + matched_keyword)
                if korean_name and korean_name != category:
                    detail_parts.append('한국어 후보: ' + korean_name)
                detail = '  ·  '.join(detail_parts)
                item = QListWidgetItem(f"{category}   [{c.get('categoryType', 'GAME')}]\n{detail}")
                item.setData(Qt.ItemDataRole.UserRole, c)
                item.setSizeHint(item.sizeHint().expandedTo(QSize(0, 52)))
                self.results.addItem(item)
            if event['data']:
                engine = 'CHZZK 공식+비공식 검색' if event.get('official') else 'CHZZK 비공식 검색'
                self.note.setText(f'{engine} 결과 {len(event["data"])}개 · 가장 정확한 카테고리를 선택해 주세요.')
            else:
                self.note.setText('검색 결과가 없습니다. 게임 이름 또는 CHZZK 카테고리 상태를 확인해 주세요.')
        elif event['kind'] == 'error' and event.get('operation') == 'processes':
            self.process.lineEdit().setPlaceholderText('게임 감지 실패 · 파일 선택으로 지정해 주세요')
            self.note.setText(event['text'])
        elif event['kind'] == 'error' and event.get('operation') == 'search':
            self.search_button.setEnabled(True)
            self.note.setText(event['text'])

    def save(self):
        if not self.selected or not self.process.currentText().strip():
            show_info(self, '입력 확인', '실행 파일과 검색 결과 카테고리를 선택해 주세요.')
            return
        try:
            game_name = str(self.selected.get('_discordName') or '').strip()
            if not game_name:
                game_name = Path(self.process.currentText().strip()).stem
            match_source = str(self.selected.get('_matchSource') or '수동 선택').strip()
            self.result_rule = Rule(
                self.process.currentText().strip(),
                self.selected['categoryId'],
                self.selected['categoryValue'],
                self.selected['categoryType'],
                game_name,
                match_source,
                getattr(getattr(self, 'existing_rule', None), 'process_aliases', ()),
            )
            from normalization import normalized_name
            if self.result_rule.process.casefold() in ('leagueclient.exe', 'league of legends.exe') and normalized_name(self.result_rule.category_name) in ('리그오브레전드', '전략적팀전투'):
                from dataclasses import replace
                self.result_rule = replace(self.result_rule, process_aliases=tuple(p for p in ('League of Legends.exe', 'LeagueClient.exe') if p.casefold() != self.result_rule.process.casefold()))
        except ValueError as e:
            show_warning(self, '입력 확인', str(e))
            return
        self.accept()


class CategoryChoiceDialog(QDialog):
    def __init__(self, parent, process, game_name, candidates):
        super().__init__(parent)
        self.setWindowTitle('치지직 카테고리 선택')
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.resize(620, 500)
        self.selected_category = None
        self.save_rule = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 20)
        layout.setSpacing(14)

        title = QLabel('카테고리 후보가 여러 개 감지되었습니다')
        title.setObjectName('pageTitle')
        layout.addWidget(title)

        detected = QLabel(f'{game_name or Path(process).stem}   ·   {process}')
        detected.setObjectName('statusPill')
        layout.addWidget(detected)

        guide = QLabel(
            '게임은 하나로 감지되었지만 치지직에서 비슷한 카테고리가 여러 개 검색되었습니다. '
            '실제로 사용할 카테고리를 선택해 주세요.'
        )
        guide.setObjectName('softHint')
        guide.setWordWrap(True)
        layout.addWidget(guide)

        self.list = QListWidget()
        self.list.setSpacing(3)
        for index, candidate in enumerate(candidates):
            name = str(candidate.get('categoryValue') or '').strip()
            category_id = str(candidate.get('categoryId') or '').strip()
            source = str(candidate.get('matchSource') or 'CHZZK').strip()
            score = int(candidate.get('score') or 0)
            keyword = str(candidate.get('matchedKeyword') or '').strip()
            meta = f'{category_id}   ·   {source}'
            if keyword and keyword != name:
                meta += f'   ·   검색: {keyword}'
            if score:
                meta += f'   ·   일치도 {score}'
            item = QListWidgetItem(f'{index + 1}.  {name}\n{meta}')
            item.setData(Qt.ItemDataRole.UserRole, candidate)
            item.setSizeHint(QSize(0, 64))
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _item: self.accept_saved())
        layout.addWidget(self.list, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(button('닫기', self.reject))
        buttons.addStretch(1)
        once = button('이번만 적용', self.accept_once)
        saved = button('선택하고 규칙 저장', self.accept_saved, True)
        saved.setDefault(True)
        buttons.addWidget(once)
        buttons.addWidget(saved)
        layout.addLayout(buttons)

    def _accept_current(self, save_rule):
        item = self.list.currentItem()
        if not item:
            return
        category = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(category, dict):
            return
        self.selected_category = dict(category)
        self.save_rule = bool(save_rule)
        self.accept()

    def accept_once(self):
        self._accept_current(False)

    def accept_saved(self):
        self._accept_current(True)


class ExistingWindow(QMainWindow):
    def __init__(self, config, preview=False):
        super().__init__()
        clean_rules, clean_pending, _removed = cleanup_auto_mappings(
            config.get('auto_rules', []),
            config.get('auto_pending', []),
            manual_rules=config.get('rules', []),
        )
        config = copy.deepcopy(config)
        config['auto_rules'] = serialize_rules(clean_rules)
        config['auto_pending'] = []
        self.config = config
        self.rules = [Rule(**r) for r in config.get('rules', [])]
        self.auto_rules = [Rule(**r) for r in config.get('auto_rules', [])]
        self.auto_pending = []
        try:
            save_config(config)
        except OSError:
            pass

        self.preview = preview
        self.quitting = False
        self.enabled = False
        self.bridge_start_error = ''
        self.update_check_worker = None
        self.update_window = None
        self.pending_update_release = None
        self.manual_update_check = False
        self.last_update_notified_version = ''
        self.connection_check_pending = False
        self.connection_verified = False
        self.category_choice_dialog_active = False
        self.auto_start_armed = bool(config.get('auto_start_change', True))
        self.last_connection_check_at = '아직 확인하지 않음'
        self.last_runtime_status = '자동 변경이 시작되지 않았습니다.'
        self.last_applied_text = '없음'

        self.bridge = LocalExtensionBridge(
            port=int(config.get('bridge_port', 5000)),
            extension_id=config.get('extension_id', ''),
        )
        if not preview:
            try:
                self.bridge.start()
            except BridgeError as e:
                self.bridge_start_error = str(e)

        self.worker = Worker(copy.deepcopy(config), bridge=self.bridge)
        self.worker.event.connect(self.on_event)

        self.setWindowTitle('CHZZK Auto Category')
        self.setWindowIcon(icon())
        self.setObjectName('appWindow')
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(1360, 860)
        self.setMinimumSize(1200, 820)

        root = QWidget()
        root.setObjectName('windowRoot')
        self.setCentralWidget(root)
        self.root_layout = QVBoxLayout(root)
        self.root_layout.setContentsMargins(12, 12, 12, 12)
        self.root_layout.setSpacing(0)

        self.shell = QFrame()
        self.shell.setObjectName('shell')
        shell_layout = QVBoxLayout(self.shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        self.root_layout.addWidget(self.shell, 1)

        shadow = QGraphicsDropShadowEffect(self.shell)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 125))
        self.shell.setGraphicsEffect(shadow)

        self.title_bar = CustomTitleBar(self)
        shell_layout.addWidget(self.title_bar, 0)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(8, 0, 8, 8)
        body_layout.setSpacing(6)
        shell_layout.addWidget(body, 1)

        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(210)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 16, 14, 14)
        sidebar_layout.setSpacing(8)

        brand_card = QFrame()
        brand_card.setObjectName('brandCard')
        brand_layout = QHBoxLayout(brand_card)
        brand_layout.setContentsMargins(10, 9, 10, 9)
        brand_layout.setSpacing(9)
        brand_icon = QLabel()
        brand_icon.setObjectName('brandIcon')
        brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_icon.setPixmap(icon().pixmap(32, 32))
        brand_icon.setFixedSize(34, 34)
        brand_layout.addWidget(brand_icon)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(1)
        brand = QLabel('CHZZK AUTO')
        brand.setObjectName('brandTitle')
        brand_sub = QLabel(f'Desktop · v{APP_VERSION}')
        brand_sub.setObjectName('brandSub')
        brand_text.addWidget(brand)
        brand_text.addWidget(brand_sub)
        brand_layout.addLayout(brand_text, 1)
        sidebar_layout.addWidget(brand_card)

        nav_section = QLabel('방송 자동화')
        nav_section.setObjectName('navSection')
        sidebar_layout.addWidget(nav_section)

        self.nav = QListWidget()
        self.nav.setObjectName('navList')
        self.nav.setSpacing(1)
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.addItems([
            '▣   게임 목록',
            '◉   계정',
            '◌   연결 상태',
            '◇   미확정 항목',
            '▤   로그',
            '⚙   설정',
            '⇧   업데이트',
            'ⓘ   앱 정보',
        ])
        self.nav.currentRowChanged.connect(self.switch_page)
        sidebar_layout.addWidget(self.nav, 1)

        auto_card = QFrame()
        auto_card.setObjectName('sidebarStatus')
        auto_layout = QVBoxLayout(auto_card)
        auto_layout.setContentsMargins(11, 9, 11, 9)
        auto_layout.setSpacing(2)
        auto_title = QLabel('자동 카테고리')
        auto_title.setObjectName('sidebarStatusTitle')
        self.sidebar_auto_state = QLabel('일시정지')
        self.sidebar_auto_state.setObjectName('sidebarStatusText')
        auto_layout.addWidget(auto_title)
        auto_layout.addWidget(self.sidebar_auto_state)
        version_footer = QLabel('v' + APP_VERSION)
        version_footer.setObjectName('sidebarStatusText')
        auto_layout.addWidget(version_footer)
        sidebar_layout.addWidget(auto_card)

        tray_button = button('트레이로 숨기기', self.close)
        sidebar_layout.addWidget(tray_button)
        body_layout.addWidget(sidebar, 0)

        content = QFrame()
        content.setObjectName('contentCard')
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 24, 20, 18)
        content_layout.setSpacing(15)

        header = QHBoxLayout()
        header.setSpacing(14)
        title_wrap = QVBoxLayout()
        title_wrap.setSpacing(3)
        self.page_title = QLabel('게임 목록')
        self.page_title.setObjectName('pageTitle')
        self.page_sub = QLabel('실행 중인 게임과 치지직 카테고리 규칙을 관리합니다.')
        self.page_sub.setObjectName('pageSub')
        self.page_sub.setWordWrap(True)
        title_wrap.addWidget(self.page_title)
        title_wrap.addWidget(self.page_sub)
        header.addLayout(title_wrap, 1)

        self.toggle_button = button('자동 변경 시작', self.toggle, True)
        self.toggle_button.setMinimumHeight(38)
        header.addWidget(self.toggle_button, 0, Qt.AlignmentFlag.AlignTop)
        content_layout.addLayout(header)

        self.pages = QStackedWidget()
        content_layout.addWidget(self.pages, 1)
        body_layout.addWidget(content, 1)

        self.size_grip = QSizeGrip(self.shell)
        self.size_grip.raise_()

        self.build_rules()
        self.build_account()
        self.build_connection()
        self.build_pending_page()
        self.build_log_page()
        self.build_options()
        self.build_update_page()
        self.build_about_page()
        self.nav.setCurrentRow(0)

        self.build_tray()
        self.refresh_table()
        self.refresh_connection_page()
        self._sync_window_frame()

        if not preview:
            self.worker.start()
            self.update_timer = QTimer(self)
            self.update_timer.timeout.connect(self.check_for_updates)
            self.refresh_update_timer_interval()


    def switch_page(self, index):
        if index < 0 or index >= self.pages.count():
            return
        titles = [
            ('게임 목록', '실행 중인 게임과 치지직 카테고리 규칙을 관리합니다.'),
            ('계정', '치지직 채널과 Chrome 확장프로그램 ID를 관리합니다.'),
            ('연결 상태', '로컬 브리지, Chrome 확장, 치지직 계정 연결을 한 곳에서 확인합니다.'),
            ('미확정 항목', '자동 감지 중 직접 선택이 필요한 항목만 모아 확인합니다.'),
            ('로그', '게임 감지, 카테고리 변경, 연결 오류 기록을 시간순으로 확인합니다.'),
            ('설정', '감지 주기, 자동 실행, 알림 및 업데이트 정책을 조정합니다.'),
            ('업데이트', '현재 버전과 GitHub Release 업데이트 상태를 확인합니다.'),
            ('앱 정보', '앱과 Chrome 확장 버전, 저장 위치와 구성 정보를 확인합니다.'),
        ]
        self.pages.setCurrentIndex(index)
        title, subtitle = titles[index]
        self.page_title.setText(title)
        self.page_sub.setText(subtitle)
        if index == 2:
            self.refresh_connection_page()
        elif index == 3:
            self.refresh_pending_page()
        elif index == 6:
            self.refresh_update_page()


    def build_account(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(12)

        card = QFrame()
        card.setObjectName('panelCard')
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 17, 18, 18)
        card_layout.setSpacing(13)

        title = QLabel('치지직 계정')
        title.setObjectName('sectionTitle')
        card_layout.addWidget(title)
        guide = QLabel(
            '치지직 채널과 Chrome Web Store 확장 ID를 저장합니다. 로그인 세션 값은 Chrome 확장프로그램이 '
            '치지직 스튜디오 안에서 사용하며 Windows 앱으로 복사하지 않습니다.'
        )
        guide.setObjectName('sectionInfo')
        guide.setWordWrap(True)
        card_layout.addWidget(guide)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.channel = QLineEdit(self.config.get('channel', ''))
        self.channel.setPlaceholderText('치지직 채널 URL 또는 32자리 채널 ID')
        self.extension_id = QLineEdit(self.config.get('extension_id', ''))
        self.extension_id.setPlaceholderText('Chrome Web Store 확장 ID · 32자리')
        form.addRow('채널', self.channel)
        form.addRow('확장 ID', self.extension_id)
        card_layout.addLayout(form)

        actions = QHBoxLayout()
        actions.addWidget(button('계정 저장', self.save_account, True))
        actions.addWidget(button('저장 후 연결 확인', lambda: (self.save_account(), QTimer.singleShot(200, lambda: self.connection_tick(force=True)))))
        actions.addStretch(1)
        card_layout.addLayout(actions)
        layout.addWidget(card)

        privacy = QFrame()
        privacy.setObjectName('panelCard')
        privacy_layout = QVBoxLayout(privacy)
        privacy_layout.setContentsMargins(18, 16, 18, 16)
        privacy_layout.setSpacing(6)
        ptitle = QLabel('로컬 브리지')
        ptitle.setObjectName('sectionTitle')
        privacy_layout.addWidget(ptitle)
        ptext = QLabel(
            '브리지 주소: http://127.0.0.1:5000\n'
            '확장프로그램과 앱은 사용자 PC 내부에서 통신합니다. 연결 여부와 마지막 확인 결과는 “연결 상태” 페이지에서 확인할 수 있습니다.'
        )
        ptext.setObjectName('softHint')
        ptext.setWordWrap(True)
        privacy_layout.addWidget(ptext)
        layout.addWidget(privacy)
        layout.addStretch(1)
        self.pages.addWidget(page)

    def _make_status_card(self, title, value, meta=''):
        card = QFrame()
        card.setObjectName('statusCard')
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 13, 15, 13)
        layout.setSpacing(5)
        top = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName('statusCardTitle')
        dot = QLabel()
        dot.setPixmap(app_icon('info', '#77756F').pixmap(16, 16))
        dot.setObjectName('statusDotOff')
        top.addWidget(title_label)
        top.addStretch(1)
        top.addWidget(dot)
        layout.addLayout(top)
        value_label = QLabel(value)
        value_label.setObjectName('statusCardValue')
        value_label.setWordWrap(True)
        layout.addWidget(value_label)
        meta_label = QLabel(meta)
        meta_label.setObjectName('statusCardMeta')
        meta_label.setWordWrap(True)
        layout.addWidget(meta_label)
        return card, dot, value_label, meta_label

    def build_connection(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.bridge_status_card, self.bridge_status_dot, self.bridge_status_value, self.bridge_status_meta = self._make_status_card(
            '로컬 브리지', '확인 중', '127.0.0.1:5000'
        )
        self.extension_status_card, self.extension_status_dot, self.extension_status_value, self.extension_status_meta = self._make_status_card(
            'Chrome 확장', '연결 대기', '5초마다 자동 확인'
        )
        self.account_status_card, self.account_status_dot, self.account_status_value, self.account_status_meta = self._make_status_card(
            '치지직 계정', '확인 전', '스튜디오 로그인 상태'
        )
        self.automation_status_card, self.automation_status_dot, self.automation_status_value, self.automation_status_meta = self._make_status_card(
            '자동 변경', '일시정지', '게임 감지 및 카테고리 변경'
        )
        grid.addWidget(self.bridge_status_card, 0, 0)
        grid.addWidget(self.extension_status_card, 0, 1)
        grid.addWidget(self.account_status_card, 1, 0)
        grid.addWidget(self.automation_status_card, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        detail = QFrame()
        detail.setObjectName('panelCard')
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(16, 14, 16, 14)
        detail_layout.setSpacing(8)
        detail_title = QLabel('연결 세부 정보')
        detail_title.setObjectName('sectionTitle')
        detail_layout.addWidget(detail_title)
        self.account_status = QLabel('Chrome 확장프로그램 연결을 기다리고 있습니다.')
        self.account_status.setObjectName('inlineStatus')
        self.account_status.setWordWrap(True)
        detail_layout.addWidget(self.account_status)
        self.status_label = QLabel('자동 변경이 시작되지 않았습니다.')
        self.status_label.setObjectName('inlineStatus')
        self.status_label.setWordWrap(True)
        detail_layout.addWidget(self.status_label)
        self.connection_last_check = QLabel('마지막 확인: 아직 확인하지 않음')
        self.connection_last_check.setObjectName('softHint')
        detail_layout.addWidget(self.connection_last_check)
        actions = QHBoxLayout()
        actions.addWidget(button('지금 연결 확인', lambda: self.connection_tick(force=True), True))
        actions.addWidget(button('확장 상태 새로고침', self.refresh_bridge_status))
        actions.addStretch(1)
        detail_layout.addLayout(actions)
        layout.addWidget(detail)
        layout.addStretch(1)
        self.pages.addWidget(page)

        self.bridge_timer = QTimer(self)
        self.bridge_timer.setInterval(5000)
        self.bridge_timer.timeout.connect(self.connection_tick)
        if not self.preview:
            self.bridge_timer.start()
            QTimer.singleShot(700, self.connection_tick)
        self.refresh_bridge_status()

    def build_pending_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        toolbar = QHBoxLayout()
        self.pending_summary = QLabel('현재 선택이 필요한 항목이 없습니다.')
        self.pending_summary.setObjectName('sectionInfo')
        toolbar.addWidget(self.pending_summary)
        toolbar.addStretch(1)
        toolbar.addWidget(button('첫 항목 선택', self.resolve_pending, True))
        toolbar.addWidget(button('자동 감지 다시 실행', lambda: self.worker.submit('sync_auto')))
        layout.addLayout(toolbar)

        self.pending_table = QTableWidget(0, 3)
        self.pending_table.setObjectName('pendingTable')
        self.pending_table.setHorizontalHeaderLabels(['실행 파일', '이유', '게임 후보'])
        self.pending_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.pending_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.pending_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.pending_table.verticalHeader().hide()
        self.pending_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.pending_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.pending_table.setAlternatingRowColors(True)
        self.pending_table.setShowGrid(False)
        layout.addWidget(self.pending_table, 1)

        self.pending_empty = QLabel('미확정 항목이 없습니다.\n실행 파일명이나 카테고리 후보가 겹치는 게임은 직접 연결할 수 있습니다.')
        self.pending_empty.setObjectName('emptyPending')
        self.pending_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pending_empty.setWordWrap(True)
        layout.addWidget(self.pending_empty, 1)
        self.pages.addWidget(page)
        self.refresh_pending_page()

    def build_log_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)
        tools = QHBoxLayout()
        note = QLabel('최근 앱 활동을 최대 200줄까지 표시합니다.')
        note.setObjectName('sectionInfo')
        tools.addWidget(note)
        tools.addStretch(1)
        tools.addWidget(button('로그 복사', self.copy_logs))
        tools.addWidget(button('화면 지우기', self.clear_logs))
        layout.addLayout(tools)
        self.log = QTextEdit()
        self.log.setObjectName('activityLog')
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(200)
        layout.addWidget(self.log, 1)
        self.pages.addWidget(page)

    def build_update_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(12)

        card = QFrame()
        card.setObjectName('panelCard')
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 17, 18, 18)
        card_layout.setSpacing(9)
        title = QLabel('버전 및 업데이트')
        title.setObjectName('sectionTitle')
        card_layout.addWidget(title)
        self.update_current_label = QLabel(f'Windows 앱  {APP_VERSION}')
        self.update_current_label.setObjectName('statusCardValue')
        card_layout.addWidget(self.update_current_label)
        self.update_extension_label = QLabel('Chrome 확장  확인할 수 없음')
        self.update_extension_label.setObjectName('softHint')
        card_layout.addWidget(self.update_extension_label)
        self.update_page_status = QLabel('GitHub Releases를 주기적으로 확인합니다.')
        self.update_page_status.setObjectName('inlineStatus')
        self.update_page_status.setWordWrap(True)
        card_layout.addWidget(self.update_page_status)
        actions = QHBoxLayout()
        actions.addWidget(button('지금 업데이트 확인', self.check_for_updates_manual, True))
        self.install_update_button = button('대기 중인 업데이트 설치', self.open_pending_update)
        actions.addWidget(self.install_update_button)
        actions.addStretch(1)
        card_layout.addLayout(actions)
        layout.addWidget(card)

        info = QFrame()
        info.setObjectName('panelCard')
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(18, 15, 18, 15)
        info_layout.setSpacing(5)
        ititle = QLabel('버전 정책')
        ititle.setObjectName('sectionTitle')
        info_layout.addWidget(ititle)
        text = QLabel('Major: 호환성이 깨지는 대규모 개편 · Minor: 호환성을 유지하는 새 기능 · Patch: 버그/안정성/보안 수정')
        text.setObjectName('softHint')
        text.setWordWrap(True)
        info_layout.addWidget(text)
        layout.addWidget(info)
        layout.addStretch(1)
        self.pages.addWidget(page)
        self.refresh_update_page()

    def build_about_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(12)

        card = QFrame()
        card.setObjectName('panelCard')
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(8)
        title = QLabel('CHZZK Auto Category')
        title.setObjectName('statusCardValue')
        card_layout.addWidget(title)
        detail = QLabel(
            f'Windows 앱 버전: {APP_VERSION}\n'
            'Chrome 확장 버전: 연결 후 확인\n'
            '설치 경로: C:\\Program Files\\CHZZK Auto Category\n'
            '설정 경로: %LOCALAPPDATA%\\ChzzkAutoCategory\n\n'
            '실행 중인 게임을 감지해 치지직 방송 카테고리를 자동으로 연결하는 로컬 데스크톱 앱입니다.'
        )
        detail.setObjectName('softHint')
        detail.setWordWrap(True)
        card_layout.addWidget(detail)
        layout.addWidget(card)
        layout.addStretch(1)
        self.pages.addWidget(page)

    def refresh_pending_page(self):
        table = getattr(self, 'pending_table', None)
        if table is None:
            return
        rows = [item for item in self.auto_pending if isinstance(item, dict)]
        table.setRowCount(len(rows))
        reason_names = {
            'multi-game': '게임 후보 여러 개',
            'category-ambiguous': '카테고리 선택 필요',
        }
        for row, item in enumerate(rows):
            process = str(item.get('process') or '')
            reason = reason_names.get(str(item.get('reason') or ''), str(item.get('reason') or '미확정'))
            games = ', '.join(str(x) for x in item.get('games', []) if str(x).strip())
            table.setItem(row, 0, QTableWidgetItem(process))
            table.setItem(row, 1, QTableWidgetItem(reason))
            table.setItem(row, 2, QTableWidgetItem(games or '카테고리 후보 확인 필요'))
        has_rows = bool(rows)
        table.setVisible(has_rows)
        self.pending_empty.setVisible(not has_rows)
        self.pending_summary.setText(f'현재 선택이 필요한 항목: {len(rows)}개' if rows else '현재 선택이 필요한 항목이 없습니다.')

    def refresh_connection_page(self):
        if not hasattr(self, 'bridge_status_value'):
            return
        bridge_ok = not self.preview and not self.bridge_start_error
        self.bridge_status_value.setText('실행 중' if bridge_ok else ('미리보기' if self.preview else '오류'))
        self.bridge_status_dot.setObjectName('statusDotOn' if bridge_ok else 'statusDotOff')
        self.bridge_status_dot.style().unpolish(self.bridge_status_dot)
        self.bridge_status_dot.style().polish(self.bridge_status_dot)
        extension_ok = bool(getattr(self.bridge, 'connected', False)) if not self.preview else False
        self.extension_status_value.setText('연결됨' if extension_ok else '연결 대기')
        self.extension_status_dot.setObjectName('statusDotOn' if extension_ok else 'statusDotOff')
        self.extension_status_dot.style().unpolish(self.extension_status_dot)
        self.extension_status_dot.style().polish(self.extension_status_dot)
        account_ok = bool(self.connection_verified)
        self.account_status_value.setText('연결 확인됨' if account_ok else ('확인 중' if self.connection_check_pending else '확인 전'))
        self.account_status_dot.setObjectName('statusDotOn' if account_ok else 'statusDotOff')
        self.account_status_dot.style().unpolish(self.account_status_dot)
        self.account_status_dot.style().polish(self.account_status_dot)
        self.automation_status_value.setText('실행 중' if self.enabled else '일시정지')
        self.automation_status_dot.setObjectName('statusDotOn' if self.enabled else 'statusDotOff')
        self.automation_status_dot.style().unpolish(self.automation_status_dot)
        self.automation_status_dot.style().polish(self.automation_status_dot)
        self.connection_last_check.setText('마지막 확인: ' + self.last_connection_check_at)

    def refresh_update_page(self):
        if not hasattr(self, 'update_page_status'):
            return
        if isinstance(self.pending_update_release, dict):
            version = str(self.pending_update_release.get('version') or '?')
            self.update_page_status.setText(f'새 버전 {version}을 설치할 수 있습니다.')
            self.install_update_button.setEnabled(True)
            self.install_update_button.setText(f'{version} 업데이트 설치')
        else:
            self.update_page_status.setText(f'현재 앱 버전 {APP_VERSION} · GitHub Releases를 설정한 주기로 확인합니다.')
            self.install_update_button.setEnabled(False)
            self.install_update_button.setText('대기 중인 업데이트 없음')


    def build_tray(self):
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip('CHZZK Auto Category · 일시정지')

        # Keep QAction state objects for existing update/status logic, but render
        # the actual tray UI with TrayPopup instead of the native QMenu.
        self.menu_status = QAction('CHZZK Auto Category', self)
        self.menu_status.setEnabled(False)
        self.pause_action = QAction('자동 변경 시작', self)
        self.pause_action.triggered.connect(self.toggle)
        self.update_action = QAction('업데이트 확인', self)
        self.update_action.triggered.connect(self.open_pending_update)
        self.update_action.setVisible(False)

        self.tray_popup = TrayPopup(self)
        self.tray.activated.connect(self.activated)
        if not self.preview:
            self.tray.show()

    def activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            if getattr(self, 'tray_popup', None):
                self.tray_popup.hide()
            self.show_main()
            return
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.Context):
            self.show_tray_popup()

    def show_tray_popup(self):
        popup = getattr(self, 'tray_popup', None)
        if popup is None:
            return
        if popup.isVisible():
            popup.hide()
            return

        popup.refresh()
        popup.adjustSize()
        cursor = QCursor.pos()
        screen = QApplication.screenAt(cursor) or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else QApplication.primaryScreen().availableGeometry()
        width = popup.width()
        height = popup.sizeHint().height()

        # Prefer opening above and to the left of the tray cursor.
        x = cursor.x() - width + 24
        y = cursor.y() - height - 14
        if y < available.top() + 8:
            y = cursor.y() + 14
        x = max(available.left() + 8, min(x, available.right() - width - 8))
        y = max(available.top() + 8, min(y, available.bottom() - height - 8))

        popup.move(x, y)
        popup.show()
        popup.raise_()
        popup.activateWindow()

    def open_page_from_tray(self, index):
        self.show_main()
        self.nav.setCurrentRow(index)

    def is_tray_background(self):
        return bool(
            not self.preview
            and QSystemTrayIcon.isSystemTrayAvailable()
            and self.tray.isVisible()
            and not self.isVisible()
        )

    def show_main(self):
        if getattr(self, 'tray_popup', None):
            self.tray_popup.hide()
        self.showNormal()
        self._sync_window_frame()
        self.raise_()
        self.activateWindow()
        if self.pending_update_release is not None and not self.category_choice_dialog_active:
            release = self.pending_update_release
            self.pending_update_release = None
            if getattr(self, 'update_action', None):
                self.update_action.setVisible(False)
            QTimer.singleShot(250, lambda r=release: self.open_update_window(r))

    def open_update_window(self, release):
        if getattr(self, 'tray_popup', None):
            self.tray_popup.hide()
        if not release or self.quitting:
            return
        if self.update_window is not None:
            try:
                self.update_window.close()
            except Exception:
                pass
        self.update_window = AutoUpdateWindow(release, self)
        self.update_window.destroyed.connect(lambda *_: setattr(self, 'update_window', None))
        self.update_window.show()
        self.update_window.raise_()
        self.update_window.activateWindow()

    def persist(self):
        candidate = copy.deepcopy(self.config)
        candidate['rules'] = [asdict(rule) for rule in self.rules]
        candidate['auto_rules'] = [asdict(rule) for rule in self.auto_rules]
        candidate['auto_pending'] = list(self.auto_pending)
        try:
            save_config(candidate)
        except OSError:
            show_warning(self, '저장 실패', '설정 파일을 저장하지 못했습니다.')
            return False
        self.config = candidate
        self.worker.submit('configure', copy.deepcopy(candidate))
        return True

    def edit_rule(self, _checked=False, new=False):
        location = self.selected_rule_location()
        if not new:
            if not location:
                return
            if location['kind'] != 'manual':
                show_info(self, '수정 제한', '자동 규칙은 직접 수정할 수 없습니다. 삭제 후 수동 규칙으로 다시 추가해 주세요.')
                return
            index = int(location['index'])
            if index < 0 or index >= len(self.rules):
                return
        else:
            index = -1

        dlg = RuleDialog(self, None if new else self.rules[index])
        saved = False
        if dlg.exec() == QDialog.DialogCode.Accepted:
            old = list(self.rules)
            all_rules = self.rules + self.auto_rules
            if any(r.process.casefold() == dlg.result_rule.process.casefold()
                   for i, r in enumerate(all_rules) if new or i != index):
                show_warning(self, '중복 실행 파일', '같은 실행 파일의 규칙이 이미 있습니다.')
                return
            if new:
                self.rules.append(dlg.result_rule)
                selected_index = len(self.rules) - 1
            else:
                self.rules[index] = dlg.result_rule
                selected_index = index
            if not self.persist():
                self.rules = old
            else:
                saved = True
            self.refresh_table()
            self.select_rule_location('manual', selected_index)
        dlg.deleteLater()
        return dlg.result_rule if saved else None

    def remove_rule(self):
        location = self.selected_rule_location()
        if not location:
            return
        kind = location['kind']
        index = int(location['index'])
        if kind == 'manual' and 0 <= index < len(self.rules):
            old = list(self.rules)
            rule = self.rules[index]
            self.rules.pop(index)
            if not self.persist():
                self.rules = old
            else:
                self.status_label.setText(f'규칙 삭제 · {rule.process} → {rule.category_name}')
            self.refresh_table()
        elif kind == 'auto' and 0 <= index < len(self.auto_rules):
            old = list(self.auto_rules)
            rule = self.auto_rules[index]
            self.auto_rules.pop(index)
            if not self.persist():
                self.auto_rules = old
            else:
                self.status_label.setText(f'자동 규칙 삭제 · {rule.process} → {rule.category_name}')
            self.refresh_table()

    def move_rule(self, delta):
        location = self.selected_rule_location()
        if not location or location['kind'] != 'manual':
            if location and location['kind'] == 'auto':
                self.status_label.setText('자동 규칙의 우선순위는 자동 감지 순서로 관리됩니다.')
            return
        index = int(location['index'])
        target = index + delta
        if 0 <= index < len(self.rules) and 0 <= target < len(self.rules):
            self.rules[index], self.rules[target] = self.rules[target], self.rules[index]
            if not self.persist():
                self.rules[index], self.rules[target] = self.rules[target], self.rules[index]
            self.refresh_table()
            self.select_rule_location('manual', target)

    def resolve_pending(self):
        if not self.auto_pending:
            show_info(self, '안내', '미확정 항목이 없습니다.')
            return
        item = self.auto_pending[0]
        dlg = RuleDialog(self)
        process = str(item.get('process', '')).strip()
        if process:
            dlg.process.setEditText(process)
            reason = str(item.get('reason') or '')
            if reason == 'multi-game':
                games = ', '.join(item.get('games', [])[:3])
                dlg.note.setText('자동 감지 후보가 여러 개입니다. 직접 카테고리를 선택해 주세요.\n후보: ' + games)
            else:
                dlg.note.setText('카테고리가 명확히 일치하지 않았습니다. 직접 선택해 주세요.')
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if any(dlg.result_rule.process.casefold() in {p.casefold() for p in r.processes} for r in (self.rules + self.auto_rules)):
                show_warning(self, '중복 실행 파일', '같은 실행 파일의 규칙이 이미 있습니다.')
            else:
                self.rules.append(dlg.result_rule)
                self.auto_pending = self.auto_pending[1:]
                self.persist()
                self.refresh_table()
        dlg.deleteLater()

    def save_account(self):
        try:
            channel = channel_id(self.channel.text())
            extension_id = self.extension_id.text().strip().lower()
            if extension_id and not all(ch in 'abcdefghijklmnop' for ch in extension_id):
                raise ValueError('Chrome 확장 ID 형식이 올바르지 않습니다.')
            if extension_id and len(extension_id) != 32:
                raise ValueError('Chrome 확장 ID는 32자리여야 합니다.')

            self.config['channel'] = channel
            self.config['extension_id'] = extension_id
            self.bridge.extension_id = extension_id
            if self.persist():
                self.channel.setText(channel)
                self.connection_verified = False
                self.connection_check_pending = False
                self.auto_start_armed = bool(self.config.get('auto_start_change', True))
                self.account_status.setText('저장했습니다. 확장 연결을 확인하고 있습니다...')
                QTimer.singleShot(100, self.connection_tick)
        except Exception as e:
            message = str(e) if isinstance(e, (ValueError, RuntimeError)) else '계정 설정 저장에 실패했습니다.'
            show_warning(self, '계정 저장 실패', message)

    def refresh_bridge_status(self):
        if self.preview:
            self.account_status.setText('미리보기 모드 · 로컬 브리지는 실행하지 않습니다.')
            self.refresh_connection_page()
            return
        if self.bridge_start_error:
            self.account_status.setText('로컬 브리지 오류 · ' + self.bridge_start_error)
            self.refresh_connection_page()
            return
        if self.bridge.connected:
            self.account_status.setText('Chrome 확장프로그램 연결됨 · 127.0.0.1:5000')
        else:
            self.account_status.setText('Chrome 확장프로그램 연결 대기 · 확장프로그램이 설치되어 있고 활성화되어 있는지 확인해 주세요.')
        self.refresh_connection_page()

    def connection_tick(self, force=False):
        if self.preview:
            return

        self.last_connection_check_at = datetime.now().strftime('%H:%M:%S')
        self.refresh_bridge_status()
        if not self.bridge.connected:
            self.connection_verified = False
            self.connection_check_pending = False
            self.refresh_connection_page()
            return

        channel = str(self.config.get('channel') or '').strip()
        if not channel:
            self.account_status.setText('Chrome 확장프로그램 연결됨 · 계정 페이지에서 채널을 저장하면 자동으로 계정 연결을 확인합니다.')
            self.refresh_connection_page()
            return

        if self.connection_check_pending:
            self.refresh_connection_page()
            return
        if self.connection_verified and not force:
            self.refresh_connection_page()
            return

        self.connection_check_pending = True
        self.account_status.setText('연결 확인 중 · 치지직 계정을 확인하고 있습니다...')
        self.refresh_connection_page()
        self.worker.submit('check')


    def save_options(self):
        autostart = self.autostart.isChecked()
        self.config.update(interval=int(self.interval.currentData()), notify=self.notify.isChecked(),
                           pending_sound=self.pending_sound.isChecked(),
                           start_hidden=self.start_hidden.isChecked(),
                           autostart=autostart,
                           auto_update=self.auto_update.isChecked(),
                           update_check_minutes=int(self.update_check_interval.currentData()),
                           update_notify=self.update_notify.isChecked(),
                           auto_start_change=self.auto_start_change.isChecked(),
                           auto_detect=self.auto_detect.isChecked(),
                           auto_aggressive=self.auto_aggressive.isChecked(),
                           auto_resolve_shared=False,
                           discord_refresh_hours=int(self.discord_refresh.currentData()),
                           chzzk_open_enabled=self.chzzk_open_enabled.isChecked())
        if not self.persist():
            return
        self.refresh_update_timer_interval()
        if self.config.get('auto_start_change', True) and not self.enabled:
            self.auto_start_armed = True
            QTimer.singleShot(100, self.connection_tick)
        elif not self.config.get('auto_start_change', True):
            self.auto_start_armed = False

        try:
            applied = set_windows_autostart(autostart)
            if applied:
                state = '사용' if autostart else '사용 안 함'
                self.append_log(f'Windows 로그인 시 자동 실행: {state}')
            elif sys.platform == 'win32':
                self.append_log('소스 실행 중에는 Windows 자동 실행 레지스트리를 변경하지 않습니다.')
        except OSError as e:
            show_warning(self, '자동 실행 설정 실패', f'Windows 시작 프로그램 설정을 변경하지 못했습니다.\n{e}')
        self.append_log('설정을 저장했습니다.')


    def test_chzzk_open_connection(self):
        self.config['chzzk_open_enabled'] = self.chzzk_open_enabled.isChecked()
        if not self.config.get('chzzk_open_enabled', True):
            self.chzzk_open_status.setText('CHZZK 공식 Open API 보조 검색이 꺼져 있습니다.')
            return
        if not self.persist():
            return
        self.chzzk_open_status.setText('CHZZK 공식 Open API 연결 확인 중...')
        self.worker.submit('chzzk_open_test')


    def refresh_update_timer_interval(self):
        timer = getattr(self, 'update_timer', None)
        if timer is None:
            return
        from scheduling import seconds_until_check
        remaining = seconds_until_check(self.config)
        timer.setSingleShot(True)
        if remaining is None:
            timer.stop()
        else:
            timer.setInterval(max(1000, int(remaining * 1000)))
            if not self.preview:
                timer.start()

    def open_pending_update(self):
        release = self.pending_update_release
        if not release:
            self.check_for_updates_manual()
            return
        self.pending_update_release = None
        if getattr(self, 'update_action', None):
            self.update_action.setVisible(False)
        self.refresh_update_page()
        self.open_update_window(release)

    def check_for_updates_manual(self):
        self.manual_update_check = True
        self.check_for_updates(force=True)

    def check_for_updates(self, force=False):
        if self.preview:
            return
        if not force and not self.config.get('auto_update', True):
            return
        if self.update_check_worker and self.update_check_worker.isRunning():
            return
        if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
            if self.manual_update_check:
                show_info(self, '업데이트 확인', '자동 업데이트는 Windows에 설치된 빌드에서 동작합니다.')
                self.manual_update_check = False
            return

        from scheduling import seconds_until_check
        if not force and (seconds_until_check(self.config) or 0) > 1:
            self.refresh_update_timer_interval()
            return
        import time
        self.config['update_last_checked_at'] = time.time()
        save_config(self.config)
        self.refresh_update_timer_interval()
        worker = UpdateCheckWorker(self, allow_prerelease=self.config.get('allow_prerelease', False))
        self.update_check_worker = worker
        worker.completed.connect(self.on_update_check_completed)
        worker.failed.connect(self.on_update_check_failed)
        worker.finished.connect(self.clear_update_check_worker)
        worker.start()

    def on_update_check_completed(self, release):
        manual = self.manual_update_check
        self.manual_update_check = False
        if not release:
            if hasattr(self, 'update_page_status'):
                self.update_page_status.setText(f'현재 최신 버전을 사용 중입니다. · {APP_VERSION}')
            self.refresh_update_page()
            if manual:
                show_info(self, '업데이트 확인', f'현재 최신 버전을 사용 중입니다.\n버전 {APP_VERSION}')
            return

        version = str(release.get('version') or '?')
        already_pending = (
            isinstance(self.pending_update_release, dict)
            and str(self.pending_update_release.get('version') or '') == version
        )
        if not already_pending:
            self.append_log(f'새 업데이트 발견: {APP_VERSION} → {version}')

        # 트레이 상태에서도 업데이트를 놓치지 않도록 메뉴에 계속 표시합니다.
        self.pending_update_release = release
        self.refresh_update_page()
        if getattr(self, 'update_action', None):
            self.update_action.setText(f'업데이트 {version} 설치')
            self.update_action.setVisible(True)

        # 일반 카테고리 알림 설정과 업데이트 알림 설정을 분리했습니다.
        # 같은 버전은 주기 확인 때마다 반복 알림하지 않습니다.
        if (
            self.config.get('update_notify', True)
            and self.tray.isVisible()
            and self.last_update_notified_version != version
        ):
            self.tray.showMessage(
                'CHZZK Auto Category 업데이트',
                f'새 버전 {version}이 있습니다. 앱을 열거나 트레이 메뉴의 업데이트 항목을 눌러 주세요.',
                self.windowIcon(),
                7000,
            )
            self.last_update_notified_version = version

        # 트레이 백그라운드 상태에서는 기존 요청대로 업데이트 창을 강제로 띄우지 않습니다.
        if self.is_tray_background() and not manual:
            return

        self.pending_update_release = None
        if getattr(self, 'update_action', None):
            self.update_action.setVisible(False)
        self.refresh_update_page()
        self.open_update_window(release)

    def clear_update_check_worker(self):
        self.update_check_worker = None

    def on_update_check_failed(self, error):
        manual = self.manual_update_check
        self.manual_update_check = False
        self.append_log('업데이트 확인 실패: ' + str(error))
        if hasattr(self, 'update_page_status'):
            self.update_page_status.setText('업데이트 확인 실패 · ' + str(error))
        if manual:
            show_warning(self, '업데이트 확인 실패', str(error))

    def toggle(self):
        self.auto_start_armed = False
        if not self.enabled and (not self.config.get('channel') or
                                 (not (self.rules or self.auto_rules) and not self.config.get('auto_detect', True))):
            show_info(self, '설정 필요', '계정과 게임 연결을 먼저 저장해 주세요.')
            return
        self.worker.submit('enable', not self.enabled)

    def copy_logs(self):
        QApplication.clipboard().setText(self.log.toPlainText())

    def clear_logs(self):
        self.log.clear()

    def append_log(self, text, detail=False):
        self.log.append('')
        self.log.insertPlainText(datetime.now().strftime('%H:%M:%S') + '  ' + text)
        if not self.preview and getattr(self, 'bridge', None):
            self.bridge.add_log(text)

    def prompt_category_choice(self, event):
        if self.preview or self.category_choice_dialog_active:
            return
        candidates = [item for item in event.get('candidates', []) if isinstance(item, dict)]
        token = str(event.get('token') or '')
        process = str(event.get('process') or '').strip()
        game_name = str(event.get('game_name') or '').strip()
        if len(candidates) < 2 or not token or not process or is_ignored_process(process):
            return

        self.category_choice_dialog_active = True

        # 트레이에 숨겨진 상태에서는 메인 창을 복원하지 않습니다.
        # 자동으로 화면에 나타나는 유일한 창은 한국어 카테고리 다중 후보 선택창입니다.
        dialog_parent = None if self.is_tray_background() else self
        dlg = CategoryChoiceDialog(dialog_parent, process, game_name, candidates)
        try:
            if dialog_parent is None:
                QTimer.singleShot(0, dlg.raise_)
                QTimer.singleShot(0, dlg.activateWindow)
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_category:
                self.worker.submit('choose_category_candidate', {
                    'token': token,
                    'process': process,
                    'game_name': game_name,
                    'category': dlg.selected_category,
                    'save_rule': dlg.save_rule,
                })
                selected_name = str(dlg.selected_category.get('categoryValue') or '')
                mode = '규칙 저장' if dlg.save_rule else '이번만 적용'
                self.status_label.setText(f'카테고리 선택 · {selected_name} · {mode}')
            else:
                self.worker.submit('dismiss_category_choice', {'token': token})
                self.status_label.setText('카테고리 선택 취소 · 현재 게임 실행 동안 다시 묻지 않습니다')
        finally:
            dlg.deleteLater()
            self.category_choice_dialog_active = False

    def on_event(self, event):
        kind = event['kind']
        if kind == 'enabled':
            self.enabled = event['value']
            text = '자동 변경 일시정지' if self.enabled else '자동 변경 시작'
            self.toggle_button.setText(text)
            self.pause_action.setText(text)
            self.sidebar_auto_state.setText('실행 중' if self.enabled else '일시정지')
            self.automation_status_meta.setText('게임 감지 및 카테고리 변경이 활성화되어 있습니다.' if self.enabled else '자동 변경이 멈춰 있습니다.')
            self.refresh_connection_page()
        elif kind == 'status':
            self.last_runtime_status = str(event['text'])
            self.status_label.setText(self.last_runtime_status)
            self.menu_status.setText(self.last_runtime_status[:45])
            self.tray.setToolTip('치지직 자동 카테고리\n' + self.last_runtime_status)
            self.refresh_connection_page()
        elif kind == 'checked':
            was_connected = self.connection_verified
            self.connection_check_pending = False
            self.connection_verified = True
            self.last_connection_check_at = datetime.now().strftime('%H:%M:%S')
            self.account_status.setText(event['text'] + ' · 자동 연결 확인 완료')
            self.account_status_meta.setText(str(self.config.get('channel') or '채널 연결됨'))
            if not was_connected or getattr(self, 'last_logged_connection', None) != event['text']:
                self.append_log('[치지직 연결] ' + event['text'])
                self.last_logged_connection = event['text']
            self.refresh_connection_page()
            if self.auto_start_armed and self.config.get('auto_start_change', True) and not self.enabled:
                self.auto_start_armed = False
                self.append_log('앱 시작 연결 확인 완료 · 자동 변경을 시작합니다.')
                self.worker.submit('enable', True)
        elif kind == 'error':
            self.append_log('[오류] ' + event['text'])
            if event.get('operation') == 'check':
                self.connection_check_pending = False
                self.connection_verified = False
                self.last_connection_check_at = datetime.now().strftime('%H:%M:%S')
                self.account_status.setText(event['text'] + ' · 5초 후 다시 확인합니다.')
                self.refresh_connection_page()
            elif event.get('operation') == 'chzzk_open_test':
                self.chzzk_open_status.setText(event['text'])
            elif event.get('operation') != 'search':
                self.last_runtime_status = str(event['text'])
                self.status_label.setText(self.last_runtime_status)
                self.refresh_connection_page()
        elif kind == 'chzzk_open_tested':
            self.chzzk_open_status.setText('공식 API 연결됨 · 자동 설정 완료')
            self.append_log('CHZZK 공식 Open API 연결 확인 성공')
        elif kind == 'category_choice_required':
            self.prompt_category_choice(event)
        elif kind == 'auto_rules':
            self.auto_rules = [Rule(**item) for item in event.get('data', [])]
            self.config['auto_rules'] = event.get('data', [])
            self.persist()
            self.refresh_table()
        elif kind == 'auto_pending':
            old_keys = {category_choice_process_key(item.get('process', ''))
                        for item in self.auto_pending if isinstance(item, dict)}
            self.auto_pending = [item for item in event.get('data', []) if isinstance(item, dict)]
            new_keys = {category_choice_process_key(item.get('process', ''))
                        for item in self.auto_pending} - old_keys - {''}
            self.config['auto_pending'] = list(self.auto_pending)
            self.persist()
            self.refresh_table()
            self.refresh_pending_page()
            if new_keys and not self.preview and self.config.get('pending_sound', True):
                play_pending_alert()
        elif kind in ('applied', 'log'):
            result = '변경 완료' if event.get('changed') else '카테고리 유지'
            text = ('[카테고리 변경] ' + result + ' · ' + event['text']) if kind == 'applied' else event['text']
            self.append_log(text, detail=bool(event.get('detail', False)))
            if kind == 'applied':
                self.last_applied_text = str(event.get('text') or '없음')
            if kind == 'applied' and event.get('changed') and self.config.get('notify', True):
                self.tray.showMessage('카테고리 변경 완료', event['text'], QSystemTrayIcon.MessageIcon.Information, 3000)

        popup = getattr(self, 'tray_popup', None)
        if popup is not None and popup.isVisible():
            popup.refresh()


    def _sync_window_frame(self):
        if not hasattr(self, 'root_layout'):
            return
        margin = 0 if self.isMaximized() else 12
        self.root_layout.setContentsMargins(margin, margin, margin, margin)
        if hasattr(self, 'size_grip'):
            self.size_grip.setVisible(not self.isMaximized())
        if hasattr(self, 'title_bar') and hasattr(self.title_bar, 'maximize'):
            self.title_bar.maximize.setText('')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'size_grip') and hasattr(self, 'shell'):
            self.size_grip.setGeometry(max(0, self.shell.width() - 20), max(0, self.shell.height() - 20), 18, 18)
            self.size_grip.raise_()

    def closeEvent(self, event):
        if self.quitting:
            event.accept()
        elif QSystemTrayIcon.isSystemTrayAvailable() and not self.preview:
            event.ignore()
            self.hide()
        else:
            event.ignore()
            self.quit_app()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            QTimer.singleShot(0, self._sync_window_frame)
            if (self.isMinimized() and QSystemTrayIcon.isSystemTrayAvailable() and not self.preview):
                QTimer.singleShot(0, self.hide)
        super().changeEvent(event)

    def quit_app(self):
        if getattr(self, 'tray_popup', None):
            self.tray_popup.hide()
        if self.quitting:
            return
        self.quitting = True
        self.toggle_button.setEnabled(False)
        self.status_label.setText('종료 중 · 진행 중인 요청을 정리하고 있습니다')
        if self.worker.isRunning():
            self.worker.submit('stop')
            self.worker.finished.connect(self.finish_quit)
        else:
            self.finish_quit()

    def finish_quit(self):
        try:
            self.bridge.stop()
        except Exception:
            pass
        self.tray.hide()
        QApplication.instance().quit()


from modern_ui import ModernWindowMixin


class Window(ModernWindowMixin, ExistingWindow):
    pass


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    apply_light_theme(app)
    app.setWindowIcon(icon())
    smoke = next((arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('--ui-smoke-output=')), None)
    if smoke:
        from modern_ui import run_packaged_ui_smoke
        return run_packaged_ui_smoke(smoke)
    lock = QLockFile(str(data_dir() / 'app.lock'))
    if not lock.tryLock(100):
        show_info(None, '이미 실행 중', '시스템 트레이 아이콘에서 메인 인터페이스를 열어 주세요.')
        return 0
    try:
        config = load_config()
        for value in config.get('rules', []):
            Rule(**value)
        for value in config.get('auto_rules', []):
            Rule(**value)
    except Exception:
        show_error(None, '설정 읽기 실패', f'설정 파일을 확인해 주세요.\n{data_dir() / "config.json"}\n기존 파일은 덮어쓰지 않았습니다.')
        return 1
    just_configured = False
    if needs_setup(config):
        setup = FirstRunSetup(config)
        setup.setWindowIcon(icon())
        if setup.exec() != QDialog.DialogCode.Accepted:
            setup.cleanup()
            lock.unlock()
            return 0
        config = setup.result_config
        just_configured = True
        setup.deleteLater()
    background_start = not just_configured and ('--background' in sys.argv or '--autostart' in sys.argv)
    try:
        set_windows_autostart(bool(config.get('autostart', True)))
    except OSError:
        pass
    try:
        ensure_start_menu_shortcut()
    except OSError:
        pass

    window = Window(config)
    if background_start and QSystemTrayIcon.isSystemTrayAvailable():
        window.hide()
    elif just_configured or '--after-install' in sys.argv or not config.get('start_hidden') or not QSystemTrayIcon.isSystemTrayAvailable():
        window.show()
    code = app.exec()
    lock.unlock()
    return code


if __name__ == '__main__':
    sys.exit(main())
