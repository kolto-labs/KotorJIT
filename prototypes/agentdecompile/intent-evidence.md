# AgentDecompile — intent evidence from the user's own words

Companion to `NORTH_STAR.md`. Built 2026-09-29 by mining **user-authored text only**:
Codex `history.jsonl` (841 prompts) plus user turns in Codex Desktop session transcripts (2026-05 → 09-28),
top-level Cursor agent transcripts (subagent/agent-written task prompts filtered out), and the user's own
Discord replies (`bodenai-data/cases/cases.jsonl`). About 2,700 unique user messages were scanned.
Claude Code transcripts were not mounted, so directives that exist only there (e.g. "no Start button",
readiness/divergence reports) are cited from `docs/plans/2026-09-21-user-requirements-ledger.md` and marked *(ledger)*.

Quotes are verbatim, including typos, and trimmed with "…". Source tags: **codex**, **cursor**, **discord**.
Counts in §2 are approximate: they count unique user messages matching a keyword pattern in an RE context.
They show the relative weight of each premise and are not exact tallies.

---

## 1. Things the user said that current docs miss or contradict

### 1.1 One-shot is the product now. It is not a multi-decade horizon.
- "i'm trying to make a program that'll one-shot decompile to full source code any program under the sun / in... one shot" — discord 2026-06-13
- "you said this: `Bounded claim: … it is not whole-binary parity or 90% recovery proof.` but this is unacceptable. … must be 90% recovery proof or preferably whole binary parity. That is obviously the goal..." — codex 2026-07-06
- "Drive the queue to completion in 24 hours or less …" (mission contract the user pasted) — codex 2026-09-08. Also a kotorxid directive: "4.6 years??? wtf. i need 24 hours or less." — codex 2026-08-23
- **Contradicts:** `VISION.md` §8 and §17 ("Full automated round-tripping … is a multi-decade horizon"). §11 also lists "A promise of near-term whole-application one-shot perfection" under what the product is *not*.
- **Nuance:** the phrase came from the user: "While this may be a multi decade long goal … agentdecompile does it well by allowing even partial implementations to be usable" — cursor 2026-08-08. He meant "partial results must still be useful." He did not mean "lower the target." The docs turned his hedge into the headline.

### 1.2 The positioning is "any program in, source out". It is not "Connect AI to Ghidra".
- "the goal is to be able to one-shot reverse engineer/decompile any and all applications quickly, accurately, and completely as a universal pipeline … we want ourselves to be a single cross-platform app." — codex 2026-06-06
- "I would really like if I could run agentdecompile without having to run a local ghidra instance and maintain a local shared project" — discord 2026-02-21
- "i've been thinking about porting ghidra from java to rust for half a year now xD (just the relevant parts necessary for the goal)" — discord 2026-06-04; "Transpiling Ghidra to Rust to get it out of the Java ecosystem once and for all" — discord 2026-06-13
- "is there some alternative project/repo besides ghidra that exists that we can use?" — codex 2026-09-10
- **Contradicts:** `docs/HERO.md` headline "**Connect AI to Ghidra**" and subhead "Run an MCP server that talks to your Ghidra project". The April framing ("agentdecompile is just an intuitive gateway into Ghidra itself, tailored for LLM agents" — discord 2026-04-01) was dropped after the Mizuchi article ("Dude found a way to ONE SHOT re dumps" — discord 2026-05-29). Ghidra is an engine behind the product. It is not the product's identity.

### 1.3 Everything you point it at becomes an LLM-readable plaintext tree, not only the .exe.
- "will also extract sfx's, zips, archives, etc (goal is to convert anything and everything we point to to natural language … the files should be plaintext preferably json or markdown (configurable). Everyything should be some format a llm can understand, not binary." — codex 2026-06-29
- "so part of this agentdecompile plan is to convert the entire installation to plaintext json" — discord 2026-04-15
- "transpiling between formats. Machine code to Assembly to C/C++ to Python to GO to hex dumps to ghidra project serialization filedata to anything lol." — cursor 2026-07-18
- "nah it's not good enough yet it's too specific. look at our daws … (dismantling binaries into structures like these)" — cursor 2026-08-08
- **Gap:** `VISION.md` covers dismantling and installer trees, but no doc names the *deliverable*: a configurable JSON/Markdown mirror of a whole installation. The `NORTH_STAR.md` product table has no row for it.

