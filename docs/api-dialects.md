# Odyssey names and callbacks

Generated from `data/api_aliases.toml` and `data/events.toml`. Do not edit by hand.

KOTOR is `CServerExoApp` in-process with one hardcoded client. The player is `CServerExoApp::GetFirstPCObject` / NWScript `GetFirstPC`, not a Halo slot id. An object is `CServerExoAppInternal::GetGameObject` / `CSWSPlayer::GetGameObject`, not `getobject`. A message is `SendMessageToPC`.

Host functions use the names the C modules registered (`readbyte`, `registertimer`, `feedback`). Scripts may also write the underscored form. Both spellings are the same C function.

**28 aliases** over **28 functions**.

## Names

| this runtime calls it | also accepts |
|---|---|
| `findsig` | `find_sig` |
| `log` | `log_msg` |
| `readbit` | `read_bit` |
| `readbyte` | `read_byte` |
| `readchar` | `read_char` |
| `readdouble` | `read_double` |
| `readdword` | `read_dword` |
| `readfloat` | `read_float` |
| `readint` | `read_int` |
| `readshort` | `read_short` |
| `readstring` | `read_string` |
| `readwidestring` | `read_wide_string` |
| `readword` | `read_word` |
| `registertimer` | `register_timer` |
| `removetimer` | `remove_timer` |
| `tokenizecmdstring` | `tokenize_cmd_string` |
| `tokenizestring` | `tokenize_string` |
| `writebit` | `write_bit` |
| `writebyte` | `write_byte` |
| `writechar` | `write_char` |
| `writedouble` | `write_double` |
| `writedword` | `write_dword` |
| `writefloat` | `write_float` |
| `writeint` | `write_int` |
| `writeshort` | `write_short` |
| `writestring` | `write_string` |
| `writewidestring` | `write_wide_string` |
| `writeword` | `write_word` |

## Events

Define a global and it is found at load:

```lua
function OnTick(tick, relevant)
    -- ...
end
```

Or register a handler by name at runtime:

```lua
function OnScriptLoad(game, build)
    register_callback(cb.OnTick, "my_tick")
    register_callback(cb.OnModulePlayerEnter, "on_enter")
end
```

A runtime registration wins over a same-named global. `unregister_callback(cb.OnTick)` removes it.

Every event in `data/events.toml` is a field on `cb` (and `events`) with the same name. **111** of them, taken from the decompiled dispatch. Common ones:

| constant | raises |
|---|---|
| `cb.OnTick` | `OnTick` |
| `cb.OnConsoleCommand` | `OnConsoleCommand` |
| `cb.OnModuleLoad` | `OnModuleLoad` |
| `cb.OnModulePlayerEnter` | `OnModulePlayerEnter` |
| `cb.OnCreatureDeath` | `OnCreatureDeath` |
| `cb.OnAreaEnter` | `OnAreaEnter` |
