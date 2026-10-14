"""Shared installer-inspired design tokens for Qt screens and dialogs."""
from PySide6.QtGui import QColor, QPalette

TOKENS = dict(background='#F7FAFB', card='#FFFFFF', sidebar='#103B3D',
              accent='#35DEB0', hover='#25C99C', text='#17313C', muted='#6D8490',
              border='#E3EBEE', success='#087D61', warning='#986300', error='#B94A59')

STYLE = '''
QWidget { font-family: "Segoe UI", "Malgun Gothic", "Noto Sans CJK KR"; font-size:13px; color:@text; }
QMainWindow#appWindow, QWidget#windowRoot { background:transparent; }
QFrame#shell { background:@background; border:1px solid @border; border-radius:18px; }
QFrame#titleBar { background:@background; border-bottom:1px solid @border; border-top-left-radius:18px; border-top-right-radius:18px; }
QLabel#titleBarApp { font-weight:700; font-size:12px; }
QLabel#titleBarVersion, QLabel#softHint, QLabel#sectionInfo, QLabel#pageSub,
QLabel#statusCardMeta, QLabel#ruleSelectionInfo { color:@muted; }
QFrame#sidebar { background:@sidebar; border-bottom-left-radius:18px; }
QFrame#brandCard { background:transparent; border:none; }
QLabel#brandTitle { color:white; font-weight:800; font-size:17px; }
QLabel#brandSub, QLabel#navSection { color:#AAD0CC; font-size:11px; }
QListWidget#navList { background:transparent; border:none; outline:0; }
QListWidget#navList::item { color:#BED8D6; padding:12px 10px; margin:3px 0; border-radius:10px; }
QListWidget#navList::item:selected { color:@accent; background:#1C5051; font-weight:700; }
QListWidget#navList::item:hover:!selected { background:#19484A; color:white; }
QFrame#sidebarStatus { background:#174648; border:1px solid #2B595B; border-radius:12px; }
QLabel#sidebarStatusTitle { color:white; font-weight:700; font-size:12px; }
QLabel#sidebarStatusText { color:#AAD0CC; font-size:11px; }
QFrame#contentCard { background:@background; border:none; border-bottom-right-radius:18px; }
QLabel#pageTitle { font-size:26px; font-weight:800; }
QLabel#sectionTitle { font-size:16px; font-weight:700; }
QLabel#settingTitle, QLabel#candidateTitle { font-weight:700; }
QFrame#settingsCard, QFrame#panelCard, QFrame#statusCard, QFrame#candidateCard {
 background:@card; border:1px solid @border; border-radius:16px;
}
QFrame#statusCardGood { background:#EDF9F4; border:1px solid #C5ECDD; border-radius:16px; }
QLabel#statusCardTitle { color:@muted; font-size:12px; }
QLabel#statusCardValue { font-size:17px; font-weight:700; }
QLabel#statusDotOn { color:@success; } QLabel#statusDotOff { color:@muted; }
QLabel#inlineStatus, QLabel#pendingBadge { background:#EFF7F7; border:1px solid @border; border-radius:10px; padding:10px; }
QLabel#emptyRules, QLabel#emptyPending { background:@card; color:@muted; padding:24px; border:1px dashed @border; border-radius:16px; }
QPushButton, QToolButton { background:@card; border:1px solid @border; border-radius:10px; padding:8px 12px; min-height:22px; }
QPushButton:hover, QToolButton:hover { background:#EDF9F4; border-color:#A8D9CF; }
QPushButton:focus, QToolButton:focus { border:2px solid @hover; }
QPushButton:disabled { background:#F1F4F5; color:#9AAAB2; border-color:@border; }
QPushButton#primary { background:@accent; border:1px solid @accent; color:@text; font-weight:700; }
QPushButton#primary:hover { background:@hover; border-color:@hover; }
QPushButton#dangerButton { color:@error; border-color:#EBCBD1; }
QPushButton#windowButton { min-width:30px; max-width:30px; padding:0; border:none; background:transparent; }
QLineEdit, QComboBox, QSpinBox { background:@card; color:@text; border:1px solid @border; border-radius:10px; padding:9px; min-height:22px; selection-background-color:#B2F3DE; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border:1px solid @hover; }
QComboBox QAbstractItemView, QListWidget, QTextEdit { background:@card; border:1px solid @border; selection-background-color:#DFF6EE; selection-color:@text; }
QTableView, QTableWidget { background:@card; alternate-background-color:#F9FBFC; border:1px solid @border; border-radius:12px; gridline-color:@border; }
QTableView::item { padding:8px; border-bottom:1px solid @border; }
QTableView::item:selected { background:#DFF6EE; color:@text; }
QHeaderView::section { background:#F0F6F7; color:@muted; padding:10px; border:none; border-bottom:1px solid @border; font-weight:700; }
QCheckBox { spacing:9px; } 


QTabWidget::pane { border:none; } QTabBar::tab { background:transparent; padding:10px 15px; color:@muted; border-bottom:2px solid transparent; }
QTabBar::tab:selected { color:@success; border-bottom:2px solid @accent; font-weight:700; }
QScrollArea, QScrollArea > QWidget > QWidget { background:transparent; border:none; }
QMenu { background:@card; border:1px solid @border; } QMenu::item { padding:9px 22px; } QMenu::item:selected { background:#DFF6EE; }
QToolTip { background:@text; color:white; padding:7px; border:none; }
QSizeGrip { background:transparent; width:16px; height:16px; }
'''
for _key, _value in TOKENS.items():
    STYLE = STYLE.replace('@' + _key, _value)


def apply_theme(app):
    app.setStyle('Fusion')
    palette = QPalette()
    for role, color in dict(Window=TOKENS['background'], WindowText=TOKENS['text'],
                            Base=TOKENS['card'], AlternateBase='#F0F6F7', Text=TOKENS['text'],
                            Button=TOKENS['card'], ButtonText=TOKENS['text'],
                            Highlight='#DFF6EE', HighlightedText=TOKENS['text'],
                            ToolTipBase=TOKENS['text'], ToolTipText='#FFFFFF').items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
    for role in ('Text', 'WindowText', 'ButtonText'):
        palette.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role), QColor('#9AAAB2'))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)
