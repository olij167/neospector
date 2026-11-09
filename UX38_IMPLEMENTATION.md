# Neospector UX38 — Signed Updates & Owner Publication Companion

**Version:** 0.7.22-ux38  
**Platform:** Linux x86-64 Xorg evaluation candidate  
**Baseline:** UX37 (0.7.21-ux37), audiovisual engine and project format unchanged.

## What the instrument does

- Starts a **non-blocking, silent HTTPS signed-feed check** shortly after the normal welcome/workspace appears (enabled by default; can be disabled in Preferences → General).
- File → **Check for Updates…**, Welcome → **Check for Updates**, and Preferences → General → **Check for updates now** use the same controller.
- Only reports a release if its **Ed25519 signed manifest** verifies against the pinned public key, targets Linux x86-64 and has a version newer than the running application.
- Presents the version and release notes. Clicking **Download verified update** downloads to the user cache; signature, signed archive size, and SHA-256 are checked. Download never installs anything.
- Clicking **Install & restart** requires confirmation, a clean instrument close and no pending unsaved changes or capture. A separate installer waits for the app to exit, verifies the archive and internal file manifest again, then installs into `~/.local/share/omne/neospector/versions/<version>`.
- The original ZIP extraction is never overwritten. A managed launcher and desktop entry are created at `~/.local/share/omne/neospector/launch.sh` and `~/.local/share/applications/neospector.desktop`. Subsequent starts from the **managed launcher** use the current installed version.
- Profile metadata is backed up before a managed version changes. Original media remains in place. A previous managed version remains available for rollback (`tools/rollback_update.py --yes`).
- No update is auto-installed and the update checker never activates camera or microphone.

## Publisher trust and prerequisites

The **public ZIP contains only `updates/public.pem`**, the trusted Ed25519 verification key. **It must never contain `owner-signing.pem`.** The owner companion is separate and its private signing key must be stored privately.

The publisher uses OpenSSL for signing; the app uses OpenSSL for signature verification. No third-party Python crypto library is installed into the Neospector runtime. There are no downloaded scripts executed before a manifest and ZIP have been verified.

The intended default feed is `https://omne.space/neospector/updates/stable.json`. **This is a proposed destination, not a verified live endpoint.** Hosting must be configured to serve `stable.json` and the named ZIP from the same HTTPS directory. You can instead change the signed feed URL in Preferences → General. In either case the pinned signing key remains the trust anchor. An unprovisioned/offline feed does not interrupt startup.

## Owner publication flow

1. In the separately delivered owner companion, select a Neospector release ZIP, your private signing key and release notes.
2. Prepare the release. The companion generates a signed `stable.json` plus the unmodified ZIP in a staging directory.
3. Upload the ZIP **first** and `stable.json` **last** to your HTTPS release folder, using confirmed SSH credentials, an existing rclone configuration, or manual upload. No hosting credentials are bundled.
4. Confirm `https://<host>/<folder>/stable.json` is accessible over HTTPS and points to the release ZIP at the same directory. On startup or manual check, clients with a trusted older version will be offered the update.
5. Never publish the private `.pem` key, project backups, owner-source credentials or a local profile. A publisher key leak requires a separately planned trust-key rotation and client redistribution.

## Safety/rollback limits

- The managed version pointer is updated only after archive signature, SHA-256, extraction safety, and internal manifest checks pass.
- Immediate failed startup restores the prior pointer if one exists. The previous release directory is not deleted.
- This is a **Linux x86-64** updater only. Windows/macOS installers and public endpoint provisioning remain out of scope.
- Owner testing must cover the real HTTPS route, Zorin's OpenSSL availability, an actual signed update to a later version, and installed camera/audio and export workflows before public release.
