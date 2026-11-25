// The harness engine adapter for builds that do not have one.
//
// The headless/TAS control plane (engine_k1.cpp / engine_k2.cpp) is written
// against the Windows PE and native Linux ELF object layouts and calling
// conventions. Neither is correct for the x86_64 macOS builds: the field
// offsets differ, `this` is an ordinary System V argument rather than ECX, and
// several harness sites are not in the Mac address tables at all. Bringing the
// harness up on macOS is a separate corpus effort (docs/release-platform-status.md
// lists it under the later acceptance gates), so rather than compile the i386
// adapter and let it read wrong memory, the Mac build links this instead.
//
// It keeps the runtime's link closed and the harness listener honest: every
// command answers "unsupported on this build" instead of touching an offset
// nobody verified for this ABI. The listener is off unless `harness_port` is
// set, so a player never reaches any of this.
//
// This file compiles only where the real adapters do not (i.e. not i386).
// hooks.cmake / runtime.cmake pick exactly one of the three.
#if !defined(__i386__) && !defined(_M_IX86)

#include <atomic>
#include <memory>
#include <string>
#include <vector>

#include "harness/engine.hpp"
#include "hooks/registry.hpp"

namespace kp::harness {
namespace {

const char* kWhy = "the headless harness has no adapter for this build's ABI (macOS x86_64)";

class UnsupportedAdapter final : public EngineAdapter {
public:
    const char* name() const override { return "unsupported"; }
    Phase phase(PhaseDetail* out) override { if (out) *out = PhaseDetail{}; return Phase::Unknown; }
    std::string module_name() override { return {}; }
    std::string chargen_stage() override { return {}; }
    float speed() const override { return 1.0f; }
    bool movies_enabled() override { return true; }

    Result load_save(const std::string&) override { return no(); }
    Result new_game() override { return no(); }
    Result chargen_select_class(int) override { return no(); }
    Result chargen_begin_play() override { return no(); }
    Result save(int, const std::string&) override { return no(); }
    Result warp(const std::string&) override { return no(); }
    Result dialog(DialogState*) override { return no(); }
    Result reply(int) override { return no(); }
    Result dialog_continue() override { return no(); }
    Result dialog_skip() override { return no(); }
    Result dialog_abort() override { return no(); }
    Result dialog_clear_sound_wait() override { return no(); }
    Result clear_auto_pause() override { return no(); }
    Result set_speed(float) override { return no(); }
    Result unpause_timers() override { return no(); }
    Result advance_tutorial() override { return no(); }
    Result finish_hidden_tutorial() override { return no(); }
    Result dismiss_status_summary() override { return no(); }
    Result dismiss_messagebox() override { return no(); }
    Result equipment_screen(bool) override { return no(); }
    Result door_use(std::uint32_t) override { return no(); }
    Result door_commit_open(std::uint32_t) override { return no(); }
    Result door_security(std::uint32_t) override { return no(); }
    bool take_door_security_result(Result*, DoorSecurityResult*) override { return false; }
    Result attack(std::uint32_t) override { return no(); }
    Result dismiss_container() override { return no(); }
    Result take_all_container() override { return no(); }
    Result accept_party_selection() override { return no(); }
    Result set_party_leader(int) override { return no(); }
    bool take_party_leader_result(Result*, PartyLeaderResult*) override { return false; }
    Result use_item(std::uint32_t, std::uint32_t) override { return no(); }
    bool take_use_item_result(Result*, UseItemResult*) override { return false; }
    Result equip_item(std::uint32_t, std::uint32_t, bool) override { return no(); }
    bool take_equip_item_result(Result*, EquipItemResult*) override { return false; }
    Result auto_levelup() override { return no(); }
    bool take_auto_levelup_result(Result*, AutoLevelResult*) override { return false; }
    Result after_frame() override { return Result::success(); }  // nothing to re-apply
    Result set_fixed_step(int) override { return no(); }
    Result set_movies(bool) override { return no(); }
    Result walk_globals(GlobalsVisitor&) override { return no(); }
    Result walk_journal(JournalVisitor&) override { return no(); }
    std::vector<std::string> missing_sites() override { return {"<all: no adapter for this ABI>"}; }

private:
    static Result no() { return Result::unsupported(kWhy); }
};

}  // namespace

std::unique_ptr<EngineAdapter> make_adapter(const hooks::AddressTable&, std::uintptr_t) {
    return std::make_unique<UnsupportedAdapter>();
}

// The two harness caves have no body on this build. install() only adds an
// optional cave when its site resolves and is a detour, and the Mac address
// tables carry neither client.set_game_speed nor client.play_movies, so a null
// detour is never handed to the hook set; returning null keeps the symbol
// defined for the unconditional reference in runtime.cpp's optional[] table.
void* client_set_game_speed_detour() { return nullptr; }
void* client_play_movies_detour() { return nullptr; }
std::atomic<void*>* adapter_original_slot(std::string_view) { return nullptr; }
void bind_adapter_originals(const hooks::HookSet&) {}

}  // namespace kp::harness

#endif  // !i386
