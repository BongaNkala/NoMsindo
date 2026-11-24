from __future__ import annotations

import os
import re
import sys
import threading
import time
import webbrowser

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QStackedWidget,
                               QSystemTrayIcon, QToolButton, QVBoxLayout, QWidget)

from . import APP_NAME, __version__, devices, safety
from .config import Channel, Settings
from .licensing import LicenceClient, LicenceError
from .pipeline import Pipeline
from .ui_widgets import (AMBER, CYAN, MINT, MUTED, RED, TEXT, Backdrop, GlassPanel, GlowSlider, PowerButton,
                         Segmented, VuMeter, Waveform, rgba)

def res(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, rel)


STYLE_TMPL = f"""
* {{ font-family: 'Segoe UI Variable Text', 'Segoe UI', 'Inter', sans-serif; color: {TEXT}; font-size: 12px; }}
QLabel {{ background: transparent; }}
QLabel#appname {{ font-size: 24px; font-weight: 600; letter-spacing: 0.5px; }}
QLabel#tagline {{ color: {MUTED}; font-size: 9px; font-weight: 600; letter-spacing: 2.4px; }}
QLabel#ptitle {{ font-size: 15px; font-weight: 600; }}
QLabel#route {{ color: {MUTED}; font-size: 11px; }}
QLabel#caps {{ color: {MUTED}; font-size: 9px; font-weight: 700; letter-spacing: 1.8px; }}
QLabel#value {{ color: {MINT}; font-size: 26px; font-weight: 300; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#warn {{ color: {AMBER}; background: rgba(255,176,32,0.09); border: 1px solid rgba(255,176,32,0.35);
    border-radius: 8px; padding: 7px 10px; }}
QLabel#err {{ color: #ff8a8a; }}
QLabel#chip {{ border: 1px solid rgba(143,255,232,0.22); border-radius: 11px; padding: 3px 12px; color: {MUTED};
    background: rgba(255,255,255,0.03); font-size: 11px; }}
QLabel#chip[warn="true"] {{ color: {AMBER}; border-color: rgba(255,176,32,0.5); }}
QLabel#pill {{ border: 1px solid rgba(42,245,181,0.6); border-radius: 13px; padding: 4px 15px; color: {MINT};
    font-weight: 700; letter-spacing: 1.4px; background: rgba(42,245,181,0.10); font-size: 11px; }}
QLabel#pill[idle="true"] {{ border-color: rgba(143,255,232,0.2); color: {MUTED}; background: rgba(255,255,255,0.03); }}
QFrame#sidebar {{ background: rgba(4,9,11,0.62); border-right: 1px solid rgba(143,255,232,0.09); }}
QFrame#statusbar {{ background: rgba(3,7,9,0.80); border-top: 1px solid rgba(143,255,232,0.09); }}
QLabel#status {{ color: {MUTED}; font-size: 11px; }}
QToolButton#nav {{ background: transparent; border: none; border-left: 3px solid transparent; color: {MUTED};
    padding: 10px 2px 8px 2px; font-size: 11px; }}
QToolButton#nav:hover {{ background: rgba(255,255,255,0.04); color: {TEXT}; }}
QToolButton#nav:checked {{ color: {TEXT}; border-left: 3px solid {MINT};
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 rgba(42,245,181,0.16), stop:1 rgba(42,245,181,0.0)); }}
QPushButton#plain {{ background: rgba(255,255,255,0.05); border: 1px solid rgba(143,255,232,0.22); border-radius: 9px;
    padding: 8px 16px; font-weight: 600; }}
QPushButton#plain:hover {{ background: rgba(42,245,181,0.12); border-color: rgba(42,245,181,0.5); }}
QPushButton#plain:disabled {{ color: #4d6a67; }}
QPushButton#link {{ background: rgba(255,255,255,0.05); border: 1px solid rgba(143,255,232,0.2); border-radius: 7px;
    padding: 4px 12px; font-size: 11px; }}
QPushButton#link:hover {{ background: rgba(42,245,181,0.12); }}
QLineEdit, QComboBox {{ background: rgba(3,8,10,0.75); border: 1px solid rgba(143,255,232,0.18); border-radius: 8px; padding: 7px 10px; }}
QLineEdit:focus, QComboBox:focus {{ border-color: rgba(42,245,181,0.65); }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url(%ARROW%); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: #0a1619; border: 1px solid rgba(143,255,232,0.25); selection-background-color: #1d6b62; outline: 0; }}
QCheckBox {{ spacing: 10px; background: transparent; }}
QCheckBox::indicator {{ width: 17px; height: 17px; border-radius: 5px; border: 1px solid rgba(143,255,232,0.35); background: rgba(3,8,10,0.75); }}
QCheckBox::indicator:checked {{ background: {MINT}; border-color: #8dffe0; }}
QDialog {{ background: #0a1619; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: rgba(143,255,232,0.25); border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(42,245,181,0.5); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QToolTip {{ background: #0a1619; color: {TEXT}; border: 1px solid rgba(143,255,232,0.3); padding: 5px; }}
"""




