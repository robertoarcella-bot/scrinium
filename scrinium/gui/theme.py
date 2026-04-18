"""Tema grafico di Scrinium: palette blu/grigia applicata via QSS."""

# Palette
NAVY = "#1e3a8a"      # blu intenso (menu bar, accenti forti)
PRIMARY = "#2563eb"   # blu primario (bottoni, focus, progress)
PRIMARY_HOVER = "#1d4ed8"
PRIMARY_PRESSED = "#1e40af"
LIGHT_BLUE = "#dbeafe"  # selezione tabelle
BG = "#f4f6fa"          # sfondo finestra
SURFACE = "#ffffff"     # sfondo input/tabelle
BORDER = "#cbd5e1"      # bordi
BORDER_STRONG = "#94a3b8"
TEXT = "#1e293b"
MUTED = "#64748b"
DISABLED_BG = "#e2e8f0"


STYLESHEET = f"""
* {{
    font-family: "Segoe UI", "SF Pro Text", system-ui, sans-serif;
    color: {TEXT};
}}

QMainWindow, QDialog {{
    background-color: {BG};
}}

QLabel[hint="true"] {{
    color: {MUTED};
    font-size: 11px;
}}

/* Bottoni */
QPushButton {{
    background-color: {PRIMARY};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: 500;
}}
QPushButton:hover {{ background-color: {PRIMARY_HOVER}; }}
QPushButton:pressed {{ background-color: {PRIMARY_PRESSED}; }}
QPushButton:disabled {{
    background-color: {DISABLED_BG};
    color: {MUTED};
}}

/* Input */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox,
QSpinBox, QDoubleSpinBox {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 6px;
    selection-background-color: {LIGHT_BLUE};
    selection-color: {NAVY};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {PRIMARY};
}}
QComboBox::drop-down {{ border: none; width: 20px; }}

/* Checkbox */
QCheckBox {{
    spacing: 8px;
    color: {TEXT};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER_STRONG};
    border-radius: 3px;
    background-color: {SURFACE};
}}
QCheckBox::indicator:checked {{
    background-color: {PRIMARY};
    border: 1px solid {PRIMARY};
}}

/* Menu bar */
QMenuBar {{
    background-color: {NAVY};
    color: white;
    padding: 2px;
}}
QMenuBar::item {{
    padding: 6px 12px;
    background-color: transparent;
    color: white;
}}
QMenuBar::item:selected {{ background-color: {PRIMARY}; }}
QMenu {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
}}
QMenu::item:selected {{
    background-color: {LIGHT_BLUE};
    color: {NAVY};
}}

/* Tabella profili */
QTableWidget {{
    background-color: {SURFACE};
    gridline-color: {DISABLED_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {LIGHT_BLUE};
    selection-color: {NAVY};
}}
QHeaderView::section {{
    background-color: {DISABLED_BG};
    color: {NAVY};
    padding: 6px 8px;
    border: none;
    border-right: 1px solid {BORDER};
    font-weight: 600;
}}

/* Progress bar */
QProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 4px;
    text-align: center;
    background-color: {SURFACE};
    color: {TEXT};
    height: 18px;
}}
QProgressBar::chunk {{
    background-color: {PRIMARY};
    border-radius: 3px;
}}

/* Status bar */
QStatusBar {{
    background-color: {DISABLED_BG};
    color: {TEXT};
    border-top: 1px solid {BORDER};
}}

/* Scroll bar moderna */
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_STRONG};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {MUTED}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""
