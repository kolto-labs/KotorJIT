# Changelog

## 0.1.0 — 2026-08-30

First public cut. KOTOR 1 Steam (Windows) is the supported game.

What works in a running game:

- 15 hooks install on the unpacked Steam image
- Lua scripts load from `<game>/kotorphasor/scripts`
- `OnRunScript`, `OnTick`, `OnScriptLoad`, `OnConsoleCommand`, `OnSave`, `OnLoad`
- Typed object events that reach `EventHandler` (module load, area enter, creature attacked, and the rest of that set)
- 769 of 772 engine routines as `kotor.<Name>`
- Cheat-console commands `lua exec`, `lua status`, `lua reload`
- `kp.as`, `kotor.registertimer`, `kotor.obj` / `kp.obj`, `kotor.struct` / `kp.struct`, `kotor.mem`

What does not work yet:

- Named callbacks such as `OnCreatureHeartbeat` and `OnDialogConditional` never fire. Filter `OnRunScript` instead.
- `AssignCommand`, `DelayCommand`, and `ActionDoCommand` are not bound
- Most `kp.*` names in `data/hostapi.toml` are not registered (use the names in [docs/user/api-status.md](docs/user/api-status.md))
- KOTOR 2 native Linux is not a 0.1.0 target
- `DelayCommand` resumes (`vm.run_script_situation`) are not hooked

See [docs/user/](docs/user/) for install, scripting, and the full status list.