STYLE = STYLE_TMPL.replace("%ARROW%", res("assets/chevron.png").replace("\\", "/"))


def app_icon() -> QIcon:
    p = res("assets/nomsindo.ico")
    return QIcon(p) if os.path.exists(p) else QIcon()


def brand_pixmap(px: int) -> QPixmap:
    pm = QPixmap(res("assets/icon_512.png")).scaled(px * 2, px * 2, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    pm.setDevicePixelRatio(2.0)
    return pm


def pretty(name: str) -> str:
    m = re.search(r"CABLE-?([A-D])?\b", name or "")
    if m:
        return "Virtual Cable " + (m.group(1) or "").strip()
    return re.sub(r"\s*\(.*?\)\s*", "", name or "").strip() or "-"


def nav_icon(kind: str) -> QIcon:
    import math
    icon = QIcon()
    for color, state in (("#7aa09c", QIcon.Off), (MINT, QIcon.On)):
        pm = QPixmap(60, 60); pm.setDevicePixelRatio(2.0); pm.fill(Qt.transparent)
        p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(color), 1.9, Qt.SolidLine, Qt.RoundCap)); p.setBrush(Qt.NoBrush)
        if kind == "routing":
            for x, y in ((8, 11), (15, 19), (22, 9)):
                p.drawLine(x, 5, x, 25); p.setBrush(QColor(color)); p.drawEllipse(QPointF(x, y), 2.8, 2.8); p.setBrush(Qt.NoBrush)
        elif kind == "devices":
            p.drawRoundedRect(QRectF(11, 3.5, 8, 13), 4, 4); p.drawArc(QRectF(7, 8, 16, 14), 200 * 16, 140 * 16)
            p.drawLine(15, 22, 15, 26); p.drawLine(11, 26, 19, 26)
        else:
            p.drawEllipse(QPointF(15, 15), 5, 5)
            for i in range(8):
                a = i * math.pi / 4
                p.drawLine(QPointF(15 + 8 * math.cos(a), 15 + 8 * math.sin(a)), QPointF(15 + 11 * math.cos(a), 15 + 11 * math.sin(a)))
        p.end(); icon.addPixmap(pm, QIcon.Normal, state)
    return icon


def badge(kind: str) -> QLabel:
    """Round icon badge for a panel header."""
    pm = QPixmap(80, 80); pm.setDevicePixelRatio(2.0); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(rgba(MINT, 0.10)); p.setPen(QPen(rgba(MINT, 0.4), 1)); p.drawEllipse(QRectF(1, 1, 38, 38))
    p.setPen(QPen(QColor(MINT), 2, Qt.SolidLine, Qt.RoundCap)); p.setBrush(Qt.NoBrush)
    if kind == "mic":
        p.drawRoundedRect(QRectF(16, 9, 8, 14), 4, 4); p.drawArc(QRectF(12, 14, 16, 12), 200 * 16, 140 * 16)
        p.drawLine(20, 26, 20, 30)
    else:
        p.drawArc(QRectF(10, 10, 20, 20), 0, 180 * 16); p.drawRoundedRect(QRectF(9, 19, 5, 9), 2, 2); p.drawRoundedRect(QRectF(26, 19, 5, 9), 2, 2)
    p.end()
    lab = QLabel(); lab.setPixmap(pm); lab.setFixedSize(40, 40)
    return lab


