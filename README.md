# NoMsindo

Real-time voice isolation for calls on Windows, modelled on IRIS Clarity's public feature set.
Removes background noise from your microphone *and* from the audio you hear, and works with any
call app (Teams, Zoom, Genesys, Webex, browsers...).

## How it works
```
Mic -> NoMsindo (RNNoise, 10 ms frames) -> virtual cable A -> call app "microphone"
Call app "speaker" -> virtual cable B -> NoMsindo -> your headphones
```
Windows needs a virtual audio device for this. v0.1 uses the free **VB-Audio Virtual Cable (A+B)**
(https://vb-audio.com/Cable/). A custom signed driver is a later phase.

Setup: install VB-Cable A+B, open NoMsindo, press Start on both cards, then in your call app set
Microphone = `CABLE-A Output` and Speaker = `CABLE-B Input`.

## Develop
```
pip install -r requirements.txt
pip install --no-deps pyrnnoise      # ships the RNNoise library
python -m pytest
python main.py                        # run the app
python -m nomsindo.cli noisy.wav clean.wav --strength 100 [--strong]
```

## Build the installer (Windows)
`pyinstaller build.spec` then `iscc installer.iss` -> `Output/NoMsindo-Setup.exe`.
The GitHub Actions workflow does this on every push and uploads the installer as an artifact.

## Interface
Follows the supplied reference screens: left sidebar (Audio Routing, Devices, Settings), a panel per
audio path with live waveform (raw input left of the playhead, cleaned audio right), VU meters,
Noise Removal Strength slider, Standard/Strong mode and ACTIVE toggle, and a status bar.
Logo and icon live in `assets/`.

## SaaS server
`server/` holds the licensing server and admin portal (accounts, trial, seats, devices, usage).
See `server/README.md`. Run `python -m server.manage init` once and commit `assets/license_public.pem`
before building the installer. For development without a server, set `NOMSINDO_DEV=1`.

## Status
- Engine, routing, UI, installer scripts, licensing client and server: written. Engine, server and licence client are unit-tested on Linux (26 tests); client checked against the real server over HTTP.
- Not yet tested on a real Windows machine with live audio devices.
- Roadmap: spectrogram view, auto-select devices, licence/trial, admin portal, Chrome extension, SDK,
  stronger model (DeepFilterNet via ONNX), custom virtual audio driver.
