-- Private owned-stage diagnostic fixture; not a shipped mod or acceptance claim.
-- Execute via F12 dofile, then begin/fire/stop/cleanup. Reload the owned save if
-- setup or teardown fails; never use this fixture on the original installation.
local F={}
local q=function(name,...) return nwscript.call(name,...) end
local valid=function(o)return o and q('GetIsObjectValid',o)==1 end
local state
local function same_context()
 assert(state and valid(state.pc),'fixture player unavailable')
 assert(kp.model.matches(state.owner),'fixture player identity changed')
 assert(q('GetArea',state.pc)==state.area and q('GetModuleFileName')==state.module,'fixture context changed')
end
local function ranged(base)return base>=12 and base<=24 or base==77 end
local function inventory(pc,right,left)
 local items={};local seen={};local count=0
 local function add(o)
  if valid(o)then items[o]={stack=q('GetItemStackSize',o),base=q('GetBaseItemType',o),owner=q('GetItemPossessor',o),tag=q('GetTag',o)}end
 end
 local o=q('GetFirstItemInInventory',pc)
 while valid(o)do
  assert(not seen[o] and count<512,'inventory enumeration incomplete; reset owned save')
  seen[o]=true;count=count+1;add(o);o=q('GetNextItemInInventory',pc)
 end
 add(right);add(left);return items
end
function F.begin()
 assert(not state,'fixture already started')
 local pc=q('GetFirstPC');assert(valid(pc),'no player')
 assert(q('GetIsInConversation',pc)==0 and q('GetIsInCombat',pc)==0,'peaceful gameplay required')
 local right,left=q('GetItemInSlot',4,pc),q('GetItemInSlot',5,pc)
 local before=inventory(pc,right,left);local gun,rank
 for id,item in pairs(before)do
  if id~=right and id~=left and item.owner==pc and item.stack==1 and ranged(item.base)then
   local priority=item.base==16 and 0 or item.base
   if not rank or priority<rank or priority==rank and id<gun then gun,rank=id,priority end
  end
 end
 assert(gun,'no unequipped single-item ranged weapon to borrow; reset owned save')
 state={pc=pc,owner=assert(kp.model.identify(pc)),area=q('GetArea',pc),module=q('GetModuleFileName'),right=right,left=left,minimum=q('GetMinOneHP',pc),borrowed=gun,inventory_before=before,borrowed_base=before[gun].base}
 state.borrowed_metadata={id=gun,stack=before[gun].stack,tag=before[gun].tag,possessor=before[gun].owner}
 q('SetMinOneHP',pc,1)
 nwscript.with_caller(pc,function()
  q('ClearAllActions')
  if valid(left)then q('ActionUnequipItem',left,1)end
  if valid(right)then q('ActionUnequipItem',right,1)end
  q('ActionEquipItem',gun,4,1)
 end)
 local p=q('GetPosition',pc);local a=math.rad(q('GetFacing',pc))
 local target=q('CreateObject',1,'g_sithtroop01',q('Location',{x=p.x+6*math.cos(a),y=p.y+6*math.sin(a),z=p.z},(q('GetFacing',pc)+180)%360),0)
 assert(valid(target),'target creation failed; reset owned save');state.target=target;state.target_owner=assert(kp.model.identify(target))
 q('SetMinOneHP',target,1);q('SetCommandable',0,target);q('ChangeToStandardFaction',target,1)
 return gun,target,state.borrowed_base
