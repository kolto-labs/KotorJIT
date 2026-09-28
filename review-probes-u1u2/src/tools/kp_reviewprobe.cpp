// Reviewer's adversarial probes for U1 (kp.vec) and U2 (function timers).
// Bare LuaJIT states: timers with no owning Script (budget path not exercised
// here; kp_supporttest covers that), vec with the host's debug-lib stripping.
#include <cmath>
#include <cstdio>
#include <cstring>
#include <set>

#include "api/output.hpp"
#include "api/timers.hpp"
#include "api/vector.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}

using namespace kp;

static unsigned g_fail = 0, g_n = 0;
static void check(bool c, const char* what) {
    ++g_n;
    std::printf("  %-70s %s\n", what, c ? "ok" : "FAIL");
    if (!c) ++g_fail;
}

static lua_State* fresh() {
    lua_State* L = luaL_newstate();
    luaL_openlibs(L);
    // Same stripping as lua::Script::load (host.cpp:133-138).
    lua_getglobal(L, "debug");
    lua_pushnil(L); lua_setfield(L, -2, "getmetatable");
    lua_pushnil(L); lua_setfield(L, -2, "setmetatable");
    lua_pushnil(L); lua_setfield(L, -2, "getregistry");
    lua_pop(L, 1);
    api::register_timers(L);
    api::register_vector(L);
    return L;
}

static bool run(lua_State* L, const char* name, const char* chunk) {
    const int base = lua_gettop(L);
    bool ok = luaL_loadbuffer(L, chunk, std::strlen(chunk), name) == 0 && lua_pcall(L, 0, 0, 0) == 0;
    if (!ok) std::printf("    %s: %s\n", name, lua_tostring(L, -1));
    lua_settop(L, base);
    return ok;
}

static bool eval_bool(lua_State* L, const char* expr) {
    const int base = lua_gettop(L);
    bool r = false;
    if (luaL_loadstring(L, expr) == 0 && lua_pcall(L, 0, 1, 0) == 0) r = lua_toboolean(L, -1);
    else std::printf("    eval '%s': %s\n", expr, lua_tostring(L, -1));
    lua_settop(L, base);
    return r;
}

static std::uint64_t g_now = 1000;
static unsigned pump_to(std::uint64_t to) {
    unsigned n = 0;
    while (g_now < to) { g_now += 50; n += api::timers::pump(g_now, 0); }
    return n;
}

static int edge_mode(const char* which) {
    lua_State* L = fresh();
    if (std::strcmp(which, "hugedelay") == 0) {
        const bool ok = run(L, "e1", "e1_id = kp.registertimer(math.huge, function() e1_ran = true; return false end)");
        std::printf("    [E1] registertimer(math.huge) accepted=%d pending=%zu\n", ok, api::timers::pending(L));
        for (int i = 0; i < 4; ++i) { g_now += 50; api::timers::pump(g_now, 0); }
        std::printf("    [E1] fired within 200ms=%d\n", eval_bool(L, "return e1_ran == true"));
        run(L, "e1b", "kp.removetimer(1e30); kp.removetimer(math.huge); kp.removetimer(-0/0)");
        std::printf("    [E1] removetimer(1e30/inf/nan) returned without raising\n");
    } else if (std::strcmp(which, "strictg") == 0) {
        run(L, "e2", R"LUA(
            kp.registertimer(0, 'no_such_global')
            setmetatable(_G, {__index = function(_, k) error('strict: undefined global ' .. tostring(k), 2) end})
        )LUA");
        std::printf("    [E2] pumping string timer under strict _G (unprotected lua_getglobal in fire_one)...\n");
        std::fflush(stdout);
        g_now += 50; api::timers::pump(g_now, 0);
        std::printf("    [E2] survived; pending=%zu\n", api::timers::pending(L));
    } else if (std::strcmp(which, "strictg_fn") == 0) {
        run(L, "e3", R"LUA(
            kp.registertimer(0, function() e3_ran = true; return false end)
            setmetatable(_G, {__index = function(_, k) error('strict ' .. tostring(k), 2) end})
        )LUA");
        g_now += 50; api::timers::pump(g_now, 0);
        std::printf("    [E3] function timer under strict _G ran=%d pending=%zu\n",
                    eval_bool(L, "return rawget(_G, 'e3_ran') == true"), api::timers::pending(L));
    }
    return 0;
}

