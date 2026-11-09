# Native release qualification — mandatory before making downloads visible

The CI workflow provides **build candidates**, not tested release ports. A passing packaging step is not a substitute for real hardware acceptance.

## All platforms

- Installer wizard starts and completes; creates launch/uninstall entry (macOS PKG may use the native installer wizard); upgrade retains user preferences, projects and source media.
- Application opens on a clean user profile, changes through all six Funk themes, and imports local pictures, audio and video.
- Effects racks A/B/Output/Transition, editable groups, per-parameter sliders/numeric values and module-wide audio reactions are persistent and responsive.
- A/B ping-pong hold/fade, active camera/mic switching and sound queue work.
- Camera capture, microphone capture, screen/window capture and per-application audio are evaluated separately; unsupported capabilities are shown as unsupported, not claimed as working.
- Recording and H.264/AAC export, frame continuity, file path quoting, native file drops and shutdown are tested.
- No private signing key, CI token, project data or runtime cache is included in artifacts; archive checksums match and uninstall leaves project media intact.

## Windows x64

- Installer is Inno Setup `Neospector_0.7.25-ux41_windows-x64_Setup.exe`; shortcuts, uninstall and optional desktop icon work.
- Portable ZIP and installed executable start without a terminal; verify bundled FFmpeg/FFprobe and Python dependencies.
- Obtain Authenticode signing for the Setup EXE and verify its signer on a clean machine. Unsigned CI artifacts stay private/candidate.

## macOS Intel and Apple Silicon

- Build each on its native GitHub runner. DMG and PKG installation paths work; use Developer ID Application/Installer certificates and notarise/staple.
- Test Camera/Microphone/Screen Recording permission prompts, FFmpeg helper signing, Gatekeeper and Rosetta expectations.
- Ensure software releases are not offered to other architectures until validated; test exports and source discovery on each architecture.

## Linux Xorg x64

- Test `Neospector_0.7.25-ux41_linux-x64.deb` in Zorin Software Installer, first-launch provisioning, profiles, multiple users, rollback and removal.
- Ensure Python 3.12 bundled wheel path (or a supported online Python dependency path), TkDnD, FFmpeg and X11 capture behave as accepted in the standalone UX41 ZIP.

## Signed updates

UX41's pinned Ed25519 feed currently supports **Linux x86-64 ZIP updates only**. Do not turn on native automatic updates until platform-specific manifests, signed installer validation and user-approved native handoff are implemented, reviewed and tested on Windows/macOS.
