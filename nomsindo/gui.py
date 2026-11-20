from __future__ import annotations

import os
import re
import sys
import webbrowser
from collections import deque

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QBrush, QColor, QIcon, QLinearGradient, QPainter, QPen,
                           QPixmap)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QFrame,
                               QHBoxLayout, QLabel, QMainWindow, QMenu, QPushButton, QSlider,
                               QStackedWidget, QSystemTrayIcon, QToolButton, QVBoxLayout, QWidget)

from . import APP_NAME, __version__, devices
from .config import Channel, Settings
from .pipeline import Pipeline

GREEN, TEAL, TEXT, MUTED = "#19e3a1", "#1fc8c0", "#dff3f0", "#7fa3a0"

STYLE = f"""
* {{ font-family: 'Segoe UI', 'Inter', sans-serif; color: {TEXT}; font-size: 12px; }}
QMainWindow, QWidget#root {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #0a1214, stop:1 #10262a); }}
QFrame#sidebar {{ background: rgba(8,16,18,200); border-right: 1px solid #1a3033; }}
QToolButton#nav {{ background: transparent; border: none; border-left: 3px solid transparent;
    color: {MUTED}; padding: 10px 4px; font-size: 11px; }}
QToolButton#nav:checked {{ background: rgba(25,227,161,0.10); border-left: 3px solid {GREEN}; color: {TEXT}; }}
QToolButton#nav:hover {{ background: rgba(255,255,255,0.05); }}
QFrame#panel, QFrame#card {{ background: rgba(14,28,31,225); border: 1px solid #1f4549; border-radius: 12px; }}
QLabel {{ background: transparent; }}
QLabel#appname {{ font-size: 20px; font-weight: 600; }}
QLabel#ptitle {{ font-size: 14px; font-weight: 600; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#pill {{ border: 1px solid {GREEN}; border-radius: 12px; padding: 4px 14px; color: {GREEN}; font-weight: 700;
    background: rgba(25,227,161,0.10); }}
QLabel#pill[idle="true"] {{ border-color: #3a5558; color: {MUTED}; background: rgba(255,255,255,0.04); }}
QFrame#statusbar {{ background: rgba(6,12,14,230); border-top: 1px solid #1a3033; }}
QLabel#status {{ color: {MUTED}; font-size: 11px; }}
QPushButton#power {{ background: #1b2b2e; border: 1px solid #2b4448; border-radius: 8px; padding: 8px 18px;
    font-weight: 700; color: {MUTED}; min-width: 70px; }}
QPushButton#power:checked {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #22e8a8, stop:1 #12b985);
    border: 1px solid #5bf3c4; color: #04251a; }}
QPushButton#seg {{ background: #0e1b1d; border: 1px solid #2b4448; padding: 6px 14px; color: {MUTED}; }}
QPushButton#seg:checked {{ background: #274a4d; color: {TEXT}; font-weight: 600; }}
QPushButton#segL {{ border-top-left-radius: 14px; border-bottom-left-radius: 14px; }}
QPushButton#segR {{ border-top-right-radius: 14px; border-bottom-right-radius: 14px; }}
QPushButton#link {{ background: #16282b; border: 1px solid #2b4448; border-radius: 6px; padding: 4px 12px; font-size: 11px; }}
QPushButton#link:hover {{ background: #1f3a3e; }}
QPushButton#plain {{ background: #1b3a3d; border: 1px solid #2f5a5e; border-radius: 8px; padding: 7px 14px; }}
QPushButton#plain:hover {{ background: #24494d; }}
QComboBox {{ background: #0b1517; border: 1px solid #2b4448; border-radius: 6px; padding: 6px 8px; }}
QComboBox QAbstractItemView {{ background: #0b1517; selection-background-color: #1f6f66; border: 1px solid #2b4448; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid #2f5a5e; background: #0b1517; }}
QCheckBox::indicator:checked {{ background: {GREEN}; border-color: #5bf3c4; }}
QSlider::groove:horizontal {{ height: 6px; background: #1c3033; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #7a5af8, stop:0.5 #3b82f6, stop:1 {TEAL});
    border-radius: 3px; }}
QSlider::handle:horizontal {{ background: #f4f8ff; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
    border: 2px solid #9ec5ff; }}
"""


def res(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, rel)


def app_icon() -> QIcon:
    p = res("assets/nomsindo.ico")
    return QIcon(p) if os.path.exists(p) else QIcon()


