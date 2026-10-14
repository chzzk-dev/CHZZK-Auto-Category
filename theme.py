"""Shared installer-inspired design tokens for Qt screens and dialogs."""
from PySide6.QtGui import QColor, QPalette

TOKENS = dict(background='#F3F1EB', card='#323232', sidebar='#252525',
              accent='#EDEBE4', hover='#DCD9D0', text='#252525', muted='#77756F',
              border='#FFFFFF', success='#EDEBE4', warning='#D6D2C7', error='#F0BEB8')

STYLE = """
QWidget { font-family:"Segoe UI", "Malgun Gothic", "Noto Sans CJK KR"; font-size:13px; color:@text; }
QMainWindow#appWindow, QWidget#windowRoot { background:transparent; }
QFrame#shell { background:@background; border:5px solid white; border-radius:22px; }
QFrame#titleBar { background:@background; border:none; border-top-left-radius:18px; border-top-right-radius:18px; }
QLabel#titleBarApp { font-weight:700; font-size:12px; }
QLabel#titleBarVersion, QLabel#pageSub, QLabel#softHint, QLabel#sectionInfo, QLabel#ruleSelectionInfo { color:@muted; }
QFrame#sidebar { background:@sidebar; border:5px solid white; border-radius:18px; }
QFrame#brandCard { background:transparent; border:none; }
QLabel#brandTitle { color:#F5F3EE; font-weight:800; font-size:15px; }
QLabel#brandSub, QLabel#navSection { color:#BBB9B3; font-size:11px; }
QListWidget#navList { background:transparent; border:none; outline:0; }
QListWidget#navList::item { color:#CCCAC4; padding:14px 10px; margin:4px 0; border:2px solid transparent; border-radius:10px; }
QListWidget#navList::item:selected { color:#252525; background:#EDEBE4; border-color:white; font-weight:700; }
QListWidget#navList::item:hover:!selected { background:#444444; color:white; border-color:#777777; }
QFrame#sidebarStatus { background:#393939; border:2px solid #ECEAE3; border-radius:12px; }
QLabel#sidebarStatusTitle { color:white; font-weight:700; }
QLabel#sidebarStatusText { color:#C6C3BA; font-size:11px; }
QFrame#contentCard { background:@background; border:none; }
QLabel#pageTitle { font-size:26px; font-weight:800; }
QLabel#sectionTitle { font-size:16px; font-weight:700; }
QLabel#settingTitle, QLabel#candidateTitle { font-weight:700; }
QFrame#panelCard, QFrame#settingsCard, QFrame#statusCard, QFrame#statusCardGood, QFrame#candidateCard {
 background:@card; border:5px solid white; border-radius:18px;
}
QFrame#panelCard QLabel, QFrame#settingsCard QLabel, QFrame#statusCard QLabel, QFrame#statusCardGood QLabel, QFrame#candidateCard QLabel { color:#F1EFE9; background:transparent; border:none; }
QFrame#panelCard QLabel#statusCardMeta, QFrame#panelCard QLabel#softHint, QFrame#settingsCard QLabel#softHint, QFrame#statusCard QLabel#statusCardMeta, QFrame#statusCard QLabel#statusCardTitle { color:#C7C4BC; }
QFrame#panelCard QCheckBox, QFrame#settingsCard QCheckBox { color:#F1EFE9; }
QLabel#statusCardTitle { font-size:12px; }
QLabel#statusCardValue { font-size:20px; font-weight:700; }
QLabel#heroGame { color:#F5F3EE; font-size:30px; font-weight:800; }
QLabel#inlineStatus, QLabel#pendingBadge { color:#F1EFE9; background:#414141; border:2px solid white; border-radius:10px; padding:10px; }
QLabel#emptyRules, QLabel#emptyPending { background:@card; color:#C7C4BC; padding:24px; border:5px solid white; border-radius:18px; }
QPushButton, QToolButton { color:#252525; background:#EDEBE4; border:2px solid white; border-radius:10px; padding:8px 12px; min-height:22px; }
QPushButton:hover, QToolButton:hover { background:#DCD9D0; border-color:#B7B3A8; }
QPushButton:focus, QToolButton:focus { border:2px solid #8A857B; }
QPushButton:disabled { color:#8F8D86; background:#DEDBD3; border-color:#E7E4DD; }
QPushButton#primary { background:#252525; border:2px solid white; color:white; font-weight:700; }
QPushButton#primary:hover { background:#484848; }
QPushButton#dangerButton { color:#7D302E; }
QPushButton#windowButton { min-width:30px; max-width:30px; padding:0; border:none; background:transparent; }
QLineEdit, QComboBox, QSpinBox { color:#252525; background:#F5F3ED; border:2px solid #D5D1C7; border-radius:10px; padding:9px; min-height:22px; selection-background-color:#CCC8BD; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color:#777168; }
QComboBox QAbstractItemView, QListWidget { color:#252525; background:#F5F3ED; border:2px solid white; selection-background-color:#D8D4CB; selection-color:#252525; }
QTextEdit { color:#F1EFE9; background:#323232; border:5px solid white; border-radius:16px; padding:12px; selection-background-color:#666666; }
QTableView, QTableWidget { color:#F1EFE9; background:#323232; alternate-background-color:#3A3A3A; border:5px solid white; border-radius:18px; gridline-color:#555555; }
QTableView::item { padding:8px; border-bottom:1px solid #555555; }
QTableView::item:selected { background:#E4E0D6; color:#252525; }
QHeaderView::section { color:#F1EFE9; background:#272727; padding:12px; border:none; border-bottom:2px solid white; font-weight:700; }
QCheckBox { spacing:9px; }
QTabWidget::pane { border:none; }
QTabBar::tab { color:#77756F; background:transparent; padding:10px 16px; border-bottom:3px solid transparent; }
QTabBar::tab:selected { color:#252525; border-bottom:3px solid #252525; font-weight:700; }
QScrollArea, QScrollArea > QWidget > QWidget { background:transparent; border:none; }
QMenu { color:#252525; background:#F3F1EB; border:3px solid white; } QMenu::item { padding:9px 22px; } QMenu::item:selected { background:#DCD9D0; }
QToolTip { background:#252525; color:white; padding:7px; border:none; }
QSizeGrip { background:transparent; width:16px; height:16px; }
"""
for _key, _value in TOKENS.items():
    STYLE = STYLE.replace('@' + _key, _value)


def apply_theme(app):
    app.setStyle('Fusion')
    palette = QPalette()
    for role, color in dict(Window=TOKENS['background'], WindowText=TOKENS['text'],
                            Base='#F5F3ED', AlternateBase='#E5E1D7', Text=TOKENS['text'],
                            Button='#EDEBE4', ButtonText=TOKENS['text'],
                            Highlight='#D8D4CB', HighlightedText=TOKENS['text'],
                            ToolTipBase=TOKENS['text'], ToolTipText='#FFFFFF').items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
    for role in ('Text', 'WindowText', 'ButtonText'):
        palette.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role), QColor('#9AAAB2'))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)
