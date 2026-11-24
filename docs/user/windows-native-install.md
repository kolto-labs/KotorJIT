# Install on Windows (PowerShell)

This page covers the two PowerShell scripts for a native Windows install:

- `scripts\install\windows\Install-Hyperstim.ps1` installs or removes Hyperstim.
- `scripts\receipts\windows-native-receipt.ps1` writes a receipt after one test run.

The Linux and Wine flow is in [install.md](install.md).

## Let PowerShell run the scripts

Windows blocks unsigned scripts by default. It also marks downloaded files as coming from the internet. Open PowerShell in the Hyperstim folder and run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
Get-ChildItem -Recurse .\scripts, .\build | Unblock-File
```

`-Scope Process` lasts until you close that window. It does not change any system setting.

If the game is under `Program Files`, open PowerShell with "Run as administrator".

## Install, check, remove

```powershell
.\scripts\install\windows\Install-Hyperstim.ps1 -GameDir 'C:\GOG Games\Star Wars - KotOR' -SourceDir .\build
.\scripts\install\windows\Install-Hyperstim.ps1 -GameDir 'C:\GOG Games\Star Wars - KotOR' -Action Status
.\scripts\install\windows\Install-Hyperstim.ps1 -GameDir 'C:\GOG Games\Star Wars - KotOR' -Action Uninstall
```

Install refuses a game exe or `binkw32.dll` it does not recognise. It copies only the address table for your build.

Uninstall reads `hyperstim\install-manifest.json`. It refuses the whole manifest, and removes nothing, if:

- a path is rooted
- a path has a `.` or `..` part
- a path points outside the game folder
- a path names a file the installer never writes
- a file is listed twice
- `binkw32.dll` is not listed exactly once
- a value is a list or number where the installer wrote text
- a folder it would delete from is a junction or symbolic link

It restores `binkw32.dll` first, from the backup. If the backup is gone, it uses `binkw32_real.dll`, but only when that file still matches the original. It deletes files one at a time and never deletes a folder with its contents. Your scripts and `hyperstim.log` stay.

## Write a receipt

Start the game, reach the main menu, press F12 on the keyboard, then quit. Then run:

```powershell
.\scripts\receipts\windows-native-receipt.ps1 -GameDir 'C:\GOG Games\Star Wars - KotOR' -F12Result pass
```

Use `fail` if the console did not open. The receipt goes to `%LOCALAPPDATA%\Hyperstim\receipts\` unless you pass `-OutFile`.

Check it, with the log, on any machine with Python:

```sh
python3 tools/platform_receipt_test.py --validate receipt.json --log hyperstim.log
```

## What a receipt shows

A receipt is supporting evidence that a run was native Windows. It is not proof.

- It reads only the newest game start in `hyperstim.log`. It needs exactly one host line and one GL line there, written by the runtime with that run's random id.
- Wine shows up through one runtime signal: an ntdll export only Wine has. Some patched Wine builds hide it. The receipt also checks for the `HKLM\Software\Wine` registry key, which only helps when the receipt script runs inside that same Wine prefix.
- GL names from Mesa, Linux drivers, macOS or VM adapters are refused. A Wine run on an NVIDIA driver reports the same GL names as Windows, so it can still pass.
- The runtime writes line breaks in script text as `\n`, so a script's `print` stays on one line. A `hyperstim.dll` built before that change let a script fake a whole game start this way.
- A `hyperstim.dll` with the change writes `log=esc1` in its host line. The receipt refuses a host line without it, so an older DLL's own lines fail. A script can still write the token itself.
- The receipt records the hash of `hyperstim.dll`. The validator does not check which build that hash belongs to. No list of release hashes exists yet.
- A Lua script can still write to `hyperstim.log` with Lua's `io` library, and so fake these lines.
