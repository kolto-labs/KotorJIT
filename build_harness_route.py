from pathlib import Path
import json,hashlib,tomllib
root=Path('/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation')
out=Path('/home/brunner56/kp-live-20260922')
base=tomllib.loads((root/'scripts/harness/scenarios/k1_endar_room3_onward.toml').read_text())
steps=[];manifest=[]
def add(**x):steps.append(x)
def gate(label,code,poll=False,timeout=30):add(label=label,do='assert_lua',code=code,equals=True,poll=poll,timeout=timeout)
def snippet(name,variant=None):
    p=root/'scripts/examples/harness'/name
    raw=p.read_text();effective=raw
    if variant:
        old,new=variant
        assert raw.count(old)==1
        effective=raw.replace(old,new)
    key=name.split('_')[0]+('-configured' if variant else '')
    manifest.append({'path':str(p.relative_to(root)),'sha256':hashlib.sha256(raw.encode()).hexdigest(),'effective_sha256':hashlib.sha256(effective.encode()).hexdigest(),'configuration':variant,'result_key':key})
    add(label='actual example '+name+(' documented configuration' if variant else ' default'),do='lua',code='validation_results=validation_results or {}; validation_results['+json.dumps(key)+']=(function()\n'+effective+'\nend)(); return validation_results['+json.dumps(key)+']',timeout=60)
