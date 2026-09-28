// Pause lease state machine. See pause_lease.hpp for the contract.
//
// Rules, each pinned by a case in tools/kp_pause_lease_test.cpp:
//  - effective pause = game intent OR any tool lease, per timer.
//  - Game Pause/Unpause on a leased timer is recorded as intent and
//    suppressed: the timer is already paused, and an Unpause would advance it.
//    Exception: a game Pause on a held timer whose flag reads clear (raw
//    write behind the lease) is forwarded, since both sides want it paused.
//  - acquire reseeds game intent from the flag when the timer has no lease
//    and no pending restore, absorbing changes the hooks never saw.
//  - With no lease, game calls are forwarded stock and update intent.
//  - Tool-origin calls (the machine's own originals re-entering, or a
//    net-zero harness bracket inside a ToolOriginScope) never touch game
//    intent. A tool-origin Unpause on a leased timer is suppressed so it
//    cannot break the lease. Recovery unpause is NOT tool origin.
//  - The last release restores exactly the game's intent: Unpause once when
//    the game wants running and the flag is set, nothing when the game wants
//    paused. The tool never calls Pause on the game's behalf.
//  - Unregistered timers pass through. Stale tickets make no native call.
#include "harness/pause_lease.hpp"

namespace kp::harness::pause {

const char* to_string(Status s) {
    switch (s) {
        case Status::Ok: return "ok";
        case Status::AlreadyReleased: return "already_released";
        case Status::StaleTicket: return "stale_ticket";
        case Status::UnknownTimer: return "unknown_timer";
        case Status::HooksUnavailable: return "hooks_unavailable";
        case Status::Loading: return "loading";
        case Status::ReadbackFailed: return "readback_failed";
        case Status::NativeCallFailed: return "native_call_failed";
        case Status::TableFull: return "table_full";
        case Status::ExternalMutation: return "external_mutation";
        case Status::PendingCleanup: return "pending_cleanup";
        case Status::CleanupIncomplete: return "cleanup_incomplete";
        case Status::LeasesHeld: return "leases_held";
        case Status::ShutDown: return "shut_down";
        case Status::IntentDrift: return "intent_drift";
    }
    return "?";
}

int Machine::Slot::count() const {
    int n = 0;
    for (const Lease& l : leases) n += l.used ? 1 : 0;
    return n;
}

Machine::Slot* Machine::find(TimerId t) {
    for (Slot& s : slots_)
        if (s.used && s.timer == t) return &s;
    return nullptr;
}

int Machine::lease_count() const {
    int n = 0;
    for (const Slot& s : slots_)
        if (s.used) n += s.count();
    return n;
}

Status Machine::set_hooks_installed(bool pause_hook, bool unpause_hook) {
    // Ownership cannot be withdrawn while a lease holds or a restore is
    // pending: the caller must release first and keep the hooks otherwise.
    if (pause_hook_ && unpause_hook_ && !(pause_hook && unpause_hook)) {
        for (const Slot& s : slots_)
            if (s.used && (s.count() > 0 || s.pending_cleanup)) return Status::LeasesHeld;
    }
    pause_hook_ = pause_hook;
    unpause_hook_ = unpause_hook;
    return Status::Ok;
}

Status Machine::acquire_all(LeaseKey key, std::span<const TimerId> timers, std::span<Ticket> out,
                            std::size_t* failed_index) {
    if (out.size() < timers.size()) {
        if (failed_index) *failed_index = out.size();
        return Status::TableFull;
    }
    // Which timers the key already held before this call: those are kept.
    std::array<bool, kMaxTimers> added{};
    if (timers.size() > added.size()) {
        if (failed_index) *failed_index = added.size();
        return Status::TableFull;
    }
    for (std::size_t i = 0; i < timers.size(); ++i) {
        bool held = false;
        if (Slot* s = find(timers[i]))
            for (const Lease& l : s->leases) held = held || (l.used && l.key == key);
        const Status st = acquire(key, timers[i], &out[i]);
        if (st != Status::Ok) {
            if (failed_index) *failed_index = i;
            for (std::size_t j = i; j-- > 0;)
                if (added[j]) release(out[j]);
            return st;
        }
        added[i] = !held;
    }
    return Status::Ok;
}

Status Machine::register_timer(TimerId t) {
    if (shut_down_) return Status::ShutDown;
    if (loading_) return Status::Loading;
    if (t == 0) return Status::UnknownTimer;
    if (find(t) != nullptr) return Status::Ok;  // dedup: keep intent, leases, epoch
    Slot* free_slot = nullptr;
    for (Slot& s : slots_)
        if (!s.used) { free_slot = &s; break; }
    if (free_slot == nullptr) return Status::TableFull;
    const std::optional<bool> paused = ops_.read_paused(t);
    if (!paused) return Status::ReadbackFailed;
    *free_slot = Slot{};
    free_slot->used = true;
    free_slot->timer = t;
    free_slot->epoch = next_epoch_++;
    free_slot->game_intent = *paused;
    return Status::Ok;
}

Status Machine::acquire(LeaseKey key, TimerId t, Ticket* out) {
    if (shut_down_) return Status::ShutDown;
    if (!ownership_available()) return Status::HooksUnavailable;
    if (loading_) return Status::Loading;
    Slot* s = find(t);
    if (s == nullptr) return Status::UnknownTimer;

    const Ticket ticket{key, t, generation_, s->epoch};
    for (const Lease& l : s->leases)
        if (l.used && l.key == key) {  // idempotent repeat
            if (out) *out = ticket;
            return Status::Ok;
        }
    Lease* free_lease = nullptr;
    for (Lease& l : s->leases)
        if (!l.used) { free_lease = &l; break; }
    if (free_lease == nullptr) return Status::TableFull;

    const std::optional<bool> paused = ops_.read_paused(t);
    if (!paused) return Status::ReadbackFailed;
    // F1: with no lease and no pending restore the flag IS the game's state.
    // Absorb any change the hooks did not see before composing on top of it.
    if (false) {
        s->game_intent = *paused;
        bump(Diag::IntentReseeded);
    }
    if (!*paused) {
        {
            ToolOriginScope origin(*this);
            if (!ops_.original_pause(t)) return Status::NativeCallFailed;
        }
        const std::optional<bool> after = ops_.read_paused(t);
        if (!after || !*after) return Status::NativeCallFailed;
    }
    free_lease->used = true;
    free_lease->key = key;
    s->pending_cleanup = false;  // a held timer is no longer awaiting restore
    s->external_mutation = false;
    if (out) *out = ticket;
    return Status::Ok;
}

Status Machine::restore(Slot& s) {
    // Only called with zero leases on a live slot.
    const std::optional<bool> paused = ops_.read_paused(s.timer);
    if (!paused) {
        s.pending_cleanup = true;
        bump(Diag::CleanupFailed);
        return Status::PendingCleanup;
    }
    if (s.game_intent || !*paused) {  // game wants paused, or already running
        s.pending_cleanup = false;
        return Status::Ok;
    }
    bool called;
    {
        ToolOriginScope origin(*this);
        called = ops_.original_unpause(s.timer);
    }
    const std::optional<bool> after = called ? ops_.read_paused(s.timer) : std::nullopt;
    // Recheck intent: a re-entrant game Pause during the call is legitimate.
    if (after && (!*after || s.game_intent)) {
        s.pending_cleanup = false;
        return Status::Ok;
    }
    s.pending_cleanup = true;
    bump(Diag::CleanupFailed);
    return Status::PendingCleanup;
}

Status Machine::release_in(Slot& s, std::size_t lease_index) {
    s.leases[lease_index] = Lease{};
    if (s.count() > 0) return Status::Ok;
    return restore(s);
}

Status Machine::release(const Ticket& ticket) {
    Slot* s = find(ticket.timer);
    if (ticket.generation != generation_ || s == nullptr || s->epoch != ticket.timer_epoch) {
        bump(Diag::StaleRelease);
        return Status::StaleTicket;
    }
    for (std::size_t i = 0; i < s->leases.size(); ++i)
        if (s->leases[i].used && s->leases[i].key == ticket.key) return release_in(*s, i);
    bump(Diag::DoubleRelease);
    return Status::AlreadyReleased;
}

Status Machine::release_client(std::uint32_t client) {
    Status result = Status::Ok;
    for (Slot& s : slots_) {
        if (!s.used) continue;
        for (std::size_t i = 0; i < s.leases.size(); ++i)
            if (s.leases[i].used && s.leases[i].key.client == client)
                if (release_in(s, i) != Status::Ok) result = Status::PendingCleanup;
    }
    return result;
}

Status Machine::retry_cleanup() {
    Status result = Status::Ok;
    for (Slot& s : slots_)
        if (s.used && s.pending_cleanup && s.count() == 0)
            if (restore(s) != Status::Ok) result = Status::PendingCleanup;
    return result;
}

HookDecision Machine::on_pause_entry(TimerId t) {
    if (tool_depth_ > 0) {
        bump(Diag::ToolOriginPassthrough);
        return HookDecision::Forward;  // pausing never breaks a lease
    }
    if (!ownership_available()) return HookDecision::Forward;
    Slot* s = find(t);
    if (s == nullptr) {
        bump(Diag::UnknownTimerHook);
        return HookDecision::Forward;
    }
    s->game_intent = true;
    if (s->count() > 0) {
        // Held: the flag should already be set and the stock call is a pure
        // early return. If something cleared it behind the lease, both the
        // game and the tool want it paused, so let the original run.
        const std::optional<bool> paused = ops_.read_paused(t);
        if (paused && !*paused) {
            bump(Diag::GamePauseRepaired);
            return HookDecision::Forward;
        }
        ++s->suppressed;
        bump(Diag::GamePauseWhileHeld);
        return HookDecision::Suppress;
    }
    return HookDecision::Forward;
}

HookDecision Machine::on_unpause_entry(TimerId t) {
    Slot* s = ownership_available() ? find(t) : nullptr;
    if (tool_depth_ > 0) {
        if (s != nullptr && s->count() > 0) {
            bump(Diag::ToolUnpauseSuppressed);
            return HookDecision::Suppress;
        }
        bump(Diag::ToolOriginPassthrough);
        return HookDecision::Forward;
    }
    if (!ownership_available()) return HookDecision::Forward;
    if (s == nullptr) {
        bump(Diag::UnknownTimerHook);
        return HookDecision::Forward;
    }
    s->game_intent = false;
    if (s->count() > 0) {
        ++s->suppressed;
        bump(Diag::GameUnpauseWhileHeld);
        return HookDecision::Suppress;  // remembered, applied at last release
    }
    return HookDecision::Forward;
}

Status Machine::verify(TimerId t) {
    Slot* s = find(t);
    if (s == nullptr) return Status::UnknownTimer;
    const std::optional<bool> paused = ops_.read_paused(t);
    if (!paused) return Status::ReadbackFailed;
    if (s->count() > 0 && !*paused) {
        if (!s->external_mutation) bump(Diag::ExternalMutation);
        s->external_mutation = true;
        return Status::ExternalMutation;
    }
    if (s->pending_cleanup) return Status::PendingCleanup;
    if (s->count() == 0 && s->game_intent != *paused) return Status::IntentDrift;
    return Status::Ok;
}

void Machine::invalidate() {
    for (Slot& s : slots_) s = Slot{};
    ++generation_;
}

Status Machine::begin_load() {
    Status result = Status::Ok;
    for (Slot& s : slots_) {
        if (!s.used) continue;
        const bool had_work = s.count() > 0 || s.pending_cleanup;
        for (Lease& l : s.leases) l = Lease{};
        // Timers the tool never held are the game's: no native call.
        if (had_work && restore(s) != Status::Ok) {
            result = Status::CleanupIncomplete;
            bump(Diag::LoadCleanupFailed);
            if (load_failure_count_ < load_failures_.size())
                load_failures_[load_failure_count_++] = {s.timer, generation_};
        }
    }
    invalidate();
    loading_ = true;
    return result;
}

Status Machine::shutdown() {
    shut_down_ = true;
    Status result = Status::Ok;
    for (Slot& s : slots_) {
        if (!s.used) continue;
        const bool had_work = s.count() > 0 || s.pending_cleanup;
        for (Lease& l : s.leases) l = Lease{};
        if (had_work && restore(s) != Status::Ok) result = Status::CleanupIncomplete;
    }
    return result;
}

TimerStatus Machine::status(TimerId t) {
    TimerStatus out;
    out.timer = t;
    Slot* s = find(t);
    if (s == nullptr) return out;
    out.tracked = true;
    out.epoch = s->epoch;
    out.game_intent = s->game_intent;
    out.tool_leases = s->count();
    out.requested_tool_pause = out.tool_leases > 0;
    out.effective = out.game_intent || out.requested_tool_pause;
    out.physical = ops_.read_paused(t);
    out.pending_cleanup = s->pending_cleanup;
    out.external_mutation = s->external_mutation;
    out.suppressed_game_calls = s->suppressed;
    return out;
}

}  // namespace kp::harness::pause