### 1.4 The output is a per-build source project you can open in an IDE, download as a zip, and read like the original developers' code.
- "all must be packaged somewhere as a C/C++ project that can be built and opened and utilized with vscode or another ide" — codex 2026-08-23 (kotorxid directive D8)
- "Produce separate assembly and readable C/C++ export packages for every build, with ProjectBorealis-style source layout, build files, and IDE usability." — codex 2026-09-08
- "pause to please create a .zip representing the current max c variant … zip it up hurry up" — codex 2026-09-16
- "It should not be ugly unparsed c++ or even c it should be as high level as possible and object-oriented and refactored as physically possible" — cursor 2026-07-24
- **Gap:** `STRATEGY.md` defines the asm-floor and max-C variants, but it never makes "download the project zip / open it in an IDE" a first-class output. `NORTH_STAR.md` "Source that rebuilds" says nothing about layout, build files or IDE use.

### 1.5 Several people use it at once, and there is an editor built into the page.
- "ensure multiple clients can connect and work concurrently with everything without affecting each other's frontend (the backend should be the same for both though obviously). Also the source code stuff, please offload that to another subprocess … Also if possible please have a button that opens in a vscode space, supporting both the website that allows users to use vscode in the browser. … ensure this is always available, embedded, etc in realtime." — codex 2026-09-09
- **Gap:** VISION, STRATEGY, CONCEPTS, FRONTEND_INTENT and the 09-21 ledger never mention multi-client isolation or an embedded VS Code.

### 1.6 Guarding against hallucination means several independent paths must agree. Receipts alone do not do it.
- "The skills on the agent require at least 3 verifications through 3 different paths (e.g. through a string search, or a match-function call …, or a get-call-graph … The way agentdecompile works is it requires multiple paths to the Aple." — discord 2026-02-09
- "multiple sub-agents to be searching the same thing … Each in their own unique way. And information that doesn't achieve a mean or average between the sub agents are ignored. As they're probably hallucinations" — discord 2026-03-17
- "a lot of other decompiling/reverse engineering projects seem to continually forget where the variable comes from and hallucinate." — cursor 2026-08-08
- **Gap:** docs cover provenance but do not describe agreement across several paths or several agents. `NORTH_STAR.md` asks for honesty rules to be *data integrity*, and this is the concrete form the user described.

### 1.7 Every binary is in scope, including DRM-wrapped or encrypted ones.
- "Cover every binary, removing any DRM and unencrypting any encryption that you find completely." — codex 2026-09-08 (this replaces the older "DRM encrypted … put on the backburner", kotorxid D5)
- "given we own the fucking game we can modify it however we want." — codex 2026-09-10 (KotorPhasor)
- **Gap:** no current doc states a scope position on protected binaries.

### 1.8 Tools should be simple, task-level and use few tokens.
- "The tools themselves should be as simple and intuitive as possible. For example: a tool called like `get_quest` which would return markdown representing …" — discord 2026-03-17
- "`as few tokens as possible while still representing the information`" — discord 2026-02-13
- "any and all of the tooling, cli commands, etc must be accessible via the swagger api thing." — cursor 2026-08-31
- **Partial:** VISION's "compose without funnels" is close, but token economy and domain-level context tools are not stated.

### 1.9 The harness, TAS and softlock detection are part of the pipeline.
- "Assess what we're doing in kotorphasor. I'd like that to be part of the pipeline/prototype." — codex 2026-09-20
- "Imagine being able to fully test your changes to the game in under a minute … detect and prevent any and all soft locks caused by additional content or other modifications." — cursor 2026-08-30
- "This harness should also double as a TAS." — codex 2026-09-10; "rewinding back through previous dialog choices should be possible, pausing, play, save state, etc. All the stuff you can do in ren'py" — codex 2026-09-22
- **Gap:** `NORTH_STAR.md`'s product table has no harness/TAS/softlock row.

