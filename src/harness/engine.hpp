// The engine adapter: what the harness commands call to drive a live game.
//
// One interface, two games. Every method is a request to the engine followed
// by nothing else -- the driver reads engine state afterwards to prove the step
// took. The adapter never waits, never sleeps, never polls.
//
// Every function and field it touches is a logical site in data/hooksites.toml,
// resolved per build by the registry. A site that did not resolve makes the
// method that needs it return Result::unsupported(site), and missing_sites()
// lists every such name so a scenario can skip by name rather than guess.
//
// Threading: the adapter is called only from the client-loop drain, on the
// game's main thread. Engine calls inside it are bracketed by
// enter_hook_body() / leave_hook_body() -- an unarmed frame, so a fault inside
// engine code is a real crash for the crash oracle and not a claimed one. The
// caller must NOT arm KP_HOOK_GUARD around an adapter method: the longjmp would
// skip engine frames and leave engine state torn (harness-design.md, amendment
// 1 of the feasibility audit).
#pragma once

#include <atomic>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace kp::hooks { class AddressTable; class HookSet; }

namespace kp::harness {

enum class Phase { Unknown, Menu, Loading, Gameplay, Dialog, Movie, Paused, Minigame, GameOver, Error };

// Raw engine reads behind a phase verdict. -1 means the field was not
// readable on this build (site unresolved or pointer chain broken).
struct PhaseDetail {
    int server_mode = -1, loading_module = -1, area_not_ready = -1, input_class = -1,
        main_menu = -1, game_over = -1, pause = -1, movie = -1, load_error = -1,
        move_pending = -1, chargen = -1, controller_pause = -1, tutorial = -1,
        modal_count = -1, status_summary = -1;
    // Bitmask of paused CWorldTimers: 1 client world, 2 server world,
    // 4 client animation. -1 when none could be read.
    int timers_paused = -1;
};

struct Result {
    bool ok;
    std::string error;
    static Result success();
    static Result fail(std::string);
    static Result unsupported(std::string site);
};

struct DialogReply {
    int visible_index;   // row in the client's reply list, what reply() takes
    int link_index;      // position in the server entry's link list
    std::string text;    // TLK-resolved text the client stored, no "%d. " prefix
    bool active = true;  // false for a greyed row; see engine_k1.cpp on how it is known
};

struct DialogState {
    bool active = false;
    int current_entry = -1;          // server CSWSDialog current entry index
    int current_reply = -1;          // server chosen link, -1 while waiting
    bool waiting_for_player = false; // reply() would be accepted right now
    bool waiting_on_sound = false;   // the owner is mid-send: VO or a node delay
    std::string entry_text;          // "strref:<n>" -- no TLK site, see engine_k1.cpp
    std::vector<DialogReply> replies;
};

struct AutoLevelResult {
    std::uint32_t player_id = 0;
    int level_before = -1;
    int level_after = -1;
    std::uint32_t experience = 0;
    int can_level_up = -1;
};

struct PartyLeaderResult {
    std::uint32_t leader_before = 0;
    std::uint32_t leader_after = 0;
};

struct UseItemResult {
    std::uint32_t item_id = 0;
    std::uint32_t target_id = 0;
};

struct DoorSecurityResult {
    std::uint32_t door_id = 0;
    bool locked_before = false;
    bool locked_after = false;
    std::uint32_t open_state_before = 0;
    std::uint32_t open_state_after = 0;
};

struct EquipItemResult {
    std::uint32_t requested_item_id = 0;
    std::uint32_t current_item_id = 0;
    std::uint32_t slot = 0;
};

struct GlobalsVisitor {
    virtual void on_bool(const char* name, bool v) = 0;
    virtual void on_number(const char* name, int v) = 0;
    virtual void on_string(const char* name, const char* v) = 0;
    virtual ~GlobalsVisitor() = default;
};

struct JournalVisitor {
    virtual void on_entry(const char* tag, int state) = 0;
    virtual ~JournalVisitor() = default;
};

class EngineAdapter {
public:
    virtual ~EngineAdapter() = default;
    virtual const char* name() const = 0;
    virtual Phase phase(PhaseDetail* out) = 0;
    virtual std::string module_name() = 0;
    virtual Result load_save(const std::string& dir) = 0;
    virtual Result new_game() = 0;
    virtual Result chargen_select_class(int index) = 0;
    // Complete character generation through the engine-owned BeginPlayGame path.
    virtual Result chargen_begin_play() = 0;
    virtual std::string chargen_stage() = 0;
    virtual Result save(int slot, const std::string& name) = 0;
    virtual Result warp(const std::string& module) = 0;
    virtual Result dialog(DialogState* out) = 0;
    virtual Result reply(int visible_index) = 0;
    // Continue a single empty-text dialog node through the engine's
    // entry-selection path (isReply=0), never the player reply path.
    virtual Result dialog_continue() { return Result::fail("dialog_continue: unsupported by this engine"); }
    virtual Result dialog_skip() = 0;
    virtual Result dialog_abort() = 0;
    virtual Result dialog_clear_sound_wait() = 0;
    virtual Result clear_auto_pause() = 0;
    virtual Result set_speed(float scale) = 0;
    // The scale set_speed last applied (1.0 when untouched).
    virtual float  speed() const { return 1.0f; }
    // Unpause the two world timers load_save pauses. The engine's own load
    // completion unpauses them; this is the route out when something skipped
    // that block, and it goes through UnpauseWorldTimer rather than writing a
    // timer's paused byte, which wedged the control channel when it was tried.
    virtual Result unpause_timers() = 0;
    // Feed the native continue event to the tutorial panel. A tutorial can
    // span pages, so the driver observes state and advances one page per call.
    virtual Result advance_tutorial() = 0;
    virtual Result finish_hidden_tutorial() = 0;
    virtual Result dismiss_status_summary() = 0;
    virtual Result dismiss_messagebox() = 0;
    // Run the equipment panel's native open/close lifecycle, including its
    // screen-change script callback.
    virtual Result equipment_screen(bool visible) = 0;
    // Queue retail door use; success means dispatch, not completed movement.
    virtual Result door_use(std::uint32_t door_id) = 0;
    // Commit a door's pending open state (CSWSDoor::MoveToNextOpenState), the
    // second phase of opening that the client's animation-done callback
    // normally runs and the headless client does not deliver for some doors.
    virtual Result door_commit_open(std::uint32_t door_id) = 0;
    // Invoke the retail door-menu Security action. It queues the game's own
    // lockpick action and skill evaluation; it never writes a lock field.
    virtual Result door_security(std::uint32_t door_id) = 0;
    virtual bool take_door_security_result(Result* status, DoorSecurityResult* out) = 0;
    virtual Result attack(std::uint32_t target_id) = 0;
    // Close the top CSWGuiContainer through its native 0x28 input event. The
    // handler sends the server close message and restores modal/input/pause
    // state; removing the panel directly would leave those paths incomplete.
    virtual Result dismiss_container() = 0;
    // Take every item from the top normal-mode CSWGuiContainer through its
    // native 0x27 event. The same handler transfers the items, sends the
    // server close message and retires the modal.
    virtual Result take_all_container() = 0;
    // Accept the initialized top CSWGuiPartySelection through its native
    // wrapper. Party composition remains a route-specific scenario assertion.
    virtual Result accept_party_selection() = 0;
    // Arm a native CSWParty::SetLeader call for a later frame. `selector` is
    // a positive current party-array index; slot 0 is already the leader.
    virtual Result set_party_leader(int selector) = 0;
    virtual bool take_party_leader_result(Result* status, PartyLeaderResult* out) = 0;
    // Send the ordinary client party-menu item-use request from a later frame.
    // A zero target selects the current player creature.
    virtual Result use_item(std::uint32_t item_id, std::uint32_t target_id) = 0;
    virtual bool take_use_item_result(Result* status, UseItemResult* out) = 0;
    virtual Result equip_item(std::uint32_t item_id, std::uint32_t slot, bool instant) = 0;
    virtual bool take_equip_item_result(Result* status, EquipItemResult* out) = 0;
    // Arm a GUI-independent PC auto-level. The engine call runs from a later
    // frame, after the channel request and its drain tick have unwound.
    virtual Result auto_levelup() = 0;
    virtual bool take_auto_levelup_result(Result* status, AutoLevelResult* out) = 0;
    virtual Result after_frame() = 0;
    virtual Result set_fixed_step(int hz) = 0;
    virtual Result set_movies(bool enabled) = 0;
    virtual bool movies_enabled() = 0;
    virtual Result walk_globals(GlobalsVisitor&) = 0;
    virtual Result walk_journal(JournalVisitor&) = 0;
    virtual std::vector<std::string> missing_sites() = 0;
};

// Picks the K1 or K2 adapter from table.game(). `image_base` is where the image
// actually loaded; 0 means the table's own image_base (no relocation).
std::unique_ptr<EngineAdapter> make_adapter(const hooks::AddressTable& table, std::uintptr_t image_base);

// Detour bodies for the two harness sites, shaped for the running platform
// (thiscall on Windows, stack-this cdecl on the native ELF), handed to
// HookSet::add as HookRequest::detour.
void* client_set_game_speed_detour();
void* client_play_movies_detour();

// Called once hooks are installed, so the two bodies can reach their originals.
std::atomic<void*>* adapter_original_slot(std::string_view site);
void bind_adapter_originals(const hooks::HookSet&);

}  // namespace kp::harness
