from pathlib import Path
import re,json,hashlib,ast
R=Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation')
O=Path('/home/brunner56/kp-live-20260922/side-audit')
def link(p,n=1): return f'[{p}]({R/p}:{n})'
rows=[]
for p in sorted(R.glob('scripts/**/*.lua'))+sorted(R.glob('tools/**/*.lua')):
 rel=str(p.relative_to(R)); s=p.read_text()
 if '/fixtures/legacy/' in rel: disposition='retired public example; regression fixture only'
 elif rel.startswith('tools/') or rel.endswith('_test.lua'): disposition='host test with mocked engine; not a live implementation'
 elif rel.endswith('model_scene.lua'): disposition='shared demo helper'
 else: disposition='current script/example'
 calls=sorted(set(re.findall(r'\b(?:q|call|nw|nwscript\.call)\(\s*["\']([A-Z]\w+)["\']',s)+re.findall(r'pcall\((?:nwscript\.call|q|call|nw),\s*["\']([A-Z]\w+)["\']',s)))
 api=sorted(set(re.findall(r'\bkp\.[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?',s)))
 callbacks=re.findall(r'^function\s+(On\w+)\(',s,re.M)
 helpers=sorted(set(re.findall(r'\bfunction\s+([\w.:]+)\s*\(',s)+re.findall(r'\b([\w.]+)\s*=\s*function\s*\(',s)))
 name=p.stem
 side='server-facing gameplay through captured NWScript VM'
 reason='Native routine bridge queries/mutates gameplay objects. The Lua file is local to the injected process; native routine ownership is not encoded in its signature.'
 if disposition.startswith('host test'):
  side='host test only';reason='Mocks/test setup execute outside the real engine; test calls do not prove any game-side execution.'
 elif '/arbitration/' in rel or '/edge_fallback/' in rel or '/edge_number_two/' in rel:
  side='process-local Lua arbitration at server VM hook';reason='Returns override/abstention values for OnRunScript; no direct client/server memory mutation.'
 elif '/edge_quarantine/' in rel:
  side='process-local Lua host test at server OnTick';reason='Deliberately errors to test host quarantine; no game-object mutation.'
 elif name=='00_probe':
  side='observer of server events plus client console and process lifecycle';reason='Logs callbacks only. Some callback names are dead and never fire; see event inventory.'
 elif name=='10_position_trace':
  side='server-facing world observation';reason='OnTick invokes GetFirstPC/GetPosition/GetFacing and logs results.'
 elif '/demos/model-memory/' in rel or name=='two_actor_freeze':
  side='both: server scene setup plus client model/animation';reason='Scene/animation setup uses server-world identity and local-state native routines; spawning configurations also use CreateObject/DestroyObject/faction. player_scale sets spawn=false. kp.model and kp.animation target client model state, with optional server ownership validation.'
 elif name=='object_blaster':
  side='both: projectile presentation and server combat effects';reason='Arms kp.projectiles replacement, which resolves server PC identity and client projectile/model resources; NWScript applies ForcePushed after server attacked-event HP-drop detection.'
 elif name=='10_cover':
  side='both, command dependent';reason='Client console event invokes server-facing world/global/action commands, global fade requests (native side unresolved), autosave, or process-local log; haste controls server MainLoop repeats.'
 elif name=='10_avatar_sync':
  side='peer networking plus local server-facing ghost actors';reason='Each injected process reads its local PC and creates/moves/destroys local ghost creatures through NWScript. Direct symmetric Winsock UDP; no dedicated authority and no world/combat/quest/inventory synchronization. Rendering follows the engine.'
 elif name=='90_bullet_time':
  side='both: server tick pacing and client time/presentation';reason='kp.speed repeats server MainLoop, kp.game_speed changes client timers; native effects/global fades add presentation.'
 elif 'SetGlobalFadeIn' in calls or 'SetGlobalFadeOut' in calls or 'MusicBattlePlay' in calls:
  side='server-facing gameplay plus presentation requests; native presentation route unresolved';reason='Object/effect/action operations target gameplay; global fade/music calls request presentation. This is semantic intent, not proof of a client-side native handler. No direct client-memory write is made by the Lua code; exact native routing remains unresolved.'
 elif 'SpeakString' in calls:
  side='server-facing world/gameplay plus engine speech presentation';reason='Reads/mutates gameplay state through NWScript and requests speech/text. Client display is a downstream engine effect, not a direct Lua client-memory implementation.'
 elif name=='20_dialog_state':
  side='native-VM dialog/world observation; exact split unresolved';reason='Object/speaker queries and GetIsConversationActive run through the captured VM; bridge signatures do not prove the client/server owner of every queried field.'
 elif name=='90_run_script':
  side='server VM script dispatch; invoked script determines effects';reason='ExecuteScript runs the supplied resref on a selected object; downstream client effects depend on that external script.'
 elif name=='80_signal_event':
  side='server object event dispatch';reason='SignalEvent targets a gameplay object; OnOpen text in this file is not a Lua callback registration.'
 rows.append(dict(path=rel,source=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),disposition=disposition,side=side,reason=reason,native_routine_literals=calls,kp_references=api,defined_callbacks=callbacks,defined_function_names=helpers))