def dark_titlebar(win: QWidget) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(win.winId()); on = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), 4)      # dark mode caption
        col = ctypes.c_int(0x0C0905)                                                     # caption colour (BGR)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(col), 4)
    except Exception:
        pass


class ChannelController(QObject):
    changed = Signal()

    def __init__(self, cfg: Channel, name: str, role: str):
        super().__init__()
        self.cfg, self.role, self.pipe = cfg, role, Pipeline(name)
        self.other: "ChannelController | None" = None
        self.in_box, self.out_box = QComboBox(), QComboBox()
        self.refresh()
        for b in (self.in_box, self.out_box):
            b.currentIndexChanged.connect(self._dev_changed)

    def _defaults(self, ins, outs):
        if self.role == "mic":
            return (devices.default_device("input"), devices.find(outs, "CABLE-A Input", "CABLE Input"))
        return (devices.find(ins, "CABLE-B Output"), devices.default_device("output"))

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
        return f"{pretty(self.in_box.currentText())}  →  {pretty(self.out_box.currentText())}"

    @property
    def running(self) -> bool:
        return self.pipe.status == "running"

    def problem(self) -> str | None:
        if self.in_box.currentData() is None or self.out_box.currentData() is None or self.other is None:
            return None
        o = self.other
        return safety.check(self.role, self.in_box.currentText(), self.out_box.currentText(),
                            o.in_box.currentText(), o.out_box.currentText())

    def _dev_changed(self) -> None:
        self.cfg.input_name, self.cfg.output_name = self.in_box.currentText(), self.out_box.currentText()
        if self.running:
            self.start()
        self.changed.emit()
        if self.other:
            self.other.changed.emit()

    def start(self) -> None:
        a, b = self.in_box.currentData(), self.out_box.currentData()
        if a is None or b is None:
            self.pipe.stop(); self.pipe.status = "select devices first"; self.cfg.enabled = False; self.changed.emit(); return
        if self.problem():                       # never start a routing that would feed back
            self.pipe.stop(); self.pipe.status = "blocked"; self.cfg.enabled = False; self.changed.emit(); return
        self.pipe.set_strength(self.cfg.strength / 100.0); self.pipe.set_mode(self.cfg.mode)
        self.pipe.start(a, b)
        self.cfg.enabled = self.running
        self.cfg.input_name, self.cfg.output_name = self.in_box.currentText(), self.out_box.currentText()
        self.changed.emit()

    def stop(self) -> None:
        self.pipe.stop(); self.cfg.enabled = False; self.changed.emit()


