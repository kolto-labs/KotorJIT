<#
.SYNOPSIS
Write a native-Windows KotorJIT receipt after one physical F12 test.

.DESCRIPTION
Run this on the Windows PC where you just played, after you:
  1. installed with scripts\install\windows\Install-KotorJIT.ps1,
  2. started the game from its own launcher or exe (not Wine, not a VM),
  3. pressed F12 on the physical keyboard in game and saw the Lua console or not,
  4. quit the game.

The script reads the game folder and kotorjit.log. It records the OS build,
the CPU and any x86 translation, the exe sha, the proxy and DLL shas, the log
hash, the runtime's own host and GL lines, and the F12 result you report.

The F12 result is your word: the script cannot see the screen.

What the log lines are worth. KotorJIT appends one block per game start
to kotorjit.log. The receipt reads only the newest block, which starts
at the last "[idle] KotorJIT <version> starting" line. The runtime writes
that banner before it loads any script. In that block, the runtime writes one
"kp-session=<id> start" line when its overlay attaches. On the first rendered
frame it adds one host line and one gl line with the same random id. These
lines skip the log sink that scripts write through, so they carry no
"<level>:" token. The runtime also escapes line breaks and other control
characters in every message. So a script's print, kp.diagnostic or error text
stays on one line and cannot start a banner, host or gl line. A DLL with that
escaping writes "log=esc1" in its host line. A host line without it came from
an older DLL, and the receipt refuses it. The receipt
splits the log only where the runtime ends a line, and refuses a line with a
carriage return inside a line of the newest block. A block with a second start, host or gl line, a
line from another run, or a line in any other shape is refused.

This is supporting evidence, not proof:
  - The escaping is only in a kotorjit.dll built with it. An older DLL let a
    script write a whole fake block, banner included, through print. The
    log=esc1 token refuses the host line an older DLL writes itself. It does
    not stop a script that writes the token too.
  - The receipt records the kotorjit.dll sha256. The validator only checks
    that it is a sha256. It does not check which build it is: no list of
    release DLL shas exists.
  - A script can still write to kotorjit.log with Lua's io library. The
    runtime does not stop that.
  - Wine is detected by one signal: ntdll exports wine_get_version only under
    Wine. Some patched Wine builds hide that export. The OS build cannot help,
    because Wine reports whatever Windows version its prefix is set to. The
    receipt also records whether HKLM\Software\Wine exists. The validator
    refuses Mesa, Linux driver and macOS GL names. A Wine run on a vendor
    driver whose GL strings match Windows can still pass.
  - tools\platform_receipt_test.py --validate checks the receipt against the
    lines it quotes. Add --log kotorjit.log to re-check against the log.

RUNNING IT
Windows blocks unsigned scripts by default. Allow this one PowerShell window
to run scripts, then unblock the downloaded file:

    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    Unblock-File .\scripts\receipts\windows-native-receipt.ps1

-Scope Process lasts only until you close that window. It changes no system
setting. The receipt is written under %LOCALAPPDATA%\KotorJIT\receipts
unless you pass -OutFile. That folder needs no admin rights, even when the
game is in Program Files.

Targets Windows PowerShell 5.1.

