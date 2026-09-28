from pathlib import Path
import time,hashlib,json,tomllib
base=Path('/home/brunner56/kp-live-20260922/projectile-research')
paths=[base/'blaster_fixture.lua',base/'blaster-fixture-baseline.toml']; receipts=[]
for p in paths:
 old=p.read_bytes();back=p.with_name(p.name+'.before-borrow-'+time.strftime('%Y%m%d-%H%M%S'));back.write_bytes(old);receipts.append({'path':str(p),'backup':str(back),'before':hashlib.sha256(old).hexdigest()})
p=paths[0];s=p.read_text();a=s.index('function F.begin()');b=s.index('-- Read-only diagnostic:',a)
s=s[:a]+'''local function ranged(base)return base>=12 and base<=24 or base==77 end
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
'''+s[b:];s=s.replace('exact created-item identity','exact borrowed-item identity').replace('state.items[1]','state.borrowed').replace('state.created_metadata','state.borrowed_metadata').replace('created_stack=','borrowed_initial_stack=').replace('created_tag=','borrowed_initial_tag=').replace('created_possessor=','borrowed_initial_possessor=')
s=s.replace(" return q('GetItemInSlot',4,state.pc)==state.borrowed and not valid(q('GetItemInSlot',5,state.pc))", " return valid(state.borrowed) and q('GetItemPossessor',state.borrowed)==state.pc and q('GetItemStackSize',state.borrowed)==1 and q('GetBaseItemType',state.borrowed)==state.borrowed_base and q('GetItemInSlot',4,state.pc)==state.borrowed and not valid(q('GetItemInSlot',5,state.pc))")
s=s.replace("  for _,item in ipairs(state.items)do if valid(item)then q('ActionUnequipItem',item,1)end end", "  assert(valid(state.borrowed) and q('GetItemPossessor',state.borrowed)==state.pc and q('GetItemStackSize',state.borrowed)==1 and q('GetBaseItemType',state.borrowed)==state.borrowed_base and q('GetTag',state.borrowed)==state.borrowed_metadata.tag,'borrowed item identity changed; reset owned save')\n  q('ActionUnequipItem',state.borrowed,1)")
s=s.replace(" for _,item in ipairs(state.items)do if valid(item)then q('DestroyObject',item,0)end end\n",'')
s=s.replace(" return not valid(state.target) and", " local after=inventory(state.pc,q('GetItemInSlot',4,state.pc),q('GetItemInSlot',5,state.pc))\n for id,item in pairs(state.inventory_before)do local now=after[id];if not now or now.stack~=item.stack or now.base~=item.base or now.owner~=item.owner or now.tag~=item.tag then return false end end\n for id in pairs(after)do if not state.inventory_before[id]then return false end end\n return not valid(state.target) and")
p.write_text(s)
p=paths[1];s=p.read_text().replace('Object blaster fixture: unmodified pistol baseline','Object blaster fixture: borrowed single ranged-weapon baseline');d=tomllib.loads(s)
steps=d['step'];old=steps[5]['code'];new=old+"; beforeitems={}; local function keep(i) if q('GetIsObjectValid',i)==1 then beforeitems[i]={stack=q('GetItemStackSize',i),base=q('GetBaseItemType',i),owner=q('GetItemPossessor',i),tag=q('GetTag',i)} end end; local i=q('GetFirstItemInInventory',p); local seen={}; local n=0; while q('GetIsObjectValid',i)==1 do assert(not seen[i] and n<512,'inventory enumeration incomplete'); seen[i]=true;n=n+1;keep(i);i=q('GetNextItemInInventory',p) end;keep(oldright);keep(oldleft); return q('GetIsInCombat',p)==0"
new=new.replace("; return q('GetIsInCombat',p)==0; beforeitems",'; beforeitems')
s=s.replace(json.dumps(old),json.dumps(new));s=s.replace('independent equipped pistol and one owned target','independent borrowed ranged weapon identity and one owned target')
old=steps[10]['code'];new=old.replace("if q('GetIsObjectValid',gun)~=1 or q('GetBaseItemType',gun)~=12 then return false end", "local prior=beforeitems[gun]; if not prior or prior.stack~=1 or gun==oldright or gun==oldleft or q('GetIsObjectValid',gun)~=1 or q('GetItemPossessor',gun)~=p or q('GetItemStackSize',gun)~=1 or q('GetBaseItemType',gun)~=prior.base or not (prior.base>=12 and prior.base<=24 or prior.base==77) then return false end; selectedgun=gun;selectedbase=prior.base")
s=s.replace(json.dumps(old),json.dumps(new));s=s.replace('independent target deletion and original equipment restoration','independent target deletion, equipment and exact inventory restoration')
old=steps[19]['code'];new="local q=nwscript.call; local after={};local seen={};local n=0; local function keep(i) if q('GetIsObjectValid',i)==1 then after[i]={stack=q('GetItemStackSize',i),base=q('GetBaseItemType',i),owner=q('GetItemPossessor',i),tag=q('GetTag',i)} end end; local i=q('GetFirstItemInInventory',p); while q('GetIsObjectValid',i)==1 do assert(not seen[i] and n<512,'inventory enumeration incomplete');seen[i]=true;n=n+1;keep(i);i=q('GetNextItemInInventory',p) end;keep(q('GetItemInSlot',4,p));keep(q('GetItemInSlot',5,p)); for id,item in pairs(beforeitems) do local now=after[id];if not now or now.stack~=item.stack or now.base~=item.base or now.owner~=item.owner or now.tag~=item.tag then return false end end; for id in pairs(after) do if not beforeitems[id] then return false end end; return q('GetIsObjectValid',target)==0 and q('GetItemInSlot',4,p)==oldright and q('GetItemInSlot',5,p)==oldleft and q('GetMinOneHP',p)==oldmin"
s=s.replace(json.dumps(old),json.dumps(new));p.write_text(s)
for r,p in zip(receipts,paths):r['after']=hashlib.sha256(p.read_bytes()).hexdigest()
(base/'borrowed-fixture-change.json').write_text(json.dumps(receipts,indent=2));print(json.dumps(receipts,indent=2))