for n,step in enumerate(base['step']):
    step=dict(step)
    verb=step.get('do');label=step.get('label','')
    if verb=='quit' or (verb=='save' and step.get('checkpoint')=='endar_starboard'):continue
    if verb=='speed':step['scale']=1.0
    if n==2:
        snippet('20_dialog_state.lua')
        gate('dialog snapshot has valid NW integer state','local r=validation_results["20"]; return (r.active==0 or r.active==1) and (r.pc_in==0 or r.pc_in==1) and type(r.partner_dist)=="number"')
        add(do='clear_auto_pause')
        add(do='advance_dialog',until='gameplay',timeout=120)
        snippet('10_world_probe.lua')
        gate('world result invariants and actual PC HP','local r=validation_results["10"]; local pc=nwscript.call("GetFirstPC"); if r.pc.hp~=nwscript.call("GetCurrentHitPoints",pc) or type(r.globals.END_ROOM3_DEAD)~="number" then return false end; local prev=-1; for _,o in ipairs(r.hostiles) do if o.dist<prev or o.dist>60 then return false end; prev=o.dist end; for _,o in ipairs(r.party) do if o.tag=="end_trask" then return true end end; return false')
        snippet('60_area_dump.lua')
        gate('area dump sorted valid creatures and player present','local pc=nwscript.call("GetFirstPC"); local seen=false; local prev=-1; for _,r in ipairs(validation_results["60"]) do if r.dist<prev or nwscript.call("GetIsObjectValid",r.id)~=1 then return false end; prev=r.dist; if r.id==pc then seen=true end end; return seen')
        snippet('40_attack_nearest.lua')
        gate('attack result documents queued, already engaged, or no enemy','local r=validation_results["40"]; return r.queued==true or r.reason=="already engaged" or r.reason=="no live hostile in radius"')
        snippet('70_pc_status.lua')
        gate('PC status real HP, equipment and inventory','local r=validation_results["70"]; local pc=nwscript.call("GetFirstPC"); if r.hp~=nwscript.call("GetCurrentHitPoints",pc) or r.max_hp~=nwscript.call("GetMaxHitPoints",pc) then return false end; for key,tag in pairs(r.slots) do local slot=tonumber(key:sub(5)); local it=nwscript.call("GetItemInSlot",slot,pc); if nwscript.call("GetTag",it):gsub("%z","")~=tag then return false end end; for _,it in ipairs(r.inventory) do if nwscript.call("GetItemPossessor",it.id)~=pc then return false end end; return true')
    if verb=='scripted_door_open' and step.get('tag')=='end_door05':
        snippet('50_doors.lua')
        gate('door default is inspection with matching live fields','local r=validation_results["50"]; return r.queued==nil and r.open==nwscript.call("GetIsOpen",r.id) and r.locked==nwscript.call("GetLocked",r.id) and r.plot==nwscript.call("GetPlotFlag",r.id)')
        snippet('50_doors.lua',('local OPEN = false','local OPEN = true'))
        # Documented driver fallback can finish the animation; its use is explicit.
        steps.append(step)
        gate('door actually open after documented driver completion','return nwscript.call("GetIsOpen",validation_results["50"].id)==1',True,30)
        snippet('30_move_to.lua')
        gate('queued move reaches configured door radius','local pc=nwscript.call("GetFirstPC"); local d=nwscript.call("GetObjectByTag","end_door05",0); return nwscript.call("GetDistanceBetween",pc,d)<=1.75',True,120)
        continue
    if label.startswith('take everything from the nearest stocked metalbox'):
        gate('snapshot actual stocked metalbox items before queue','local pc=nwscript.call("GetFirstPC"); local a=nwscript.call("GetArea",pc); local best,dist=nil,1e9; local o=nwscript.call("GetFirstObjectInArea",a,64); while nwscript.call("GetIsObjectValid",o)==1 do if nwscript.call("GetTag",o):gsub("%z","")=="metalbox" and nwscript.call("GetIsObjectValid",nwscript.call("GetFirstItemInInventory",o))==1 then local d=nwscript.call("GetDistanceBetween",pc,o); if d<dist then best,dist=o,d end end; o=nwscript.call("GetNextObjectInArea",a,64) end; if not best then return false end; validation_loot={box=best,items={},gold=nwscript.call("GetGold",pc)}; local it=nwscript.call("GetFirstItemInInventory",best); while nwscript.call("GetIsObjectValid",it)==1 do validation_loot.items[#validation_loot.items+1]={id=it,tag=nwscript.call("GetTag",it):gsub("%z","")}; it=nwscript.call("GetNextItemInInventory",best) end; return #validation_loot.items>0')
        snippet('110_loot_container.lua')
        gate('queued count identifies exact source container','local r=validation_results["110"]; return r.container==validation_loot.box and r.taken==#validation_loot.items')
        gate('exact container emptied, ordinary items possessed, credits reflected','local pc=nwscript.call("GetFirstPC"); if nwscript.call("GetIsObjectValid",nwscript.call("GetFirstItemInInventory",validation_loot.box))==1 then return false end; local credit=false; for _,it in ipairs(validation_loot.items) do if it.tag:find("credits",1,true) then credit=true elseif nwscript.call("GetItemPossessor",it.id)~=pc then return false end end; return not credit or nwscript.call("GetGold",pc)>validation_loot.gold',True,60)
        continue
    if label=='fire the room5 ambush (area UserDefined 20)':
        snippet('80_signal_event.lua');continue
    if verb=='clear_room' and step.get('until_global')=='END_ROOM5_DEAD':
        gate('event20 produced three authored hostile Sith','local pc=nwscript.call("GetFirstPC"); local n=0; for _,tag in ipairs({"end_cut2_sith1","end_cut2_sith2","end_cut2_sith4"}) do local o=nwscript.call("GetObjectByTag",tag,0); if nwscript.call("GetIsObjectValid",o)==1 and (nwscript.call("GetIsEnemy",o,pc)==1 or nwscript.call("GetIsDead",o)==1) then n=n+1 end end; return n==3',True,60)
    if label=='open the bridge door through its own OnFailToOpen':
        gate('authored bridge script prerequisites','return nwscript.call("GetGlobalNumber","END_ROOM8_DEAD")>=2')
        snippet('90_run_script.lua');continue
    if label=='take the transition to the starboard section':
        snippet('100_module_transition.lua')
        gate('transition default only inspected Endar','local r=validation_results["100"]; return r.module_now:lower():gsub("%z","")=="end_m01aa" and r.requested==nil and r.party==1 and r.door_valid==1')
        snippet('100_module_transition.lua',('local INSPECT = true','local INSPECT = false'));continue
    steps.append(step)
gate('final exact starboard gameplay party state','return nwscript.call("GetModuleName"):lower():gsub("%z","")=="end_m01ab" and nwscript.call("GetPartyMemberCount")==1')
add(screenshot=True,label='final-starboard')
text='name = "Current Lua harness examples through Endar"\ntarget = "k1"\n\n[settings]\ngame_speed = 1.0\nhang_seconds = 90\ndefault_timeout = 240\nload_timeout = 600\n'
for step in steps:
    text+='\n[[step]]\n'
    for k,v in step.items():text+=k+' = '+json.dumps(v,ensure_ascii=True)+'\n'
(out/'harness-examples.toml').write_text(text)
(out/'harness-snippet-manifest.json').write_text(json.dumps(manifest,indent=2))
print(len(steps),'steps;',len(manifest),'exact source/configured executions')
