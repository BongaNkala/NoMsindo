# PyInstaller spec -> dist/NoMsindo/NoMsindo.exe   (build on Windows: pyinstaller build.spec)
import importlib.util, os
from PyInstaller.utils.hooks import collect_data_files

spec = importlib.util.find_spec("pyrnnoise")
rn_dir = list(spec.submodule_search_locations)[0]
binaries = [(os.path.join(rn_dir, "rnnoise.dll"), "nomsindo/lib")]
datas = collect_data_files("_sounddevice_data") + [("assets", "assets")]  # PortAudio + logo/icons

a = Analysis(["main.py"], binaries=binaries, datas=datas,
             excludes=["matplotlib", "tkinter", "scipy", "PySide6.QtWebEngineCore", "PySide6.QtQml"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="NoMsindo", console=False,
          icon="assets/nomsindo.ico")
coll = COLLECT(exe, a.binaries, a.datas, name="NoMsindo")