class ChannelPanel(GlassPanel):
    def __init__(self, ctrl: ChannelController, title: str, kind: str):
        super().__init__(18)
        self.setMinimumHeight(300)
        self.ctrl = ctrl
        lay = QVBoxLayout(self); lay.setContentsMargins(20, 16, 20, 16); lay.setSpacing(10)

        head = QHBoxLayout(); head.setSpacing(12)
        head.addWidget(badge(kind))
        tl = QVBoxLayout(); tl.setSpacing(0)
        self.title = QLabel(title); self.title.setObjectName("ptitle")
        self.route = QLabel(); self.route.setObjectName("route")
        tl.addWidget(self.title); tl.addWidget(self.route); head.addLayout(tl); head.addStretch(1)
        self.voice = QLabel("● VOICE"); self.voice.setObjectName("caps")
        self.live = QLabel(); self.live.setObjectName("caps")
        head.addWidget(self.voice); head.addSpacing(10); head.addWidget(self.live)
        lay.addLayout(head)

        mid = QHBoxLayout(); mid.setSpacing(12)
        self.wave, self.vu = Waveform(), VuMeter()
        mid.addWidget(self.wave, 1); mid.addWidget(self.vu); lay.addLayout(mid, 1)

        self.warn = QLabel(); self.warn.setObjectName("warn"); self.warn.setWordWrap(True); self.warn.setMinimumHeight(58); self.warn.hide()
        lay.addWidget(self.warn)

        bot = QHBoxLayout(); bot.setSpacing(18)
        nb = QVBoxLayout(); nb.setSpacing(0)
        nr = QHBoxLayout(); cap = QLabel("NOISE REMOVAL"); cap.setObjectName("caps")
        self.pct = QLabel(f"{ctrl.cfg.strength}%"); self.pct.setObjectName("value")
        nr.addWidget(cap); nr.addStretch(1); nr.addWidget(self.pct)
        self.slider = GlowSlider(ctrl.cfg.strength)
        nb.addLayout(nr); nb.addWidget(self.slider); bot.addLayout(nb, 1)
        mb = QVBoxLayout(); mb.setSpacing(6)
        mcap = QLabel("MODE"); mcap.setObjectName("caps")
        self.mode = Segmented(["Standard", "Strong"], 0 if ctrl.cfg.mode == 1 else 1)
        mb.addWidget(mcap); mb.addWidget(self.mode); mb.addStretch(1); bot.addLayout(mb)
        self.power = PowerButton(); bot.addWidget(self.power, 0, Qt.AlignVCenter)
        lay.addLayout(bot)

        self.slider.valueChanged.connect(self._strength)
        self.mode.changed.connect(lambda i: self._mode(i + 1))
        self.power.clicked.connect(self._toggle)
        ctrl.changed.connect(self.sync); self.sync()

    def _strength(self, v: int) -> None:
        self.ctrl.cfg.strength = v; self.pct.setText(f"{v}%"); self.ctrl.pipe.set_strength(v / 100.0)

    def _mode(self, m: int) -> None:
        self.ctrl.cfg.mode = m; self.ctrl.pipe.set_mode(m)

    def _toggle(self) -> None:
        self.ctrl.stop() if self.ctrl.running else self.ctrl.start()

    def sync(self) -> None:
        run = self.ctrl.running
        self.route.setText(self.ctrl.title())
        self.power.setChecked(run); self.wave.idle = not run; self.set_glow(run)
        self.live.setText(f"<span style='color:{MINT}'>●</span> LIVE" if run else f"<span style='color:#4d6a67'>●</span> OFF")
        self.live.setStyleSheet(f"color: {MINT if run else MUTED};")
        st = self.ctrl.pipe.status
        msg = self.ctrl.problem() or ("" if st in ("running", "stopped", "blocked") else st[:1].upper() + st[1:])
        if not msg and st == "blocked":
            msg = "This routing was stopped to prevent feedback."
        self.warn.setText(("⚠  " + msg) if msg else ""); self.warn.setVisible(bool(msg))
        self.wave.update()

    def tick(self) -> None:
        a, b = self.ctrl.pipe.take_peaks()
        self.wave.push(a, b)
        self.vu.set_levels(self.ctrl.pipe.level_in_db, self.ctrl.pipe.level_out_db)
        on = self.ctrl.pipe.speech_prob > 0.5
        self.voice.setStyleSheet(f"color: {MINT if on else '#3d5b58'};")


def section(title: str, hint: str = "") -> tuple[GlassPanel, QVBoxLayout]:
    f = GlassPanel(16); v = QVBoxLayout(f); v.setContentsMargins(20, 16, 20, 16); v.setSpacing(7)
    t = QLabel(title); t.setObjectName("ptitle"); v.addWidget(t)
    if hint:
        h = QLabel(hint); h.setObjectName("muted"); h.setWordWrap(True); v.addWidget(h)
    return f, v