def pretty(name: str) -> str:
    m = re.search(r"CABLE-?([A-D])?\b", name or "")
    if m:
        return "Virtual Cable " + (m.group(1) or "").strip()
    return re.sub(r"\s*\(.*?\)\s*", "", name or "").strip() or "-"


def _pct_db(db: float) -> float:
    return max(0.0, min(1.0, (db + 60.0) / 60.0))


def nav_icon(kind: str, color: str) -> QIcon:
    pm = QPixmap(30, 30); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 2, Qt.SolidLine, Qt.RoundCap); p.setPen(pen)
    if kind == "routing":
        for x, y in ((8, 11), (15, 19), (22, 9)):
            p.drawLine(x, 5, x, 25); p.setBrush(QColor(color)); p.drawEllipse(QPointF(x, y), 3, 3)
    elif kind == "devices":
        p.setBrush(Qt.NoBrush); p.drawRoundedRect(QRectF(11, 4, 8, 13), 4, 4)
        p.drawArc(QRectF(7, 8, 16, 14), 200 * 16, 140 * 16); p.drawLine(15, 22, 15, 26); p.drawLine(11, 26, 19, 26)
    else:
        p.setBrush(Qt.NoBrush); p.drawEllipse(QPointF(15, 15), 5, 5)
        import math
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(QPointF(15 + 8 * math.cos(a), 15 + 8 * math.sin(a)),
                       QPointF(15 + 11 * math.cos(a), 15 + 11 * math.sin(a)))
    p.end()
    return QIcon(pm)


