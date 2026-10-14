import copy
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QStackedWidget, QVBoxLayout, QWidget)
from bridge import LocalExtensionBridge, BridgeError
from core import channel_id
from app_icons import set_button_icon
from storage import WEBSTORE_EXTENSION_ID, save_config


def needs_setup(config):
    return config.get('setup_completed') is not True


class FirstRunSetup(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = copy.deepcopy(config)
        self.result_config = None
        self.bridge = None
        self.setWindowTitle('치지직 자동 카테고리 · 처음 시작하기')
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.resize(880, 660)
        self.setMinimumSize(760, 600)
        self.setStyleSheet('QDialog { background: #F3F1EB; }')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 26, 30, 26)
        outer.setSpacing(18)
        heading = QLabel('치지직 자동 카테고리 시작하기')
        heading.setObjectName('sectionTitle')
        outer.addWidget(heading)
        self.steps = QLabel()
        self.steps.setStyleSheet('color: #252525; font-size: 14px; font-weight: bold;')
        outer.addWidget(self.steps)
        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)

        page, layout = self.new_page('1. 방송 채널을 알려 주세요',
            '게임을 실행하면 입력한 치지직 채널의 방송 카테고리를 변경합니다.\n본인의 채널 주소를 복사해서 붙여 넣어 주세요.')
        self.channel = QLineEdit(self.config.get('channel', ''))
        self.channel.setPlaceholderText('https://chzzk.naver.com/내 채널 ID')
        self.channel.setMinimumHeight(44)
        layout.addWidget(self.channel)
        paste = QPushButton('채널 주소 붙여넣기')
        paste.clicked.connect(lambda: self.channel.setText(QApplication.clipboard().text().strip()))
        layout.addWidget(paste)
        layout.addStretch()
        self.note(layout, '설정을 완료한 뒤부터 게임 감지와 자동 변경을 시작합니다.')

        page, layout = self.new_page('2. Chrome 확장프로그램을 연결해 주세요',
            '① Chrome에 연결 확장프로그램을 설치합니다.\n② 같은 Chrome에서 치지직 스튜디오를 열고 방송 계정으로 로그인합니다.\n③ 확장프로그램 팝업을 열어 앱 연결을 확인합니다.')
        row = QHBoxLayout()
        install = QPushButton('확장프로그램 설치 페이지')
        install.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(
            'https://chromewebstore.google.com/detail/' + WEBSTORE_EXTENSION_ID)))
        studio = QPushButton('치지직 스튜디오 열기')
        studio.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://studio.chzzk.naver.com/')))
        row.addWidget(install)
        row.addWidget(studio)
        layout.addLayout(row)
        self.extension_status = self.note(layout, '확장 연결을 기다리고 있습니다.')
        retry = QPushButton('연결 다시 확인')
        retry.clicked.connect(self.start_bridge)
        layout.addWidget(retry)
        self.advanced = QCheckBox('직접 설치한 확장프로그램 ID 입력')
        self.extension_id = QLineEdit(self.config.get('extension_id') or WEBSTORE_EXTENSION_ID)
        self.extension_id.setPlaceholderText('chrome://extensions 에 표시된 32자리 ID')
        custom = self.extension_id.text() != WEBSTORE_EXTENSION_ID
        self.advanced.setChecked(custom)
        self.extension_id.setVisible(custom)
        self.advanced.toggled.connect(self.extension_id.setVisible)
        self.extension_id.editingFinished.connect(self.start_bridge)
        layout.addWidget(self.advanced)
        layout.addWidget(self.extension_id)
        layout.addStretch()
        self.note(layout, 'Chrome이 다른 PC에서 실행되면 연결되지 않습니다.\n확장 연결 확인은 앱과 확장의 통신 확인이며, 방송 계정 연결은 메인 화면에서 추가로 확인합니다.')

        page, layout = self.new_page('3. 설정을 저장하고 시작하세요',
            '게임을 켜 두면 자동으로 감지합니다.\n메인 창을 닫아도 트레이에서 계속 실행할 수 있습니다.')
        self.summary = self.note(layout, '')
        self.auto_change = QCheckBox('계정 연결이 확인되면 자동 변경 시작')
        self.auto_change.setChecked(self.config.get('auto_start_change', True))
        self.autostart = QCheckBox('Windows 로그인 시 자동 실행')
        self.autostart.setChecked(self.config.get('autostart', True))
        layout.addWidget(self.auto_change)
        layout.addWidget(self.autostart)
        self.allow_unconnected = QCheckBox('확장은 나중에 연결하고 프로그램 먼저 열기')
        layout.addWidget(self.allow_unconnected)
        layout.addStretch()
        self.note(layout, '완료한 설정창은 다음 실행부터 자동으로 나타나지 않습니다.\n채널과 연결 설정은 프로그램의 “연결 관리 → 계정 설정” 화면에서 변경할 수 있습니다.')

        self.error = QLabel('')
        self.error.setStyleSheet('color: #B94A59;')
        self.error.setWordWrap(True)
        outer.addWidget(self.error)
        actions = QHBoxLayout()
        cancel = QPushButton('종료 · 다음에 설정')
        cancel.clicked.connect(self.reject)
        self.back = QPushButton('이전')
        self.back.clicked.connect(lambda: self.show_page(self.pages.currentIndex() - 1))
        self.next = QPushButton('다음')
        self.next.setStyleSheet('background: #252525; color: #FFFFFF; font-weight: bold;')
        self.next.clicked.connect(self.advance)
        actions.addWidget(cancel)
        actions.addStretch()
        actions.addWidget(self.back)
        actions.addWidget(self.next)
        outer.addLayout(actions)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh_connection)
        self.finished.connect(self.cleanup)
        for widget in self.findChildren(QPushButton):
            set_button_icon(widget, 'connections' if '연결' in widget.text() else 'success' if widget is self.next else 'info')
        self.show_page(0)

    def note(self, layout, text):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName('sectionInfo')
        layout.addWidget(label)
        return label

    def new_page(self, title, description):
        page = QFrame()
        page.setObjectName('panelCard')
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        heading = QLabel(title)
        heading.setObjectName('sectionTitle')
        layout.addWidget(heading)
        self.note(layout, description)
        self.pages.addWidget(page)
        return page, layout

    def show_page(self, index):
        self.pages.setCurrentIndex(index)
        self.steps.setText(f'{index + 1} / 3     채널 입력  →  확장 연결  →  시작')
        self.back.setEnabled(index > 0)
        self.next.setText('설정 완료 · 프로그램 열기' if index == 2 else '다음')
        self.error.clear()
        if index == 1:
            self.start_bridge()
        if index == 2:
            self.refresh_connection()

    def extension_value(self):
        value = self.extension_id.text().strip().lower()
        if len(value) != 32 or any(c not in 'abcdefghijklmnop' for c in value):
            raise ValueError('확장 ID는 a~p로 이루어진 32자리 값입니다.')
        return value

    def start_bridge(self):
        try:
            extension_id = self.extension_value()
            if self.bridge is None:
                self.bridge = LocalExtensionBridge(port=int(self.config.get('bridge_port', 5000)), extension_id=extension_id)
            if self.bridge.extension_id != extension_id:
                self.bridge.connected_at = 0
            self.bridge.extension_id = extension_id
            self.bridge.start()
            self.timer.start()
            self.error.clear()
            self.refresh_connection()
        except (ValueError, BridgeError) as exc:
            self.error.setText(str(exc))

    def refresh_connection(self):
        connected = bool(self.bridge and self.bridge.connected)
        text = '확장 연결 확인됨' if connected else '확장 연결 대기 · Chrome과 확장프로그램 팝업을 열어 주세요.'
        self.extension_status.setText(text)
        self.summary.setText('채널: ' + self.channel.text().strip() + '\n' + text)
        self.allow_unconnected.setVisible(not connected)

    def advance(self):
        try:
            index = self.pages.currentIndex()
            if index == 0:
                self.channel.setText(channel_id(self.channel.text()))
            if index == 1:
                self.extension_value()
            if index < 2:
                self.show_page(index + 1)
                return
            if not (self.bridge and self.bridge.connected) and not self.allow_unconnected.isChecked():
                raise ValueError('확장을 연결하거나 “확장은 나중에 연결하고 프로그램 먼저 열기”를 선택해 주세요.')
            candidate = copy.deepcopy(self.config)
            candidate.update(channel=channel_id(self.channel.text()), extension_id=self.extension_value(),
                             auto_start_change=self.auto_change.isChecked(), autostart=self.autostart.isChecked(),
                             setup_completed=True)
            save_config(candidate)
            self.result_config = candidate
            self.accept()
        except (ValueError, OSError) as exc:
            self.error.setText('설정을 완료하지 못했습니다. ' + str(exc))

    def cleanup(self, *_args):
        self.timer.stop()
        if self.bridge:
            self.bridge.stop()
            self.bridge = None