class DevicesPage(QWidget):
    def __init__(self, mic: ChannelController, spk: ChannelController):
        super().__init__()
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 16, 18, 16); lay.setSpacing(12)
        for title, hint, ctrl, l_in, l_out in (
            ("Microphone path", "In your call app set Microphone to <b>CABLE-A Output</b>", mic, "Your microphone", "Send cleaned voice to (virtual cable input)"),
            ("Speaker path", "In your call app set Speaker to <b>CABLE-B Input</b>", spk, "Call audio from (virtual cable output)", "Your headphones")):
            f, v = section(title, hint)
            for text, box in ((l_in, ctrl.in_box), (l_out, ctrl.out_box)):
                c = QLabel(text.upper()); c.setObjectName("caps"); v.addSpacing(2); v.addWidget(c); v.addWidget(box)
            lay.addWidget(f)
        f, v = section("Hearing yourself or an echo?")
        tips = QLabel("1. In Windows Sound settings, open the <b>Recording</b> tab, right-click <b>CABLE-A Output</b>, choose "
                      "Properties, then <b>Listen</b>, and make sure <i>Listen to this device</i> is off.<br>"
                      "2. Your call app must use <b>CABLE-A Output</b> as its microphone and <b>CABLE-B Input</b> as its speaker.<br>"
                      "3. Wear a headset. With loudspeakers, your microphone picks the other person up and sends it back as an echo.")
        tips.setObjectName("muted"); tips.setWordWrap(True); v.addWidget(tips); lay.addWidget(f)
        row = QHBoxLayout()
        rb = QPushButton("Refresh devices"); rb.setObjectName("plain"); rb.clicked.connect(lambda: (mic.refresh(), spk.refresh()))
        dl = QPushButton("Get VB-Audio Virtual Cable"); dl.setObjectName("plain"); dl.clicked.connect(lambda: webbrowser.open("https://vb-audio.com/Cable/"))
        row.addWidget(rb); row.addWidget(dl); row.addStretch(1); lay.addLayout(row); lay.addStretch(1)


class SettingsPage(QWidget):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        s = win.settings
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 16, 18, 16); lay.setSpacing(12)
        f, v = section("General")
        for text, attr in (("Start NoMsindo when Windows starts", "run_at_login"), ("Start minimized to the tray", "start_minimized"),
                           ("Start audio automatically on launch", "autostart_audio"),
                           ("Keep running in the tray when the window is closed", "close_to_tray")):
            cb = QCheckBox(text); cb.setChecked(getattr(s, attr)); cb.toggled.connect(lambda on, a=attr: win.set_option(a, on)); v.addWidget(cb)
        lay.addWidget(f)
        acct, av = section("Account")
        self.acct_info = QLabel(); self.acct_info.setObjectName("muted"); self.acct_info.setWordWrap(True); av.addWidget(self.acct_info)
        so = QPushButton("Sign out of this computer"); so.setObjectName("plain"); so.clicked.connect(win.sign_out)
        av.addWidget(so, 0, Qt.AlignLeft); lay.addWidget(acct); win.lic_widgets.append(self.acct_info)
        a, ah = section("About")
        row = QHBoxLayout(); row.setSpacing(18)
        logo = QLabel(); pm = QPixmap(res("assets/logo_tile.png")).scaledToWidth(240, Qt.SmoothTransformation); logo.setPixmap(pm)
        row.addWidget(logo)
        txt = QVBoxLayout(); n = QLabel(f"NoMsindo {__version__}"); n.setObjectName("ptitle")
        d = QLabel("Real-time AI voice isolation for calls.\nNoise removal by RNNoise (BSD licence).\n"
                   "Virtual audio routing via VB-Audio Virtual Cable.")
        d.setObjectName("muted"); txt.addWidget(n); txt.addWidget(d); txt.addStretch(1); row.addLayout(txt, 1)
        ah.addLayout(row); lay.addWidget(a); lay.addStretch(1)


def set_run_at_login(on: bool) -> None:
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        if on:
            exe = sys.executable if getattr(sys, "frozen", False) else f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f"{exe} --minimized")
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass


class Bus(QObject):
    licence = Signal()


