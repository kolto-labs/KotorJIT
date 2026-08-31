-- Direct-UDP avatar sync: see another KotorPhasor player walk around your game.
--
-- Reverse-engineered from Project [redacted] (MIT-licensed, fan-made,
-- unaffiliated with any publisher; a spiritual continuation of the [redacted]
-- project) to understand the *mechanism*, not to be protocol-compatible with
-- it. [redacted] needed a MinHook proxy DLL, a
-- feat-routine side channel, named shared memory, and half a dozen satellite
-- .exe processes because a slim injected DLL has no other way to reach native
-- code from compiled NWScript. KotorPhasor doesn't have that problem -- Lua
-- already sits where their native hook did -- so this file replaces all of
-- that with: OnTick, the routine bridge, and LuaJIT's ffi calling ws2_32
-- directly. One script, nothing external, no dedicated server process.
--
-- Scope, on purpose ([redacted]' own README draws the same line and for the
-- same reason -- combat/quest/inventory state depends on far more than two
-- creatures agreeing on where they stand): this syncs a remote player's
-- position, facing and name as a placeholder actor. It does not sync combat,
-- dialogue, quests, items, or the world. Both players must be in the same
-- area (compared by area tag) for a peer's actor to appear. Realistically
-- caps out around 2-4 players, same as the project this was reverse-engineered
-- from -- the sync loop is O(peers) per tick with no interest management.
--
-- SETUP: edit the CONFIG block below on every machine, then load the game.
-- The first launch only writes the ghost actor's template into Override and
-- logs that a restart is needed -- KOTOR caches a missing ResRef for the
-- process lifetime, so the template must exist before the game starts asking
-- for it. Second launch onward, it just works.
priority = 0

-- =============================================================================
-- CONFIG -- edit before playing. Every machine in the session needs its own
-- LISTEN_PORT and its own idea of where its peers are.
-- =============================================================================

local LOCAL_NAME    = "Player"        -- shown in kotorphasor.log, not in-game
local LISTEN_PORT   = 39131           -- UDP port this instance listens on
local PEERS = {
    -- One entry per other player. Symmetric: if A lists B, B must list A.
    -- { host = "203.0.113.10", port = 39131 },
}

-- Escape hatch: if the generated ghost template (see GFF section) fails to
-- spawn on your build, point this at any existing, already-loaded creature
-- template resref instead (an existing NPC's resref from the current module
-- works). You lose the inert/non-hostile guarantees the generated template
-- gives you -- the substitute keeps its own scripts and AI package.
local GHOST_TEMPLATE_RESREF = "kp_mp_ghost"

local SEND_INTERVAL_TICKS = 3     -- how often we broadcast our own state
local PEER_TIMEOUT_MS     = 8000  -- despawn a peer's actor if it goes quiet
local MOVE_RUN_THRESHOLD  = 2.0   -- meters/tick delta that plays a run anim

-- =============================================================================
-- byte helpers -- little-endian packers. Stock LuaJIT has no string.pack, and
-- this needs to run identically whether or not this build's LuaJIT has it.
-- =============================================================================

local function q(name, ...)
    if not kotor then return nil end
    local fn = kotor[name]
    if not fn then return nil end
    local ok, v = pcall(fn, ...)
    return ok and v or nil
end

local function u8(n) return string.char(n % 256) end
local function u32(n)
    if n < 0 then n = n + 0x100000000 end
    n = n % 0x100000000
    local b1 = n % 256; n = math.floor(n / 256)
    local b2 = n % 256; n = math.floor(n / 256)
    local b3 = n % 256; n = math.floor(n / 256)
    local b4 = n % 256
    return string.char(b1, b2, b3, b4)
end
local function i32(n) return u32(n) end