(O/'scripts.json').write_text(json.dumps({'scope':'Every Lua file under scripts/ and tools/ in the current worktree; excludes vendored Lua, generated scratch/build trees, and private external experiments. Named native routines are call sites, not implementations written here. Helper functions inherit file classification unless listed by public API separately.','counts':{'scripts_tree':sum(x['path'].startswith('scripts/') for x in rows),'tools_tree':sum(x['path'].startswith('tools/') for x in rows),'total':len(rows)},'scripts':rows},indent=2)+'\n')
md=['# Lua script side inventory','', 'Source-only audit. Native routine call names identify requested operations; the generic bridge does not establish every native handler\'s memory ownership. Public API inventory and actual event-dispatch inventory give the independently traced native boundaries. No new live tests were run.','', '| Lua file | Side / route | Status and evidence |','|---|---|---|']
for x in rows: md.append(f"| {link(x['path'])} | {x['side']} | {x['disposition']}. {x['reason']} |")
md += ['', '## Coverage console commands', '', '| `cover` command | Side |', '|---|---|', '| `help`, `pick` | Process-local logging. `pick` does not select a dialog reply. |','| `setb`, `setn`, `getb`, `getn` | Server-facing global state through native VM. |','| `talk`, `jump`, `module` | Server-facing action/world requests through native VM; talk produces client dialog presentation downstream. |','| `fade0` | Fade request through native VM; exact native handler side unresolved, no direct client-memory call. |','| `autosave` | Native single-player save request; exact client/server handler path is not proven by the bridge signature. |','| `convo` | Native conversation query; exact internal owner unresolved. |','| `haste` | Server MainLoop repeat multiplier via kp.speed. |','', '## Interpretation', '', 'The two-actor freeze demo is mixed, not purely client-side: it creates server-side scene actors before manipulating client animation. Most cursed examples also include fades or speech; a server-facing effect may be rendered by the client without constituting a separate client implementation. The multiplayer avatar example is a separate symmetric UDP experiment from the native KotorPhasor split-process transport. Its ghost template has host-level test evidence; this audit does not establish live or multiplayer acceptance.', '', 'The machine-readable inventory includes hashes, all explicitly named Lua function definitions, registered global callback definitions, public API references, and native routine string literals. It does not mistake event names in comments for implemented callbacks.']
md += ['', '## Built-in engine console commands', '', '`lua status` reports process-local host/runtime state. `lua reload` reloads local Lua states (callbacks may affect either side). `lua exec <code>` executes console Lua in the injected process; its API calls determine engine side. `lua` or unknown lua arguments print help. Entry is the client console seam, not a remote server evaluator. [Implementation]('+str(R/'src/runtime/hook_bodies.cpp')+':951).']
(O/'scripts.md').write_text('\n'.join(md)+'\n')

