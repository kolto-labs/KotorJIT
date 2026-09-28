local items={[440]={base=8,stack=1},[441]={base=5,stack=1},[510]={base=12,stack=4},[513]={base=16,stack=1},[514]={base=18,stack=1}}
local slots={[4]=440,[5]=441};local tags={};local possessor={};local minimum=0;local target=false;local iterator;local destroyed={};local attacks=0
local function inventory()
 local out={};for id in pairs(items)do if id~=slots[4] and id~=slots[5] then out[#out+1]=id end end;table.sort(out);return out
end
nwscript={with_caller=function(_,f)return f()end,call=function(name,...)
 local a={...};local id=a[1]
 if name=='GetFirstPC'then return 1 elseif name=='GetIsObjectValid'then return (id==1 or id==900 and target or items[id]) and 1 or 0
 elseif name=='GetArea'then return 2 elseif name=='GetModuleFileName'then return 'test'
 elseif name=='GetIsInConversation' or name=='GetIsInCombat'then return 0
 elseif name=='GetItemInSlot'then return slots[id] or 2130706432
 elseif name=='GetMinOneHP'then return minimum elseif name=='SetMinOneHP'then if id==1 then minimum=a[2]end
 elseif name=='GetBaseItemType'then return items[id].base elseif name=='GetItemStackSize'then return items[id].stack
 elseif name=='GetItemPossessor'then return possessor[id] or 1 elseif name=='GetTag'then return tags[id] or 'item'..id..'\0'
 elseif name=='GetFirstItemInInventory'then iterator=inventory();return table.remove(iterator,1) or 2130706432
 elseif name=='GetNextItemInInventory'then return table.remove(iterator,1) or 2130706432
 elseif name=='ActionUnequipItem'then for slot,value in pairs(slots)do if value==id then slots[slot]=nil end end
 elseif name=='ActionEquipItem'then slots[a[2]]=id
 elseif name=='GetPosition'then return {x=0,y=0,z=0} elseif name=='GetFacing'then return 0 elseif name=='Location'then return a[1]
 elseif name=='CreateObject'then target=true;return 900
 elseif name=='DestroyObject'then assert(id==900,'borrowed inventory item destroyed');target=false;destroyed[#destroyed+1]=id
 elseif name=='ActionAttack'then attacks=attacks+1
 elseif name=='ClearAllActions' or name=='SetCommandable' or name=='ChangeToStandardFaction'then return
 else error('unexpected engine operation '..name)end
end}
kp={model={identify=function(id)return id end,matches=function()return true end}}
local f=dofile('/home/brunner56/kp-live-20260922/projectile-research/blaster_fixture.lua')
local gun,t,base=f.begin();assert(gun==513 and t==900 and base==16);assert(items[510].stack==4);assert(f.ready());assert(f.fire());assert(attacks==1);assert(f.cleanup());assert(f.restored());assert(slots[4]==440 and slots[5]==441);assert(items[513].stack==1 and items[510].stack==4 and #destroyed==1)
print('borrow selection, exact identity, no inventory deletion, equipment and inventory restoration passed')

-- Stage 0: restore_report() host cases. Every case starts from the all-pass state.
local readonly={GetIsObjectValid=true,GetArea=true,GetModuleFileName=true,GetItemInSlot=true,GetMinOneHP=true,GetBaseItemType=true,GetItemStackSize=true,GetItemPossessor=true,GetTag=true,GetFirstItemInInventory=true,GetNextItemInInventory=true}
local engine=nwscript.call;local throw
local function snapshot()
 local copy={}
 for id,item in pairs(items)do copy[#copy+1]=id..':'..item.base..':'..item.stack end;table.sort(copy)
 return table.concat(copy,',')..'|'..tostring(slots[4])..'|'..tostring(slots[5])..'|'..minimum..'|'..tostring(target)..'|'..#destroyed..'|'..attacks
end
local function report()
 local before=snapshot();local calls={}
 nwscript.call=function(name,...)
  calls[#calls+1]=name;assert(readonly[name],'restore_report issued non-query routine '..name)
  if throw==name then error('mock '..name..' failure')end
  return engine(name,...)
 end
 local ok,text,r=pcall(f.restore_report);nwscript.call=engine
 assert(ok,'restore_report raised: '..tostring(text))
 assert(snapshot()==before,'restore_report mutated mock state')
 assert(type(text)=='string' and text:sub(1,15)=='restore_report:','marker missing: '..tostring(text))
 return text,r,#calls
end
local passed=0
local keys={'target_invalid','slot4_restored','slot5_restored','min_one_hp_restored','inventory_unchanged'}
local function expect(name,failing,check)
 local text,r=report()
 for _,key in ipairs(keys)do assert(r[key]==(key~=failing),name..': '..key..'='..tostring(r[key])..' '..text)end
 assert(r.all_pass==(failing==nil),name..': all_pass');assert(r.all_pass==f.restored(),name..': oracle mismatch with restored()')
 assert(#r.failing==(failing and 1 or 0) and r.failing[1]==failing,name..': failing list '..text)
 if check then check(r,text)end
 passed=passed+1;print('restore_report case passed: '..name..' -> '..text)
end
local function same(list,want)return table.concat(list,',')==table.concat(want,',')end
expect('all five pass',nil,function(r)assert(#r.missing==0 and #r.new==0 and #r.stack_changed==0 and #r.other_changed==0 and r.context_ok)end)
target=true;expect('target still valid','target_invalid',function(r,t)assert(r.values.target==900 and t:find('target_valid=true',1,true))end);target=false
slots[4]=513;expect('slot 4 still holds borrowed gun','slot4_restored',function(r)assert(r.values.slot4==513 and r.values.slot4_expected==440 and r.values.borrowed_in_slot4)end);slots[4]=440
slots[4]=nil;expect('slot 4 empty, right item back in inventory','slot4_restored',function(r)assert(r.values.slot4==2130706432 and not r.values.borrowed_in_slot4)end);slots[4]=440
slots[5]=nil;expect('slot 5 empty, left item back in inventory','slot5_restored',function(r)assert(r.values.slot5==2130706432 and r.values.slot5_expected==441)end);slots[5]=441
minimum=1;expect('min-one-HP left set','min_one_hp_restored',function(r)assert(r.values.min_one_hp==1 and r.values.min_one_hp_expected==0)end);minimum=0
items[510].stack=5;expect('stack change','inventory_unchanged',function(r,t)assert(same(r.stack_changed,{510}) and #r.missing==0 and #r.new==0 and #r.other_changed==0 and t:find('stack_changed=[510:4->5]',1,true))end);items[510].stack=4
local saved=items[514];items[514]=nil;expect('missing id','inventory_unchanged',function(r)assert(same(r.missing,{514}) and #r.new==0 and #r.stack_changed==0)end);items[514]=saved
items[999]={base=16,stack=1};items[552]={base=12,stack=1};expect('new ids','inventory_unchanged',function(r,t)assert(same(r.new,{552,999}) and #r.missing==0 and t:find('new=[552,999]',1,true))end);items[999]=nil;items[552]=nil
saved=items[514];items[514]=nil;items[552]={base=12,stack=1};items[510].stack=3;expect('missing, new and stack change together','inventory_unchanged',function(r)assert(same(r.missing,{514}) and same(r.new,{552}) and same(r.stack_changed,{510}))end);items[514]=saved;items[552]=nil;items[510].stack=4
tags[513]='other\0';expect('tag change','inventory_unchanged',function(r)assert(same(r.other_changed,{513}) and #r.stack_changed==0)end);tags[513]=nil
possessor[441]=7;expect('possessor change','inventory_unchanged',function(r)assert(same(r.other_changed,{441}))end);possessor[441]=nil
items[440].base=9;expect('base change','inventory_unchanged',function(r)assert(same(r.other_changed,{440}))end);items[440].base=8
expect('all five pass after reverting',nil)
throw='GetMinOneHP';do local text,r=report();assert(r.min_one_hp_restored==nil and r.failing[1]=='min_one_hp_restored' and text:find('errors=[',1,true),text);passed=passed+1;print('restore_report case passed: query error is reported, not raised -> '..text)end;throw=nil
throw='GetNextItemInInventory';do local text,r=report();assert(r.inventory_unchanged==nil and r.slot4_restored==true and #r.failing==1,text);passed=passed+1;print('restore_report case passed: inventory error keeps other conditions -> '..text)end;throw=nil
local fresh=dofile('/home/brunner56/kp-live-20260922/projectile-research/blaster_fixture.lua');local text,r=fresh.restore_report();assert(text=='restore_report: state=nil' and r.state==false);passed=passed+1;print('restore_report case passed: state=nil before begin -> '..text)
assert(passed==17,'expected 17 restore_report cases, ran '..passed);print('restore_report host cases passed: '..passed)