.EXAMPLE
.\windows-native-receipt.ps1 -GameDir 'C:\GOG Games\Star Wars - KotOR' -F12Result pass
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$GameDir,
    [Parameter(Mandatory = $true)][ValidateSet('pass', 'fail', 'not-run')][string]$F12Result,
    [string]$OutFile = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Get-Sha256OrNull([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

# --- BEGIN session parser ------------------------------------------------------
# tools\platform_receipt_test.py session_evidence() is the same logic in
# Python; its parity test dot-sources this block and compares the two on the
# fixture logs. Change both or neither.
# Line shapes: src\devtools\overlay.cpp writes the kp-session lines through
# Runtime::log ("[<phase>] <body>\n"); script output always carries
# "[<phase>] <level>: ". Runtime::log escapes "\r" and "\n" in every message,
# and writes the banner at the idle phase, before any script loads. The host
# line carries log=esc1, which only a DLL with that escaping writes; a host
# line without it ($PreEscapeHostPattern) is refused with its own message.
# -cmatch: case-sensitive, whole line.
$BannerPattern = '^\[idle\] (?:KotorJIT|KotorPhasor) \S+ starting \([a-z-]+ role\)$'
$SessionPattern = '^\[[a-z-]+\] kp-session=([0-9a-f]{32}) start$'
$HostPattern = '^\[[a-z-]+\] kp-session=([0-9a-f]{32}) log=esc1 host: wine=(yes|no) wine_version=(\S+) os=(\d+)\.(\d+)\.(\d+) overlays=(\S+)$'
$PreEscapeHostPattern = '^\[[a-z-]+\] kp-session=([0-9a-f]{32}) host: wine=(yes|no) wine_version=(\S+) os=(\d+)\.(\d+)\.(\d+) overlays=(\S+)$'
$GlPattern = '^\[[a-z-]+\] kp-session=([0-9a-f]{32}) gl: vendor="([^"]*)" renderer="([^"]*)" version="([^"]*)"$'

function Split-LogText([string]$Text) {
    # Lines as Runtime::log ends them: at "\n". A "\r" just before it (an
    # editor saving CRLF) is dropped. Any other "\r" stays in the line, where
    # Get-SessionEvidence refuses it. Get-Content would split there instead.
    $lines = New-Object System.Collections.ArrayList
    foreach ($l in ($Text -split "`n")) {
        if ($l.EndsWith("`r")) { $l = $l.Substring(0, $l.Length - 1) }
        [void]$lines.Add($l)
    }
    if (($lines.Count -gt 0) -and ($lines[$lines.Count - 1] -eq '')) { $lines.RemoveAt($lines.Count - 1) }
    return , ([string[]]$lines.ToArray())
}

function Get-SessionEvidence([string[]]$Lines) {
    $ev = [ordered]@{
        session_start_line = $null; session_id = $null; host_line = $null; gl_line = $null
        session_marker_lines = 0; host_like_lines = 0; gl_like_lines = 0; problems = @()
    }
    $problems = New-Object System.Collections.ArrayList
    $all = @($Lines | Where-Object { $null -ne $_ })
    $start = -1
    for ($i = 0; $i -lt $all.Count; $i++) { if ($all[$i] -cmatch $BannerPattern) { $start = $i } }
    if ($start -lt 0) {
        [void]$problems.Add('no KotorJIT start banner in the log')
        $ev.problems = $problems.ToArray()
        return $ev
    }
    $ev.session_start_line = $all[$start]
    $starts = New-Object System.Collections.ArrayList
    $hosts = New-Object System.Collections.ArrayList
    $gls = New-Object System.Collections.ArrayList
    $ids = New-Object System.Collections.ArrayList
    $n = 0
    for ($i = $start + 1; $i -lt $all.Count; $i++) {
        $n++
        if ($all[$i].Contains("`r")) {
            [void]$problems.Add("session line $n has a carriage return inside it; the runtime never writes one")
        }
        # Each piece of a line split by "\r" still counts as a claim.
        foreach ($line in ($all[$i] -split "`r")) {
            if ($line.Contains('kp-session=')) {
                $ev.session_marker_lines++
                $id = $null
                if ($line -cmatch $SessionPattern) { $id = $Matches[1]; [void]$starts.Add(@{ n = $n; line = $line }) }
                elseif ($line -cmatch $HostPattern) { $id = $Matches[1] }
                elseif ($line -cmatch $GlPattern) { $id = $Matches[1] }
                if (($null -eq $id) -and ($line -cmatch $PreEscapeHostPattern)) {
                    [void]$problems.Add("session line $n is a host line without log=esc1: the kotorjit.dll that wrote it does not escape script text")
                }
                elseif ($null -eq $id) { [void]$problems.Add("session line $n mentions kp-session= but is not a runtime line") }
                elseif (-not $ids.Contains($id)) { [void]$ids.Add($id) }
            }
            if ($line.Contains('host: wine=')) { $ev.host_like_lines++; [void]$hosts.Add(@{ n = $n; line = $line }) }
            if ($line.Contains('gl: vendor=')) { $ev.gl_like_lines++; [void]$gls.Add(@{ n = $n; line = $line }) }
        }
    }
    if ($starts.Count -ne 1) { [void]$problems.Add("$($starts.Count) kp-session start lines in the current session, want 1") }
    if ($ids.Count -gt 1) { [void]$problems.Add("$($ids.Count) different session ids in the current session") }
    if ($hosts.Count -ne 1) { [void]$problems.Add("$($hosts.Count) host lines in the current session, want 1") }
    if ($gls.Count -ne 1) { [void]$problems.Add("$($gls.Count) gl lines in the current session, want 1") }
    if ($problems.Count -eq 0) {
        if (-not ($hosts[0].line -cmatch $HostPattern)) { [void]$problems.Add("the host line is not in the runtime's anchored format") }
        if (-not ($gls[0].line -cmatch $GlPattern)) { [void]$problems.Add("the gl line is not in the runtime's anchored format") }
        if (-not (($starts[0].n -lt $hosts[0].n) -and ($starts[0].n -lt $gls[0].n))) {
            [void]$problems.Add('host or gl line comes before the session start line')
        }
    }
    if ($problems.Count -eq 0) {
        [void]($starts[0].line -cmatch $SessionPattern)
        $ev.session_id = $Matches[1]
        $ev.host_line = $hosts[0].line
        $ev.gl_line = $gls[0].line
    }
    $ev.problems = $problems.ToArray()
    return $ev
}
# --- END session parser --------------------------------------------------------

$GameDir = (Resolve-Path -LiteralPath $GameDir).Path
if (-not $OutFile) {
    # Not the game folder: under Program Files that write fails without
    # elevation, after all the work is done.
    $base = $env:LOCALAPPDATA
    if (-not $base) { $base = [System.IO.Path]::GetTempPath() }
    $dir = [System.IO.Path]::Combine($base, 'KotorJIT', 'receipts')
    [void][System.IO.Directory]::CreateDirectory($dir)
    $OutFile = Join-Path $dir ('kotorjit-receipt-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '.json')
}

# --- OS -------------------------------------------------------------------
$cv = Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
$ubr = $null
if ($cv.PSObject.Properties.Name -contains 'UBR') { $ubr = [string]$cv.UBR }
$displayVersion = $null
if ($cv.PSObject.Properties.Name -contains 'DisplayVersion') { $displayVersion = [string]$cv.DisplayVersion }
$osv = [Environment]::OSVersion.Version
$os = [ordered]@{
    family          = 'windows'
    product         = [string]$cv.ProductName
    display_version = $displayVersion
    version         = "$($osv.Major).$($osv.Minor)"
    build           = [string]$cv.CurrentBuildNumber
    ubr             = $ubr
}
# A second Wine signal, independent of the runtime's: every Wine prefix has
# this key. It only means something when this script runs in the same prefix.
$wineRegistry = 'no'
if (Test-Path -LiteralPath 'HKLM:\Software\Wine') { $wineRegistry = 'yes' }

# --- CPU and translation --------------------------------------------------
# The game is 32-bit x86. On x64 Windows it runs under WOW64 with no
# translation; on ARM64 Windows it runs under x86 emulation, which a receipt
# must say out loud. IsWow64Process2 reports the real machine even when this
# PowerShell is itself an emulated x64 process, where PROCESSOR_ARCHITECTURE
# says AMD64. It needs Windows 10 1709 or later; older systems fall back to
# Win32_Processor, then the environment.
$osArch = $env:PROCESSOR_ARCHITECTURE
if ($env:PROCESSOR_ARCHITEW6432) { $osArch = $env:PROCESSOR_ARCHITEW6432 }
$detectedBy = 'environment'
$cpuName = $null
$cpuArchCode = $null
try {
    $proc = Get-CimInstance -ClassName Win32_Processor | Select-Object -First 1
    $cpuName = $proc.Name
    $cpuArchCode = $proc.Architecture
} catch { $cpuName = $null }
$nativeMachine = $null
try {
    Add-Type -Namespace KotorJITReceipt -Name Native -ErrorAction Stop -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)]
public static extern bool IsWow64Process2(System.IntPtr process, out ushort processMachine, out ushort nativeMachine);
[System.Runtime.InteropServices.DllImport("kernel32.dll")]
public static extern System.IntPtr GetCurrentProcess();
'@
    [UInt16]$processMachine = 0
    [UInt16]$machine = 0
    if ([KotorJITReceipt.Native]::IsWow64Process2([KotorJITReceipt.Native]::GetCurrentProcess(), [ref]$processMachine, [ref]$machine)) {
        $nativeMachine = $machine
    }
} catch { $nativeMachine = $null }
if ($null -ne $nativeMachine) {
    $detectedBy = 'IsWow64Process2'
    switch ([int]$nativeMachine) {
        0xAA64 { $osArch = 'ARM64' }
        0x8664 { $osArch = 'AMD64' }
        0x014C { $osArch = 'x86' }
        default { $osArch = ('machine-0x{0:X4}' -f [int]$nativeMachine) }
    }
} elseif ($cpuArchCode -eq 12) {
    $detectedBy = 'Win32_Processor'
    $osArch = 'ARM64'
}
$translation = 'none'
if ($osArch -eq 'ARM64') { $translation = 'x86-on-arm64-emulation' }
$cpu = [ordered]@{ arch = $osArch; name = $cpuName; translation = $translation; detected_by = $detectedBy }

# --- game and runtime files ------------------------------------------------
$exe = $null
foreach ($n in @('swkotor.exe', 'swkotor2.exe')) {
    $p = Join-Path $GameDir $n
    if (Test-Path -LiteralPath $p -PathType Leaf) { $exe = $p; break }
}
if (-not $exe) { throw "no swkotor.exe or swkotor2.exe in $GameDir" }
$exeSha = Get-Sha256OrNull $exe
$manifestPath = [System.IO.Path]::Combine($GameDir, 'kotorjit', 'install-manifest.json')
$legacyManifestPath = [System.IO.Path]::Combine($GameDir, 'kotorphasor', 'install-manifest.json')
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf) -and (Test-Path -LiteralPath $legacyManifestPath -PathType Leaf)) {
    $manifestPath = $legacyManifestPath
}
$build = $null
$method = 'proxy'
if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    $m = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($m.PSObject.Properties['game'] -and $m.game.PSObject.Properties['build']) { $build = $m.game.build }
    if ($m.PSObject.Properties['method'] -and ($m.method -is [string]) -and $m.method) { $method = $m.method }
}
$game = [ordered]@{
    exe_name         = (Split-Path -Leaf $exe)
    exe_sha256       = $exeSha
    # A PE is a single image: container and slice are the same bytes. The
    # fields exist so a Mac receipt (fat container, one slice) fits the schema.
    container_sha256 = $exeSha
    slice_sha256     = $exeSha
    build            = $build
}
if (($method -eq 'inject') -or ($method -eq 'launcher')) {
    $runtime = [ordered]@{
        method                  = $method
        kphasor_dll_sha256      = Get-Sha256OrNull (Join-Path $GameDir 'kotorjit.dll')
        proxy_binkw32_sha256    = $null
        real_binkw32_sha256     = Get-Sha256OrNull (Join-Path $GameDir 'binkw32.dll')
        launcher_exe_sha256     = Get-Sha256OrNull (Join-Path $GameDir 'kotorjit-launch.exe')
        install_manifest_sha256 = Get-Sha256OrNull $manifestPath
    }
} else {
    $runtime = [ordered]@{
        method                  = $method
        kphasor_dll_sha256      = Get-Sha256OrNull (Join-Path $GameDir 'kotorjit.dll')
        proxy_binkw32_sha256    = Get-Sha256OrNull (Join-Path $GameDir 'binkw32.dll')
        real_binkw32_sha256     = Get-Sha256OrNull (Join-Path $GameDir 'binkw32_real.dll')
        launcher_exe_sha256     = $null
        install_manifest_sha256 = Get-Sha256OrNull $manifestPath
    }
}

