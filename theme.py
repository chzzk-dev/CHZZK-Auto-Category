"""Unicorn Pro-inspired Clean White & Coral Minimal Theme for CHZZK-Auto-Category."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

# Color palettes: Default is Unicorn Pro Coral Red ('coral'), with optional Chzzk Mint ('chzzk')
PALETTES = {
    'coral': {
        'background': '#FFFFFF',
        'card': '#FFFFFF',
        'sidebar': '#F8F9FB',
        'accent': '#F0564A',
        'accent_hover': '#DF4539',
        'accent_soft': '#FFF0EE',
        'accent_border': '#F4938B',
        'hover': '#F3F5F8',
        'text': '#1E2024',
        'muted': '#8B909A',
        'border': '#ECEEF2',
        'success': '#F0564A',
        'warning': '#F59E0B',
        'error': '#E11D48',
    },
    'chzzk': {
        'background': '#FFFFFF',
        'card': '#FFFFFF',
        'sidebar': '#F8FAFC',
        'accent': '#00C77B',
        'accent_hover': '#00B06D',
        'accent_soft': '#E8FBF3',
        'accent_hover_soft': '#D3F7E8',
        'accent_border': '#6CE0B4',
        'hover': '#F2F6F5',
        'text': '#1E2024',
        'muted': '#8B909A',
        'border': '#ECEEF2',
        'success': '#00C77B',
        'warning': '#F59E0B',
        'error': '#E11D48',
    },
}

TOKENS: dict[str, str] = dict(PALETTES['coral'])

_STYLE_TEMPLATE = """
QWidget {
    font-family: "Pretendard", "Malgun Gothic", "Noto Sans KR", "Noto Sans CJK KR", "Segoe UI", sans-serif;
    font-size: 13px;
    font-weight: 400;
    color: @text;
}

QMainWindow#appWindow,
QWidget#windowRoot {
    background: transparent;
}

QDialog#subDialog {
    background: @background;
    border: 1px solid @border;
    border-radius: 14px;
}

QFrame#shell {
    background: @background;
    border: 1px solid #DFE2E8;
    border-radius: 14px;
}

/* Frameless Title Bar */
QFrame#titleBar {
    background: @background;
    border-top-left-radius: 14px;
    border-top-right-radius: 14px;
    border-bottom: 1px solid #F3F4F6;
}

QLabel#titleBarApp {
    color: @text;
    font-size: 12px;
    font-weight: 700;
}

QLabel#titleBarVersion,
QLabel#pageSub,
QLabel#softHint,
QLabel#sectionInfo,
QLabel#ruleSelectionInfo {
    color: @muted;
    font-size: 12px;
}

QPushButton#windowButton,
QToolButton#windowButton {
    background: transparent;
    border: none;
    border-radius: 6px;
    color: #555962;
    min-width: 32px;
    max-width: 32px;
    min-height: 28px;
    max-height: 28px;
    font-size: 13px;
}

QPushButton#windowButton:hover,
QToolButton#windowButton:hover {
    background: @hover;
    color: @text;
}

QPushButton#closeButton:hover,
QToolButton#closeButton:hover {
    background: @accent;
    color: #FFFFFF;
}

/* Far-Left Slim Icon Rail (Unicorn Pro Style) */
QFrame#iconRail {
    background: @background;
    border-right: 1px solid @border;
    min-width: 62px;
    max-width: 62px;
}

QToolButton#railButton {
    background: transparent;
    border: none;
    border-radius: 12px;
    padding: 8px;
    min-width: 40px;
    max-width: 40px;
    min-height: 40px;
    max-height: 40px;
}

QToolButton#railButton:hover {
    background: @hover;
}

QToolButton#railButton[active="true"] {
    background: @accent_soft;
}

QToolButton#railBottomButton {
    background: transparent;
    border: none;
    border-radius: 10px;
    padding: 6px;
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    max-height: 32px;
    color: @muted;
}

