-- Trigger PC local number5=2. Three owned, command-disabled humanoids; no combat.
priority=30
local directory=debug.getinfo(1,"S").source:sub(2):match("^(.*[/\\])") or ""
local scene=dofile(directory.."model_scene.lua").new{
  name="wave",trigger=2,hold_ticks=90,spawn=true,resref="g_sithtroop01",faction=2,
  scales={{0.4,2.0,0.4},{2.0,0.4,2.0},{1.0,1.0,1.0},
          {0.4,2.0,0.4},{2.0,0.4,2.0},{1.0,1.0,1.0}}
}
function OnTick() scene:tick() end
function OnScriptUnload() scene:unload() end