# --- the runtime's own view --------------------------------------------------
$logPath = Join-Path $GameDir 'kotorjit.log'
if (-not (Test-Path -LiteralPath $logPath -PathType Leaf)) { throw "no kotorjit.log in $GameDir; did the game start with KotorJIT?" }
# Read the bytes as they are: Get-Content would split a line at a lone "\r".
# FileShare.ReadWrite, as Get-Content does, in case the game is still open.
$logStream = New-Object System.IO.FileStream($logPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
try {
    $logReader = New-Object System.IO.StreamReader($logStream, (New-Object System.Text.UTF8Encoding $false), $true)
    $logText = $logReader.ReadToEnd()
} finally { $logStream.Dispose() }
$ev = Get-SessionEvidence (Split-LogText $logText)
$hostInfo = [ordered]@{ wine = $null; wine_version = $null; log_os = $null; overlays = $null; wine_registry = $wineRegistry }
if ($ev.host_line -and ($ev.host_line -cmatch $HostPattern)) {
    $hostInfo.wine = $Matches[2]
    $hostInfo.wine_version = $Matches[3]
    $hostInfo.log_os = "$($Matches[4]).$($Matches[5]).$($Matches[6])"
    $hostInfo.overlays = $Matches[7]
}
$gl = [ordered]@{ vendor = $null; renderer = $null; version = $null }
if ($ev.gl_line -and ($ev.gl_line -cmatch $GlPattern)) {
    $gl.vendor = $Matches[2]; $gl.renderer = $Matches[3]; $gl.version = $Matches[4]
}
$log = [ordered]@{
    sha256               = Get-Sha256OrNull $logPath
    bytes                = (Get-Item -LiteralPath $logPath).Length
    session_start_line   = $ev.session_start_line
    session_id           = $ev.session_id
    host_line            = $ev.host_line
    gl_line              = $ev.gl_line
    session_marker_lines = $ev.session_marker_lines
    host_like_lines      = $ev.host_like_lines
    gl_like_lines        = $ev.gl_like_lines
    problems             = $ev.problems
}

$receipt = [ordered]@{
    schema       = 'kotorphasor.native-receipt/v1'
    kind         = 'windows-native'
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
    os           = $os
    cpu          = $cpu
    host         = $hostInfo
    game         = $game
    runtime      = $runtime
    gl           = $gl
    log          = $log
    f12          = [ordered]@{ result = $F12Result; method = 'physical-keyboard'; attested_by = 'user' }
}
# BOM-less UTF-8: Windows PowerShell 5.1's Set-Content -Encoding UTF8 adds a
# BOM. .NET resolves a relative path against the process directory, not the
# PowerShell location, so make it absolute first.
$OutFile = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutFile)
$json = $receipt | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText($OutFile, $json, (New-Object System.Text.UTF8Encoding $false))
Write-Output "receipt written: $OutFile"
foreach ($p in $ev.problems) { Write-Warning "kotorjit.log: $p" }
if ($wineRegistry -eq 'yes') { Write-Warning 'HKLM\Software\Wine exists: this is a Wine prefix, not a native receipt' }
if ($hostInfo.wine -and ($hostInfo.wine -ne 'no')) { Write-Warning 'the log says wine=yes; this is not a native receipt' }
if (-not $ev.host_line) {
    Write-Warning ('no usable host line in the newest session of kotorjit.log. The runtime writes it ' +
        'on the first frame the game draws with KotorJIT loaded, not on F12. Start the game, ' +
        'reach the main menu, quit, and run this again.')
}
