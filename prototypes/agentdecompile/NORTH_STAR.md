# AgentDecompile — north star

Read this before any plan, spec or design doc. When another document disagrees with this one, this one wins.

## One sentence

Upload a program; get back its source, a modding API that survives every patch, and a port that runs anywhere.

## What the user considers too obvious to say

1. **You drop it in; it does the rest.** Every build, platform, patch and version of a program goes in. It recognises them by content, groups them into programs, and works through everything with nobody steering. There is no Start button and no per-stage button. The one control is pause/resume.
2. **The program is the unit, not the binary.** The builds are the same application compiled differently, or from older or newer source. Every view is organised around the logical program and its logical functions, with the concrete build one click down. More builds means more evidence, not more work.
3. **Ghidra-level analysis is mid.** It hands a human data to infer from. AgentDecompile does the inferring: following pointers, walking call graphs, matching across builds, naming, typing structs, recovering vtables, identifying the compiler. Exhaustively and deterministically, across the whole corpus. The code browser is the drill-down, not the product.
4. **Every product falls out of understanding.** Byte-matching source, portable signatures, the runtime Lua bridge, code caves, headers and struct paths, the browser port, multiplayer groundwork, agent context. None of them is a separate project. Each one is a view of the same recovered program.
5. **Addresses are an implementation detail.** Everything (functions, structs, fields, globals, caves, patch points) is found by signature on every build. A mod written once runs everywhere the signature resolves. Where builds diverge, show it and keep one identity with several shapes; never force a match.
6. **Agents are first-class users.** The name says it. Agents drive the recovery, and the recovered program is context an agent reads as easily as source (MCP).
7. **Watching it should be exciting.** The interface draws the work: the program map filling in, pointers resolving, bytes turning from red to identical. Pictures carry the meaning; sentences live in tooltips.

## The products

| Product | What someone gets | Replaces |
|---|---|---|
| Source that rebuilds | C/C++ whose compiled output is the shipped bytes, whole image | Years of hand-matched decompilation |
| Portable signatures | Every entity located on every build without an address | Offset tables that break on every patch |
| Script extender | Inject; every routine callable and every event hookable from Lua | Hand-built extenders, rebuilt per version |
| Code caves | Verified unused spans, found by signature | Guesswork in a hex editor |
| Headers and struct paths | Per-build headers; pointer paths that hold across builds | Reversing layouts by hand |
| Learn the build | Compiler and flags read off the bytes, then reproduced | Trial and error |
| Browser port | The program rebuilt to WebAssembly, running on the user's own files | Emulators and bespoke ports |
| Multiplayer | Engine state understood well enough to network | Multi-year one-off mods |
| Agent context | MCP server over the whole corpus | Manual RE plus prompting |

## Why the strategy is strong

- **Byte identity is ground truth.** Every result is objectively checkable against the shipped bytes.
- **Cross-build unification multiplies evidence.** One recovery pays off in every variant; what one build hides another reveals.
- **Compile-gated propagation** lets the machine run unattended without poisoning itself.
- **Deterministic and reuse-first.** Same inputs, same outputs; nothing is redone.
- **Autonomy with overrides.** Review happens afterwards and never blocks progress.
- **Generic by construction.** Product specifics live in data, never in code or docs.

## Why the last month stalled

Agents optimised for not being wrong. Honesty rules meant to make outputs trustworthy became the product: receipts, claim tiers, audits and disclaimers on every screen ("receipt" and "verify" appear about 2,700 times in last month's docs; the browser build and modding fewer than 100 times combined). Ghidra parity was treated as the core. Plans stood in for progress, and each session re-derived intent from a partial read of an ever-growing pile.

## Rules for every agent from here

1. Judge every plan by one question: does this move a product forward on the real corpus?
2. Show progress toward products (how much is recovered, portable, scriptable, playable), not paperwork. Evidence stays one hover away and never in the way.
3. Build the walking skeleton first, then deepen. Agent-hours, not engineer-days.
4. Do not ask the user to re-explain. This file, the requirements ledger and the prototype are the brief.
5. Keep the honesty rules as data integrity: never count wrapper bytes as source, never draw more certainty than the evidence. Keep them out of the UI copy.

## Reference prototype

`agentdecompile-cockpit.html`: drop zone, program map filling in, the machine's lanes, and a shelf of products, each with its own live showcase. It runs on the real corpus totals and real signature and prologue data. It shows the intended experience; it is not the implementation.
