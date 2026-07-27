# ClipperX Desktop

ClipperX v0.3 opens in its own Electron window, not a browser tab.

## Run
```bash
npm install
npm run doctor
pip install -r requirements.txt
npm run desktop
```

## Build the installable Windows EXE

Double-click `CREATE INSTALLABLE EXE.bat`, or run:

```bat
npm install
npm run desktop:installer
```

The NSIS installer is written to `release/` as `ClipperX-Setup-0.4.0-x64.exe`. It creates Start Menu and desktop shortcuts. The installed program always opens in its own rounded Electron window, never in a browser. FFmpeg, FFprobe and Python must be on PATH.

## If the engine reports a missing module

Use **Details & fix → Repair engine** inside ClipperX. For example, `No module named 'cv2'` is repaired by installing the requirements containing OpenCV. The same diagnostics cover missing YOLO, Whisper, MediaPipe, scene detection, SciPy, SoundFile, FFmpeg, disk space, memory, permissions, and first-run model downloads.

The installer builder now runs `npm run setup:engine` before diagnostics and tests, preventing a broken installer from being produced silently.

## Hermes Python conflict

If the environment contains `C:\Users\...\hermes\hermes-agent\venv\Scripts\python.exe`, ClipperX now ignores it. That private agent environment does not provide pip and must not be used as the video engine. ClipperX instead checks the Windows `py` launcher, normal Python 3.11 installations, common installation folders, and PATH. It saves the selected absolute interpreter in `.clipperx-python.json` so setup, diagnostics, tests, the backend, and the installed app all use the same Python.
