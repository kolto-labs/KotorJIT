-- Test-driver observer: reads engine state; never claims an event or mutates actors.
priority = -2000
local previous = {}
local last_speed, original_pc_row
local function q(name,...)
  if not nwscript then return nil end
  local ok,value=pcall(nwscript.call,name,...)
  if ok then return value end
end
function OnTick(tick)
  if tick%10~=0 then return end
  local pc=q('GetFirstPC')
  if q('GetIsObjectValid',pc)~=1 then return end
  if not original_pc_row then original_pc_row=q('GetAppearanceType',pc) end
  local speed=kp.game_speed()
  if speed~=last_speed then kp.print(('[validation:speed] tick=%d speed=%.3f'):format(tick,speed));last_speed=speed end
  local area=q('GetArea',pc)
  local o=q('GetFirstObjectInArea',area,1)
  local copied=0
  for count=1,256 do
    if q('GetIsObjectValid',o)~=1 then break end
    local row,hp,dead=q('GetAppearanceType',o),q('GetCurrentHitPoints',o),q('GetIsDead',o)
    local party=q('IsObjectPartyMember',o)
    local old=previous[o]
    if not old or old.row~=row then
      kp.print(('[validation:appearance] tick=%d id=%u row=%d dead=%d party=%d'):format(tick,o,row or -1,dead or -1,party or -1))
    end
    if old and hp and old.hp and hp<old.hp then kp.print(('[validation:hp] tick=%d id=%u before=%d after=%d dead=%d'):format(tick,o,old.hp,hp,dead or -1)) end
    if party~=1 and row==original_pc_row then copied=copied+1 end
    local types={}
    local e=q('GetFirstEffect',o)
    for index=1,128 do
      if q('GetIsEffectValid',e)~=1 then break end
      local typ=q('GetEffectType',e)
      if typ then types[typ]=(types[typ] or 0)+1 end
      e=q('GetNextEffect',o)
    end
    if old then for typ,n in pairs(types) do
      if n>(old.types[typ] or 0) then kp.print(('[validation:effect] tick=%d id=%u type=%d before=%d after=%d'):format(tick,o,typ,old.types[typ] or 0,n)) end
    end end
    previous[o]={row=row,hp=hp,types=types}
    o=q('GetNextObjectInArea',area,1)
  end
  if copied>=3 then kp.print(('[validation:copies] tick=%d original_row=%d nonparty=%d'):format(tick,original_pc_row,copied)) end
end
