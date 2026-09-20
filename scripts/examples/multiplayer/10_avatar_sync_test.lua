-- Standalone regression test for 10_avatar_sync.lua. Run with a system
-- LuaJIT (not the game host): `luajit 10_avatar_sync_test.lua` from this
-- directory, or point SCRIPT_PATH elsewhere.
--
-- This drives the REAL shipped script (loaded via loadfile, unmodified) with
-- mocked nwscript/kp surfaces, reaching into the loaded chunk's own
-- closures via debug.getupvalue/setupvalue to inject test packets and stub
-- the two things that genuinely need a live OS socket (udp_recv/udp_send) --
-- everything else (GFF encoding, packet framing, peer/ghost lifecycle,
-- area-gating, timeout, sender validation, NaN/Inf rejection) runs for real.
--
-- Not covered here, because it needs a live game process: whether the
-- generated .utc blueprint actually loads in KOTOR, and whether the raw
-- ws2_32 socket calls behave as expected outside this mock.

local SCRIPT_DIR = (arg and arg[0] and arg[0]:match("(.*/)")) or "./"
local SCRIPT_PATH = SCRIPT_DIR .. "10_avatar_sync.lua"
local FAKE_GAMEDIR = os.tmpname() .. "_kpmp_test"
os.execute("mkdir -p '" .. FAKE_GAMEDIR .. "/Override'")

local failures = 0
local function check(cond, msg)
    if not cond then
        failures = failures + 1
        io.stderr:write("FAIL: " .. msg .. "\n")
    end
end

-- ---- upvalue helpers --------------------------------------------------------
local function find_upval(f, name)
    local i = 1
    while true do
        local n = debug.getupvalue(f, i)
        if not n then return nil end
        if n == name then return i end
        i = i + 1
    end
end
local function get_up(f, name)
    local i = find_upval(f, name)
    assert(i, "no such upvalue: " .. name)
    local _, v = debug.getupvalue(f, i)
    return v
end
local function set_up(f, name, value)
    local i = find_upval(f, name)
    assert(i, "no such upvalue: " .. name)
    debug.setupvalue(f, i, value)
end