QToolButton#railBottomButton:hover {
    background: @hover;
    color: @text;
}

/* Secondary Navigation Sidebar (Unicorn Settings Style) */
QFrame#sidebar {
    background: @sidebar;
    border-right: 1px solid @border;
    border-top-left-radius: 0px;
    border-bottom-left-radius: 0px;
}

QFrame#brandCard {
    background: transparent;
    border: none;
    padding: 4px 0px;
}

QLabel#brandTitle {
    color: @text;
    font-size: 18px;
    font-weight: 800;
}

QLabel#brandSub {
    color: @muted;
    font-size: 11px;
}

QLabel#navSection {
    color: @muted;
    font-size: 11px;
    font-weight: 700;
    padding: 4px 12px;
}

QListWidget#navList {
    background: transparent;
    border: none;
    outline: none;
    padding: 4px 0px;
}

QListWidget#navList::item {
    color: #4E525B;
    background: transparent;
    padding: 12px 16px;
    margin: 2px 0px;
    border-left: 3px solid transparent;
    border-radius: 0px;
    font-size: 13px;
    font-weight: 500;
}

QListWidget#navList::item:selected {
    color: @accent;
    background: transparent;
    border-left: 3px solid @accent;
    font-weight: 700;
}

QListWidget#navList::item:hover:!selected {
    color: @text;
    background: #F1F3F6;
}

QFrame#sidebarStatus {
    background: #FFFFFF;
    border: 1px solid @border;
    border-radius: 12px;
    padding: 10px;
}

/* Main Content Area & Headers */
QLabel#pageTitle {
    color: @text;
    font-size: 20px;
    font-weight: 800;
}

QLabel#sectionTitle {
    color: @text;
    font-size: 15px;
    font-weight: 700;
}

/* Clean White Cards & Metric Cards */
QFrame#panelCard,
QFrame#settingsCard,
QFrame#statusCard,
QFrame#statusCardGood,
QFrame#candidateCard,
QFrame#metricCard,
QFrame#ruleSelectionCard {
    background: @card;
    border: 1px solid @border;
    border-radius: 14px;
}

QFrame[dashboardCard="true"] {
    background: #FFFFFF;
    border: 1px solid #EFEFEF;
    border-radius: 14px;
}

QFrame#dashboardHero {
    background: #FFFFFF;
    border: none;
}

QLabel#heroGame {
    color: @text;
    font-size: 24px;
    font-weight: 700;
}

QLabel#heroStatus {
    color: @text;
    font-size: 24px;
    font-weight: 700;
}

QLabel#heroMeta {
    color: @muted;
    font-size: 13px;
}

QLabel#metricLabel {
    color: @muted;
    font-size: 12px;
    font-weight: 500;
}

QLabel#metricValue {
    color: @text;
    font-size: 20px;
    font-weight: 800;
}

/* Flat Divider Setting Rows (Screenshot 2 Style) */
QFrame#settingRow {
    background: transparent;
    border: none;
    border-bottom: 1px solid #F0F2F5;
    padding: 14px 2px;
}

QLabel#settingTitle {
    color: @text;
    font-size: 14px;
    font-weight: 600;
}

QLabel#settingDesc {
    color: @muted;
    font-size: 12px;
}

QFrame#dashboardActivityRow {
    background: transparent;
    border: none;
    border-bottom: 1px solid #F1F3F5;
    padding: 8px 0px;
}

/* Status Pill Badge (Screenshot 3 Style: "상태 : 사용가능") */
QLabel#statusPillBadge,
QLabel#inlineStatus,
QLabel#pendingBadge {
    background: #FFFFFF;
    color: @accent;
    border: 1px solid @accent_border;
    border-radius: 14px;
    padding: 5px 16px;
    font-size: 12px;
    font-weight: 600;
}

QLabel#emptyPending {
    background: #FAFBFC;
    color: @muted;
    border: 1px dashed @border;
    border-radius: 12px;
    padding: 24px;
}

