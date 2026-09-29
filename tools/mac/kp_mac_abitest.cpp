// Unit tests for the x86_64-specific decode/layout logic the macOS port adds.
//
// These run on any x86_64 host (the CI Linux box, or a Mac): they exercise the
// pure functions whose correctness depends on the 64-bit engine ABI, with
// synthetic inputs shaped like the real engine's, so a regression in the
// widths or the decoders is caught without a game.
//
//   clang++ -std=c++20 -O2 -Isrc tools/mac/kp_mac_abitest.cpp -o kp_mac_abitest
//   ./kp_mac_abitest
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <vector>

#include "api/abi_layout.hpp"
#include "api/enginestruct.hpp"
#include "platform/target.hpp"

static int g_fail = 0;
#define CHECK(cond, msg) do { if (!(cond)) { std::printf("FAIL: %s\n", msg); ++g_fail; } } while (0)

int main() {
    using namespace kp;

    // --- the compiled-in engine layout is the x86_64 one on a 64-bit build ---
    CHECK(abi::kX64 == (sizeof(void*) == 8), "kX64 tracks pointer width");
    if (abi::kX64) {
        const auto& L = api::layout::kEngine;
        CHECK(L.exostring_length == 8, "x64 CExoString length at +8");
        CHECK(L.arraylist_bytes == 16 && L.arraylist_size_field == 8, "x64 CExoArrayList 16B, size at +8");
        CHECK(L.script_event_bytes == 0x48, "x64 CScriptEvent 0x48");
        CHECK(L.script_event_objects == 0x38 && L.object_id_bytes == 8, "x64 object list 8B elems at +0x38");
        CHECK(L.game_object_id == 8, "x64 CGameObject id at +8");
        CHECK(L.commands_table == 0x18 && L.command_entry_bytes == 16, "x64 command table +0x18, 16B entries");
        CHECK(L.commands_has_caller == 8 && L.commands_caller_id == 0x10, "x64 has_caller +8, caller_id +0x10");
        CHECK(L.area_game_object == 0x158 && L.module_game_object == 0x28, "x64 area/module subobject offsets");
        CHECK(L.module_game_object_is_pointer == false, "x64 module embeds CGameObject");
    }

    // --- object id truncation crosses the boundary as 32 bits ---------------
    {
        abi::ObjectId wide = abi::kX64 ? 0x0000000180000042ull : 0x80000042ull;
        CHECK(abi::script_id(wide) == 0x80000042u, "script_id keeps low 32 bits (high-bit id survives)");
        CHECK(abi::script_id(0x7f000000u) == 0x7f000000u, "OBJECT_INVALID round-trips");
    }

    // --- ExecuteCommand bound decoders --------------------------------------
    // x86_64 clang: cmp esi, imm32 ; jg  -> count = imm+1 (ids 0..imm valid).
    {
        // 81 fe 6d 03 00 00   cmp esi, 0x36d
        // 7f xx               jg
        const std::uint8_t jg[] = {0x55, 0x48, 0x89, 0xe5, 0x81, 0xfe, 0x6d, 0x03, 0x00, 0x00, 0x7f, 0x10, 0x90, 0x90};
        std::uint32_t out = 0;
        CHECK(api::decode_execute_command_bound_x64(jg, sizeof jg, out) && out == 0x36d + 1,
              "x64 ExecuteCommand jg bound -> imm+1");
        // 0F 8F rel32 form of jg
        const std::uint8_t jg32[] = {0x81, 0xfe, 0x04, 0x03, 0x00, 0x00, 0x0f, 0x8f, 0x01, 0x00, 0x00, 0x00};
        out = 0;
        CHECK(api::decode_execute_command_bound_x64(jg32, sizeof jg32, out) && out == 0x304 + 1,
              "x64 ExecuteCommand jg(rel32) bound -> imm+1");
        // jge form -> count = imm
        const std::uint8_t jge[] = {0x81, 0xfe, 0x04, 0x03, 0x00, 0x00, 0x7d, 0x08};
        out = 0;
        CHECK(api::decode_execute_command_bound_x64(jge, sizeof jge, out) && out == 0x304,
              "x64 ExecuteCommand jge bound -> imm");
        // garbage refuses
        const std::uint8_t none[] = {0x90, 0x90, 0xc3};
        out = 0xdead;
        CHECK(!api::decode_execute_command_bound_x64(none, sizeof none, out), "x64 bound decoder refuses non-match");
    }

    // --- the i386 decoder still works (cmp edx, imm32) -----------------------
    {
        const std::uint8_t k1[] = {0x8b, 0x54, 0x24, 0x04, 0x81, 0xfa, 0x04, 0x03, 0x00, 0x00};
        std::uint32_t out = 0;
        CHECK(api::decode_execute_command_bound(k1, sizeof k1, out) && out == 0x304,
              "i386 ExecuteCommand bound -> imm");
    }

    if (g_fail == 0) std::printf("PASS kp_mac_abitest (%s build)\n", abi::kX64 ? "x86_64" : "i386");
    return g_fail == 0 ? 0 : 1;
}