-- ---- mocked nwscript/kp surfaces, with call logging -------------------------
local calls = {}
local function log_call(name, ...) calls[#calls + 1] = { name, ... } end

local pc_pos = { x = 0.0, y = 0.0, z = 0.0 }
local pc_facing = 0.0
local objects = { [1] = { valid = true } }
local next_obj_id = 2
local area_obj, other_area_obj = 999, 998
local pc_area = area_obj
local clock_ms = 1000

local engine_routines = {
    GetFirstPC = function() return 1 end,
    GetIsObjectValid = function(id) return (objects[id] and objects[id].valid) and 1 or 0 end,
    GetArea = function(pc) return pc_area end,
    GetTag = function(obj)
        if obj == area_obj then return "area_a" end
        if obj == other_area_obj then return "area_b" end
        return "obj_" .. tostring(obj)
    end,
    GetPosition = function(pc) return pc_pos end,
    GetFacing = function(pc) return pc_facing end,
    Location = function(pos, facing) return { pos = pos, facing = facing } end,
    CreateObject = function(otype, template, loc, anim)
        local id = next_obj_id; next_obj_id = next_obj_id + 1
        objects[id] = { valid = true, template = template, loc = loc }
        log_call("CreateObject", template)
        return id
    end,
    DestroyObject = function(id)
        if objects[id] then objects[id].valid = false end
        log_call("DestroyObject", id)
    end,
    CutsceneMove = function(id, pos, run)
        objects[id].pos = { pos.x, pos.y, pos.z }
        log_call("CutsceneMove", id, pos.x, pos.y, pos.z, run)
    end,
    SetFacing = function(f) log_call("SetFacing", f) end,
}
nwscript = {
    call = function(name, ...)
        local fn = engine_routines[name]
        assert(fn, "unexpected NWScript routine " .. tostring(name))
        return fn(...)
    end,
}
kp = {
    gamedir = function() return FAKE_GAMEDIR end,
    time = function() return clock_ms end,
    as = function(id, fn) return fn() end,
}
kp.print = function(...)
    local parts = {}
    for i, v in ipairs({ ... }) do parts[i] = tostring(v) end
    io.stderr:write("[log] " .. table.concat(parts, "\t") .. "\n")
end

-- ---- load the real script ---------------------------------------------------
local chunk = assert(loadfile(SCRIPT_PATH))
assert(pcall(chunk))
assert(OnScriptLoad and OnTick and OnScriptUnload, "callbacks not defined")

OnScriptLoad("k1", "k1_steam_103")

local drain_incoming = get_up(OnTick, "drain_incoming")
local reconcile = get_up(OnTick, "reconcile")
local broadcast = get_up(OnTick, "broadcast")

local pack_packet = get_up(broadcast, "pack_packet")
local MSG_STATE = get_up(broadcast, "MSG_STATE")
local MSG_BYE = get_up(drain_incoming, "MSG_BYE")

-- =============================================================================
-- 1) ghost template: written once, self-consistent GFF bytes, idempotent
-- =============================================================================
do
    local path = FAKE_GAMEDIR .. "/Override/kp_mp_ghost.utc"
    local f = io.open(path, "rb")
    check(f ~= nil, "ghost template was not written to " .. path)
    local bytes = f and f:read("*a") or ""
    if f then f:close() end

    local function ru32(s, off)
        local b1, b2, b3, b4 = s:byte(off + 1, off + 4)
        return b1 + b2 * 256 + b3 * 65536 + b4 * 16777216
    end
    check(bytes:sub(1, 4) == "UTC ", "ghost template missing UTC magic")
    check(bytes:sub(5, 8) == "V3.2", "ghost template missing V3.2 version")
    local struct_off, struct_count = ru32(bytes, 8), ru32(bytes, 12)
    local field_off, field_count = ru32(bytes, 16), ru32(bytes, 20)
    local label_off, label_count = ru32(bytes, 24), ru32(bytes, 28)
    local fielddata_off, fielddata_size = ru32(bytes, 32), ru32(bytes, 36)
    check(struct_off == 56 and struct_count == 1, "top-level struct header wrong")
    check(field_off == 68, "field array does not follow the struct")
    check(label_off == field_off + field_count * 12, "label array offset wrong")
    check(fielddata_off == label_off + label_count * 16, "field-data offset wrong")
    check(fielddata_off + fielddata_size <= #bytes, "field data runs past end of file")

    local mtime1 = bytes
    OnScriptLoad("k1", "k1_steam_103")
    local f2 = io.open(path, "rb")
    local mtime2 = f2 and f2:read("*a") or ""
    if f2 then f2:close() end
    check(mtime1 == mtime2, "second OnScriptLoad rewrote an existing template")
end

-- OnScriptLoad's own udp_open() fails on Linux (no ws2_32), so sock stays
-- nil after every real call above. Force it non-nil now, after the last
-- OnScriptLoad call, so the behavioral tests below reach OnTick's body --
-- udp_recv/udp_send are stubbed below and never touch sock for real. Read
-- local_client_id here too, after the last OnScriptLoad call, since it is
-- re-randomized on every call -- caching it earlier would go stale the
-- moment the idempotency re-check above called OnScriptLoad a second time.
set_up(OnTick, "sock", "FAKE_SOCKET")
-- Configure one peer so peer_allowed() has something to match against.
set_up(broadcast, "PEERS", { { host = "127.0.0.1", port = 39999 } })
local local_client_id = get_up(drain_incoming, "local_client_id")

-- =============================================================================
-- 2) wire packet: round-trip, and truncated/garbage input fails closed
-- =============================================================================
do
    local unpack_packet = get_up(drain_incoming, "unpack_packet")
    local cases = {
        { MSG_STATE, 12345, 1, 0, 0, 0, 0, "", "Bob" },
        { MSG_STATE, 4294967295, 999, 123.456, -78.9, 0.0, 271.5, "tar_m02ab", "Alice the Long-Named Jedi X" },
        { MSG_BYE, 1, 2, 0, 0, 0, 0, "danm14", "" },
    }
    for i, c in ipairs(cases) do
        local raw = pack_packet(unpack(c))
        local p = unpack_packet(raw)
        check(p ~= nil, "case " .. i .. " failed to unpack")
        if p then
            check(p.msgtype == c[1] and p.client_id == c[2] and p.seq == c[3], "case " .. i .. " header mismatch")
            check(math.abs(p.x - c[4]) < 1e-3 and math.abs(p.facing - c[7]) < 1e-3, "case " .. i .. " float mismatch")
            check(p.area_tag == c[8]:sub(1, 32) and p.name == c[9]:sub(1, 32), "case " .. i .. " string mismatch")
        end
    end
    check(unpack_packet("") == nil, "empty input must not unpack")
    check(unpack_packet("XXXX") == nil, "bad magic must not unpack")
    check(unpack_packet(pack_packet(MSG_STATE, 1, 1, 0, 0, 0, 0, "", ""):sub(1, 20)) == nil,
          "truncated packet must not unpack")

    -- Zero and negative zero round-trip correctly through the hand-rolled
    -- f32/rf32 codec (subnormal-magnitude values are out of scope: no real
    -- world coordinate is anywhere near that small, and MAX_COORD/finite_state
    -- already reject values far larger than where that would even matter).
    local f32 = get_up(pack_packet, "f32")
    local rf32 = get_up(unpack_packet, "rf32")
    for _, v in ipairs({ 0.0, -0.0, 1.0, -1.0, 3.14159265, -123.456 }) do
        local back = rf32(f32(v), 0)
        check(math.abs(back - v) <= math.abs(v) * 1e-5 + 1e-9,
              ("f32/rf32 round-trip mismatch for %g -> %g"):format(v, back))
    end
