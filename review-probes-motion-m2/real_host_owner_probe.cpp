// Review probe (motion M2): the REAL lua::Host drives Script::owner(L) and
// Script::staged() through load, hot reload (stage -> old OnScriptUnload ->
// commit -> new OnScriptLoad), failed reload and unload. The owner probe bound
// here is the one the M2 plan specifies for the runtime (I-M2):
//   Script* s = Script::owner(L); !s ? None : s->staged() ? Staged : Loaded
// The backend is a small sparse-memory fake seeded from the real profile.
#include "api/engine_gate.hpp"
#include "api/motion.hpp"
#include "events/contract.hpp"
#include "lua/host.hpp"
#include "lua/value.hpp"
#include <chrono>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <map>
#include <string>
#include <vector>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
}
using namespace kp;
using namespace kp::api::motion;
namespace fs = std::filesystem;

namespace {
struct Fake : Backend {
    const Profile& p; std::map<Address, unsigned char> bytes;
    Address manager = 0x1000000, server = 0x1001000, internal = 0x1002000, array = 0x1003000, crate = 0x1004000;
    unsigned sets = 0;
    template <class T> void put(Address a, T v) { auto* b = reinterpret_cast<unsigned char*>(&v); for (unsigned i = 0; i < sizeof v; ++i) bytes[a + i] = b[i]; }
    template <class T> T get(Address a) const { T v{}; auto* b = reinterpret_cast<unsigned char*>(&v); for (unsigned i = 0; i < sizeof v; ++i) b[i] = bytes.at(a + i); return v; }
    explicit Fake(const Profile& pr) : p(pr) {
        auto digit = [](char c) { return c <= '9' ? c - '0' : c - 'a' + 10; };
        for (const auto& s : p.spans) if (s.va)
            for (std::size_t j = 0; j * 2 < std::strlen(s.hex); ++j) bytes[s.va + j] = (digit(s.hex[j * 2]) << 4) | digit(s.hex[j * 2 + 1]);
        for (const auto& s : p.slots) if (s.va) put<std::uint32_t>(s.va, s.target);
        put<std::uint32_t>(p.manager_slot, manager); put<std::uint32_t>(manager + p.manager_server, server);
        put<std::uint32_t>(server + p.server_internal, internal); put<std::uint32_t>(internal + p.internal_array, array);
        put<std::uint8_t>(array, 1);
        Address o = crate;
        put<std::uint32_t>(o, p.placeable_vtable); put<std::uint32_t>(o + p.id, 42); put<std::uint8_t>(o + p.type, p.placeable_type);
        put<std::uint32_t>(o + p.area_id, 0x7f000123);
        put(o + p.position, 1.5f); put(o + p.position + 4, -2.25f); put(o + p.position + 8, 0.125f);
        put(o + p.orientation, 0.f); put(o + p.orientation + 4, 1.f); put(o + p.orientation + 8, 0.f);
        put<std::uint32_t>(o + p.push_gate, 1); put<std::uint32_t>(o + p.dirty, 0);
        put<std::int32_t>(o + p.aabb_marker, -1);
        for (int i = 0; i < 4; ++i) put(o + p.quaternion + 4 * i, i == 0 ? 1.f : 0.f);
    }
    Abi abi() const override { return p.abi; }
    unsigned width() const override { return p.width; }
    bool read(Address a, void* out, std::size_t n) const override {
        auto* b = static_cast<unsigned char*>(out);
        for (std::size_t i = 0; i < n; ++i) { auto it = bytes.find(a + i); if (it == bytes.end()) return false; b[i] = it->second; }
        return true;
    }
    Address placeable(Address, Address, std::uint32_t id) override { return id == 42 ? crate : 0; }
    void set_position(Address, Address o, const std::array<float, 3>& v, std::int32_t, std::int32_t, std::int32_t a4) override {
        ++sets;
        std::array<float, 3> cur{get<float>(o + p.position), get<float>(o + p.position + 4), get<float>(o + p.position + 8)};
        if (engine_equal(cur, v)) return;
        put(o + p.position, v[0]); put(o + p.position + 4, v[1]); put(o + p.position + 8, v[2]);
        if (a4 == 0) put<std::uint32_t>(o + p.dirty, get<std::uint32_t>(o + p.dirty) | 2u);
    }
};

std::vector<std::string> g_notes;
// The plan's runtime binding, verbatim.
Writer runtime_probe(lua_State* L, void*) {
    lua::Script* s = lua::Script::owner(L);
    return !s ? Writer::None : s->staged() ? Writer::Staged : Writer::Loaded;
}
bool gate_yes(void*) { return true; }
int note(lua_State* L) {
    std::string tag = luaL_checkstring(L, 1);
    std::string v = lua_isnil(L, 2) ? ("ERR " + std::string(lua_tostring(L, 3) ? lua_tostring(L, 3) : "?"))
                                   : ("OK " + std::string(lua_tostring(L, 3) ? lua_tostring(L, 3) : "-"));
    g_notes.push_back(tag + ": " + v);
    std::printf("  %s: %s\n", tag.c_str(), v.c_str());
    return 0;
}
events::EventContract ev(const char* n) { events::EventContract e; e.lua_name = n; return e; }
const events::EventContract kLoad = ev("OnScriptLoad"), kUnload = ev("OnScriptUnload"), kTick = ev("OnTick");

void write(const fs::path& p, const std::string& body) {
    std::error_code ec; bool existed = fs::exists(p, ec);
    auto before = existed ? fs::last_write_time(p, ec) : fs::file_time_type{};
    { std::ofstream(p, std::ios::binary) << body; }
    if (existed) fs::last_write_time(p, before + std::chrono::seconds(2), ec);
}
unsigned failures = 0;
void expect(const char* what, bool ok) { std::printf("%s %s\n", ok ? "PASS" : "FAIL", what); if (!ok) ++failures; }
bool has(const std::string& s) { for (auto& n : g_notes) if (n.rfind(s, 0) == 0) return true; return false; }

const char* kHelpers = R"(
local T={x=2,y=-2.25,z=0.125}
local T2={x=2.5,y=-2.25,z=0.125}
function rel(tag,t) local c=kp.motion.capture(42) local m,s=kp.motion.relocate(c,t or T) note(tag,m,s) end
function res(tag) local m,e=kp.motion.restore(42) note(tag,m,m and tostring(m.position.x) or e) end
)";
}