QFrame#gameEmptyState {
    background: transparent;
    border: none;
}

QLabel#gameEmptyIcon {
    background: #F7F8FA;
    border: none;
    border-radius: 24px;
}

QLabel#gameEmptyTitle {
    color: @text;
    font-size: 15px;
    font-weight: 600;
}

QLabel#gameEmptyDescription {
    color: @muted;
    font-size: 12px;
}

/* Underline Tabs (Screenshot 2 Style) */
QTabWidget::pane {
    border: none;
    border-top: 1px solid @border;
    background: @background;
    top: -1px;
}

QTabBar {
    background: transparent;
    border-bottom: 1px solid @border;
}

QTabBar::tab {
    background: transparent;
    color: #5A5F6A;
    padding: 10px 4px;
    margin-right: 28px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 13px;
    font-weight: 500;
}

QTabBar::tab:selected {
    color: @accent;
    border-bottom: 2px solid @accent;
    font-weight: 700;
}

QTabBar::tab:hover:!selected {
    color: @text;
}

/* Buttons */
QPushButton,
QToolButton {
    background: #FFFFFF;
    color: @text;
    border: 1px solid #DCDFE6;
    border-radius: 6px;
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton:hover,
QToolButton:hover {
    background: @hover;
    border-color: #C8CDD6;
}

QPushButton:disabled,
QToolButton:disabled {
    background: #F5F6F8;
    color: #B4B8C2;
    border-color: #EAECEF;
}

/* Solid Coral Primary Button (Screenshot 1 Popup "앱 업데이트 하기") */
QPushButton#primary {
    background: @accent;
    color: #FFFFFF;
    border: 1px solid @accent;
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 700;
}

QPushButton#primary:hover {
    background: @accent_hover;
    border-color: @accent_hover;
}

/* Outlined Coral Action Button (Screenshot 1 "여기를 눌러 앱 업데이트 하기") */
QPushButton#outlineAccentButton,
QPushButton#dashboardAction {
    background: #FFFFFF;
    color: @accent;
    border: 1px solid @accent_border;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton#outlineAccentButton:hover,
QPushButton#dashboardAction:hover {
    background: @accent_soft;
    border-color: @accent;
}

/* Minimal Text-Only Accent Link Button (Screenshot 2 & 3 "앱별로 설정하기", "기기등록 해제") */
QPushButton#textAccentButton {
    background: transparent;
    color: @accent;
    border: none;
    padding: 6px 2px;
    font-size: 13px;
    font-weight: 700;
    text-align: left;
}

QPushButton#textAccentButton:hover {
    color: @accent_hover;
    text-decoration: underline;
}

/* Bottom Sync Button (Screenshot 3 "이용권 동기화") */
QPushButton#syncGhostButton {
    background: transparent;
    color: #4E525B;
    border: none;
    padding: 8px 14px;
    font-size: 13px;
    font-weight: 600;
}

QPushButton#syncGhostButton:hover {
    color: @text;
    background: @hover;
    border-radius: 8px;
}

QPushButton#dangerButton,
QPushButton#danger {
    background: #FFFFFF;
    color: @error;
    border: 1px solid #FECDD3;
}

QPushButton#dangerButton:hover,
QPushButton#danger:hover {
    background: #FFF1F2;
    border-color: @error;
}

/* Inputs, ComboBoxes, Tables & Scrollbars */
QLineEdit,
QComboBox,
QSpinBox,
QTextEdit {
    background: #FFFFFF;
    color: @text;
    border: 1px solid #DCDFE6;
    border-radius: 6px;
    padding: 7px 10px;
}

QLineEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QTextEdit:focus {
    border: 1px solid @accent;
}

QTableView {
    background: #FFFFFF;
    alternate-background-color: #FAFBFC;
    color: @text;
    border: 1px solid @border;
    border-radius: 10px;
    gridline-color: #F1F3F5;
    selection-background-color: @accent_soft;
    selection-color: @text;
}