class Waveform(QWidget):
    """Raw input flows in from the left, cleaned audio flows out to the right of the playhead."""
    STEP = 4

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(110)
        self.inp = deque([0.0] * 400, maxlen=400)
        self.out = deque([0.0] * 400, maxlen=400)

    def push(self, a: float, b: float) -> None:
        self.inp.append(a); self.out.append(b); self.update()

    @staticmethod
    def _h(v: float) -> float:
        return min(1.0, (v ** 0.5) * 1.15)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height(); cy = h / 2
        bg = QLinearGradient(0, 0, 0, h); bg.setColorAt(0, QColor("#071012")); bg.setColorAt(1, QColor("#0b1b1d"))
        p.setBrush(QBrush(bg)); p.setPen(QPen(QColor("#1f4549"), 1)); p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)
        p.setPen(QPen(QColor(255, 255, 255, 18), 1)); p.drawLine(6, int(cy), w - 6, int(cy))
        ph = int(w * 0.58); amp = cy - 8
        n_left, n_right = ph // self.STEP, (w - ph) // self.STEP
        for i in range(n_left):
            v = self._h(self.inp[-1 - i]); x = ph - i * self.STEP
            c = QColor(235, 240, 255, max(40, 230 - i * 2)); p.setPen(QPen(c, 2, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(x, cy - v * amp - 1), QPointF(x, cy + v * amp + 1))
        for i in range(n_right):
            v = self._h(self.out[-1 - i]); x = ph + i * self.STEP
            t = i / max(1, n_right)
            c = QColor(int(30 + 10 * t), int(230 - 60 * t), int(170 + 40 * t), max(60, 235 - int(i * 1.6)))
            p.setPen(QPen(c, 2, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(x, cy - v * amp - 1), QPointF(x, cy + v * amp + 1))
        p.setPen(QPen(QColor(31, 200, 192, 200), 1)); p.drawLine(ph, 4, ph, h - 4)


class VuMeter(QWidget):
    TICKS = [(0, "0"), (-6, "-6"), (-12, "-12"), (-24, "-24"), (-40, "-40"), (-60, "-60")]

    def __init__(self):
        super().__init__()
        self.setFixedWidth(74); self.setMinimumHeight(110)
        self.lv_in = self.lv_out = 0.0

    def set_levels(self, in_db: float, out_db: float) -> None:
        self.lv_in, self.lv_out = _pct_db(in_db), _pct_db(out_db); self.update()

    def _bar(self, p: QPainter, x: float, level: float) -> None:
        h = self.height() - 22; top = 6
        p.setPen(Qt.NoPen); p.setBrush(QColor("#0a1416")); p.drawRoundedRect(QRectF(x, top, 14, h), 3, 3)
        g = QLinearGradient(0, top, 0, top + h)
        g.setColorAt(0, QColor("#ff4d4d")); g.setColorAt(0.22, QColor("#ffd23f")); g.setColorAt(0.45, QColor(GREEN)); g.setColorAt(1, QColor("#0f9f72"))
        fh = h * level
        p.setBrush(QBrush(g)); p.drawRoundedRect(QRectF(x, top + h - fh, 14, fh), 3, 3)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        self._bar(p, 2, self.lv_in); self._bar(p, self.width() - 16, self.lv_out)
        h = self.height() - 22; p.setPen(QColor(MUTED)); f = p.font(); f.setPixelSize(9); p.setFont(f)
        for db, t in self.TICKS:
            y = 6 + h * (1 - _pct_db(db)); p.drawText(QRectF(16, y - 6, self.width() - 32, 12), Qt.AlignCenter, t)
        p.drawText(QRectF(0, self.height() - 14, 30, 12), Qt.AlignCenter, "IN")
        p.drawText(QRectF(self.width() - 32, self.height() - 14, 32, 12), Qt.AlignCenter, "OUT")


class TickSlider(QWidget):
    valueChanged = Signal(int)

    def __init__(self, value: int):
        super().__init__()
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        self.slider = QSlider(Qt.Horizontal); self.slider.setRange(0, 100); self.slider.setValue(value)
        self.slider.setTickPosition(QSlider.NoTicks)
        self.slider.valueChanged.connect(self.valueChanged)
        self.ticks = QWidget(); self.ticks.setFixedHeight(22); self.ticks.paintEvent = self._paint_ticks
        lay.addWidget(self.slider); lay.addWidget(self.ticks)

    def _paint_ticks(self, _):
        p = QPainter(self.ticks); pad = 8; w = self.ticks.width() - 2 * pad
        f = p.font(); f.setPixelSize(9); p.setFont(f)
        for v in range(0, 101, 10):
            x = pad + w * v / 100
            p.setPen(QPen(QColor("#3a5a5e"), 1)); p.drawLine(QPointF(x, 1), QPointF(x, 5))
            p.setPen(QColor(MUTED)); tx = min(x, self.ticks.width() - 20)
            p.drawText(QRectF(tx - 20, 7, 40, 12), Qt.AlignCenter, f"{v}%" if v == 100 else str(v))


class ChannelController(QObject):
    changed = Signal()

    def __init__(self, cfg: Channel, name: str, role: str):
        super().__init__()
        self.cfg, self.role, self.pipe = cfg, role, Pipeline(name)
        self.in_box, self.out_box = QComboBox(), QComboBox()
        self.refresh()
        for b in (self.in_box, self.out_box):
            b.currentIndexChanged.connect(self._dev_changed)

    def _defaults(self, ins, outs):
        if self.role == "mic":
            return (devices.default_device("input"),
                    devices.find(outs, "CABLE-A Input", "CABLE Input"))
        return (devices.find(ins, "CABLE-B Output", "CABLE-A Output"), devices.default_device("output"))

    def refresh(self) -> None:
        try:
            ins, outs = devices.inputs(), devices.outputs()
            d_in, d_out = self._defaults(ins, outs)
        except Exception:
            ins, outs, d_in, d_out = [], [], None, None
        for box, pool, saved, dflt in ((self.in_box, ins, self.cfg.input_name, d_in),
                                       (self.out_box, outs, self.cfg.output_name, d_out)):
            box.blockSignals(True); box.clear(); box.addItem("- select a device -", None)
            for d in pool:
                box.addItem(d.name, d.index)
            want = (devices.find(pool, saved) if saved else None) or dflt
            if want:
                box.setCurrentIndex(max(0, box.findData(want.index)))
            box.blockSignals(False)
        self.changed.emit()

    def title(self) -> str:
        return f"{pretty(self.in_box.currentText())}  ->  {pretty(self.out_box.currentText())}"

    @property
    def running(self) -> bool:
        return self.pipe.status == "running"

    def _dev_changed(self) -> None:
        self.cfg.input_name, self.cfg.output_name = self.in_box.currentText(), self.out_box.currentText()
        if self.running:
            self.start()
        self.changed.emit()

    def start(self) -> None:
        a, b = self.in_box.currentData(), self.out_box.currentData()
        if a is None or b is None:
            self.pipe.status = "select devices first"; self.changed.emit(); return
        self.pipe.set_strength(self.cfg.strength / 100.0); self.pipe.set_mode(self.cfg.mode)
        self.pipe.start(a, b)
        self.cfg.enabled = self.running
        self.cfg.input_name, self.cfg.output_name = self.in_box.currentText(), self.out_box.currentText()
        self.changed.emit()

    def stop(self) -> None:
        self.pipe.stop(); self.cfg.enabled = False; self.changed.emit()


class ChannelPanel(QFrame):
    def __init__(self, ctrl: ChannelController):
        super().__init__()
        self.setObjectName("panel"); self.ctrl = ctrl
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 12, 16, 12); lay.setSpacing(8)
        self.title = QLabel(); self.title.setObjectName("ptitle"); lay.addWidget(self.title)

        row = QHBoxLayout(); row.setSpacing(10)
        self.wave, self.vu = Waveform(), VuMeter()
        row.addWidget(self.wave, 1); row.addWidget(self.vu); lay.addLayout(row, 1)

        top = QHBoxLayout()
        lbl = QLabel("Noise Removal Strength"); self.pct = QLabel(f"{ctrl.cfg.strength}%")
        top.addWidget(lbl); top.addStretch(1); top.addWidget(self.pct)
        mode_lbl = QLabel("Mode"); top.addSpacing(30); top.addWidget(mode_lbl)
        lay.addLayout(top)

        bot = QHBoxLayout(); bot.setSpacing(14)
        self.slider = TickSlider(ctrl.cfg.strength); bot.addWidget(self.slider, 1)
        seg = QHBoxLayout(); seg.setSpacing(0)
        self.b_std, self.b_str = QPushButton("Standard"), QPushButton("Strong")
        for b, nm in ((self.b_std, "segL"), (self.b_str, "segR")):
            b.setCheckable(True); b.setObjectName("seg"); b.setProperty("class", nm); seg.addWidget(b)
        self.b_std.setObjectName("seg"); self.b_str.setObjectName("seg")
        self.b_std.setStyleSheet("border-top-left-radius:14px;border-bottom-left-radius:14px;")
        self.b_str.setStyleSheet("border-top-right-radius:14px;border-bottom-right-radius:14px;")
        grp = QButtonGroup(self); grp.setExclusive(True); grp.addButton(self.b_std); grp.addButton(self.b_str)
        (self.b_std if ctrl.cfg.mode == 1 else self.b_str).setChecked(True)
        bot.addLayout(seg)
        self.power = QPushButton("ACTIVE"); self.power.setObjectName("power"); self.power.setCheckable(True)
        bot.addWidget(self.power); lay.addLayout(bot)

        self.err = QLabel(""); self.err.setObjectName("muted"); lay.addWidget(self.err)

        self.slider.valueChanged.connect(self._strength)
        self.b_std.clicked.connect(lambda: self._mode(1)); self.b_str.clicked.connect(lambda: self._mode(2))
        self.power.clicked.connect(self._toggle)
        ctrl.changed.connect(self.sync); self.sync()

    def _strength(self, v: int) -> None:
        self.ctrl.cfg.strength = v; self.pct.setText(f"{v}%"); self.ctrl.pipe.set_strength(v / 100.0)

    def _mode(self, m: int) -> None:
        self.ctrl.cfg.mode = m; self.ctrl.pipe.set_mode(m)

    def _toggle(self) -> None:
        self.ctrl.stop() if self.ctrl.running else self.ctrl.start()

    def sync(self) -> None:
        self.title.setText(self.ctrl.title())
        self.power.setChecked(self.ctrl.running)
        st = self.ctrl.pipe.status
        self.err.setText("" if st in ("running", "stopped") else st.capitalize())

    def tick(self) -> None:
        a, b = self.ctrl.pipe.take_peaks()
        self.wave.push(a, b)
        self.vu.set_levels(self.ctrl.pipe.level_in_db, self.ctrl.pipe.level_out_db)


class DevicesPage(QWidget):
    def __init__(self, mic: ChannelController, spk: ChannelController, cable_ok):
        super().__init__()
        lay = QVBoxLayout(self); lay.setContentsMargins(14, 14, 14, 14); lay.setSpacing(12)
        for title, hint, ctrl, l_in, l_out in (
            ("Microphone path", "Call app microphone = CABLE-A Output", mic, "Your microphone", "Send cleaned voice to (virtual cable input)"),
            ("Speaker path", "Call app speaker = CABLE-B Input", spk, "Call audio from (virtual cable output)", "Your headphones / speakers")):
            f = QFrame(); f.setObjectName("card"); v = QVBoxLayout(f); v.setContentsMargins(16, 12, 16, 14); v.setSpacing(6)
            t = QLabel(title); t.setObjectName("ptitle"); h = QLabel(hint); h.setObjectName("muted")
            v.addWidget(t); v.addWidget(h); v.addWidget(QLabel(l_in)); v.addWidget(ctrl.in_box)
            v.addWidget(QLabel(l_out)); v.addWidget(ctrl.out_box); lay.addWidget(f)
        row = QHBoxLayout()
        rb = QPushButton("Refresh devices"); rb.setObjectName("plain")
        rb.clicked.connect(lambda: (mic.refresh(), spk.refresh()))
        dl = QPushButton("Get VB-Audio Virtual Cable"); dl.setObjectName("plain")
        dl.clicked.connect(lambda: webbrowser.open("https://vb-audio.com/Cable/"))
        row.addWidget(rb); row.addWidget(dl); row.addStretch(1); lay.addLayout(row); lay.addStretch(1)


class SettingsPage(QWidget):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        s = win.settings
        lay = QVBoxLayout(self); lay.setContentsMargins(14, 14, 14, 14); lay.setSpacing(12)
        f = QFrame(); f.setObjectName("card"); v = QVBoxLayout(f); v.setContentsMargins(16, 12, 16, 14); v.setSpacing(10)
        t = QLabel("General"); t.setObjectName("ptitle"); v.addWidget(t)
        for text, attr in (("Start NoMsindo when Windows starts", "run_at_login"),
                           ("Start minimized to the tray", "start_minimized"),
                           ("Start audio automatically on launch", "autostart_audio"),
                           ("Keep running in the tray when the window is closed", "close_to_tray")):
            cb = QCheckBox(text); cb.setChecked(getattr(s, attr))
            cb.toggled.connect(lambda on, a=attr: win.set_option(a, on)); v.addWidget(cb)
        lay.addWidget(f)
        a = QFrame(); a.setObjectName("card"); h = QHBoxLayout(a); h.setContentsMargins(16, 12, 16, 12); h.setSpacing(16)
        pm = QPixmap(res("assets/logo_tile.png"))
        logo = QLabel(); logo.setPixmap(pm.scaledToWidth(130, Qt.SmoothTransformation)); h.addWidget(logo)
        txt = QVBoxLayout()
        n = QLabel(f"NoMsindo {__version__}"); n.setObjectName("ptitle")
        d = QLabel("Real-time AI voice isolation for calls.\nNoise removal by RNNoise (BSD licence).\n"
                   "Virtual audio routing via VB-Audio Virtual Cable.")
        d.setObjectName("muted"); txt.addWidget(n); txt.addWidget(d); txt.addStretch(1); h.addLayout(txt, 1)
        lay.addWidget(a); lay.addStretch(1)


def set_run_at_login(on: bool) -> None:
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        if on:
            exe = sys.executable if getattr(sys, "frozen", False) else f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'{exe} --minimized')
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME); self.setWindowIcon(app_icon())
        self.settings = Settings.load()
        self.mic = ChannelController(self.settings.mic, "mic", "mic")
        self.spk = ChannelController(self.settings.speaker, "speaker", "speaker")
        self.ctrls = [self.mic, self.spk]

        root = QWidget(); root.setObjectName("root"); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        head = QHBoxLayout(); head.setContentsMargins(16, 10, 16, 10)
        ic = QLabel(); ic.setPixmap(QPixmap(res("assets/icon_48.png")).scaled(34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        nm = QLabel("NoMsindo"); nm.setObjectName("appname")
        self.pill = QLabel("ACTIVE"); self.pill.setObjectName("pill")
        head.addWidget(ic); head.addSpacing(6); head.addWidget(nm); head.addStretch(1); head.addWidget(self.pill)
        outer.addLayout(head)

        body = QHBoxLayout(); body.setSpacing(0)
        side = QFrame(); side.setObjectName("sidebar"); side.setFixedWidth(84)
        sl = QVBoxLayout(side); sl.setContentsMargins(0, 10, 0, 0); sl.setSpacing(2)
        self.pages = QStackedWidget()
        routing = QWidget(); rl = QVBoxLayout(routing); rl.setContentsMargins(14, 14, 14, 14); rl.setSpacing(12)
        self.panels = [ChannelPanel(c) for c in self.ctrls]
        for p in self.panels:
            rl.addWidget(p, 1)
        self.pages.addWidget(routing)
        self.pages.addWidget(DevicesPage(self.mic, self.spk, devices.virtual_cable_present))
        self.pages.addWidget(SettingsPage(self))
        grp = QButtonGroup(self)
        for i, (label, kind) in enumerate((("Audio\nRouting", "routing"), ("Devices", "devices"), ("Settings", "settings"))):
            b = QToolButton(); b.setObjectName("nav"); b.setText(label); b.setCheckable(True)
            b.setIcon(nav_icon(kind, "#9fe8d6")); b.setIconSize(b.iconSize() * 1.0)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon); b.setFixedHeight(76); b.setFixedWidth(84)
            b.clicked.connect(lambda _, i=i: self.pages.setCurrentIndex(i)); grp.addButton(b); sl.addWidget(b)
            if i == 0:
                b.setChecked(True)
        sl.addStretch(1)
        body.addWidget(side); body.addWidget(self.pages, 1); outer.addLayout(body, 1)

        sb = QFrame(); sb.setObjectName("statusbar"); sbl = QHBoxLayout(sb); sbl.setContentsMargins(14, 6, 10, 6)
        self.status = QLabel(); self.status.setObjectName("status")
        dl = QPushButton("VB-Audio"); dl.setObjectName("link"); dl.clicked.connect(lambda: webbrowser.open("https://vb-audio.com/Cable/"))
        sbl.addWidget(self.status, 1); sbl.addWidget(dl); outer.addWidget(sb)

        for c in self.ctrls:
            c.changed.connect(self.refresh_status)
        self.refresh_status()
        self.timer = QTimer(self); self.timer.timeout.connect(self._tick); self.timer.start(33)
        self._tray(); self.resize(760, 700); self.setMinimumSize(700, 640)

    # ---- state
    def set_option(self, attr: str, on: bool) -> None:
        setattr(self.settings, attr, on)
        if attr == "run_at_login":
            set_run_at_login(on)
        self.settings.save()

    def refresh_status(self) -> None:
        try:
            engine = "RNNoise Engine OK (10ms Chunks)"
            from .engine import FRAME
            assert FRAME == 480
        except Exception:
            engine = "RNNoise Engine ERROR"
        try:
            cable = "VB-Audio Cable Connected" if devices.virtual_cable_present() else "VB-Audio Cable not found"
        except Exception:
            cable = "VB-Audio Cable not found"
        run = any(c.running for c in self.ctrls)
        self.status.setText(f"{'Running' if run else 'Ready'} | {engine} | {cable}")
        self.pill.setText("ACTIVE" if run else "IDLE"); self.pill.setProperty("idle", not run)
        self.pill.style().unpolish(self.pill); self.pill.style().polish(self.pill)

    def _tick(self) -> None:
        if self.isVisible() and not self.isMinimized():
            for p in self.panels:
                p.tick()

    def auto_start(self) -> None:
        if self.settings.autostart_audio:
            for c in self.ctrls:
                if c.cfg.enabled and c.cfg.input_name and c.cfg.output_name:
                    c.start()

    # ---- tray
    def _tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self)
        m = QMenu()
        a_open = QAction("Open NoMsindo", self); a_open.triggered.connect(self.showNormal)
        a_quit = QAction("Quit", self); a_quit.triggered.connect(self.quit)
        m.addAction(a_open); m.addSeparator(); m.addAction(a_quit)
        self.tray.setContextMenu(m); self.tray.setToolTip("NoMsindo")
        self.tray.activated.connect(lambda r: self.showNormal() if r == QSystemTrayIcon.Trigger else None)
        self.tray.show()

    def closeEvent(self, e) -> None:
        if self.settings.close_to_tray and self.tray.isVisible() and any(c.running for c in self.ctrls):
            self.hide()
            self.tray.showMessage(APP_NAME, "Still cleaning your audio from the tray.", QSystemTrayIcon.Information, 2500)
            e.ignore()
        else:
            self.quit(); e.accept()

    def quit(self) -> None:
        for c in self.ctrls:
            c.stop()
        self.settings.save(); self.tray.hide(); QApplication.quit()


def run() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE); app.setWindowIcon(app_icon()); app.setQuitOnLastWindowClosed(False)
    w = MainWindow()
    if "--minimized" not in sys.argv and not w.settings.start_minimized:
        w.show()
    QTimer.singleShot(400, w.auto_start)
    return app.exec()
