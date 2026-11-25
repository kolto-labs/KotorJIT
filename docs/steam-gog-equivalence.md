# The Steam KOTOR 1 build, and why GOG addresses work on it

Every address KotorJIT uses for KOTOR 1 was derived from the GOG build. The primary
target is the Steam build. Here is why that is sound, and what the Steam wrapper is.

## The Steam executable is encrypted on disk

`swkotor.exe` from Steam (sha256 `34e6d971…439f34c88`) has a `.text` section that is not
code. Shannon entropy is 7.999 bits per byte across every 256 KB chunk of it. There is not a
single `55 8b ec` function prologue in 3.3 MB. There is no `0xCC` padding anywhere.
Reading a known address out of the file returns noise:

```
CVirtualMachine::RunScript  VA=0x005d0fc0  ->  ae a0 f4 4b 60 1f af c1 …
```

The entry point sits at `0x0086d2ed`, inside a fifth section named `.bind`.

## It is SteamStub, not SafeDisc

`.bind` is used by both, so the section name alone does not settle it. Running the game
without Steam does:

> Application load error 5:0000065434

That is SteamStub's error. It is why the executable cannot be launched standalone under
Wine. The stub refuses before the game gets control. Consequently the automated harness
runs against the **deciphered** image rather than the shipped one.

An earlier draft of this project's notes called the wrapper "SafeDisc-style". That was wrong,
and it mattered. SafeDisc and SteamStub need different handling, and only one of them is
removed by the tooling we have.

## Steam and GOG differ by the wrapper, and by 38 bytes of letter case

| | Steam | GOG |
|---|---|---|
| file size | 4,395,008 | 4,042,752 |
| sections | `.text` `.rdata` `.data` `.rsrc` **`.bind`** | `.text` `.rdata` `.data` `.rsrc` |
| entry point | `0x0086d2ed` (in `.bind`) | `0x006fb38d` |

The size difference is exactly the size of `.bind` (`0x56000` = 352,256 bytes):

```
4,395,008 − 352,256 = 4,042,752
```

Deciphering the Steam image and comparing its `.text` against GOG's, page by page:

- **828 of 828** 4 KB pages are identical
- both entry points resolve to `0x006fb38d`
- all four shared sections sit at the same virtual addresses

The other three sections are not quite untouched. The difference is worth stating
precisely rather than rounding to zero:

| section | bytes differing, Steam vs GOG |
|---|---|
| `.rdata` | **38** of 327,680 |
| `.data` | 0 of 94,208 |
| `.rsrc` | 0 of 225,280 |

All 38 are the letter case of imported DLL names. Steam writes `KERNEL32.dll`,
`OPENGL32.dll`, `USER32.dll`; GOG writes them lowercase. No vtable, string literal, or
function-pointer table is affected, so nothing a hook touches differs.

So the Steam build **is** the GOG build with a DRM wrapper bolted on. Every GOG address
applies verbatim to the Steam build once `.text` has been deciphered in memory.

## Why this is not circular

Comparing the unpacked image against GOG and finding the code identical would prove
nothing on its own. Someone splicing GOG's code into a Steam shell would produce exactly
that result. What rules it out is an asymmetry in the *other* sections.

```
           steam-vs-gog   unpacked-vs-steam   unpacked-vs-gog
.rdata           38                0                38
.data             0                0                 0
.rsrc             0                0                 0
```

The unpacked image's `.rdata` matches **Steam**, not GOG, while its `.text` matches
**GOG**. A splice would have carried GOG's `.rdata` across too. It did not, so the
unpacker decrypted the Steam file in place. That is the thing we needed to believe.

Independently of the unpacker at all: Steam's own on-disk `.data` and `.rsrc` are already
byte-identical to GOG's, and Steam `.text` matches GOG in 13,270 of 3,391,488 bytes.
That is 1 in 256, exactly chance, confirming the whole section is encrypted rather than
partly shared.

Two further checks agree:

1. A separate project derived Steam addresses for the VM stack accessors by its own means and
   landed on `0x005D1000`, `0x005D1010`, `0x005D1080`, `0x005D1090`. Those are precisely the GOG
   addresses the corpus records for `StackPop/PushInteger` and `StackPop/PushString`.
2. The routine count is 772 by three separate routes: parsing `nwscript.nss`, the
   `ScriptFunctions` enum recovered from the binary, and the binary's own `cmp edx, 0x304`.

## What this means for the runtime

- `data/addresses/k1_steam_103.json` is generated from the GOG symbol source on purpose. The
  `symbol_source` field records that, so it is visible rather than implied.
- Hooks must never be installed from `DllMain`. At that point `.text` is still ciphertext.
  The `image/` module waits for the stub to decipher, re-parses the image from memory, and
  verifies the plaintext before any address is resolved.
- Verification is a hash of the deciphered `.text` against the known-good GOG value. A
  mismatch means refuse to install, not proceed and hope.

## Harness note

The headless harness runs the deciphered image, because the shipped one will not start
without Steam. `scripts/harness/` keeps the original alongside it as
`swkotor.exe.steamstub.bak` so the encrypted-path tests still have their input.
