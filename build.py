import sys
import subprocess

if sys.platform != "win32":
    raise SystemExit("Run this build script on Windows.")
cmd = [
    sys.executable, "-m", "nuitka",
    "--onefile",
    "--enable-plugin=pyside6",
    "--windows-console-mode=disable",
    "--output-dir=dist",
    "--output-filename=LANMessenger.exe",
    "--include-package=lanmessenger",
    "src/lanmessenger/__main__.py",
]
raise SystemExit(subprocess.call(cmd))
