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
function F.begin()
 assert(not state,'fixture already started')
 local pc=q('GetFirstPC');assert(valid(pc),'no player')
 assert(q('GetIsInConversation',pc)==0 and q('GetIsInCombat',pc)==0,'peaceful gameplay required')
 state={pc=pc,owner=assert(kp.model.identify(pc)),area=q('GetArea',pc),module=q('GetModuleFileName'),right=q('GetItemInSlot',4,pc),left=q('GetItemInSlot',5,pc),minimum=q('GetMinOneHP',pc),items={}}
 q('SetMinOneHP',pc,1)
 local gun=q('CreateItemOnObject','g_w_blstrpstl001',pc,1);assert(valid(gun),'pistol creation failed');state.items[#state.items+1]=gun
 assert(q('GetBaseItemType',gun)==12,'unexpected pistol class')
 nwscript.with_caller(pc,function()
  q('ClearAllActions')
  if valid(state.left)then q('ActionUnequipItem',state.left,1)end
  if valid(state.right)then q('ActionUnequipItem',state.right,1)end
  q('ActionEquipItem',gun,4,1)
 end)
 local p=q('GetPosition',pc);local a=math.rad(q('GetFacing',pc))
 local target=q('CreateObject',1,'g_sithtroop01',q('Location',{x=p.x+6*math.cos(a),y=p.y+6*math.sin(a),z=p.z},(q('GetFacing',pc)+180)%360),0)
 assert(valid(target),'target creation failed');state.target=target;state.target_owner=assert(kp.model.identify(target))
 q('SetMinOneHP',target,1);q('SetCommandable',0,target);q('ChangeToStandardFaction',target,1)
 return gun,target
end
function F.ready()
 same_context();assert(valid(state.target) and kp.model.matches(state.target_owner),'fixture target unavailable')
 return q('GetItemInSlot',4,state.pc)==state.items[1] and not valid(q('GetItemInSlot',5,state.pc))
end
function F.fire()
 assert(F.ready(),'weapon equip has not settled')
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
  for _,item in ipairs(state.items)do if valid(item)then q('ActionUnequipItem',item,1)end end
  if valid(state.right)then q('ActionEquipItem',state.right,4,1)end
  if valid(state.left)then q('ActionEquipItem',state.left,5,1)end
 end)
 for _,item in ipairs(state.items)do if valid(item)then q('DestroyObject',item,0)end end
 q('SetMinOneHP',state.pc,state.minimum)
 -- Keep state available to verify deferred engine actions before dropping it.
 return true
end
function F.restored()
 same_context()
 return not valid(state.target) and q('GetItemInSlot',4,state.pc)==state.right and q('GetItemInSlot',5,state.pc)==state.left and q('GetMinOneHP',state.pc)==state.minimum
end
return F