end
-- Read-only diagnostic: retain exact borrowed-item identity guard below.
function F.diagnostic()
 if not state then return 'state=nil' end
 local function safe(name,...)
  local ok,value=pcall(q,name,...)
  if not ok then return 'error:'..tostring(value) end
  return value
 end
 local function typed(value)return type(value)..':'..tostring(value) end
 local function item(value)
  local alive=safe('GetIsObjectValid',value)
  local base=alive==1 and safe('GetBaseItemType',value) or 'not_queried_invalid'
  local kind=alive==1 and safe('GetObjectType',value) or 'not_queried_invalid'
  local tag=alive==1 and safe('GetTag',value) or 'not_queried_invalid'
  local owner=alive==1 and safe('GetItemPossessor',value) or 'not_queried_invalid'
  local stack=alive==1 and safe('GetItemStackSize',value) or 'not_queried_invalid'
  return '{id='..typed(value)..',valid='..typed(alive)..',base='..typed(base)..',object_type='..typed(kind)..
   ',tag='..string.format('%q',tostring(tag))..',possessor='..typed(owner)..',stack='..typed(stack)..'}'
 end
 local right=safe('GetItemInSlot',4,state.pc)
 local left=safe('GetItemInSlot',5,state.pc)
 local scoped_right,scoped_left
 local scoped_ok,scoped_error=pcall(function()
  nwscript.with_caller(state.pc,function()
   scoped_right=q('GetItemInSlot',4,state.pc)
   scoped_left=q('GetItemInSlot',5,state.pc)
  end)
 end)
 local inventory={};local seen={};local current=safe('GetFirstItemInInventory',state.pc);local count=0
 while type(current)=='number' and safe('GetIsObjectValid',current)==1 and not seen[current] and count<32 do
  seen[current]=true;count=count+1;inventory[#inventory+1]=item(current)
  current=safe('GetNextItemInInventory',state.pc)
 end
 local created=state.borrowed_metadata or {}
 return 'resref=unavailable_no_K1_GetResRef_routine,borrowed_initial_stack='..typed(created.stack)..
  ',borrowed_initial_tag='..string.format('%q',tostring(created.tag))..',borrowed_initial_possessor='..typed(created.possessor)..',pc='..typed(state.pc)..',current_pc='..typed(safe('GetFirstPC'))..
  ',expected='..item(state.borrowed)..',right='..item(right)..',left='..item(left)..
  ',right_equals_expected='..tostring(right==state.borrowed)..
  ',scoped_ok='..tostring(scoped_ok)..',scoped_right='..typed(scoped_right)..
  ',scoped_left='..typed(scoped_left)..',scoped_error='..tostring(scoped_error)..
  ',original_right='..item(state.right)..',original_left='..item(state.left)..
  ',inventory_count='..count..',inventory_more='..tostring(type(current)=='number' and safe('GetIsObjectValid',current)==1)..
  ',inventory=['..table.concat(inventory,';')..']'
end
function F.ready()
 same_context();assert(valid(state.target) and kp.model.matches(state.target_owner),'fixture target unavailable')
 return valid(state.borrowed) and q('GetItemPossessor',state.borrowed)==state.pc and q('GetItemStackSize',state.borrowed)==1 and q('GetBaseItemType',state.borrowed)==state.borrowed_base and q('GetItemInSlot',4,state.pc)==state.borrowed and not valid(q('GetItemInSlot',5,state.pc))
end
function F.fire()
 local ready=F.ready()
 assert(ready,'weapon equip has not settled; '..(not ready and F.diagnostic() or ''))
 nwscript.with_caller(state.pc,function()q('ClearAllActions');q('ActionAttack',state.target,0)end)
 return true
end
function F.stop()
 same_context();nwscript.with_caller(state.pc,function()q('ClearAllActions')end);return true
end
function F.cleanup()
 if not state then return true end
 F.stop()
 if valid(state.target)then assert(kp.model.matches(state.target_owner),'refusing reused target');q('DestroyObject',state.target,0)end
 nwscript.with_caller(state.pc,function()
  assert(valid(state.borrowed) and q('GetItemPossessor',state.borrowed)==state.pc and q('GetItemStackSize',state.borrowed)==1 and q('GetBaseItemType',state.borrowed)==state.borrowed_base and q('GetTag',state.borrowed)==state.borrowed_metadata.tag,'borrowed item identity changed; reset owned save')
  q('ActionUnequipItem',state.borrowed,1)
  if valid(state.right)then q('ActionEquipItem',state.right,4,1)end
  if valid(state.left)then q('ActionEquipItem',state.left,5,1)end
 end)
 q('SetMinOneHP',state.pc,state.minimum)
 -- Keep state available to verify deferred engine actions before dropping it.
 return true
end
function F.restored()
 same_context()
 local after=inventory(state.pc,q('GetItemInSlot',4,state.pc),q('GetItemInSlot',5,state.pc))
 for id,item in pairs(state.inventory_before)do local now=after[id];if not now or now.stack~=item.stack or now.base~=item.base or now.owner~=item.owner or now.tag~=item.tag then return false end end
 for id in pairs(after)do if not state.inventory_before[id]then return false end end
 return not valid(state.target) and q('GetItemInSlot',4,state.pc)==state.right and q('GetItemInSlot',5,state.pc)==state.left and q('GetMinOneHP',state.pc)==state.minimum
end
-- Stage 0 read-only diagnostic. Reports the five restored() conditions
-- separately against the begin() snapshot. Uses only query routines and
-- inventory iteration, never raises, and always starts with 'restore_report:'.
-- One snapshot: queued equips or a deferred destroy may not have settled yet.
local conditions={'target_invalid','slot4_restored','slot5_restored','min_one_hp_restored','inventory_unchanged'}
function F.restore_report()
 local marker='restore_report:'
 if not state then return marker..' state=nil',{state=false} end
 local r={state=true,missing={},new={},stack_changed={},other_changed={},errors={}}
 local function try(key,fn)
  local ok,value=pcall(fn)
  if ok then return value end
  r.errors[#r.errors+1]=key..'='..tostring(value);return nil
 end
 r.context_ok=pcall(same_context)
 local right=try('slot4',function()return q('GetItemInSlot',4,state.pc)end)
 local left=try('slot5',function()return q('GetItemInSlot',5,state.pc)end)
 local minimum=try('min_one_hp',function()return q('GetMinOneHP',state.pc)end)
 local target_valid=try('target',function()return valid(state.target)end)
 if target_valid~=nil then r.target_invalid=not target_valid end
 if right~=nil then r.slot4_restored=right==state.right end
 if left~=nil then r.slot5_restored=left==state.left end
 if minimum~=nil then r.min_one_hp_restored=minimum==state.minimum end
 local after=try('inventory',function()return inventory(state.pc,right,left)end)
 if after then
  for id,item in pairs(state.inventory_before)do
   local now=after[id]
   if not now then r.missing[#r.missing+1]=id
   else
    if now.stack~=item.stack then r.stack_changed[#r.stack_changed+1]=id end
    if now.base~=item.base or now.owner~=item.owner or now.tag~=item.tag then r.other_changed[#r.other_changed+1]=id end
   end
  end
  for id in pairs(after)do if not state.inventory_before[id]then r.new[#r.new+1]=id end end
  for _,list in ipairs({r.missing,r.new,r.stack_changed,r.other_changed})do table.sort(list)end
  r.inventory_unchanged=#r.missing==0 and #r.new==0 and #r.stack_changed==0 and #r.other_changed==0
 end
 r.failing={};r.all_pass=true
 for _,key in ipairs(conditions)do if r[key]~=true then r.failing[#r.failing+1]=key;r.all_pass=false end end
 r.values={slot4=right,slot4_expected=state.right,slot5=left,slot5_expected=state.left,borrowed=state.borrowed,
  borrowed_in_slot4=right~=nil and right==state.borrowed,target=state.target,min_one_hp=minimum,min_one_hp_expected=state.minimum}
 local function ids(list,detail)
  local out={}
  for i,id in ipairs(list)do
   if i>32 then out[#out+1]='+'..(#list-32)..' more';break end
   out[#out+1]=detail and detail(id) or tostring(id)
  end
  return '['..table.concat(out,',')..']'
 end
 local function stack(id)
  local now=after and after[id]
  return tostring(id)..':'..tostring(state.inventory_before[id].stack)..'->'..tostring(now and now.stack)
 end
 local v=r.values
 local parts={marker,'all_pass='..tostring(r.all_pass),'failing='..ids(r.failing)}
 for _,key in ipairs(conditions)do parts[#parts+1]=key..'='..tostring(r[key])end
 parts[#parts+1]='missing='..ids(r.missing);parts[#parts+1]='new='..ids(r.new)
 parts[#parts+1]='stack_changed='..ids(r.stack_changed,stack);parts[#parts+1]='other_changed='..ids(r.other_changed)
 parts[#parts+1]='slot4='..tostring(v.slot4)..'/want='..tostring(v.slot4_expected)..',borrowed_in_slot4='..tostring(v.borrowed_in_slot4)
 parts[#parts+1]='slot5='..tostring(v.slot5)..'/want='..tostring(v.slot5_expected)
 parts[#parts+1]='target='..tostring(v.target)..',target_valid='..tostring(target_valid)
 parts[#parts+1]='min_one_hp='..tostring(v.min_one_hp)..'/want='..tostring(v.min_one_hp_expected)
 parts[#parts+1]='context_ok='..tostring(r.context_ok)
 if #r.errors>0 then parts[#parts+1]='errors='..ids(r.errors)end
 return table.concat(parts,' '),r
end
return F