# Every exact TCP dispatch branch, with independent logical ownership classification.
C='src/harness/commands.cpp'; E='src/harness/engine_k1.cpp'; s=(R/C).read_text()
entries={}
def add(names,side,reason,line=None):
 for name in names.split():
  m=re.search(r'void cmd_'+re.escape(name)+r'\(',s)
  entries[name]={'command':name,'side':side,'reason':reason,'wrapper_source':str(R/C)+':'+str(s[:m.start()].count('\n')+1 if m else 1),'adapter_source':str(R/E)+':'+str(line) if line else None}
add('ping','process-local','Harness/runtime liveness, version and server tick counter; no object mutation.')
add('status','process-local runtime metadata','Build, phase, hook/script counts, local client/server tick counters, and adapter metadata; no direct game-object reads.')
add('state','both, read-only aggregate','Combines runtime state with client GUI/input/timers and server mode/module/pause/world state.',409)
add('events subscribe unsubscribe','process-local event transport','Reads/subscribes the runtime event ring. Each event retains its own origin; this is not a new game event hook.')
add('devtools','process-local console protocol; submitted code can reach either side','status, submit, outcome, output, complete, cancel address the shared local console. Console Lua code determines game effects.')
add('lua','process-local Lua executor; submitted code can reach either side','Runs code in harness Lua state. Native APIs/VM calls determine client/server access.')
add('reload','process-local script host','Reloads scripts; their unload/load callbacks may perform client/server operations.')
add('load_save','both plus local filesystem','Unpacks save resources, accesses client and server app, pauses world timers, routes load requests. Split Server role prepares authoritative save and waits; split Client uses transport request.',679)
add('new_game chargen_select_class chargen_begin_play','client GUI','Native main-menu/class-selection/chargen callbacks; engine may create/load world downstream.',1078)
add('save','client-to-server request','Client SendSaveGameRequest; server consumes/save on subsequent tick.',1305)
add('warp','server','Sets pending module/start-waypoint fields on server app; server loop executes transition.',1328)
add('dialog','both, read-only','Client GUI panel/replies combined with server owner/dialog state.',1388)
add('reply','client dialog selection with server validation','Checks GUI and server dialog agreement; calls SelectReply on the client dialog panel, not directly on server dialog.',1472)
add('dialog_continue','client dialog selection with server validation','Checks combined dialog state, then GUI SetDialogSelection and UpdateDialog.',1535)
add('dialog_skip','server mutation selected through client UI','Resolves GUI owner to server object and calls server SkipPastDialog.',1560)
add('dialog_abort','client primary, server fallback','GUI HandleDialogSelection(-2) when available; otherwise server object StopDialog.',1591)
add('dialog_clear_sound_wait','server mutation selected through client UI','Resolves GUI owner and clears server object.dialog_send_pending.',1618)
add('clear_auto_pause','server','Writes server.pause_state.',1644)
add('speed','client timers','Uses client.set_game_speed; distinct from kp.speed server-loop repetition.',1669)
add('fixed_step','both','Changes fixed snapshot rate on client world/pause/animation and server world/pause timers.',2620)
add('unpause_timers','both','Unpauses client and server world timers and client animation/pause flags.',2098)
add('advance_tutorial finish_hidden_tutorial dismiss_status_summary dismiss_messagebox equipment_screen','client GUI','Native GUI/tutorial/panel operations.',2127)
add('door_use','client-to-server request plus server validation','Validates server door, sends client message handler change_door_state.',2249)
add('door_commit_open','server','Calls door.move_to_next_open_state and checks server door open_state.',2280)
add('door_security','client-to-server request plus server readback','Client message handler unlock_object; server door identity/state validation before and after.',2309)
add('attack','client-to-server request plus server validation','Maps/validates IDs through server, sends client message handler attack.',2417)
add('dismiss_container take_all_container','client GUI','Container panel input handling; take-all causes downstream inventory gameplay.',2492)
add('accept_party_selection','both','Client party-selection GUI/party plus server pause state.',2562)
add('auto_levelup','server mutation through client player selection','Client party PC resolves to server creature/stats; native stats.auto_levelup mutates server stats.',1739)
add('set_party_leader','client party','Client party members/creatures and party.set_leader, verified client slot0.',1805)
add('use_item','client action request','Client actor/target and client_creature.party_menu_use_item. Does not directly call server RunEquip.',1880)
add('equip_item','server mutation through client player selection','Client party leader resolves to server creature/item, calls creature.run_equip and reads server inventory; K1-only gate.',1960)
add('movies','client playback policy','Controls client.play_movies hook suppression.',2663)
add('screenshot','client renderer plus filesystem','Deferred render-thread OpenGL framebuffer read/write, not server-world snapshot.')
add('globals journal','server read-only','Server global-variable or party-journal tables.',2673)
add('quit','process lifecycle','Sets quit request; client loop flushes harness and returns its exit indication. Does not mean a game-server network disconnect.')
names=re.findall(r'cmd == "([^"]+)"',s)
assert len(names)==46 and set(names)==set(entries),(len(names),set(names)^set(entries))
ordered=[entries[n] for n in names]
mods=[]
for p in sorted((R/'scripts/harness/kpharness').glob('*.py')):
 tree=ast.parse(p.read_text()); funcs=[]
 for n in tree.body:
  if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)): funcs.append({'name':n.name,'line':n.lineno})
  elif isinstance(n,ast.ClassDef):
   funcs += [{'name':n.name+'.'+f.name,'line':f.lineno} for f in n.body if isinstance(f,(ast.FunctionDef,ast.AsyncFunctionDef))]
 mods.append({'path':str(p.relative_to(R)),'classification':'external host orchestration; engine side inherited from invoked command/Lua or OS input/capture','functions':funcs,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(O/'harness.json').write_text(json.dumps({'scope':'All 46 in-process TCP commands, six devtools operations, and all Python harness module-level/class functions. Host callbacks do not become engine-server code because the protocol is a TCP server.','commands':ordered,'devtools_operations':['status','submit','outcome','output','complete','cancel'],'python_modules':mods},indent=2)+'\n')
md=['# Harness side inventory','','The Python/CLI/browser harness runs on the external host. Its loopback TCP connection reaches a listener inside the game process; that listener queues work rather than running game calls on the socket thread. Commands drain at game-loop boundaries; post-frame work/screenshot runs from the client frame hook. Engine object ownership and caller thread are distinct.','','| Command | Logical side / route | Evidence |','|---|---|---|']
for x in ordered:
 source=x['adapter_source'] or x['wrapper_source'];md.append(f"| `{x['command']}` | {x['side']} | {x['reason']} [source]({source}) |")
md += ['','## Devtools operations','','All six operations (`status`, `submit`, `outcome`, `output`, `complete`, `cancel`) manage the local console protocol/session. Only submitted Lua makes arbitrary game calls. [Protocol source]('+str(R/'src/harness/console_protocol.cpp')+':203).','','## External harness','','Every module/function listed in harness.json is external host code. Python `Channel.request` sends a JSON command to the injected listener. `lua`/scenario snippets may then reach client or server APIs. Display/input/capture modules manipulate the OS/compositor/rendered output; resource/GFF/BWM/checkpoint/export modules inspect files. Neither is a server-gameplay implementation.','','CLI commands: `boot`, `status`, `state`, `reply`, `exec`, `events`, `shots`, `run`, `down`, `list`, `devtools-bridge`; pioneer subcommands `init`, `step`, `commit`, `discard`, `status`, `attach`, `play`, `fastforward`, `stop`, `reclaim`. They are external host coordinators; native command or Lua payload determines engine-side effects.','','Source inventory includes '+str(len(mods))+' Python modules and '+str(sum(len(x['functions']) for x in mods))+' top-level/class function definitions. This is a side classification, not a claim that every feature is live validated or supported on every build.','','## Build/role limitations','','The adapter uses per-build resolved sites and rejects missing capabilities; the file name engine_k1.cpp does not mean every method is K1-only. `equip_item` explicitly is K1-only. Split Client role does not automatically forward arbitrary harness Lua or direct server-memory mutations to a remote authority. Most commands assume embedded client+server objects; routing must be assessed per command.']
(O/'harness.md').write_text('\n'.join(md)+'\n')
print('script counts',len(rows),sum(x['path'].startswith('scripts/') for x in rows),'harness commands',len(ordered),'Python modules/functions',len(mods),sum(len(x['functions']) for x in mods))