int main(int argc, char** argv) {
    fs::path root = argc > 1 ? argv[1] : "/tmp/kp-m2-review-host";
    std::string err;
    Fake fake(profiles().front());
    if (!operations().bind(profiles().front().sha256, 0x400000, &fake, err)) { std::printf("bind: %s\n", err.c_str()); return 2; }
    api::engine::bind_gate(gate_yes, nullptr);
    bind_owner_probe(runtime_probe, nullptr);

    // --- Case A: load, hot reload with restore in the old OnScriptUnload ----
    {
        fs::path dir = root / "a"; fs::remove_all(dir); fs::create_directories(dir);
        lua::HostConfig cfg; cfg.script_dir = dir.string();
        cfg.on_state_created = [](lua_State* L) { register_all(L); lua_register(L, "note", note); };
        lua::Host host(std::move(cfg));
        host.set_lifecycle(&kLoad, &kUnload, "k1", "review");
        write(dir / "zz.lua", std::string(kHelpers) + R"(
rel("v1.top")                               -- chunk top level: staged
function OnScriptLoad() rel("v1.load") end
function OnScriptUnload() rel("v1.unload.relocate", {x=2.25,y=-2.25,z=0.125}) res("v1.unload.restore") end
)");
        std::vector<std::string> errs; host.load_all(errs);
        for (auto& e : errs) std::printf("  load error: %s\n", e.c_str());
        write(dir / "zz.lua", std::string(kHelpers) + R"(
rel("v2.top")
function OnScriptLoad() rel("v2.load") end
function OnTick() rel("v2.tick", {x=2.5,y=-2.25,z=0.125}) end
)");
        if (!host.reload_one("zz", err)) std::printf("  reload error: %s\n", err.c_str());
        host.dispatch(kTick, {});
        expect("A v1 chunk top level refused (staged)", has("v1.top: ERR unsupported: only a loaded script"));
        expect("A v1 OnScriptLoad moves (loaded)", has("v1.load: OK moved"));
        expect("A old gen OnScriptUnload during reload: relocate refused (staged)", has("v1.unload.relocate: ERR unsupported: only a loaded script"));
        expect("A old gen OnScriptUnload during reload: restore allowed", has("v1.unload.restore: OK 1.5"));
        expect("A v2 chunk top level refused (staged)", has("v2.top: ERR unsupported: only a loaded script"));
        expect("A v2 OnScriptLoad moves (object free again)", has("v2.load: OK moved"));
        expect("A v2 OnTick moves onward", has("v2.tick: OK moved"));
        // unload_one: OnScriptUnload with staged()==false -> Loaded, so restore works
        g_notes.clear();
        write(dir / "zz.lua", std::string(kHelpers) + R"(
function OnScriptLoad() end
)");
    }
    // Ledger left by case A's last generation (no restore) is an orphan: the
    // Host destructor closed the state; M3 is not landed.
    std::printf("  after case A host destroyed: owner_of(42)=%llu ledger=%zu\n",
                (unsigned long long)operations().owner_of(42), operations().ledger_size());
    expect("A orphan remains after host teardown (documented M3 gap)", operations().owner_of(42) != 0);
    operations().unbind(); operations().bind(profiles().front().sha256, 0x400000, &fake, err);
    fake.put(fake.crate + fake.p.position, 1.5f);   // reset pose
    g_notes.clear();

    // --- Case B: reload without restore -> new generation is locked out ----
    {
        fs::path dir = root / "b"; fs::remove_all(dir); fs::create_directories(dir);
        lua::HostConfig cfg; cfg.script_dir = dir.string();
        cfg.on_state_created = [](lua_State* L) { register_all(L); lua_register(L, "note", note); };
        lua::Host host(std::move(cfg));
        host.set_lifecycle(&kLoad, &kUnload, "k1", "review");
        write(dir / "zz.lua", std::string(kHelpers) + "function OnScriptLoad() rel('b1.load') end\n");
        std::vector<std::string> errs; host.load_all(errs);
        write(dir / "zz.lua", std::string(kHelpers) + "function OnScriptLoad() rel('b2.load', {x=2.5,y=-2.25,z=0.125}) res('b2.restore') end\n");
        host.reload_one("zz", err);
        expect("B v1 load moves", has("b1.load: OK moved"));
        expect("B v2 (same script, new generation) refused as owned: orphan lock", has("b2.load: ERR owned"));
        expect("B v2 cannot restore the orphan either", has("b2.restore: ERR not_owner"));
    }
    operations().unbind(); operations().bind(profiles().front().sha256, 0x400000, &fake, err);
    fake.put(fake.crate + fake.p.position, 1.5f);
    g_notes.clear();

    // --- Case C: failed reload clears staged(); the running generation can still write
    {
        fs::path dir = root / "c"; fs::remove_all(dir); fs::create_directories(dir);
        lua::HostConfig cfg; cfg.script_dir = dir.string();
        cfg.on_state_created = [](lua_State* L) { register_all(L); lua_register(L, "note", note); };
        lua::Host host(std::move(cfg));
        host.set_lifecycle(&kLoad, &kUnload, "k1", "review");
        write(dir / "zz.lua", std::string(kHelpers) + "function OnTick() rel('c1.tick') end\n");
        std::vector<std::string> errs; host.load_all(errs);
        write(dir / "zz.lua", std::string(kHelpers) + "rel('c2.top')\nerror('boom')\n");
        bool ok = host.reload_one("zz", err);
        std::printf("  reload ok=%d err=%s\n", ok, err.c_str());
        lua::Script* s = host.find("zz");
        expect("C failed reload leaves staged()==false", s && !s->staged());
        host.dispatch(kTick, {});
        expect("C failed chunk top level refused (staged at the time)", has("c2.top: ERR unsupported: only a loaded script"));
        expect("C running generation still writes after failed reload", has("c1.tick: OK moved"));
        // unload_one: OnScriptUnload outside a reload is Loaded -> restore allowed
        g_notes.clear();
    }
    std::printf("%u failure(s)\n", failures);
    return failures ? 1 : 0;
}