end

-- ---- packet-injection plumbing for the behavioral tests below ---------------
local incoming_queue = {}
set_up(drain_incoming, "udp_recv", function(s)
    local item = table.remove(incoming_queue, 1)
    if not item then return nil end
    return item[1], item[2], item[3]
end)
set_up(broadcast, "udp_send", function(s, host, port, data) log_call("udp_send", host, port); return true end)

local ALLOWED_HOST, ALLOWED_PORT = "127.0.0.1", 39999
local function inject(msgtype, client_id, seq, x, y, z, facing, area_tag, name, from_host, from_port)
    incoming_queue[#incoming_queue + 1] = {
        pack_packet(msgtype, client_id, seq, x, y, z, facing, area_tag, name),
        from_host or ALLOWED_HOST, from_port or ALLOWED_PORT,
    }
end

-- =============================================================================
-- 3) a peer in our area spawns a ghost and gets moved
-- =============================================================================
calls = {}
inject(MSG_STATE, 42, 1, 10.0, 20.0, 0.0, 90.0, "area_a", "Bob")
OnTick(1, true)
do
    local spawned = false
    for _, c in ipairs(calls) do if c[1] == "CreateObject" then spawned = true end end
    check(spawned, "expected a spawn on first sighting of a same-area peer")
end

calls = {}
inject(MSG_STATE, 42, 2, 15.0, 25.0, 0.0, 100.0, "area_a", "Bob")
OnTick(2, true)
do
    local moved, spawned_again = false, false
    for _, c in ipairs(calls) do
        if c[1] == "CutsceneMove" then moved = true end
        if c[1] == "CreateObject" then spawned_again = true end
    end
    check(moved, "expected CutsceneMove after the peer's position changed")
    check(not spawned_again, "must not respawn a ghost that is still valid")
end

-- =============================================================================
-- 4) unchanged position -> no redundant CutsceneMove
-- =============================================================================
calls = {}
inject(MSG_STATE, 42, 3, 15.0, 25.0, 0.0, 100.0, "area_a", "Bob")
OnTick(3, true)
do
    local redundant = false
    for _, c in ipairs(calls) do if c[1] == "CutsceneMove" then redundant = true end end
    check(not redundant, "identical position should not re-issue CutsceneMove")
end

-- =============================================================================
-- 5) cross-area peer despawns immediately, same-area peer respawns
-- =============================================================================
calls = {}
inject(MSG_STATE, 42, 4, 15.0, 25.0, 0.0, 100.0, "area_b", "Bob")
OnTick(4, true)
do
    local despawned = false
    for _, c in ipairs(calls) do if c[1] == "DestroyObject" then despawned = true end end
    check(despawned, "expected despawn when the peer reports a different area")
end

calls = {}
inject(MSG_STATE, 42, 5, 15.0, 25.0, 0.0, 100.0, "area_a", "Bob")
OnTick(5, true)
do
    local respawned = false
    for _, c in ipairs(calls) do if c[1] == "CreateObject" then respawned = true end end
    check(respawned, "expected a fresh spawn once the peer is back in our area")
end

-- =============================================================================
-- 6) MSG_BYE despawns and forgets the peer immediately
-- =============================================================================
calls = {}
inject(MSG_BYE, 42, 6, 0, 0, 0, 0, "area_a", "")
OnTick(6, true)
do
    local peers = get_up(drain_incoming, "peers")
    local bye_despawn = false
    for _, c in ipairs(calls) do if c[1] == "DestroyObject" then bye_despawn = true end end
    check(bye_despawn, "expected despawn on MSG_BYE")
    check(peers[42] == nil, "peer should be forgotten after MSG_BYE")