QHeaderView::section {
    background: #F8F9FB;
    color: #5A5F6A;
    border: none;
    border-bottom: 1px solid @border;
    padding: 10px 8px;
    font-size: 12px;
    font-weight: 700;
}

QTableView#rulesTable {
    border-radius: 4px;
    outline: 0;
}

QTableView#rulesTable::item {
    padding: 0px 10px;
    border: none;
    border-bottom: 1px solid #F2F3F5;
}

QTableView#rulesTable::item:selected {
    background: @accent_soft;
    color: @text;
    border: none;
}

QScrollArea {
    background: transparent;
    border: none;
}

QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: #D5D9E0;
    border-radius: 4px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: #B4BAC4;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}

QProgressBar {
    background: #F1F3F6;
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}

QProgressBar::chunk {
    background: @accent;
    border-radius: 4px;
}

QMenu {
    background: #FFFFFF;
    border: 1px solid @border;
    border-radius: 8px;
    padding: 6px;
}

QMenu::item {
    padding: 7px 14px;
    border-radius: 5px;
}

QMenu::item:selected {
    background: @accent_soft;
    color: @accent;
}

QToolTip {
    background: #1E2024;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
}

QFrame#contentCard { background: @background; border: none; }
QFrame#shell { border-radius: 8px; }
QFrame#iconRail { min-width: 54px; max-width: 54px; }
QToolButton#railButton, QToolButton#railBrand {
    min-width: 36px; max-width: 36px; min-height: 36px; max-height: 36px;
    padding: 0; border: none; border-radius: 8px; background: transparent;
}
QToolButton#railButton[active="true"] { background: @accent_soft; }
QToolButton#railButton:hover, QToolButton#railBrand:hover { background: @hover; }
QFrame#brandCard { padding: 0; }
QLabel#brandTitle { font-size: 16px; font-weight: 600; padding-left: 8px; }
QLabel#navSection { font-weight: 400; font-size: 10px; padding: 10px 18px; }
QListWidget#navList::item {
    padding: 10px 18px; margin: 3px 0; border-left: 2px solid transparent;
    font-weight: 400; font-size: 12px;
}
QListWidget#navList::item:selected {
    border-left: 2px solid @accent; color: @accent; background: transparent;
}
QFrame#sidebarStatus { background: transparent; border: none; padding: 10px; }
QLabel#sidebarStatusTitle { color: @text; font-size: 11px; }
QLabel#sidebarStatusText { color: @muted; font-size: 10px; }
QLabel#pageTitle { font-size: 19px; font-weight: 600; }
QLabel#settingTitle { font-size: 13px; font-weight: 500; }
QLabel#settingDescription, QLabel#statusCardMeta, QLabel#dashboardTime {
    color: @muted; font-size: 11px;
}
QFrame#settingRow { padding: 4px 0; border-bottom: 1px solid @border; }
QFrame#panelCard, QFrame#settingsCard, QFrame#statusCard,
QFrame#statusCardGood, QFrame#connectionCenter {
    background: @background; border: none; border-radius: 0;
}
QFrame[dashboardCard="true"] { border: 1px solid @border; border-radius: 8px; }
QLabel#heroGame { font-size: 22px; font-weight: 600; }
QLabel#statusCardTitle { color: @muted; font-size: 11px; }
QLabel#statusCardValue { color: @text; font-size: 20px; font-weight: 600; }
QLabel#dashboardDetailValue, QLabel#dashboardActivityText { color: @text; font-size: 12px; }
QLabel#inlineStatus { border-radius: 5px; padding: 5px 12px; }
QTableWidget { background: white; color: @text; gridline-color: @border; border: 1px solid @border; }
QComboBox::drop-down { border: none; width: 24px; }
QCheckBox { color: @text; spacing: 8px; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #CDD1D8; border-radius: 3px; background: white; }
QCheckBox::indicator:checked { background: @accent; border-color: @accent; }
QPushButton#mandatoryBadge { background: @accent_soft; color: @accent; border: none; }
"""


def _compile_style(tokens: dict[str, str], template: str = _STYLE_TEMPLATE) -> str:
    style = template
    # Sort keys by length descending so @accent_border is replaced before @accent
    for key in sorted(tokens.keys(), key=len, reverse=True):
        style = style.replace(f'@{key}', tokens[key])
    return style


STYLE: str = _compile_style(TOKENS)

UPDATE_STYLE = STYLE + _compile_style(TOKENS, """
QMainWindow { background: @background; }
QFrame#updateShell { background: @background; border: 1px solid @border; border-radius: 6px; }
QLabel#updateHeading { color: @text; font-size: 15px; font-weight: 600; }
QLabel#updateVersion { color: @text; font-size: 14px; font-weight: 600; }
QLabel#updateCaption { color: @muted; font-size: 11px; }
QFrame#updateDivider { background: @border; min-height: 1px; max-height: 1px; border: none; }
QTextBrowser#releaseNotes { background: @background; color: @text; border: none; padding: 0; font-size: 12px; }
QLabel#updateNotice { color: @accent; font-size: 11px; }
QLabel#updateError { color: @error; font-size: 12px; }
QLabel#status { color: @text; font-size: 16px; font-weight: 600; }
QLabel#detail, QLabel#miniLabel { color: @muted; font-size: 12px; }
QLabel#miniValue { color: @text; font-size: 12px; }
QLabel#version { color: @muted; font-size: 11px; }
QProgressBar { min-height: 5px; max-height: 5px; background: @border; border: none; border-radius: 2px; color: transparent; }
QProgressBar::chunk { background: @accent; border-radius: 2px; }
QToolButton { min-width: 26px; max-width: 26px; min-height: 24px; max-height: 24px; padding: 0; border: none; background: transparent; }
QToolButton:hover { background: @hover; }
QToolButton#closeButton:hover { background: @accent_soft; color: @error; }
QPushButton { min-height: 18px; padding: 8px 14px; border-radius: 4px; font-size: 12px; }
QPushButton#primary:disabled { background: #F5F6F8; color: #B4B8C2; border: 1px solid @border; }
""")


def set_accent_palette(palette_name: str = 'coral', app=None) -> str:
    """Switch between 'coral' (Unicorn Pro Red) and 'chzzk' (Chzzk Mint Green) palettes."""
    global STYLE
    chosen = PALETTES.get(palette_name, PALETTES['coral'])
    TOKENS.clear()
    TOKENS.update(chosen)
    STYLE = _compile_style(TOKENS)
    if app is not None:
        apply_theme(app)
    return STYLE


def apply_theme(app) -> None:
    """Apply the clean white Unicorn Pro theme and QPalette to QApplication or widget."""
    if hasattr(app, 'setStyle'):
        app.setStyle('Fusion')

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(TOKENS['background']))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TOKENS['text']))
    palette.setColor(QPalette.ColorRole.Base, QColor('#FFFFFF'))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor('#F8F9FB'))
    palette.setColor(QPalette.ColorRole.Text, QColor(TOKENS['text']))
    palette.setColor(QPalette.ColorRole.Button, QColor('#FFFFFF'))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TOKENS['text']))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(TOKENS['accent_soft']))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(TOKENS['accent']))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(TOKENS['text']))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor('#FFFFFF'))

    disabled_color = QColor('#B4B8C2')
    for role_name in ('Text', 'WindowText', 'ButtonText'):
        role = getattr(QPalette.ColorRole, role_name)
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled_color)

    if hasattr(app, 'setPalette'):
        app.setPalette(palette)
    if hasattr(app, 'setStyleSheet'):
        app.setStyleSheet(STYLE)


apply_light_theme = apply_theme
