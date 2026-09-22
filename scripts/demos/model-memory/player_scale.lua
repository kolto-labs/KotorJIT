-- Trigger PC local number5=1 in peaceful gameplay. Visible change on first ready tick.
priority=30
local directory=debug.getinfo(1,"S").source:sub(2):match("^(.*[/\\])") or ""
local scene=dofile(directory.."model_scene.lua").new{
  name="player",trigger=1,hold_ticks=90,spawn=false,
  scales={{0.35},{2.4},{1.0},{0.35},{2.4},{1.0}}
}
function OnTick() scene:tick() end
function OnScriptUnload() scene:unload() end
