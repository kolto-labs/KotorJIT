// The event ring: what the engine was about to do, in order, with a cursor.
//
// Every hook body already has a point where it knows the engine is about to
// run a script, fire a module event, save or load. Each pushes one record here.
// The driver reads them by sequence number, so "OnModuleLoad was followed by
// OnAreaEnter was followed by a k_pend_* script" is a cursor comparison and
// not a sleep.
//
// Fixed at 4096 records and never allocates after construction: pushes happen
// inside hook bodies on the game's own thread, where an allocation failure is
// not a thing to discover. Text fields are truncated to fit; script and module
// names are ResRefs, sixteen characters, so nothing the engine names is cut.
//
// Not synchronised. Every producer and every reader runs on the main thread:
// the bodies push from inside the engine's calls, and the commands read from
// the client-loop drain. A second thread touching this would be a design
// change, not a missing lock.
#pragma once

#include <cstddef>
#include <cstdint>
#include <string_view>
#include <vector>

namespace kp::harness {

struct EventField {
    enum class Kind : std::uint8_t { None, Int, Uint, Text };

    static constexpr std::size_t kTextCap = 32;   // including the terminator

    const char*   key = nullptr;   // static string; never freed
    Kind          kind = Kind::None;
    std::int64_t  i = 0;
    char          text[kTextCap] = {0};

    static EventField integer(const char* key, std::int64_t v);
    static EventField unsigned_(const char* key, std::uint64_t v);
    static EventField str(const char* key, std::string_view v);   // truncates
};

struct EventRecord {
    static constexpr std::size_t kMaxFields = 4;

    std::uint64_t seq = 0;           // 1 for the first record ever pushed
    std::uint64_t server_tick = 0;
    const char*   name = "";         // static string, e.g. "OnRunScript"
    EventField    fields[kMaxFields];

    std::size_t field_count() const;
};

class EventRing {
public:
    static constexpr std::size_t kCapacity = 4096;

    EventRing();

    // Returns the sequence number assigned. `name` must outlive the ring: the
    // contract table's lua_name strings and string literals both qualify.
    std::uint64_t push(const char* name, std::uint64_t server_tick,
                       const EventField* fields = nullptr, std::size_t count = 0);

    std::uint64_t last_seq() const { return next_seq_ - 1; }
    // Sequence number of the oldest record still held, or 0 when empty.
    std::uint64_t oldest_seq() const;
    std::size_t   size() const { return count_; }

    // Records with seq > `since`, oldest first, at most `limit`. Returns how
    // many were appended. A `since` older than the ring's tail starts at the
    // tail; the caller compares oldest_seq() to notice the gap.
    std::size_t read_since(std::uint64_t since, std::size_t limit,
                           std::vector<EventRecord>& out) const;

    void clear();

private:
    EventRecord   slots_[kCapacity];
    std::size_t   head_ = 0;      // next slot to write
    std::size_t   count_ = 0;
    std::uint64_t next_seq_ = 1;
};

// The process-wide ring the hook bodies push into and the commands read.
EventRing& ring();

}  // namespace kp::harness
