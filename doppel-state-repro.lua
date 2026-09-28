local F=dofile('tools/tests/examples/fixture.lua')
local rows={[1]=6,[20]=28}
local f=F.new('cursed/70_doppelganger.lua',{
 GetAppearanceType=function(id)return rows[id]end,
 ApplyEffectToObject=function(_,effect,id)
  if effect.effect=='EffectDisguise' then rows[id]=effect.args[1] end
 end,
}):load()
f:arm(); f.env.OnCreatureAttacked(1,20)
print('original PC=6; current PC='..rows[1]..'; copied enemy='..rows[20])
assert(rows[1]==21,'PC should become Malak')
assert(rows[20]==6,'enemy should wear original player appearance, not new Malak appearance')
