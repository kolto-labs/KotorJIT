// Small, side-effect-free proof for the character-generation panel delta.
#pragma once

#include <cstdint>
#include <span>

namespace kp::harness {

struct ChargenPanelPair {
    std::uintptr_t main = 0;
    std::uintptr_t child = 0;

    constexpr explicit operator bool() const { return main != 0 && child != 0; }
};

// MainCharGen owns its initial route child.  The manager's insertion order is
// unspecified, so accept either ordering only when that direct link proves it.
inline ChargenPanelPair classify_chargen_panel_pair(std::span<const std::uintptr_t> added,
                                                    std::span<const std::uintptr_t> routes) {
    if (added.size() != 2 || routes.size() != 2 || added[0] == 0 || added[1] == 0 ||
        added[0] == added[1])
        return {};
    if (routes[0] == added[1]) return {added[0], added[1]};
    if (routes[1] == added[0]) return {added[1], added[0]};
    return {};
}

}  // namespace kp::harness
