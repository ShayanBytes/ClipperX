# Windows installer privilege fix — v2.0.1

## Fixed failure

Electron Builder 24 downloaded `winCodeSign-2.6.0.7z` and attempted to unpack two macOS compatibility symlinks. Standard Windows accounts without Developer Mode or administrator symlink privileges failed with:

`ERROR: Cannot create symbolic link: A required privilege is not held by the client.`

The application had already compiled successfully. The failure was in optional executable resource editing, not the ClipperX frontend, backend or video engine.

## v2.0.1 solution

The Windows build now sets:

- `win.signAndEditExecutable: false`
- `CSC_IDENTITY_AUTO_DISCOVERY=false`

This produces an unsigned NSIS installer without invoking the `winCodeSign` resource-editing package, so the installer can be built from a normal command prompt without Windows symlink privileges.

The package also includes valid `description` and `author` metadata, removing the earlier warnings.

## Build

Double-click `CREATE INSTALLABLE EXE.bat` again. The resulting installer will be under `release` as:

`ClipperX-Setup-2.0.1-x64.exe`

Because this is a local unsigned build, Windows SmartScreen may show a warning. Choose **More info → Run anyway**. Code signing can be enabled later only when a real Windows signing certificate is configured.

If a previous failed cache remains, delete:

`%LOCALAPPDATA%\electron-builder\Cache\winCodeSign`

This cache deletion should not normally be necessary in v2.0.1 because the code-signing helper is no longer requested.
