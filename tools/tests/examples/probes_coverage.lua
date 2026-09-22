return function(test)
test('probe/00_probe.lua','every observer abstains; throttle and sidecar',function(F,p)
 local f=F.new(p):load()
 for name,fn in pairs(f.env) do if type(fn)=='function' and name:match('^On') and name~='OnSave' then
  assert(select('#',fn('test',1,1,true))==0,name)
 end end
 assert(f.env.OnSave()=='cave-witness')
 local before=#f.prints; for i=2,99 do f.env.OnTick(i) end; assert(#f.prints==before)
 f.env.OnTick(100); assert(f:has('OnTick x100'))
end)
test('probe/10_position_trace.lua','poll and strict movement thresholds',function(F,p)
 local f=F.new(p):load(); f.env.OnTick(9); assert(#f.calls==0)
 f.env.OnTick(10); assert(#f.prints==1); f.objects[1].x=.02; f.env.OnTick(20); assert(#f.prints==1)
 f.objects[1].x=.021; f.env.OnTick(30); assert(#f.prints==2)
 f.overrides.GetIsObjectValid=function() return 0 end; f.env.OnTick(40); assert(#f.prints==2)
end)
local cases={
 {'setb flag 0','SetGlobalBoolean','flag',0}, {'setn count 7','SetGlobalNumber','count',7},
 {'getb flag','GetGlobalBoolean','flag'}, {'getn count','GetGlobalNumber','count'},
 {'talk bastila dialog','ActionStartConversation',2,'dialog',caller=1},
 {'jump bastila','JumpToObject',2,1,caller=1}, {'fade0','SetGlobalFadeIn',0},
 {'module end_m01ab','StartNewModule','end_m01ab'}, {'autosave','DoSinglePlayerAutoSave'},
 {'convo','GetIsConversationActive'},
}
for _,c in ipairs(cases) do test('coverage/10_cover.lua',c[1],function(F,p)
 local f=F.new(p):load(); assert(f.env.OnConsoleCommand('cover '..c[1],true)==false)
 local call=assert(f:last(c[2])); if c[3]~=nil then assert(call.args[1]==c[3]) end
 if c[4]~=nil then assert(call.args[2]==c[4]) end; assert(call.caller==c.caller)
end) end
test('coverage/10_cover.lua','prefix rejection, help, pick, haste and missing target',function(F,p)
 local f=F.new(p):load(); for _,s in ipairs({'covering','xcover',23}) do assert(select('#',f.env.OnConsoleCommand(s))==0) end
 assert(#f.calls==0 and #f.prints==0)
 f.env.OnConsoleCommand('cover'); assert(f:has('setb <name>'))
 f.env.OnConsoleCommand('cover pick 3'); assert(f:has('pick=3') and #f.calls==0)
 f.env.OnConsoleCommand('cover haste 100'); assert(f:has('speed=16'))
 f.env.OnConsoleCommand('cover talk absent'); assert(f:count('ActionStartConversation')==0 and f:has('no object absent'))
 f.env.OnConsoleCommand('cover jump absent'); assert(f:count('JumpToObject')==0)
end)
end
