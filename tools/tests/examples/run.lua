local F = dofile('tools/tests/examples/fixture.lua')
local passed=0
local function test(path,name,fn)
  F.instances={}
  local ok,err=pcall(function()
    fn(F,path)
    for _,f in ipairs(F.instances) do assert(#f.unexpected==0, table.concat(f.unexpected,",")) end
  end)
  if not ok then error(path..' ['..name..']: '..tostring(err),0) end
  passed=passed+1; print('PASS\t'..path..'\t'..name)
end
for _,suite in ipairs({'showcase','probes_coverage','cursed','harness'}) do
  dofile('tools/tests/examples/'..suite..'.lua')(test)
end
print('CASES\t'..passed)