int main(int argc, char** argv) {
    api::timers::set_clock(g_now);
    if (argc > 1) return edge_mode(argv[1]);
    const char* prelude = R"LUA(
        weak = setmetatable({}, {__mode = 'k'})
        function tok(name) local t = {} ; weak[t] = name ; return t end
        function live(name) collectgarbage(); collectgarbage()
            for k, v in pairs(weak) do if v == name then return true end end return false end
    )LUA";

    std::printf("=== U2 probes ===\n");
    {
        lua_State* L = fresh();
        run(L, "prelude", prelude);

        // P1: removetimer(self) inside own callback -> raises inside callback,
        // timer is cancelled (error path), fn ref released.
        check(run(L, "p1", R"LUA(
            local t = tok('self_remove')
            p1_err = nil
            p1_id = kp.registertimer(0, function(id) local _ = t
                local ok, e = pcall(kp.removetimer, id); p1_err = e; return true end)
        )LUA"), "P1 register");
        pump_to(g_now + 200);
        check(eval_bool(L, "return p1_err ~= nil and p1_err:find('own callback') ~= nil"),
              "P1 removetimer(self) raises (pcall-caught) inside own callback");
        check(eval_bool(L, "return live('self_remove')") && api::timers::pending(L) == 1,
              "P1 pcall-swallowed self-remove + return true: timer keeps renewing");
        check(run(L, "p1c", "kp.removetimer(p1_id)"), "P1 removetimer from outside");
        check(!eval_bool(L, "return live('self_remove')") && api::timers::pending(L) == 0,
              "P1 ref released after external removetimer");

        // P2: unprotected self-remove -> callback throws -> timer cancelled, ref released.
        run(L, "p2", R"LUA(
            local t = tok('self_remove2')
            kp.registertimer(0, function(id) local _ = t; kp.removetimer(id); return true end)
        )LUA");
        pump_to(g_now + 100);
        check(!eval_bool(L, "return live('self_remove2')") && api::timers::pending(L) == 0,
              "P2 unprotected self-remove: error path cancels, ref released");

        // P3: re-registration inside callback (same closure) with delay 0:
        // does not fire in the same pump; fires next pump.
        run(L, "p3", R"LUA(
            p3_fires = 0
            local function cb(id, count)
                p3_fires = p3_fires + 1
                if p3_fires < 3 then kp.registertimer(0, cb) end
                return false
            end
            kp.registertimer(0, cb)
        )LUA");
        g_now += 50; unsigned f1 = api::timers::pump(g_now, 0);
        check(f1 == 1 && eval_bool(L, "return p3_fires == 1"), "P3 re-registered timer not fired in same pump");
        g_now += 50; api::timers::pump(g_now, 0);
        g_now += 50; api::timers::pump(g_now, 0);
        g_now += 50; api::timers::pump(g_now, 0);
        check(eval_bool(L, "return p3_fires == 3") && api::timers::pending(L) == 0,
              "P3 chain of re-registrations runs 3 times then stops");

        // P4: callback cancels a later timer due in the same pump -> skipped, released.
        run(L, "p4", R"LUA(
            p4_b_ran = false
            local tb = tok('p4b')
            p4_b = nil
            kp.registertimer(0, function() kp.removetimer(p4_b); return false end)
            p4_b = kp.registertimer(0, function() local _ = tb; p4_b_ran = true; return false end)
        )LUA");
        g_now += 50; api::timers::pump(g_now, 0);
        check(eval_bool(L, "return p4_b_ran == false") && !eval_bool(L, "return live('p4b')")
              && api::timers::pending(L) == 0,
              "P4 cancelled-mid-pump timer skipped and its ref released");

        // P5: registered from inside a coroutine; the coroutine dies and is
        // collected; the closure's upvalue (a coroutine local) survives.
        run(L, "p5", R"LUA(
            p5_seen = nil
            local co = coroutine.create(function()
                local secret = 41
                kp.registertimer(0, function() secret = secret + 1; p5_seen = secret; return false end)
                coroutine.yield()
            end)
            coroutine.resume(co)
            co = nil
            collectgarbage(); collectgarbage()
        )LUA");
        check(api::timers::pending(L) == 1, "P5 coroutine timer owned by main state");
        g_now += 50; api::timers::pump(g_now, 0);
        check(eval_bool(L, "return p5_seen == 42") && api::timers::pending(L) == 0,
              "P5 fires on main state after coroutine collected; upvalue intact");

        // P6: yield from a timer callback -> error, isolated, cancelled.
        run(L, "p6", R"LUA(
            p6_after = false
            kp.registertimer(0, function() coroutine.yield(); return true end)
            kp.registertimer(0, function() p6_after = true; return false end)
        )LUA");
        g_now += 50; api::timers::pump(g_now, 0);
        check(eval_bool(L, "return p6_after") && api::timers::pending(L) == 0,
              "P6 yield-across-C error isolated; next timer still runs");

        // P7: a C function as callback (label [C]:-1), and error() with a non-string.
        run(L, "p7", R"LUA(
            kp.registertimer(0, error, {})       -- error(id, count, data) -> throws a number
            kp.registertimer(0, function() error({}) end)
        )LUA");
        g_now += 50; unsigned f7 = api::timers::pump(g_now, 0);
        check(f7 == 2 && api::timers::pending(L) == 0, "P7 C-function and table-error callbacks isolated");

        // P8: slot reuse: after many register/end cycles, fresh refs are distinct
        // (a double unref would put one slot twice on the free list).
        run(L, "p8", R"LUA(
            for i = 1, 20 do kp.registertimer(0, function() return false end, {}) end
            for i = 1, 20 do kp.registertimer(0, function() error('x') end, {}) end
            p8_ids = {}
            for i = 1, 20 do p8_ids[#p8_ids+1] = kp.registertimer(99999, function() end, {}) end
        )LUA");
        g_now += 50; api::timers::pump(g_now, 0);
        run(L, "p8b", "for _, id in ipairs(p8_ids) do kp.removetimer(id) end");
        {
            std::set<int> refs; bool distinct = true;
            for (int i = 0; i < 128; ++i) {
                lua_newtable(L);
                int r = luaL_ref(L, LUA_REGISTRYINDEX);
                if (!refs.insert(r).second) distinct = false;
            }
            for (int r : refs) luaL_unref(L, LUA_REGISTRYINDEX, r);
            check(distinct, "P8 128 fresh registry refs distinct after 60 complete/error/cancel cycles");
        }

        // P9: bad args.
        check(eval_bool(L, "return not pcall(kp.registertimer, 0/0, function() end)"), "P9 NaN delay rejected");
        check(eval_bool(L, "return not pcall(kp.registertimer, 0, setmetatable({}, {__call=function() end}))"),
              "P9 callable table rejected (documented: string or function only)");
        check(eval_bool(L, "return not pcall(kp.registertimer, 0, function() end, 1, 2)"), "P9 4 args rejected");
        check(api::timers::pending(L) == 0, "P9 nothing scheduled by rejected calls");

        // P10: close with a function timer pending, plus finaliser in round 1
        // (before sentinel, newest-first) and a finaliser CREATED during round 1
        // (runs in round 2, after the sentinel).
        run(L, "p10", R"LUA(
            kp.registertimer(10, function() return true end, {})
            p10_log = {}
            local p = newproxy(true)
            getmetatable(p).__gc = function()
                local ok = pcall(kp.registertimer, 0, function() end)
                local q = newproxy(true)
                getmetatable(q).__gc = function()
                    local ok2, e = pcall(kp.registertimer, 0, function() end)
                    io.stdout:write('    [p10] round2 fn register ok=', tostring(ok2), ' ', tostring(e), '\n')
                end
                _G.keep_q = q
                io.stdout:write('    [p10] round1 fn register ok=', tostring(ok), '\n')
            end
            _G.keep_p = p
        )LUA");
        const std::size_t before = api::timers::pending();
        lua_close(L);
        check(api::timers::pending(L) == 0, "P10 no timers survive lua_close (both finaliser rounds)");
        g_now += 50;
        check(api::timers::pump(g_now, 0) == 0, "P10 pump after close touches nothing");
        std::printf("    pending before close=%zu after=%zu\n", before, api::timers::pending());
    }

    std::printf("=== U1 probes ===\n");
    {
        lua_State* L = fresh();
        run(L, "prelude", prelude);
        auto ok = [&](const char* name, const char* chunk) { check(run(L, name, chunk), name); };
        ok("V1 metatable unreachable (host debug stripping)", R"LUA(
            local v = kp.vec(1,2,3)
            assert(getmetatable(v) == 'kp.vec')
            assert(not pcall(setmetatable, v, {}))
            assert(debug.getmetatable == nil and debug.getregistry == nil)
            -- method functions reachable, the method table is not
            assert(type(v.length) == 'function' and rawget(v, 'length') == nil)
            -- the only upvalue-less C functions: nothing to steal via getupvalue
            assert(debug.getupvalue(v.length, 1) == nil)
        )LUA");
        ok("V2 fields writable; junk revalidated on every op", R"LUA(
            local v = kp.vec(1,2,3)
            v.x = 0/0;          assert(not pcall(function() return v + v end))
            v.x = '1';          assert(not pcall(function() return v:length() end))
            v.x = math.huge;    assert(not pcall(function() return v:normalize() end))
            v.x = nil;          assert(not pcall(function() return -v end))
            local w, w2 = kp.vec(1,2,3), kp.vec(1,2,3); w.y = 0/0; w2.y = 0/0
            assert(pcall(function() return w == w2 end), '== with NaN field does not raise')
            assert((w == w2) == false, 'NaN field compares unequal')
            io.stdout:write('    [V2] tostring(nan-field vec) = ', tostring(w), '\n')
        )LUA");
        ok("V3 overflow caught at result", R"LUA(
            local big = kp.vec(1e308, 1e308, 0)
            assert(not pcall(function() return big * 10 end))
            assert(not pcall(function() return big + big end))
            local okl, l = pcall(function() return big:length() end)
            io.stdout:write('    [V3] kp.vec(1e308,1e308,0):length() ok=', tostring(okl), ' -> ', tostring(l), '\n')
            local m = kp.vec(1e155, 0, 0)
            io.stdout:write('    [V3] kp.vec(1e155,0,0): length=', tostring(m:length()), ' lengthsq=', tostring(m:lengthsq()),
                            ' dot=', tostring(m:dot(m)), ' distance0=', tostring(m:distance(kp.vec(0,0,0))),
                            ' normalize=', tostring(m:normalize()), '\n')
        )LUA");
        ok("V4 method shadowing by field", R"LUA(
            local v = kp.vec(3,4,0); v.length = 7
            assert(v.length == 7)            -- plain table semantics; documented as writable
            assert(kp.vec(3,4,0):length() == 5)
        )LUA");
        ok("V5 eq/lerp/normalize/-0", R"LUA(
            assert(kp.vec(0,0,0) == kp.vec(-0,-0,-0))
            local a, b = kp.vec(1e-300, 2, 3), kp.vec(-7, 1e10, 0.1)
            assert(a:lerp(b, 0) == a and a:lerp(b, 1) == b)
            local n = kp.vec(1e-200, 0, 0):normalize()  -- dot underflows to 0
            io.stdout:write('    tiny normalize -> ', tostring(n), '\n')
        )LUA");
        ok("V6 kp.vec with __index proxy and with string numbers", R"LUA(
            local proxy = setmetatable({}, {__index = {x=1,y=2,z=3}})
            local v = kp.vec(proxy); assert(v.x == 1 and rawget(v,'x') == 1)
            assert(not pcall(kp.vec, '1', 2, 3))
            assert(not pcall(function() return kp.vec(1,2,3) * '2' end))
        )LUA");
        // Finite double but not a finite float: marshals to +inf in the VM.
        check(eval_bool(L, "return pcall(kp.vec, 1e39, 0, 0)"),
              "V7 (observation) kp.vec(1e39,0,0) accepted though > FLT_MAX");
        // V8: 1e-200 normalize
        lua_close(L);
    }
    std::printf("\n%u check(s), %u failure(s)\n", g_n, g_fail);
    return g_fail ? 1 : 0;
}