-- IEEE-754 single precision, by hand: math.frexp/math.floor are the only
-- primitives every Lua 5.1/LuaJIT build has that this needs.
local function f32bits(x)
    -- Without this, NaN/Inf falls through into math.frexp and the bit math
    -- below, which produces a non-integer/out-of-range byte value -- u32()
    -- then hands string.char a NaN and errors out of the whole script. This
    -- can't reach the network today (drain_incoming rejects non-finite
    -- coordinates before packing anything back out), but f32/f32bits is
    -- also what broadcast() uses to send our OWN position, so a defensive
    -- guard here is what stands between a freak non-finite engine read and
    -- a crashed script rather than one skipped broadcast.
    if x ~= x then return 0x7FC00000 end       -- canonical quiet NaN
    if x == math.huge then return 0x7F800000 end
    if x == -math.huge then return 0xFF800000 end
    if x == 0 then return (1 / x < 0) and 0x80000000 or 0 end
    local sign = 0
    if x < 0 then sign = 1; x = -x end
    local mant, exp = math.frexp(x)  -- x = mant * 2^exp, 0.5 <= mant < 1
    exp = exp - 1
    mant = mant * 2 - 1              -- now in [0, 1), implicit leading 1 dropped
    local biased = exp + 127
    local m = math.floor(mant * 0x800000 + 0.5)
    if m >= 0x800000 then m = 0; biased = biased + 1 end
    return sign * 0x80000000 + biased * 0x800000 + m
end
local function f32(x) return u32(f32bits(x)) end

local function ru32(s, off)
    local b1, b2, b3, b4 = s:byte(off + 1, off + 4)
    return b1 + b2 * 256 + b3 * 65536 + b4 * 16777216
end
local function rf32(s, off)
    local bits = ru32(s, off)
    local sign = (bits >= 0x80000000) and -1 or 1
    if sign < 0 then bits = bits - 0x80000000 end
    local biased = math.floor(bits / 0x800000)
    local mant = bits % 0x800000
    if biased == 0 then
        -- Zero and subnormals both have a zero biased exponent and carry no
        -- implicit leading 1, unlike the normal-number path below. The old
        -- `bits == 0` special case only caught +0.0; -0.0 (sign bit set,
        -- everything else zero) and any real subnormal fell through into the
        -- normal-number formula, which wrongly adds the implicit 1.
        if mant == 0 then return sign * 0.0 end
        return sign * (mant / 0x800000) * (2 ^ -126)
    end
    return sign * (1 + mant / 0x800000) * (2 ^ (biased - 127))
end

-- =============================================================================
-- ghost template -- a hand-built GFF/UTC blueprint, installed into Override on
-- first load. Field set is close to [redacted]' own [redacted]ghost.base.utc
-- (decoded by hand for this project): blank Script* fields so it never runs
-- its own AI, Plot/Min1HP/NoPermDeath/NotReorienting so nothing -- not combat,
-- not death, not the engine's own reorientation -- ever touches it except us.
--
-- This encoder is deliberately narrow: one flat struct, no nested List/Struct
-- fields (so no ClassList/SkillList/FeatList/ItemList). That's the single
-- least-verified part of this file -- it was checked for internal byte
-- consistency (offsets, field/label counts, round-trip decode) with a
-- standalone Lua interpreter, but never loaded by the real engine, since
-- there is no live KOTOR process in the environment this was written in. If
-- the template fails to spawn, switch GHOST_TEMPLATE_RESREF above to an
-- existing template instead of debugging GFF bytes blind.
-- =============================================================================

local GffType = {
    BYTE = 0, CHAR = 1, WORD = 2, SHORT = 3, DWORD = 4, INT = 5,
    FLOAT = 8, CEXOSTRING = 10, RESREF = 11, CEXOLOCSTRING = 12,
}

local function new_gff_builder()
    return {
        fields = {}, labels = {}, label_index = {},
        fielddata = {}, fielddata_len = 0,
    }
end