end

-- =============================================================================
-- 7) stale peer times out and is despawned
-- =============================================================================
inject(MSG_STATE, 7, 1, 1.0, 1.0, 0.0, 0.0, "area_a", "Timeout Guy")
OnTick(7, true)
clock_ms = clock_ms + 999999
calls = {}
OnTick(8, true)
do
    local peers = get_up(drain_incoming, "peers")
    local timeout_despawn = false
    for _, c in ipairs(calls) do if c[1] == "DestroyObject" then timeout_despawn = true end end
    check(peers[7] == nil, "peer 7 should have timed out and been forgotten")
    check(timeout_despawn, "expected despawn on timeout")
end

-- =============================================================================
-- 8) self-originated and stale/out-of-order packets are rejected
-- =============================================================================
calls = {}
inject(MSG_STATE, local_client_id, 1, 5, 5, 0, 0, "area_a", "Me")
OnTick(9, true)
check(#calls == 0, "a packet with our own client_id must be ignored entirely")

inject(MSG_STATE, 55, 10, 1, 1, 0, 0, "area_a", "Seq")
OnTick(10, true)
inject(MSG_STATE, 55, 3, 999, 999, 0, 0, "area_a", "Seq")  -- stale, lower seq
OnTick(11, true)
do
    local p55 = get_up(drain_incoming, "peers")[55]
    check(p55.x == 1 and p55.y == 1, "a lower/stale seq number must not overwrite newer state")
end

-- =============================================================================
-- 9) packets from a non-configured sender are dropped entirely
-- =============================================================================
calls = {}
inject(MSG_STATE, 999, 1, 1, 1, 0, 0, "area_a", "Spoofer", "10.0.0.99", 4444)
OnTick(12, true)
do
    local peers = get_up(drain_incoming, "peers")
    check(peers[999] == nil, "a packet from an unconfigured sender must not create peer state")
end

-- =============================================================================
-- 10) NaN/Infinity coordinates are rejected before reaching the engine
-- =============================================================================
calls = {}
local nan = 0 / 0
inject(MSG_STATE, 321, 1, nan, 0, 0, 0, "area_a", "Nan")
OnTick(13, true)
do
    local peers = get_up(drain_incoming, "peers")
    check(peers[321] == nil, "NaN coordinates must not create peer state")
end

calls = {}
local inf = 1 / 0
inject(MSG_STATE, 322, 1, inf, 0, 0, 0, "area_a", "Inf")
OnTick(14, true)
do
    local peers = get_up(drain_incoming, "peers")
    check(peers[322] == nil, "Infinite coordinates must not create peer state")
end

-- Infinity in facing specifically: Inf == Inf is true in Lua, so the NaN
-- self-inequality check does not catch it -- only a magnitude check does.
calls = {}
inject(MSG_STATE, 323, 1, 0, 0, 0, inf, "area_a", "InfFacing")
OnTick(15, true)
do
    local peers = get_up(drain_incoming, "peers")
    check(peers[323] == nil, "Infinite facing must not create peer state")
end

-- =============================================================================
-- 11) a stale/replayed packet is rejected even past seq 1000
-- =============================================================================
-- Regression test: an earlier "(existing.seq - p.seq) > 1000" wraparound
-- heuristic treated any packet as "fresher" once the tracked seq climbed
-- past 1000 -- real sessions reach that in a couple of minutes -- silently
-- defeating stale/replay rejection. The fix is a plain monotonic check.
inject(MSG_STATE, 777, 1500, 50, 50, 0, 0, "area_a", "HighSeq")
OnTick(16, true)
inject(MSG_STATE, 777, 5, 999, 999, 0, 0, "area_a", "HighSeq")  -- stale replay
OnTick(17, true)
do
    local p777 = get_up(drain_incoming, "peers")[777]
    check(p777 ~= nil and p777.seq == 1500 and p777.x == 50,
          "a stale replay with seq far below the tracked seq must still be rejected")
end

-- =============================================================================
-- 12) OnScriptUnload runs cleanly
-- =============================================================================
do
    local ok, err = pcall(OnScriptUnload)
    check(ok, "OnScriptUnload raised: " .. tostring(err))
end

if failures == 0 then
    print("OK: all checks passed")
    os.exit(0)
else
    print(("FAILED: %d check(s) did not pass"):format(failures))
    os.exit(1)
end
