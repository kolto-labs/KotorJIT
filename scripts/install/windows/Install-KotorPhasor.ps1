<#
.SYNOPSIS
Install KotorPhasor into a native Windows game folder, or take it back out.

.DESCRIPTION
The Windows twin of scripts/install_to_game.sh, with stricter rules because a
native install has no Wine prefix to throw away.

Install refuses unless the game executable is on the exe allowlist and the
game's binkw32.dll is on the Bink allowlist. It copies the original Bink to a
backup and to binkw32_real.dll, then drops in the proxy, kphasor.dll and the
address tables. Every file it writes is recorded in
kotorphasor\install-manifest.json with its hash. If any step fails, the steps
already done are undone in reverse order.

Uninstall reads that manifest. Before it touches anything, it checks every
value and path in it. Each value must be a single string, not a list. Paths may
not be rooted, have a '.' or '..' segment, or resolve outside the game folder.
Only the file names this script writes are allowed, each listed once, with
exactly one binkw32.dll entry. The backup folder must be named exactly
kotorphasor\backup\<timestamp>. No folder on the way to a file it removes may
be a junction or symbolic link. A manifest that fails any check is refused and
nothing is removed. It removes a file only when the file still has the hash we
wrote. It restores binkw32.dll first, from the backup, or from
binkw32_real.dll if the backup is gone, and only when that copy's hash matches
the recorded original. It never deletes a folder recursively. Scripts, logs
and anything else you added stay put.

Targets Windows PowerShell 5.1, which every supported Windows ships.

RUNNING IT
Windows blocks unsigned scripts by default, and marks downloaded files as
coming from the internet. Allow this one PowerShell window to run scripts, then
unblock the downloaded files:

    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    Get-ChildItem -Recurse .\scripts, .\build | Unblock-File

