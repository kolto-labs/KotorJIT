// The event ring. See ring.hpp for the contract.
#include "harness/ring.hpp"

#include <cstring>

namespace kp::harness {

EventField EventField::integer(const char* key, std::int64_t v) {
    EventField f;
    f.key = key;
    f.kind = Kind::Int;
    f.i = v;
    return f;
}

EventField EventField::unsigned_(const char* key, std::uint64_t v) {
    EventField f;
    f.key = key;
    f.kind = Kind::Uint;
    f.i = static_cast<std::int64_t>(v);
    return f;
}

EventField EventField::str(const char* key, std::string_view v) {
    EventField f;
    f.key = key;
    f.kind = Kind::Text;
    const std::size_t n = v.size() < kTextCap - 1 ? v.size() : kTextCap - 1;
    std::memcpy(f.text, v.data(), n);
    f.text[n] = '\0';
    return f;
}

std::size_t EventRecord::field_count() const {
    std::size_t n = 0;
    for (const EventField& f : fields) {
        if (f.kind == EventField::Kind::None) break;
        ++n;
    }
    return n;
}

EventRing::EventRing() = default;

std::uint64_t EventRing::push(const char* name, std::uint64_t server_tick,
                              const EventField* fields, std::size_t count) {
    EventRecord& r = slots_[head_];
    r.seq = next_seq_++;
    r.server_tick = server_tick;
    r.name = name != nullptr ? name : "";
    std::size_t i = 0;
    for (; i < count && i < EventRecord::kMaxFields; ++i) r.fields[i] = fields[i];
    for (; i < EventRecord::kMaxFields; ++i) r.fields[i] = EventField{};

    head_ = (head_ + 1) % kCapacity;
    if (count_ < kCapacity) ++count_;
    return r.seq;
}

std::uint64_t EventRing::oldest_seq() const {
    if (count_ == 0) return 0;
    const std::size_t tail = (head_ + kCapacity - count_) % kCapacity;
    return slots_[tail].seq;
}

std::size_t EventRing::read_since(std::uint64_t since, std::size_t limit,
                                  std::vector<EventRecord>& out) const {
    if (count_ == 0 || limit == 0) return 0;
    const std::uint64_t oldest = oldest_seq();
    const std::uint64_t newest = last_seq();
    if (since >= newest) return 0;

    // The ring is dense in seq, so the first wanted record is at a computable
    // slot rather than a scanned one.
    const std::uint64_t first = since + 1 < oldest ? oldest : since + 1;
    const std::size_t tail = (head_ + kCapacity - count_) % kCapacity;
    std::size_t slot = (tail + static_cast<std::size_t>(first - oldest)) % kCapacity;

    std::size_t appended = 0;
    for (std::uint64_t s = first; s <= newest && appended < limit; ++s) {
        out.push_back(slots_[slot]);
        slot = (slot + 1) % kCapacity;
        ++appended;
    }
    return appended;
}

void EventRing::clear() {
    head_ = 0;
    count_ = 0;
    // Sequence numbers keep counting: a cursor the driver holds stays valid
    // across a clear, it just sees nothing until the next push.
}

EventRing& ring() {
    static EventRing r;
    return r;
}

}  // namespace kp::harness
