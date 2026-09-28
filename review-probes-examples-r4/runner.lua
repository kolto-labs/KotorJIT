local F = dofile('tools/tests/examples/fixture.lua')
F.sources = assert(dofile(arg[1]))
local function test(path,name,fn)
  if path~='cursed/40_chain_reaction.lua' then return end
  F.instances={}
  local ok,err=pcall(function() fn(F,path) for _,f in ipairs(F.instances) do assert(#f.unexpected==0, 'unexpected: '..table.concat(f.unexpected,",")) end end)
  print((ok and 'PASS' or 'FAIL')..'\t'..name..(ok and '' or '\t'..tostring(err)))
end
dofile('tools/tests/examples/cursed.lua')(test, F)