### 1.10 The Lua bridge should feel like a full modding environment, with names taken from the reversed code.
- "all functions and commands and events etc must be named after and representative of the ghidra data we're referencing" — cursor 2026-08-30
- "Lua should not have equivalent function/variable names [to NWScript]. CLEAR separation." — codex 2026-09-17
- "consider other games that have lua scripting integrations … such as, garry's mod … I'd like more power/utility" and "double as a modding environment/development environment … as thoroughly as Blender" — codex 2026-09-22
- "Exporting Phasor within AgentDecompile's pipeline allows us to easy create a Phasor clone for whatever we're working" — cursor 2026-09-08
- **Partial:** STRATEGY covers hookpack + generated Lua. The *feel* bar (GMod-familiar API, Ren'Py-style rewind, Blender-level interactivity) exists only in KotorPhasor sessions.

### 1.11 The browser/WASM port and multiplayer are real, but secondary.
- "embed the entire game(s) in a browser with WASM. It should be part of the KotorPhasor project" / "it should not publish to github any game assets … requiring the user to have the game installed locally" / "**wasm should be offloaded to a low priority task**" — codex 2026-09-22
- Multiplayer only appears for a separate browser project ("create a multiplayer variant … fully playable in the browser" — cursor 2026-07-18). It is never an AgentDecompile deliverable.
- **Contradiction risk:** `NORTH_STAR.md` shows "Browser port" and "Multiplayer" as peer products. The evidence supports "the port runs on the user's own files" but ranks it low priority, and multiplayer is weakly evidenced.

### 1.12 More than native C/C++: managed runtimes, Unity, and other languages.
- "The full Unity Editor project that matches what the actual developers have … Must be part of `agentdecompile-cli`." — codex 2026-09-10
- "I'm currently using it to reverse engineer tslpatcher back to pascal" — discord 2026-04-01
- **Partial:** the ledger says "C/C++ is one supported language", but the `NORTH_STAR.md` product rows assume C/C++ only.

### 1.13 Reuse all prior work before starting anything.
- "Fix the problem where it wasn't already reusing the corpus stuff properly so it cannot happen again by ensuring this investigation is done first as highest priority before actually starting work" — codex 2026-09-15
- "Where the heck is all the months of work we've done? … aggregate comprehensively … so we don't have to continue combining/investigating previous work" — cursor 2026-09-22
- **Partial:** "never redo completed work" is in the ledger. *Discovering and importing scattered prior artifacts first* is not.

---

## 2. Obvious-to-the-user premises (ranked)

Ranked by weight: repetition, how angry the user gets when it is violated, and whether it is ever explained.

| # | Premise | ≈msgs | Representative quote |
|---|---|---|---|
| 1 | **Point it at a program and it produces the source. One shot, unattended.** | 53 | "Goal is to make a single cli that can be pointed to a folderpath and will one shot the source code on the first try." — codex 2026-06-29 |
| 2 | **Byte-accurate, whole-binary parity is the target. A bounded claim is a failure.** | 88 | "note the entire point of the goal is '90%/whole parity'." — codex 2026-07-06 |
| 3 | **Nothing specific to any product. Fully binary-agnostic.** | 63 | "absolutely NOTHING in agentdecompile or the codebase should be specific to swkotor2.exe or swkotor.exe … It's supposed to be dynamic and robust and flexible and ambiguous to the target" — cursor 2026-07-25 |
| 4 | **No human in the loop after the first prompt.** | 48 | "please stop telling the user to do things. For anything requiring a user, spawn a subagent automatically. No human in the loop past the first prompt" — codex 2026-06-06 |
| 5 | **Readable, high-level, object-oriented, linted C. Not a Ghidra dump.** | 75 | "It shouold be as close as possible to what the original developers were working with" — cursor 2026-07-12 |
| 6 | **Many builds are one program, and cross-matching is how the work is organized.** | 49 | "updating one specific will update that specific for all of the binaries" — cursor 2026-09-08 |
| 7 | **Never redo, never lose, always resume real state.** | ~120 (inflated by "resume") | "Ensure force killing the server or anything will never lose our work." — cursor/codex 2026-09-08 |
| 8 | **Fast in hours, without a special "fast path".** | 54 | "i don't want 'fastpath' i want it to just simply *be* fast while still being comprehensive and deep." — cursor 2026-07-25 |
| 9 | **Everything that can run concurrently does.** | 79 | "Can we do more things concurrently pls ensure it's wired in so I don't have to ask again." — codex 2026-09-18 |
| 10 | **Addresses are an implementation detail. Signatures work on every build.** | 34 | "Ideally the signature should be the same for ALL the binaries … so it's not reliant on absolute addresses per binary anymore." — cursor 2026-09-08 |
| 11 | **Any context, in any form, is both input and output.** | (broad) | "give it context like puzzle pieces in various forms for it to just seamlessly integrate … without guessswork and fully procedurally." — codex/cursor 2026-07-08, 07-12 |
| 12 | **Modding (Lua bridge + codecaves) is a first-class output.** | 54 | "provide a list of all codecaves/events/lua functions and tell me which ones work atm" — cursor 2026-08-30 |
| 13 | **Everything the CLI/MCP can do is reachable from the UI and the API.** | ~15 | "all of the agentdecompile-cli/mcp tooling must be available and comprehensively designed in the frontend page(s)" — cursor 2026-08-31 |
| 14 | **Prove it by driving it live. Tests come last.** | 28 | "Tests should only ever be ran once the bytecode parity is achieved in a roundtrip" — cursor 2026-07-25 |
| 15 | **It never needs a restart.** | 13 | "any change in any python code will automatically take effect without requiring a restart? this must also include existing objects" — codex 2026-09-20 |

---

## 3. UI/feel directives (verbatim-backed)

1. **Draw the work.** Statistics and spinners are not enough. "For example a 'running' piece of text next to a circle spinning isn't very informative, don't do stuff like that." And, about "Compiled 100 of 5,467 K1 candidates…": "Nope this is still wrong. Actually animate/draw shit so it's actually showing WHAT is being done rather than useless statistics like this." — codex 2026-09-20
2. **No Start button.** Analysis starts when a project is opened, binaries are added, or work is resumed. The only control is pause/resume. *(ledger, 2026-09-21)* Supporting: "If no project is loaded it should automatically be creating/using one" — cursor 2026-08-31.
3. **All binaries as one.** "treating multiple binaries in the project as the same binary … The main focus should be working with all the binaries as one" — codex 2026-09-20. "instead of showing just *one* binary it shows *all* of the binaries we're working with." — cursor 2026-08-31
4. **One page, few tabs, no digging.** "the user doesn't have to dig deep into nested pages etc. Ideally everything should be on *one* page. Also refrain from using tabs unless you have to." — cursor 2026-08-31
5. **No links behind links.** "there's a lot of convoluted links behind links behind links and it's not really intuitive what we're clicking through" — codex 2026-08-23
6. **Dynamic and binary-agnostic copy.** "Most of it should be above all, completely *dynamic*. Much of it hardcodes specific text, and assumes specific projects. It should instead be COMPLETELY agnostic to the binaries used" — codex 2026-08-23
7. **Looks like desktop RE tools.** "Make it look more like ghidra's UI combined with ida pro combined with … cheatengine" — cursor 2026-09-01. "Think about the designs of x64dbg/ida pro/ghidra especially the generated graph stuffz" — cursor 2026-08-31
8. **A per-function, per-binary bar where validation overlaps decompilation.** "It's extremely important that the validation linker is shown as a progress bar PER function PER binary in a way that overlaps the original function's horizontal progress bar representing the decompilation status." — cursor 2026-08-31
9. **Compile-back never blocks.** "compiling back to executable binary is not a type of task that will force other tasks to wait for it … a validation loop … updating real-time progress bars" — cursor 2026-08-31
10. **Dialogs never block.** "The dialog should instead offload the task/job and close instantly so the rest of the frontend can be used..." — cursor 2026-09-08
11. **Crash-safe, real-time save.** "always saving back to the project in real time … force killing the server or anything will never lose our work." — cursor 2026-09-08
12. **Multi-client with an embedded VS Code.** See §1.5 — codex 2026-09-09.
13. **Keep flow with high-powered controls.** "How could we reduce tediousness and implement high powered controls that don't feel clunky or nested and lets users keep flow?" — cursor 2026-09-01. "I'm still not liking the UI design at all. Feels extremely clunky." — cursor 2026-09-01
14. **Projects are dropped in, sticky, and colored by kind.** "drop a .gpr file in, a .rep folder in, [a shared-server folder] … create a global tab at the top representing the session. This should be stickied … shared servers connected over http should be a specific different color than filesystem shared server project vs local .gpr project … tabs should be renameable." — cursor 2026-08-31
15. **Pick, don't type.** "ensure as many of these textboxes as possible are converted to comboboxes … for binaries obviously just ensure it's always showing the available binaries in the project." — cursor 2026-08-31
16. **Every tool is in the UI, with realtime reactions.** "all actions must have realtime comprehensive reactions" — cursor 2026-08-31. Also "add shutdown/restart buttons to the dashboard itself." — cursor 2026-09-01
17. **One port.** "something is serving 3000, 8791, 5173, 8173 which is bizarre since everything should exclusively be on one port." — codex 2026-09-10. The optional rich app on 5174 is allowed: "Static page should be served with the mcp server and the vite page should be an optional program" — codex 2026-09-08
18. **Opening a project resumes the real state.** "Ensure when you start using the dashboard properly it'll resume existing work … rather than overwriting or resuming stale data/states." And "all of this is obnoxious and makes it difficult to just start seamlessly using the dashboard." — codex 2026-09-17
19. **One pipeline carries every directive.** "Any and all directives given in the last few days should be part of the single pipeline that the dashboard should facilitate..." — codex 2026-09-17
20. **Works remotely.** "Ensure both are reachable … remotely via our ipv4 address" — codex 2026-08-23
21. **Hot reload, no restarts.** "do not restart servers unless you're fixing a hot-reload problem as the whole point is i don't want to restart" — codex 2026-09-10
22. **Plain language.** "/anti-slop … for the entirety of the site. Please re-evaluate what it's *supposed* to be doing directly and in plain langauge" — cursor 2026-09-08
23. **Show progress and a way to cancel or resume.** "it shows a progress bar and what it's working on and allowing the user to cancel early … Should also let them completely resume at any point." — codex 2026-06-29
24. **Superseded:** "none of this should static pages pls make it all react" (cursor 2026-09-08) was replaced the same day by static-on-MCP + optional Vite.

---

## 4. Products/outputs the user expects at the end of the pipeline

| # | Output | Verbatim evidence |
|---|---|---|
| 1 | **Whole-image byte-identical rebuild** (code bytes; data may differ) | "compiling back to .exe and confirming they're teh same (only the code matters, not the data)" — codex 2026-06-29 |
| 2 | **Readable, linted, high-level C/C++** close to what the original developers wrote | "c/c++ source code should be clean and linted automatically otherwise you're not truly done" — codex 2026-07-08 |
| 3 | **Two variants per build**: asm-floor (compiles now) and max-C, with assembly progressively replaced | "Main priority is to get something to compile and be byte accurate even if it starts off requiring embed asm like .s files … Second priority is … replacing the built in assembly with c/c++ … starting from ghidra's output … and moving onto llm based generations" — codex 2026-09-15 |
| 4 | **IDE-ready project + zip** (layout, build files, headers) | §1.4 quotes (D8, 09-08 mission, 09-16 zip) |
| 5 | **Build system and toolchain ("learn the build")** | "*Source code* · *Build system and configuration* · *Compiler/toolchain behavior* · *Symbol and type relationships* · *Dependencies* · *Project structure*" — codex 2026-06-11 (/goal). "seems you're struggling to understand the compiler, the flags, and how they affect the compiled result?" — codex 2026-06-29 |
| 6 | **Cross-build identity with unified names, types and structs, written back to every build** | "function labels and structures are cross matched across all the binaries so updating one specific will update that specific for all" — cursor 2026-09-08 |
| 7 | **Portable signatures, one per entity for all builds** | "Ideally the signature should be the same for ALL the binaries" — cursor 2026-09-08 |
| 8 | **Codecaves + ABI, verified live** | "confirm the codecaves are functional please, find a way to test them backed by reality." — cursor 2026-08-30 |
| 9 | **A Lua bridge / Phasor-style script extender, exported for any program** | "export an equivalent to KotorPhasor or Phasor for whatever binaries AgentDecompile is working with" — cursor 2026-09-08. "LUA scripting + code injection for adding various events and api" — discord 2026-03-30 |
| 10 | **Headers, struct layouts, format specs, bytecode docs** for engine reimplementers | "use it and our Ghidra analysis to produce format specs, struct layouts, and NCS bytecode docs … directly useful to reone/xoreos and the modding community" — cursor 2026-08-08 |
| 11 | **Readiness and divergence reports** (where builds differ, say so and show it) | *(ledger 2026-09-21)* "When the surrounding call-graph/CFG is too different, point it out and display it properly" |
| 12 | **Corpus and per-function call graphs** with cross-build bindings | "Provide corpus and per-function call graphs that show callers, callees, cross-build identity bindings, confidence, and provenance" — cursor 2026-08-31 |
| 13 | **Anything → LLM-readable text trees** (installers, SFX, archives, whole installs → JSON/MD) | §1.3 quotes (codex 2026-06-29; discord 2026-04-15) |
| 14 | **Format-to-format transpiling** | "Machine code to Assembly to C/C++ to Python to GO to hex dumps to ghidra project serialization filedata to anything" — cursor 2026-07-18 |
| 15 | **Context-pack / MCP agent context with puzzle-piece intake** (notes, gzf, .gpr, partial dumps) | "pass in some 'context' which could be e.g. unstructured notes, structured notes, gzf dump, or other ghidra project files" — codex 2026-07-08 |
| 16 | **Ghidra project kept in sync** (shared repo writable, changes saved step by step) | "the shared odyssey repository is NOT read only it should be synced with a local project so the data is available in both." — codex 2026-09-10 |
| 17 | **Headless harness, TAS and softlock detection**, with gameplay videos as proof | "a full functional comprehensive and thorough way to detect and prevent any and all soft locks" — cursor 2026-08-30. "when you live prove things … actually create a video" — codex 2026-09-10 |
| 18 | **Browser/WASM port** using the user's local files (low priority) | §1.11 quotes (codex 2026-09-22) |
| 19 | **Managed/engine projects** (e.g. a full Unity Editor project) and non-C targets | §1.12 quotes |
| 20 | **Mods from a prompt**, the product the pipeline ultimately serves | "what i'd like to do is make another agent that can just create entire mods based on a prompt" — discord 2026-04-01. Example of the one-shot patch ask: "modify fully this program so that the number of party companions … is more than 3" — discord 2026-02-13 |
| 21 | **Packaged install via `uvx`, pointed at a binary** | "`uvx --from git+https://<repo_url> mizuchi-cli <path/to/binary/to/re>`" — codex 2026-07-06 (name later anonymized) |

---

### Method notes
- Excluded as not user-authored: Cursor "user" turns that are agent-dispatched task prompts ("Investigate…", "Repo: …", "You are…"), Codex subagent sessions, pasted AI output, and pasted plans ("A previous agent produced…").
- Directives from unrelated projects (site, infra, ModSync, CLI wrappers) were ignored unless they state a general preference the user applied to AgentDecompile.
- Working files (not deliverables) are in the device session's `~/work/` (`codex_re.txt`, `cx_keep.txt`, `cursor_user.txt`, `discord.txt`).
