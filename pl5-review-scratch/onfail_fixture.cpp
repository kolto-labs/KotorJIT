#include <cassert>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <vector>
#include <bits/stdc++.h>
#include "/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/hooks/registry.hpp"
#define private public
#include "/home/brunner56/kp-live-20260922/pl5-scratch/src/harness/engine_k1.cpp"
#undef private

static std::uint32_t g_server = 0;
static void fake_create(void* self, int) {
    *reinterpret_cast<std::uint32_t*>(reinterpret_cast<std::uintptr_t>(self) + 8) = g_server;
}

static void put32(std::vector<std::uint8_t>& b, std::size_t at, std::uint32_t v) {
    std::memcpy(b.data() + at, &v, 4);
}

static void make_inputs(const std::filesystem::path& root) {
    std::filesystem::create_directories(root / "slot");
    std::vector<std::uint8_t> gff(56 + 12 + 12 + 16 + 8, 0);
    put32(gff, 8, 56); put32(gff, 12, 1); put32(gff, 16, 68); put32(gff, 20, 1);
    put32(gff, 24, 80); put32(gff, 28, 1); put32(gff, 32, 96); put32(gff, 36, 8);
    put32(gff, 40, 0); put32(gff, 44, 0);
    put32(gff, 56 + 4, 0); put32(gff, 56 + 8, 1);
    put32(gff, 68, 10); put32(gff, 72, 0); put32(gff, 76, 0);
    std::memcpy(gff.data() + 80, "LASTMODULE", 10);
    put32(gff, 96, 3); std::memcpy(gff.data() + 100, "ebo", 3);
    std::ofstream nfo(root / "slot" / "savenfo.res", std::ios::binary); nfo.write(reinterpret_cast<char*>(gff.data()), gff.size());

    std::vector<std::uint8_t> erf(44, 0); std::memcpy(erf.data(), "MOD V1.0", 8);
    put32(erf, 16, 0); put32(erf, 24, 44); put32(erf, 28, 44);
    std::ofstream sav(root / "slot" / "SAVEGAME.sav", std::ios::binary); sav.write(reinterpret_cast<char*>(erf.data()), erf.size());
}

static void bind_field(kp::harness::GameAdapter& a, const char* name, std::uint32_t off) {
    kp::harness::Bound b; b.ok = true; b.is_field = true; b.offset = off; b.size = 4; a.bound_[name] = b;
}
static void bind_fn(kp::harness::GameAdapter& a, const char* name, void* fn) {
    kp::harness::Bound b; b.ok = true; b.addr = reinterpret_cast<std::uintptr_t>(fn); a.bound_[name] = b;
}

int main() {
    const std::filesystem::path root = "/home/brunner56/kp-live-20260922/pl5-review-scratch/onfail-input";
    make_inputs(root);
    setenv("KOTORPHASOR_SAVES_DIR", root.c_str(), 1);
    setenv("KOTORPHASOR_GAMEINPROGRESS_DIR", (root / "gameinprogress").c_str(), 1);

    std::uint32_t global = 0, manager[8] = {}, client[2] = {}, cint[4] = {}, server[2] = {}, sint[2] = {};
    global = reinterpret_cast<std::uintptr_t>(manager);
    manager[1] = reinterpret_cast<std::uintptr_t>(client);
    client[1] = reinterpret_cast<std::uintptr_t>(cint);
    server[1] = reinterpret_cast<std::uintptr_t>(sint);
    g_server = reinterpret_cast<std::uintptr_t>(server);

    kp::hooks::AddressTable table;
    kp::harness::GameAdapter a("onfail", kp::harness::Layout{}, table, 0);
    a.shape_ = kp::harness::CallShape::ThisOnStack;
    kp::harness::Bound appmgr; appmgr.ok = true; appmgr.is_field = true; appmgr.addr = reinterpret_cast<std::uintptr_t>(&global); appmgr.size = 4; a.bound_["g.app_manager"] = appmgr;
    bind_fn(a, "app.create_server", reinterpret_cast<void*>(&fake_create));
    for (const char* n : {"net.start_connect_to_session", "msg.request_status", "app.set_load_from_savegame", "client.set_loading_savegame", "client.send_load_game_request"}) bind_fn(a, n, reinterpret_cast<void*>(&fake_create));
    bind_field(a, "client.net_layer", 8); bind_field(a, "client.message_handler", 12);
    assert(!a.pause_machine_.loading());
    const kp::harness::Result result = a.load_save("slot");
    assert(!result.ok);
    assert(result.error == "load_save: client.net_layer not readable");
    assert(!a.pause_machine_.loading());
    assert(a.end_load_calls_ == 1);
    std::puts("actual GameAdapter::load_save -> on_fail call path: PASS");
}