local function gff_label(b, name)
    local idx = b.label_index[name]
    if idx then return idx end
    idx = #b.labels
    b.labels[#b.labels + 1] = name .. string.rep("\0", 16 - #name)
    b.label_index[name] = idx
    return idx
end

local function gff_push_fielddata(b, bytes)
    local off = b.fielddata_len
    b.fielddata[#b.fielddata + 1] = bytes
    b.fielddata_len = b.fielddata_len + #bytes
    return off
end

local function gff_add_field(b, label, ftype, value)
    local li = gff_label(b, label)
    local dataoroffset
    if ftype == GffType.BYTE or ftype == GffType.CHAR or ftype == GffType.WORD
       or ftype == GffType.SHORT or ftype == GffType.DWORD or ftype == GffType.INT then
        dataoroffset = value
    elseif ftype == GffType.FLOAT then
        dataoroffset = f32bits(value)
    elseif ftype == GffType.CEXOSTRING then
        dataoroffset = gff_push_fielddata(b, u32(#value) .. value)
    elseif ftype == GffType.RESREF then
        local v = value:sub(1, 16)
        dataoroffset = gff_push_fielddata(b, u8(#v) .. v)
    elseif ftype == GffType.CEXOLOCSTRING then
        local body = i32(value.strref or -1) .. u32(#value.strings)
        for _, s in ipairs(value.strings) do
            body = body .. i32((s.lang or 0) * 2 + (s.gender or 0))
                        .. u32(#s.text) .. s.text
        end
        dataoroffset = gff_push_fielddata(b, u32(#body) .. body)
    else
        error("gff_add_field: unsupported type " .. tostring(ftype))
    end
    local fi = #b.fields
    b.fields[#b.fields + 1] = { type = ftype, labelindex = li, dataoroffset = dataoroffset }
    return fi
end

-- One top-level struct, field_specs = { {label=,type=,value=}, ... }.
local function gff_build(field_specs, file_type, file_version)
    local b = new_gff_builder()
    local field_indices = {}
    for _, spec in ipairs(field_specs) do
        field_indices[#field_indices + 1] = gff_add_field(b, spec.label, spec.type, spec.value)
    end

    local fieldindices_blob = ""
    local struct_dataoroffset, struct_fieldcount
    if #field_indices == 0 then
        struct_dataoroffset, struct_fieldcount = 0, 0
    elseif #field_indices == 1 then
        struct_dataoroffset, struct_fieldcount = field_indices[1], 1
    else
        local parts = {}
        for _, fi in ipairs(field_indices) do parts[#parts + 1] = u32(fi) end
        fieldindices_blob = table.concat(parts)
        struct_dataoroffset, struct_fieldcount = 0, #field_indices
    end

    local header_size = 56
    local struct_size = 12  -- exactly one struct: the top-level one
    local field_size = #b.fields * 12
    local label_size = #b.labels * 16
    local fielddata_blob = table.concat(b.fielddata)

    local struct_off = header_size
    local field_off = struct_off + struct_size
    local label_off = field_off + field_size
    local fielddata_off = label_off + label_size
    local fieldindices_off = fielddata_off + #fielddata_blob
    local listindices_off = fieldindices_off + #fieldindices_blob

    local out = {
        file_type, file_version,
        u32(struct_off), u32(1),
        u32(field_off), u32(#b.fields),
        u32(label_off), u32(#b.labels),
        u32(fielddata_off), u32(#fielddata_blob),
        u32(fieldindices_off), u32(#fieldindices_blob),
        u32(listindices_off), u32(0),
        u32(0xFFFFFFFF) .. u32(struct_dataoroffset) .. u32(struct_fieldcount),
    }
    for _, f in ipairs(b.fields) do
        out[#out + 1] = u32(f.type) .. u32(f.labelindex) .. u32(f.dataoroffset)
    end
    for _, l in ipairs(b.labels) do out[#out + 1] = l end
    out[#out + 1] = fielddata_blob
    out[#out + 1] = fieldindices_blob
    return table.concat(out)
end

local function build_ghost_utc()
    local T = GffType
    return gff_build({
        { label = "TemplateResRef", type = T.RESREF, value = GHOST_TEMPLATE_RESREF },
        { label = "Tag", type = T.CEXOSTRING, value = "KP_MP_GHOST" },
        { label = "Comment", type = T.CEXOSTRING,
          value = "KotorPhasor multiplayer avatar placeholder. Generated at "
                .. "runtime by 10_avatar_sync.lua; no vanilla game assets included." },
        { label = "FirstName", type = T.CEXOLOCSTRING,
          value = { strref = -1, strings = { { lang = 0, gender = 0, text = "MP Ghost" } } } },
        { label = "Race", type = T.BYTE, value = 6 },
        { label = "Gender", type = T.BYTE, value = 0 },
        { label = "Appearance_Type", type = T.WORD, value = 17 },
        { label = "FactionID", type = T.WORD, value = 5 },      -- non-hostile
        { label = "WalkRate", type = T.INT, value = 7 },
        { label = "SoundSetFile", type = T.WORD, value = 38 },
        { label = "NotReorienting", type = T.BYTE, value = 1 },
        { label = "NoPermDeath", type = T.BYTE, value = 1 },
        { label = "Min1HP", type = T.BYTE, value = 1 },
        { label = "Plot", type = T.BYTE, value = 1 },
        { label = "IsPC", type = T.BYTE, value = 0 },
        { label = "Interruptable", type = T.BYTE, value = 0 },
        { label = "Disarmable", type = T.BYTE, value = 0 },
        { label = "PartyInteract", type = T.BYTE, value = 0 },
        { label = "Str", type = T.BYTE, value = 10 },
        { label = "Dex", type = T.BYTE, value = 10 },
        { label = "Con", type = T.BYTE, value = 10 },
        { label = "Int", type = T.BYTE, value = 10 },
        { label = "Wis", type = T.BYTE, value = 10 },
        { label = "Cha", type = T.BYTE, value = 10 },
        { label = "CurrentHitPoints", type = T.SHORT, value = 8 },
        { label = "MaxHitPoints", type = T.SHORT, value = 8 },
        { label = "HitPoints", type = T.SHORT, value = 8 },
        { label = "ScriptHeartbeat", type = T.RESREF, value = "" },
        { label = "ScriptOnNotice", type = T.RESREF, value = "" },
        { label = "ScriptSpawn", type = T.RESREF, value = "" },
        { label = "ScriptUserDefine", type = T.RESREF, value = "" },
        { label = "ScriptOnBlocked", type = T.RESREF, value = "" },
        { label = "ScriptAttacked", type = T.RESREF, value = "" },
        { label = "ScriptDamaged", type = T.RESREF, value = "" },
        { label = "ScriptDisturbed", type = T.RESREF, value = "" },
        { label = "ScriptEndRound", type = T.RESREF, value = "" },
        { label = "ScriptDialogue", type = T.RESREF, value = "" },
        { label = "ScriptSpellAt", type = T.RESREF, value = "" },
        { label = "ScriptRested", type = T.RESREF, value = "" },
        { label = "ScriptDeath", type = T.RESREF, value = "" },
        { label = "PaletteID", type = T.BYTE, value = 3 },
    }, "UTC ", "V3.2")
end

-- kp.gamedir is spec-only on this build (docs/user/api-status.md lists it
-- under "Spec only (nil)"), so calling it returns nil rather than a path.
-- Fall back to "." -- relative to the process's own working directory,
-- which is the game install directory on every normal launch (Windows sets
-- cwd to the exe's own folder, and so does Steam) -- so Override/ still
-- resolves without a bound path API. Tries the real API first so this keeps
-- working automatically if a future build binds it.
local function game_dir()
    if kp and kp.gamedir then
        local ok, v = pcall(kp.gamedir)
        if ok and type(v) == "string" and v ~= "" then return v end
    end
    return "."
end

-- Writes the template once. Returns "ready", "installed" (needs a restart to
-- take effect), or "error". Idempotent: checks file presence before writing.
local function ensure_ghost_template()
    local path = game_dir() .. "/Override/" .. GHOST_TEMPLATE_RESREF .. ".utc"

    local existing = io.open(path, "rb")
    if existing then existing:close(); return "ready" end

    local ok, bytes = pcall(build_ghost_utc)
    if not ok then
        print("[mp] failed to build ghost template: " .. tostring(bytes))
        return "error"
    end
    local f, err = io.open(path, "wb")
    if not f then
        print("[mp] cannot write " .. path .. ": " .. tostring(err))
        return "error"
    end
    -- Buffered I/O failures (disk full, quota) often only surface at
    -- close(), not write(); checking write() alone missed them.
    local ok_write = f:write(bytes)
    local ok_close = f:close()
    if not ok_write or not ok_close then
        os.remove(path)
        print("[mp] short write to " .. path .. "; removed the partial file")
        return "error"
    end
    return "installed"
end

-- =============================================================================
-- networking -- LuaJIT ffi straight to ws2_32.dll. Direct IP:port UDP, no
-- discovery, no relay server: every instance sends its own state to every
-- address in PEERS and listens on LISTEN_PORT for the same from them.
-- =============================================================================

local ffi_ok, ffi = pcall(require, "ffi")
local ws2, sock = nil, nil

if ffi_ok then
    pcall(function()
        ffi.cdef[[
        typedef uint32_t SOCKET;
        typedef struct { int16_t sin_family; uint16_t sin_port;
                         uint32_t sin_addr; char sin_zero[8]; } SOCKADDR_IN;
        typedef struct { uint16_t wVersion; uint16_t wHighVersion;
                         char szDescription[257]; char szSystemStatus[129];
                         uint16_t iMaxSockets; uint16_t iMaxUdpDg;
                         char *lpVendorInfo; } WSADATA;

        int __stdcall WSAStartup(uint16_t wVersionRequested, WSADATA *lpWSAData);
        int __stdcall WSACleanup(void);
        SOCKET __stdcall socket(int af, int type, int protocol);
        int __stdcall closesocket(SOCKET s);
        int __stdcall bind(SOCKET s, const void *name, int namelen);
        int __stdcall sendto(SOCKET s, const char *buf, int len, int flags,
                              const void *to, int tolen);
        int __stdcall recvfrom(SOCKET s, char *buf, int len, int flags,
                                void *from, int *fromlen);
        int __stdcall ioctlsocket(SOCKET s, int32_t cmd, uint32_t *argp);
        uint16_t __stdcall htons(uint16_t hostshort);
        uint32_t __stdcall inet_addr(const char *cp);
        char* __stdcall inet_ntoa(uint32_t in);
        int __stdcall WSAGetLastError(void);
        ]]
        ws2 = ffi.load("ws2_32")
    end)
end

local AF_INET, SOCK_DGRAM, IPPROTO_UDP = 2, 2, 17
local INVALID_SOCKET = 0xFFFFFFFF
local FIONBIO = 0x8004667E
local recv_buf, recv_len_arg, addr_in, addr_len_arg, nb_mode

local function make_sockaddr(host, port)
    local a = ffi.new("SOCKADDR_IN")
    a.sin_family = AF_INET
    a.sin_port = ws2.htons(port)
    a.sin_addr = ws2.inet_addr(host)
    return a
end

local function udp_open(port)
    if not ws2 then return nil end
    local wsadata = ffi.new("WSADATA")
    if ws2.WSAStartup(0x0202, wsadata) ~= 0 then return nil end

    local s = ws2.socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
    if s == INVALID_SOCKET then ws2.WSACleanup(); return nil end

    nb_mode = ffi.new("uint32_t[1]", 1)
    if ws2.ioctlsocket(s, FIONBIO, nb_mode) ~= 0 then
        ws2.closesocket(s); ws2.WSACleanup(); return nil
    end

    local a = make_sockaddr("0.0.0.0", port)
    if ws2.bind(s, a, ffi.sizeof(a)) ~= 0 then
        ws2.closesocket(s); ws2.WSACleanup(); return nil
    end

    recv_buf = ffi.new("char[?]", 2048)
    recv_len_arg = 2048
    addr_in = ffi.new("SOCKADDR_IN")
    addr_len_arg = ffi.new("int[1]", ffi.sizeof(addr_in))
    return s
end

local function udp_send(s, host, port, data)
    if not s then return false end
    local a = make_sockaddr(host, port)
    local ok = pcall(ws2.sendto, s, data, #data, 0, a, ffi.sizeof(a))
    return ok
end

-- Drains at most one datagram. Returns bytes, sender_host, sender_port, or
-- nothing when there was nothing to read. The sender address matters: see
-- drain_incoming, which refuses anything not from a configured peer.
local function udp_recv(s)
    if not s then return nil end
    addr_len_arg[0] = ffi.sizeof(addr_in)
    local ok, n = pcall(ws2.recvfrom, s, recv_buf, recv_len_arg, 0, addr_in, addr_len_arg)
    if not ok or n == nil or n < 0 then return nil end
    if n == 0 then return nil end
    local data = ffi.string(recv_buf, n)
    local host_ok, host_ptr = pcall(ws2.inet_ntoa, addr_in.sin_addr)
    local host = (host_ok and host_ptr ~= nil) and ffi.string(host_ptr) or nil
    -- htons is its own inverse (a 16-bit byte swap), so it also decodes.
    local port_ok, port = pcall(ws2.htons, addr_in.sin_port)
    return data, host, port_ok and port or nil
end

-- =============================================================================
-- wire packet -- fixed-size header, two short variable strings.
-- =============================================================================

-- No separate HELLO: a peer's first STATE packet is indistinguishable from,
-- and does the same job as, an explicit join announcement.
local MAGIC, PROTO_VERSION = "KPMP", 1
local MSG_STATE, MSG_BYE = 1, 2
local HEADER_LEN = 4 + 1 + 1 + 4 + 4 + 4 * 4  -- magic+ver+type+id+seq+4 floats = 30

local function pack_packet(msgtype, client_id, seq, x, y, z, facing, area_tag, name)
    area_tag = (area_tag or ""):sub(1, 32)
    name = (name or ""):sub(1, 32)
    return table.concat({
        MAGIC, u8(PROTO_VERSION), u8(msgtype), u32(client_id), u32(seq),
        f32(x), f32(y), f32(z), f32(facing),
        u8(#area_tag), area_tag,
        u8(#name), name,
    })
end

local function unpack_packet(bytes)
    if #bytes < HEADER_LEN + 2 then return nil end
    if bytes:sub(1, 4) ~= MAGIC then return nil end
    if bytes:byte(5) ~= PROTO_VERSION then return nil end
    local off = HEADER_LEN
    local area_len = bytes:byte(off + 1)
    if not area_len or #bytes < off + 1 + area_len + 1 then return nil end
    local area_tag = bytes:sub(off + 2, off + 1 + area_len)
    off = off + 1 + area_len
    local name_len = bytes:byte(off + 1)
    if not name_len or #bytes < off + 1 + name_len then return nil end
    local name = bytes:sub(off + 2, off + 1 + name_len)
    return {
        msgtype = bytes:byte(6),
        client_id = ru32(bytes, 6),
        seq = ru32(bytes, 10),
        x = rf32(bytes, 14), y = rf32(bytes, 18), z = rf32(bytes, 22),
        facing = rf32(bytes, 26),
        area_tag = area_tag, name = name,
    }
end

-- =============================================================================
-- peer / ghost lifecycle
-- =============================================================================

local local_client_id = 0
local send_seq = 0
local peers = {}  -- client_id -> { host, port, seq, x,y,z,facing, area_tag, name,
                   --                last_seen_ms, ghost_id, applied_x/y/z/facing }
local ghost_status = "pending"
local tick_count = 0

-- kp.time is spec-only (nil) on this build, same as kp.gamedir above -- a
-- bare `(kp and kp.time and kp.time()) or 0` would return 0 forever, which
-- makes every peer-timeout comparison `0 - 0 > PEER_TIMEOUT_MS` false: peers
-- would never expire. os.time() (whole seconds, always available) is coarser
-- than a real millisecond clock but is enough for an 8-second timeout.
-- Tries kp.time first so this upgrades automatically if it gets bound later.
local function now_ms()
    if kp and kp.time then
        local ok, v = pcall(kp.time)
        if ok and type(v) == "number" and v > 0 then return v end
    end
    return ((os.time and os.time()) or 0) * 1000
end

local function local_area_tag()
    local pc = q("GetFirstPC")
    if not pc or q("GetIsObjectValid", pc) ~= 1 then return nil end
    local area = q("GetArea", pc)
    if not area then return nil end
    return q("GetTag", area)
end

local function despawn_peer(p)
    if p.ghost_id and q("GetIsObjectValid", p.ghost_id) == 1 then
        q("DestroyObject", p.ghost_id, 0.0, 0, 0.0)
    end
    p.ghost_id = nil
end

local function ensure_peer_ghost(p, pos)
    if p.ghost_id and q("GetIsObjectValid", p.ghost_id) == 1 then
        return p.ghost_id
    end
    local loc = q("Location", pos, p.facing or 0.0)
    if not loc then return nil end
    -- OBJECT_TYPE_CREATURE = 1; bUseAppearAnimation = 0 -- no spawn-in fanfare.
    local id = q("CreateObject", 1, GHOST_TEMPLATE_RESREF, loc, 0)
    if not id or q("GetIsObjectValid", id) ~= 1 then return nil end
    p.ghost_id = id
    p.applied_x, p.applied_y, p.applied_z, p.applied_facing = nil, nil, nil, nil
    return id
end

local function apply_peer_state(p)
    local id = p.ghost_id
    if not id then return end
    local pos = { x = p.x, y = p.y, z = p.z }

    local moved = (p.applied_x == nil)
        or math.abs(p.x - p.applied_x) > 0.05
        or math.abs(p.y - p.applied_y) > 0.05
        or math.abs(p.z - p.applied_z) > 0.05
    if moved then
        local dist = 0
        if p.applied_x then
            local dx, dy = p.x - p.applied_x, p.y - p.applied_y
            dist = math.sqrt(dx * dx + dy * dy)
        end
        q("CutsceneMove", id, pos, dist > MOVE_RUN_THRESHOLD and 1 or 0)
        p.applied_x, p.applied_y, p.applied_z = p.x, p.y, p.z
    end

    if p.applied_facing == nil or math.abs(p.facing - p.applied_facing) > 1.0 then
        if kp and kp.as then
            pcall(kp.as, id, function() q("SetFacing", p.facing) end)
        end
        p.applied_facing = p.facing
    end
end

local function reconcile(my_area)
    local now = now_ms()
    for cid, p in pairs(peers) do
        if now - p.last_seen_ms > PEER_TIMEOUT_MS then
            despawn_peer(p)
            peers[cid] = nil
        elseif not my_area or p.area_tag ~= my_area then
            -- Different area (or ours is unknown, e.g. loading screen): the
            -- peer's actor has no business existing in a world we're not in.
            despawn_peer(p)
        else
            local id = ensure_peer_ghost(p, { x = p.x, y = p.y, z = p.z })
            if id then apply_peer_state(p) end
        end
    end
end

local function broadcast(my_area)
    if not sock or #PEERS == 0 then return end
    local pc = q("GetFirstPC")
    if not pc or q("GetIsObjectValid", pc) ~= 1 then return end
    local pos = q("GetPosition", pc)
    if type(pos) ~= "table" then return end
    local facing = q("GetFacing", pc) or 0.0

    send_seq = send_seq + 1
    local packet = pack_packet(MSG_STATE, local_client_id, send_seq,
                                pos.x, pos.y, pos.z, facing,
                                my_area or "", LOCAL_NAME)
    for _, peer in ipairs(PEERS) do
        udp_send(sock, peer.host, peer.port, packet)
    end
end

-- host+port must exactly match a configured PEERS entry. This design is
-- direct symmetric UDP with no rendezvous server, so for two players to
-- reach each other at all, each side's LISTEN_PORT must already be reachable
-- (a manual port-forward or the same LAN) -- there is no NAT-remapped-port
-- case to tolerate here the way there would be for an outbound-only client.
local function peer_allowed(host, port)
    if not host then return false end
    for _, peer in ipairs(PEERS) do
        if peer.host == host and peer.port == port then return true end
    end
    return false
end

-- Position/facing must be finite and inside a sane world-coordinate range
-- before they ever reach CreateObject/CutsceneMove/SetFacing. rf32 decodes
-- IEEE-754 exponent-255 bit patterns (Inf/NaN) as ordinary large numbers
-- rather than rejecting them, so a malformed or adversarial packet could
-- otherwise hand the engine a coordinate like 2^128.
local MAX_COORD = 100000.0
local function finite_state(p)
    if type(p.x) ~= "number" or type(p.y) ~= "number" or type(p.z) ~= "number"
       or type(p.facing) ~= "number" then
        return false
    end
    if p.x ~= p.x or p.y ~= p.y or p.z ~= p.z or p.facing ~= p.facing then
        return false  -- NaN is the only Lua value that isn't equal to itself
    end
    -- Infinity passes the NaN check above (Inf == Inf), so it needs its own
    -- test; this header comment says "position/facing" must be bounded, but
    -- only x/y/z were actually range-checked here -- a peer packet encoding
    -- facing as +Inf (0x7F800000) would otherwise reach SetFacing unchecked.
    if math.abs(p.x) > MAX_COORD or math.abs(p.y) > MAX_COORD or math.abs(p.z) > MAX_COORD
       or math.abs(p.facing) > MAX_COORD then
        return false
    end
    return true
end

local function drain_incoming()
    if not sock then return end
    for _ = 1, 32 do  -- bounded: never let a packet flood stall the tick
        local data, src_host, src_port = udp_recv(sock)
        if not data then break end
        if peer_allowed(src_host, src_port) then
            local p = unpack_packet(data)
            if p and p.client_id ~= local_client_id and finite_state(p) then
                -- Plain monotonic check, not a wraparound heuristic: seq is a
                -- Lua number (double) that a real session will never come
                -- close to overflowing (2^53 exact-integer packets), so
                -- there is no wraparound to detect. An earlier "or (existing
                -- seq - p.seq) > 1000" guess at handling wraparound instead
                -- made every packet look fresh again once existing.seq
                -- climbed past 1000 -- a couple of minutes at the default
                -- broadcast rate -- silently defeating the stale/out-of-
                -- order rejection this check exists for.
                local existing = peers[p.client_id]
                if not existing or p.seq > existing.seq then
                    if p.msgtype == MSG_BYE then
                        if existing then despawn_peer(existing) end
                        peers[p.client_id] = nil
                    else
                        peers[p.client_id] = {
                            host = src_host, port = src_port,
                            seq = p.seq, x = p.x, y = p.y, z = p.z, facing = p.facing,
                            area_tag = p.area_tag, name = p.name,
                            last_seen_ms = now_ms(),
                            ghost_id = existing and existing.ghost_id,
                            applied_x = existing and existing.applied_x,
                            applied_y = existing and existing.applied_y,
                            applied_z = existing and existing.applied_z,
                            applied_facing = existing and existing.applied_facing,
                        }
                    end
                end
            end
        end
    end
end

-- =============================================================================
-- callbacks
-- =============================================================================

function OnScriptLoad(game, build)
    -- now_ms() alone is only whole-seconds on this build (kp.time is
    -- unbound), so two instances launched in the same second would seed
    -- identically and draw the same client_id, silently disabling their own
    -- sync (each would then discard the other's packets as "self"). Mix in
    -- os.clock() (sub-second, since Lua-state start) and a fresh table's
    -- address (unique per process) as cheap extra entropy that doesn't
    -- depend on any kp.* binding.
    local addr_bits = tonumber(tostring({}):match("0x?(%x+)") or "0", 16) or 0
    math.randomseed(now_ms() + math.floor(((os.clock and os.clock()) or 0) * 1e6) + addr_bits)
    local_client_id = math.random(1, 0x7FFFFFFE)

    ghost_status = ensure_ghost_template()
    if ghost_status == "installed" then
        print("[mp] ghost template written to Override -- restart KOTOR once for it to take effect.")
    elseif ghost_status == "error" then
        print("[mp] could not install the ghost template; avatars will not spawn until fixed.")
    end

    if not ffi_ok then
        print("[mp] LuaJIT ffi unavailable -- networking disabled on this build.")
    else
        sock = udp_open(LISTEN_PORT)
        if not sock then
            print("[mp] failed to open UDP socket on port " .. LISTEN_PORT .. ".")
        else
            print(("[mp] listening on UDP %d, client_id=%08X, %d configured peer(s)")
                  :format(LISTEN_PORT, local_client_id, #PEERS))
        end
    end
end

function OnScriptUnload()
    for _, p in pairs(peers) do despawn_peer(p) end
    if sock then
        local bye = pack_packet(MSG_BYE, local_client_id, send_seq + 1, 0, 0, 0, 0, "", "")
        for _, peer in ipairs(PEERS) do
            udp_send(sock, peer.host, peer.port, bye)
        end
        if ws2 then
            ws2.closesocket(sock)
            ws2.WSACleanup()
        end
    end
    sock = nil
end

function OnTick(tick, relevant)
    tick_count = tick + 1
    -- No peers configured: drain/reconcile would only spin over an
    -- always-empty peers table (peer_allowed() rejects everything when
    -- PEERS is empty), so skip the native VM queries entirely -- mirrors
    -- broadcast()'s own #PEERS == 0 guard.
    if not sock or #PEERS == 0 then return end

    drain_incoming()

    local my_area = local_area_tag()
    reconcile(my_area)

    if tick_count % SEND_INTERVAL_TICKS == 0 then
        broadcast(my_area)
    end
end