-Scope Process lasts only until you close that window. It changes no system
setting. Install into Program Files needs an elevated window ("Run as
administrator"). See docs\user\windows-native-install.md.

.EXAMPLE
.\Install-KotorPhasor.ps1 -GameDir 'C:\GOG Games\Star Wars - KotOR' -SourceDir .\build
.\Install-KotorPhasor.ps1 -GameDir 'C:\GOG Games\Star Wars - KotOR' -Action Uninstall
.\Install-KotorPhasor.ps1 -GameDir 'C:\GOG Games\Star Wars - KotOR' -Action Status
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$GameDir,
    [ValidateSet('Install', 'Uninstall', 'Status')][string]$Action = 'Install',
    # Folder holding kphasor.dll and the proxy binkw32.dll.
    [string]$SourceDir = '',
    # Folder holding the per-build address tables (data\addresses in the repo).
    [string]$AddressDir = '',
    # A Bink hash you vouch for that is not on the allowlist (K2's Bink is not
    # recorded yet). Must be the exact SHA-256; it is written to the manifest.
    [string]$TrustBinkSha256 = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$ManifestSchema = 'kotorphasor.install-manifest/v1'

# Game executables KotorPhasor has an installable address table for. Values are
# BuildRecord aliases from src\generated\builds.inc; the Python contract test
# (tools\platform_receipt_test.py) fails if a hash here is not a BuildRecord.
# k1_steam_103_unpacked is a harness artifact, not something a player runs.
# k2_steam_aspyr is left out: its builds.inc note and its address table
# disagree about whether it is installable.
$ExeAllowlist = @{
    '9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435' = 'k1_gog_103'
    '34e6d971c034222a417995d8e1e8fdd9f8781795c9c289bd86c499a439f34c88' = 'k1_steam_103'
    '777bee235a9e8bdd9863f6741bc3ac54bb6a113b62b1d2e4d12bbe6db963a914' = 'k2_gog_aspyr'
}

# Original RAD Game Tools binkw32.dll builds, by where they were hashed. The
# one entry today is the K1 Steam install's original (tmp/k1_harness). The GOG
# K1 and K2 Bink builds have not been hashed; if they differ, install refuses
# and names the -TrustBinkSha256 value to pass.
$BinkAllowlist = @{
    '2d0ae23a6175dc7b635c402a5e7e9542e923c0d1c376a8c5ef876ca0d5959d23' = 'K1 Steam original binkw32.dll (375808 bytes)'
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Test-OurProxy([string]$Path) {
    # Our proxy is small and names kphasor.dll; the real Bink is ~370 KB of codec.
    $item = Get-Item -LiteralPath $Path
    if ($item.Length -ge 200000) { return $false }
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $text = [System.Text.Encoding]::ASCII.GetString($bytes)
    return $text.Contains('kphasor.dll')
}

function Test-KnownBink([string]$Sha) {
    if ($BinkAllowlist.ContainsKey($Sha)) { return $true }
    if ($TrustBinkSha256 -and ($Sha -eq $TrustBinkSha256.ToLowerInvariant())) { return $true }
    return $false
}

function Find-GameExe([string]$Dir) {
    foreach ($name in @('swkotor.exe', 'swkotor2.exe')) {
        $p = Join-Path $Dir $name
        if (Test-Path -LiteralPath $p -PathType Leaf) { return $p }
    }
    return $null
}

function Get-Field($Object, [string]$Name) {
    # StrictMode 2 throws on a missing property; a manifest may lack one.
    # The leading comma keeps a one-element array an array: without it,
    # PowerShell unrolls ["x"] to "x", and the check would see a string
    # where the use later sees an array (review M1).
    if ($null -eq $Object) { return $null }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $null }
    return , $prop.Value
}

function Get-StringField($Object, [string]$Name, [string]$What) {
    # A manifest value this script wrote as a string, or $null when missing.
    # Anything else is refused: -eq and -match on an array filter the array
    # instead of comparing (review M2).
    $v = Get-Field $Object $Name
    if (($null -ne $v) -and -not ($v -is [string])) { throw "manifest $What is not a single string" }
    return $v
}

# The backup folder this script creates, and nothing else. \z, not $: in .NET
# '$' also matches before a final newline (review M7). -cmatch: this script
# writes these names in exactly this case.
$BackupDirPattern = '^kotorphasor[\\/]backup[\\/][0-9]{8}T[0-9]{6}Z\z'
# The files this script creates. A manifest naming anything else is not ours.
$CreatedPattern = '^(binkw32_real\.dll|kphasor\.dll|kotorphasor[\\/]addresses[\\/][A-Za-z0-9_-]+\.json)\z'
$ShaPattern = '^[0-9a-f]{64}\z'

function Resolve-Owned([object]$Rel, [string]$What) {
    # One manifest path to one absolute path strictly inside the game folder,
    # or a throw. Checked on both separators: '..\x' is one file name to
    # PowerShell on Linux but a traversal on Windows.
    if (($null -eq $Rel) -or -not ($Rel -is [string]) -or ($Rel.Length -eq 0)) {
        throw "manifest $What is null or empty"
    }
    if (($Rel -match '^[\\/]') -or ($Rel -match ':')) {
        throw "manifest $What '$Rel' is rooted or names a drive or stream"
    }
    foreach ($seg in ($Rel -split '[\\/]')) {
        # Windows drops trailing dots and spaces from a name, so '.. ' is '..'.
        if (($seg.Trim() -eq '') -or ($seg -match '^[. ]+$') -or ($seg -match '[. ]$')) {
            throw "manifest $What '$Rel' has an empty, '.' or '..' segment"
        }
    }
    $full = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($GameDir, $Rel))
    if (-not $full.StartsWith($GameRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "manifest $What '$Rel' resolves outside the game folder"
    }
    return $full
}

function Test-ReparsePoint([string]$Path) {
    # A junction or symbolic link, judged on the link itself, not its target.
    # A path that does not exist is not one.
    try { $attr = [System.IO.File]::GetAttributes($Path) } catch { return $false }
    return [bool]($attr -band [System.IO.FileAttributes]::ReparsePoint)
}

function Assert-NoReparsePoint([string]$Full, [string]$What) {
    # GetFullPath checks the path as text; it does not follow links. So every
    # folder from the game folder down to $Full, and $Full itself, must be a
    # plain folder or file (review M6). Windows PowerShell 5.1 can follow a
    # junction when it deletes, so this runs before anything is removed.
    $p = $Full.TrimEnd('\', '/')
    while (($null -ne $p) -and ($p.Length -ge $GameRoot.Length)) {
        if (Test-ReparsePoint $p) { throw "'$p', on the way to the $What, is a junction or symbolic link; refusing, nothing removed" }
        $p = [System.IO.Path]::GetDirectoryName($p)
    }
}

function Remove-BackupDir([string]$Dir) {
    # Our timestamped backup folder holds one file, binkw32.dll. Remove plain
    # files one by one, then the folder only if it is empty. No -Recurse, so
    # a junction or folder someone put inside is never walked into.
    if (-not (Test-Path -LiteralPath $Dir -PathType Container)) { return }
    Assert-NoReparsePoint $Dir 'backup folder'
    foreach ($c in @(Get-ChildItem -LiteralPath $Dir -Force)) {
        if ($c.PSIsContainer -or (Test-ReparsePoint $c.FullName)) {
            Write-Warning "backup folder holds '$($c.Name)', which this script did not write; folder left in place"
            continue
        }
        Remove-Item -LiteralPath $c.FullName -Force
    }
    if (-not (Get-ChildItem -LiteralPath $Dir -Force)) { Remove-Item -LiteralPath $Dir -Force }
}

function Assert-Manifest($m) {
    # Every value and path in the manifest, checked in the form it is used,
    # before anything is read or removed.
    $bd = Get-StringField $m 'backup_dir' 'backup_dir'
    if (($null -eq $bd) -or ($bd -cnotmatch $BackupDirPattern)) {
        throw "manifest backup_dir '$bd' is not kotorphasor\backup\<yyyyMMddTHHmmssZ>; refusing, nothing removed"
    }
    [void](Resolve-Owned $bd 'backup_dir')
    $filesValue = Get-Field $m 'files'
    if (-not ($filesValue -is [array])) { throw 'manifest files is not a list; refusing, nothing removed' }
    $files = @($filesValue)
    if ($files.Count -eq 0) { throw 'manifest lists no files; refusing, nothing removed' }
    $replaced = 0
    $seen = @{}
    foreach ($f in $files) {
        $path = Get-StringField $f 'path' 'file path'
        [void](Resolve-Owned $path 'file path')
        # One entry per file. NTFS ignores case and takes either separator.
        $key = ($path -replace '/', '\').ToLowerInvariant()
        if ($seen.ContainsKey($key)) { throw "manifest lists '$path' more than once" }
        $seen[$key] = $true
        $action = Get-StringField $f 'action' "action of '$path'"
        $sha = Get-StringField $f 'sha256' "sha256 of '$path'"
        if (($null -eq $sha) -or ($sha -cnotmatch $ShaPattern)) { throw "manifest entry '$path' has no sha256" }
        if ($action -ceq 'created') {
            if ($path -cnotmatch $CreatedPattern) { throw "manifest entry '$path' is not a file this script creates" }
        } elseif ($action -ceq 'replaced') {
            $replaced++
            if ($path -cne 'binkw32.dll') { throw "manifest replaced entry '$path' is not binkw32.dll" }
            $orig = Get-StringField $f 'original_sha256' 'original_sha256 of binkw32.dll'
            if (($null -eq $orig) -or ($orig -cnotmatch $ShaPattern)) { throw 'manifest binkw32.dll entry has no original_sha256' }
            $backup = Get-StringField $f 'backup' 'backup file'
            [void](Resolve-Owned $backup 'backup file')
            $want = ($bd -replace '/', '\') + '\binkw32.dll'
            if (($backup -replace '/', '\') -cne $want) { throw "manifest backup file '$backup' is not inside backup_dir" }
        } else {
            throw "manifest entry '$path' has unknown action '$action'"
        }
    }
    # Without the binkw32.dll entry, uninstall would leave the proxy in place
    # and still report success (review M4).
    if ($replaced -ne 1) { throw "manifest has $replaced binkw32.dll entries, want exactly 1; refusing, nothing removed" }
}

function Read-Manifest([string]$Path) {
    $m = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $schema = Get-StringField $m 'schema' 'schema'
    if ($schema -cne $ManifestSchema) { throw "unknown manifest schema '$schema' in $Path" }
    Assert-Manifest $m
    return $m
}

$GameDir = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $GameDir).Path)
# Every path this script deletes must start with this, compared ignoring case.
$GameRoot = $GameDir.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
$Proxy = Join-Path $GameDir 'binkw32.dll'
$Real = Join-Path $GameDir 'binkw32_real.dll'
$OwnDir = Join-Path $GameDir 'kotorphasor'
$ManifestPath = Join-Path $OwnDir 'install-manifest.json'

if ($TrustBinkSha256 -and ($TrustBinkSha256 -notmatch '^[0-9a-fA-F]{64}$')) {
    throw '-TrustBinkSha256 must be a 64-character SHA-256 hex string'
}

# --------------------------------------------------------------------------
if ($Action -eq 'Status') {
    if (Test-Path -LiteralPath $ManifestPath) {
        $m = Read-Manifest $ManifestPath
        # pwsh 7 turns ISO strings into DateTime on the way in; print the string.
        $at = $m.installed_at
        if ($at -is [DateTime]) { $at = $at.ToUniversalTime().ToString('o') }
        Write-Output "installed ($($m.game.build), since $at)"
        foreach ($f in $m.files) {
            $p = Resolve-Owned $f.path 'file path'
            $state = 'missing'
            if (Test-Path -LiteralPath $p -PathType Leaf) {
                if ((Get-Sha256 $p) -eq $f.sha256) { $state = 'ok' } else { $state = 'changed' }
            }
            Write-Output ("  {0,-8} {1}" -f $state, $f.path)
        }
    } elseif ((Test-Path -LiteralPath $Proxy) -and (Test-OurProxy $Proxy)) {
        Write-Output 'proxy present but no manifest: installed by another tool; not managed here'
    } else {
        Write-Output 'not installed'
    }
    return
}

# --------------------------------------------------------------------------
if ($Action -eq 'Uninstall') {
    if (-not (Test-Path -LiteralPath $ManifestPath)) {
        throw "no $ManifestPath; nothing this script installed is here, so nothing is removed"
    }
    try { $m = Read-Manifest $ManifestPath }
    catch { throw "uninstall refused, nothing removed; manifest kept: $($_.Exception.Message)" }
    $files = @($m.files)
    [array]::Reverse($files)

    # Pass 1 decides everything and touches nothing. One changed file means
    # nothing is removed, so a refused uninstall leaves a coherent install.
    # Read-Manifest has already refused any path that is rooted, has a '.' or
    # '..' segment, or resolves outside the game folder, and any value that is
    # not a single string.
    $backupDir = Resolve-Owned $m.backup_dir 'backup_dir'
    try {
        Assert-NoReparsePoint $backupDir 'backup folder'
        foreach ($f in $files) {
            Assert-NoReparsePoint (Resolve-Owned $f.path 'file path') 'file'
            if ($f.action -ceq 'replaced') { Assert-NoReparsePoint (Resolve-Owned $f.backup 'backup file') 'backup file' }
        }
    } catch { throw "uninstall refused, nothing removed; manifest kept: $($_.Exception.Message)" }
    $kept = New-Object System.Collections.ArrayList
    $plan = New-Object System.Collections.ArrayList
    foreach ($f in $files) {
        $p = Resolve-Owned $f.path 'file path'
        $replaced = ($f.action -eq 'replaced')
        if (-not (Test-Path -LiteralPath $p -PathType Leaf)) {
            if ($replaced) {
                Write-Warning "$($f.path) is missing; restore it from $($f.backup)"
                [void]$kept.Add($f.path)
            }
            continue
        }
        $sha = Get-Sha256 $p
        if ($replaced -and ($sha -eq $f.original_sha256)) { continue }  # already restored
        if ($sha -ne $f.sha256) {
            Write-Warning "$($f.path) changed since install; left in place"
            [void]$kept.Add($f.path)
            continue
        }
        $source = $null
        if ($replaced) {
            # The backup first; binkw32_real.dll is the same original, so it
            # serves when the backup is gone, if its hash still matches.
            $backup = Resolve-Owned $f.backup 'backup file'
            if ((Test-Path -LiteralPath $backup -PathType Leaf) -and ((Get-Sha256 $backup) -eq $f.original_sha256)) {
                $source = $backup
            } elseif ((Test-Path -LiteralPath $Real -PathType Leaf) -and ((Get-Sha256 $Real) -eq $f.original_sha256)) {
                Write-Warning "backup $($f.backup) missing or changed; restoring $($f.path) from binkw32_real.dll, which matches the recorded original"
                $source = $Real
            } else {
                Write-Warning "neither backup $($f.backup) nor binkw32_real.dll matches the recorded original; $($f.path) left in place"
                [void]$kept.Add($f.path)
                continue
            }
        }
        [void]$plan.Add(@{ entry = $f; full = $p; source = $source })
    }
    if ($kept.Count -gt 0) {
        throw "uninstall refused, nothing removed; manifest kept. Files: $($kept -join ', ')"
    }

    # Pass 2 acts on exactly what pass 1 verified. binkw32.dll is restored
    # first, whatever order the manifest lists it in, because its source may
    # be binkw32_real.dll, which a later step removes (review M3).
    $steps = @($plan | Where-Object { $_.entry.action -ceq 'replaced' }) + @($plan | Where-Object { $_.entry.action -cne 'replaced' })
    foreach ($step in $steps) {
        if ($step.entry.action -ceq 'replaced') {
            Copy-Item -LiteralPath $step.source -Destination $step.full -Force
            Write-Output "restored original $($step.entry.path)"
        } else {
            Remove-Item -LiteralPath $step.full -Force
        }
    }
    # Our own bookkeeping, only once every game file is back. backup_dir was
    # checked against kotorphasor\backup\<timestamp>, resolved inside the
    # game folder and checked for links before pass 1.
    Remove-BackupDir $backupDir
    $backupParent = Join-Path $OwnDir 'backup'
    if ((Test-Path -LiteralPath $backupParent) -and -not (Get-ChildItem -LiteralPath $backupParent -Force)) {
        Remove-Item -LiteralPath $backupParent -Force
    }
    $addr = Join-Path $OwnDir 'addresses'
    if ((Test-Path -LiteralPath $addr) -and -not (Get-ChildItem -LiteralPath $addr -Force)) {
        Remove-Item -LiteralPath $addr -Force
    }
    Remove-Item -LiteralPath $ManifestPath -Force
    Write-Output 'uninstalled (scripts and logs left in place)'
    return
}

# --------------------------------------------------------------------------
# Install: every check before the first write.
if (-not $SourceDir) { $SourceDir = [System.IO.Path]::Combine($PSScriptRoot, '..', '..', '..', 'build') }
if (-not $AddressDir) { $AddressDir = [System.IO.Path]::Combine($PSScriptRoot, '..', '..', '..', 'data', 'addresses') }
$SourceDir = (Resolve-Path -LiteralPath $SourceDir).Path
$AddressDir = (Resolve-Path -LiteralPath $AddressDir).Path

if (Test-Path -LiteralPath $ManifestPath) { throw 'already installed; run -Action Uninstall first' }

$exe = Find-GameExe $GameDir
if (-not $exe) { throw "no swkotor.exe or swkotor2.exe in $GameDir" }
$exeSha = Get-Sha256 $exe
if (-not $ExeAllowlist.ContainsKey($exeSha)) {
    throw "$(Split-Path -Leaf $exe) sha256 $exeSha is not a supported build; refusing"
}
$build = $ExeAllowlist[$exeSha]

if (-not (Test-Path -LiteralPath $Proxy -PathType Leaf)) { throw "no binkw32.dll in $GameDir" }
if (Test-OurProxy $Proxy) { throw 'binkw32.dll is already a KotorPhasor proxy but there is no manifest; restore the original by hand first' }
$binkSha = Get-Sha256 $Proxy
if (-not (Test-KnownBink $binkSha)) {
    throw "binkw32.dll sha256 $binkSha is not a known Bink build; pass -TrustBinkSha256 $binkSha only if you know it is the game's original"
}
if (Test-Path -LiteralPath $Real) {
    $realSha = Get-Sha256 $Real
    if (-not (Test-KnownBink $realSha)) { throw "binkw32_real.dll sha256 $realSha is unknown; refusing" }
    if ($realSha -ne $binkSha) { throw 'binkw32_real.dll differs from binkw32.dll; refusing to guess which is original' }
}

$srcDll = Join-Path $SourceDir 'kphasor.dll'
$srcProxy = Join-Path $SourceDir 'binkw32.dll'
foreach ($f in @($srcDll, $srcProxy)) {
    if (-not (Test-Path -LiteralPath $f -PathType Leaf)) { throw "missing $f; build first" }
}
if (-not (Test-OurProxy $srcProxy)) { throw "$srcProxy is not a KotorPhasor proxy" }
$table = Join-Path $AddressDir "$build.json"
if (-not (Test-Path -LiteralPath $table -PathType Leaf)) { throw "missing address table $table" }
if (Test-Path -LiteralPath (Join-Path $GameDir 'kphasor.dll')) { throw 'kphasor.dll already in the game folder and not ours; refusing' }

# Program Files needs an elevated shell. Find out now, not halfway through.
$probe = Join-Path $GameDir ('.kp-write-probe-' + [guid]::NewGuid().ToString('N'))
try {
    [System.IO.File]::WriteAllText($probe, 'probe')
    Remove-Item -LiteralPath $probe -Force
} catch {
    throw "cannot write to $GameDir (run from an elevated shell, or move the game out of Program Files): $($_.Exception.Message)"
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$backupRel = [System.IO.Path]::Combine('kotorphasor', 'backup', $stamp)
$records = New-Object System.Collections.ArrayList
$undo = New-Object System.Collections.ArrayList   # scriptblocks, run in reverse
$createdDirs = New-Object System.Collections.ArrayList

function Add-Dir([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
        [void]$createdDirs.Add($Path)
    }
}

function Add-Created([string]$Rel, [string]$From) {
    $dst = Join-Path $GameDir $Rel
    if (Test-Path -LiteralPath $dst) { throw "$Rel already exists and is not ours; refusing" }
    Copy-Item -LiteralPath $From -Destination $dst
    [void]$undo.Add({ Remove-Item -LiteralPath $dst -Force -ErrorAction SilentlyContinue }.GetNewClosure())
    [void]$records.Add([ordered]@{ path = $Rel; action = 'created'; sha256 = (Get-Sha256 $dst) })
}

try {
    Add-Dir $OwnDir
    Add-Dir (Join-Path $OwnDir 'backup')
    Add-Dir (Join-Path $GameDir $backupRel)
    Add-Dir (Join-Path $OwnDir 'addresses')
    Add-Dir (Join-Path $OwnDir 'scripts')

    # 1. The original Bink, copied (never moved) before anything is replaced.
    $backupFile = [System.IO.Path]::Combine($backupRel, 'binkw32.dll')
    Copy-Item -LiteralPath $Proxy -Destination (Join-Path $GameDir $backupFile)
    if ((Get-Sha256 (Join-Path $GameDir $backupFile)) -ne $binkSha) { throw 'backup copy of binkw32.dll does not verify' }
    if (-not (Test-Path -LiteralPath $Real)) { Add-Created 'binkw32_real.dll' $Proxy }

    # 2. Runtime and tables.
    Add-Created 'kphasor.dll' $srcDll
    # Only the detected build's table: the runtime loads <build>.json.
    Add-Created ([System.IO.Path]::Combine('kotorphasor', 'addresses', "$build.json")) $table

    # 3. The proxy last: until this point the game still starts unmodded.
    # The undo goes in first, so a copy that fails halfway is still put back.
    [void]$undo.Add({ Copy-Item -LiteralPath (Join-Path $GameDir $backupFile) -Destination $Proxy -Force }.GetNewClosure())
    Copy-Item -LiteralPath $srcProxy -Destination $Proxy -Force
    [void]$records.Add([ordered]@{
        path = 'binkw32.dll'; action = 'replaced'; sha256 = (Get-Sha256 $Proxy)
        original_sha256 = $binkSha; backup = $backupFile
    })

    $trusted = $null
    if (-not $BinkAllowlist.ContainsKey($binkSha)) { $trusted = $binkSha }
    $manifest = [ordered]@{
        schema = $ManifestSchema
        installed_at = (Get-Date).ToUniversalTime().ToString('o')
        game = [ordered]@{ exe = (Split-Path -Leaf $exe); sha256 = $exeSha; build = $build }
        bink_original_sha256 = $binkSha
        bink_trusted_override = $trusted
        backup_dir = $backupRel
        files = $records
    }
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8
} catch {
    $err = $_
    $steps = @($undo)
    [array]::Reverse($steps)
    foreach ($s in $steps) { try { & $s } catch { Write-Warning "rollback step failed: $($_.Exception.Message)" } }
    $backupAbs = Join-Path $GameDir $backupRel
    if (Test-Path -LiteralPath $backupAbs) {
        # Only after binkw32.dll is back, and only our own timestamped folder.
        if ((Test-Path -LiteralPath $Proxy) -and ((Get-Sha256 $Proxy) -eq $binkSha)) {
            try { Remove-BackupDir $backupAbs } catch { Write-Warning "backup folder left in place: $($_.Exception.Message)" }
        }
    }
    $dirs = @($createdDirs)
    [array]::Reverse($dirs)
    foreach ($d in $dirs) {
        if ((Test-Path -LiteralPath $d) -and -not (Get-ChildItem -LiteralPath $d -Force)) { Remove-Item -LiteralPath $d -Force }
    }
    if (Test-Path -LiteralPath $ManifestPath) { Remove-Item -LiteralPath $ManifestPath -Force }
    throw "install failed and was rolled back: $($err.Exception.Message)"
}

Write-Output "installed $build into $GameDir"
Write-Output "  scripts go in $(Join-Path $OwnDir 'scripts')"
Write-Output "  manifest: $ManifestPath"