class ActivationDialog(QDialog):
    def __init__(self, client: LicenceClient, message: str = ""):
        super().__init__()
        self.client = client
        self.setWindowTitle("Sign in to NoMsindo"); self.setWindowIcon(app_icon()); self.setMinimumWidth(440)
        lay = QVBoxLayout(self); lay.setContentsMargins(26, 24, 26, 22); lay.setSpacing(8)
        head = QHBoxLayout(); ic = QLabel(); ic.setPixmap(brand_pixmap(44))
        t = QLabel("Sign in to NoMsindo"); t.setObjectName("appname"); t.setStyleSheet("font-size: 20px;")
        head.addWidget(ic); head.addSpacing(6); head.addWidget(t, 1); lay.addLayout(head)
        self.msg = QLabel(message or "Use the email and password your administrator gave you."); self.msg.setObjectName("muted"); self.msg.setWordWrap(True)
        lay.addWidget(self.msg)
        for label, attr, widget in (("SERVER ADDRESS", "server", QLineEdit(client.server or "https://")), ("EMAIL", "email", QLineEdit()),
                                    ("PASSWORD", "pw", QLineEdit())):
            c = QLabel(label); c.setObjectName("caps"); lay.addSpacing(2); lay.addWidget(c); lay.addWidget(widget); setattr(self, attr, widget)
        self.pw.setEchoMode(QLineEdit.Password)
        self.err = QLabel(""); self.err.setObjectName("err"); self.err.setWordWrap(True); lay.addWidget(self.err)
        row = QHBoxLayout(); trial = QPushButton("Start a free trial"); trial.setObjectName("plain")
        trial.clicked.connect(lambda: webbrowser.open(self.server.text().strip().rstrip("/") + "/signup"))
        self.go = QPushButton("Sign in"); self.go.setObjectName("plain"); self.go.setDefault(True); self.go.clicked.connect(self.submit)
        row.addWidget(trial); row.addStretch(1); row.addWidget(self.go); lay.addLayout(row)
        self.pw.returnPressed.connect(self.submit)

    def submit(self) -> None:
        self.err.setText(""); self.go.setEnabled(False); self.go.setText("Signing in...")
        QApplication.setOverrideCursor(Qt.WaitCursor); QApplication.processEvents()
        try:
            st = self.client.sign_in(self.server.text(), self.email.text().strip(), self.pw.text())
            if st.status == "ok":
                self.accept(); return
            self.err.setText(st.message)
        except LicenceError as e:
            self.err.setText(e.message)
        finally:
            QApplication.restoreOverrideCursor(); self.go.setEnabled(True); self.go.setText("Sign in")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME); self.setWindowIcon(app_icon())
        self.settings = Settings.load()
        self.dev_mode = os.environ.get("NOMSINDO_DEV") == "1"
        self.licence = LicenceClient()
        self.lic_widgets: list = []
        self.bus = Bus(); self.bus.licence.connect(self.on_licence_changed)
        self._usage = {"mic": 0.0, "speaker": 0.0}; self._usage_lock = threading.Lock()
        self._last = time.monotonic(); self._last_flush = time.monotonic(); self._last_refresh = 0.0
        self.mic = ChannelController(self.settings.mic, "mic", "mic")
        self.spk = ChannelController(self.settings.speaker, "speaker", "speaker")
        self.mic.other, self.spk.other = self.spk, self.mic
        self.ctrls = [self.mic, self.spk]

        root = Backdrop(); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        head = QHBoxLayout(); head.setContentsMargins(20, 14, 22, 12); head.setSpacing(0)
        ic = QLabel(); ic.setPixmap(brand_pixmap(46))
        names = QVBoxLayout(); names.setSpacing(0); names.setContentsMargins(0, 0, 0, 0)
        nm = QLabel("NoMsindo"); nm.setObjectName("appname"); tg = QLabel("VOICE ISOLATION"); tg.setObjectName("tagline")
        names.addWidget(nm); names.addWidget(tg)
        self.lic = QLabel(); self.lic.setObjectName("chip")
        self.pill = QLabel("ACTIVE"); self.pill.setObjectName("pill")
        head.addWidget(ic); head.addSpacing(12); head.addLayout(names); head.addStretch(1)
        head.addWidget(self.lic); head.addSpacing(10); head.addWidget(self.pill)
        outer.addLayout(head)

        body = QHBoxLayout(); body.setSpacing(0)
        side = QFrame(); side.setObjectName("sidebar"); side.setFixedWidth(92)
        sl = QVBoxLayout(side); sl.setContentsMargins(0, 12, 0, 12); sl.setSpacing(4)
        self.pages = QStackedWidget()
        routing = QWidget(); rl = QVBoxLayout(routing); rl.setContentsMargins(18, 16, 18, 16); rl.setSpacing(14)
        self.panels = [ChannelPanel(self.mic, "Microphone", "mic"), ChannelPanel(self.spk, "Speaker", "spk")]
        for p in self.panels:
            rl.addWidget(p, 1)
        self.pages.addWidget(self._scroll(routing))
        self.pages.addWidget(self._scroll(DevicesPage(self.mic, self.spk)))
        self.pages.addWidget(self._scroll(SettingsPage(self)))
        self.nav = []
        for i, (label, kind) in enumerate((("Audio\nRouting", "routing"), ("Devices", "devices"), ("Settings", "settings"))):
            b = QToolButton(); b.setObjectName("nav"); b.setText(label); b.setCheckable(True); b.setAutoExclusive(True)
            b.setIcon(nav_icon(kind)); b.setIconSize(b.iconSize() * 1.0); b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setFixedSize(92, 78); b.clicked.connect(lambda _, i=i: self.pages.setCurrentIndex(i)); sl.addWidget(b); self.nav.append(b)
        self.nav[0].setChecked(True)
        sl.addStretch(1)
        ver = QLabel(f"v{__version__}"); ver.setObjectName("muted"); ver.setAlignment(Qt.AlignCenter); sl.addWidget(ver)
        body.addWidget(side); body.addWidget(self.pages, 1); outer.addLayout(body, 1)

        sb = QFrame(); sb.setObjectName("statusbar"); sbl = QHBoxLayout(sb); sbl.setContentsMargins(18, 7, 12, 7)
        self.status = QLabel(); self.status.setObjectName("status"); self.status.setTextFormat(Qt.RichText)
        dl = QPushButton("VB-Audio"); dl.setObjectName("link"); dl.clicked.connect(lambda: webbrowser.open("https://vb-audio.com/Cable/"))
        sbl.addWidget(self.status, 1); sbl.addWidget(dl); outer.addWidget(sb)

        for c in self.ctrls:
            c.changed.connect(self.refresh_status)
        self.refresh_status()
        self.timer = QTimer(self); self.timer.timeout.connect(self._tick); self.timer.start(33)
        self._tray(); self.resize(840, 840); self.setMinimumSize(760, 620)
        self.update_licence_ui()
        self.lic_timer = QTimer(self); self.lic_timer.timeout.connect(self.check_licence); self.lic_timer.start(60_000)

    @staticmethod
    def _scroll(w: QWidget) -> QScrollArea:
        sa = QScrollArea(); sa.setWidgetResizable(True); sa.setFrameShape(QFrame.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); sa.setWidget(w)
        sa.viewport().setAutoFillBackground(False); w.setAutoFillBackground(False)
        return sa

    def showEvent(self, e) -> None:
        super().showEvent(e); dark_titlebar(self)

    # ---- state
    def set_option(self, attr: str, on: bool) -> None:
        setattr(self.settings, attr, on)
        if attr == "run_at_login":
            set_run_at_login(on)
        self.settings.save()

    def refresh_status(self) -> None:
        dot = lambda ok, warn=False: f"<span style='color:{MINT if ok else (AMBER if warn else RED)}'>●</span>"
        try:
            from .engine import FRAME
            eng_ok = FRAME == 480
        except Exception:
            eng_ok = False
        try:
            cable_ok = devices.virtual_cable_present()
        except Exception:
            cable_ok = False
        run = any(c.running for c in self.ctrls)
        self.status.setText(f"{dot(True) if run else dot(True, True)} {'Running' if run else 'Ready'} &nbsp;&nbsp;│&nbsp;&nbsp; "
                            f"{dot(eng_ok)} RNNoise engine {'OK' if eng_ok else 'error'} (10 ms chunks) &nbsp;&nbsp;│&nbsp;&nbsp; "
                            f"{dot(cable_ok)} VB-Audio cable {'connected' if cable_ok else 'not found'}")
        self.pill.setText(f"●  {'ACTIVE' if run else 'IDLE'}"); self.pill.setProperty("idle", not run)
        self.pill.style().unpolish(self.pill); self.pill.style().polish(self.pill)

    def _tick(self) -> None:
        now = time.monotonic(); dt = min(1.0, now - self._last); self._last = now
        for key, c in (("mic", self.mic), ("speaker", self.spk)):
            if c.running:
                with self._usage_lock:
                    self._usage[key] += dt
        if now - self._last_flush > 300:
            self._last_flush = now; self.flush_usage()
        if self.isVisible() and not self.isMinimized():
            for p in self.panels:
                p.tick()

    # ---- licence
    def update_licence_ui(self) -> None:
        if self.dev_mode:
            self.lic.setText("Developer mode"); text = "Developer mode: licence checks are off."; warn = False
        else:
            st = self.licence.state()
            if st.status == "ok":
                kind = "Trial" if st.plan == "trial" else "Subscription"
                self.lic.setText(f"{st.org_name}  ·  {kind}  ·  {st.days_left} day{'' if st.days_left == 1 else 's'} left")
                text = f"Signed in as {st.email} ({st.org_name}). {kind}, {st.days_left} days left."
            else:
                self.lic.setText("Not signed in"); text = st.message or "Not signed in."
            warn = st.status != "ok" or (st.plan == "trial" and st.days_left <= 3)
        self.lic.setProperty("warn", warn)
        self.lic.style().unpolish(self.lic); self.lic.style().polish(self.lic)
        for w in self.lic_widgets:
            w.setText(text)

    def ensure_licence(self) -> bool:
        """Block until licensed. Returns False if the user gives up."""
        if self.dev_mode:
            return True
        while True:
            st = self.licence.state()
            if st.status == "ok":
                self.update_licence_ui(); return True
            if st.status == "unconfigured":
                QMessageBox.critical(None, APP_NAME, st.message); return False
            for c in self.ctrls:
                c.stop()
            dlg = ActivationDialog(self.licence, st.message)
            dark_titlebar(dlg)
            if dlg.exec() != QDialog.Accepted:
                return False

    def check_licence(self) -> None:
        if self.dev_mode:
            return
        st = self.licence.state()
        if st.status != "ok":
            self.bus.licence.emit(); return
        if (st.needs_refresh or time.monotonic() - self._last_refresh > 6 * 3600) and time.monotonic() - self._last_refresh > 300:
            self._last_refresh = time.monotonic()
            def work():
                try:
                    self.licence.refresh()
                except LicenceError:
                    pass           # offline: keep running until the token's own expiry
                self.bus.licence.emit()
            threading.Thread(target=work, daemon=True).start()
        self.update_licence_ui()

    def on_licence_changed(self) -> None:
        self.update_licence_ui()
        if self.licence.state().status != "ok":
            if not self.ensure_licence():
                self.quit()

    def sign_out(self) -> None:
        if QMessageBox.question(self, APP_NAME, "Sign out of NoMsindo on this computer? Audio cleaning will stop.") == QMessageBox.Yes:
            for c in self.ctrls:
                c.stop()
            self.flush_usage(wait=True)
            self.licence.sign_out()
            if not self.ensure_licence():
                self.quit()

    def flush_usage(self, wait: bool = False) -> None:
        with self._usage_lock:
            mic, spk = int(self._usage["mic"]), int(self._usage["speaker"])
            self._usage["mic"] -= mic; self._usage["speaker"] -= spk
        if (mic <= 0 and spk <= 0) or self.dev_mode:
            return
        def work():
            if not self.licence.report_usage(mic, spk):      # put it back and retry next time
                with self._usage_lock:
                    self._usage["mic"] += mic; self._usage["speaker"] += spk
        t = threading.Thread(target=work, daemon=True); t.start()
        if wait:
            t.join(3)

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
        self.flush_usage(wait=True)
        self.settings.save(); self.tray.hide(); QApplication.quit()


def run() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE); app.setWindowIcon(app_icon()); app.setQuitOnLastWindowClosed(False)
    w = MainWindow()
    if not w.ensure_licence():
        return 0
    if "--minimized" not in sys.argv and not w.settings.start_minimized:
        w.show()
    QTimer.singleShot(400, w.auto_start)
    return app.exec()
