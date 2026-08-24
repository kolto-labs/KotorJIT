// Objects and the party: turning an id into something a script can hold.
//
// This is where Phasor's resolveplayer / getplayer / getplayerobject /
// getteamsize / getname / getobjectcoords land, reshaped for KOTOR. Two shape
// changes do most of the work:
//
//   * A party of up to three, not sixteen network players. Phasor's constant
//     index<->id indirection over 16 fixed slots collapses to a short walk of
//     GetPartyMemberCount and GetPartyMemberByIndex.
//   * The engine already answers these questions. GetPosition, GetTag, GetName,
//     GetFirstPC, GetArea and GetObjectByTag are engine routines, so almost
//     nothing here is new engine work -- it is a named layer over the routine
//     bridge in api/routines.hpp. Where a Phasor function has a routine behind
//     it, we call the routine and the engine does its own bookkeeping.
//
// The one thing this module adds that the routine bridge does not have is a
// typed handle. A bare object id is a number that says nothing about what it
// names and stays a number after the object it named is gone; ids are recycled,
// so a stale number can start naming something else. A handle records the id
// and the object type it had when it was made, and every use re-asks the engine
// whether both still hold. A handle that no longer resolves says so; it never
// hands back a stale answer.
//
// Nothing in this file dereferences an engine address, which is why there is no
// call to platform::is_readable here. Everything goes through a routine, and
// the addresses stay on the engine's side of that call.
#pragma once

#include <cstdint>

struct lua_State;

namespace kp::api::entity {

// The engine's "no object" sentinel. Verified at 0x7f000000 by
// CScriptEvent::GetObjectID, which returns exactly this for an out-of-range
// slot (docs/event-semantics.md).
inline constexpr std::uint32_t kInvalidObject = 0x7f000000u;

// What a script holds and passes around, and what the struct layer can take
// instead of a bare number.
//
// `type` is whatever routine GetObjectType returned when the handle was made.
// This module never interprets it: the numbers are the VM's OBJECT_TYPE_*
// constants, which are a different set from the one-byte object_type at
// CGameObject+0x08 that the struct layer uses to pick a layout (4=area,
// 5=creature, 6=item, 9=placeable, 10=door...). Conflating the two is a real
// trap, so this module stores the number, compares it for equality, and leaves
// the meaning to whoever knows which set they are looking at.
struct Handle {
    std::uint32_t id = kInvalidObject;
    int           type = 0;
    bool          type_known = false;
};

// Register kotor.obj.* into one script's state. The runtime calls this once per
// script, next to the other modules' registrars.
//
// The `kotor` table is shared: this checks for it and reuses it rather than
// installing a fresh one, and api::register_all must do the same, because the
// order the two run in is not fixed and whichever ran first would otherwise
// lose its functions. The same check applies to `kp`, where data/hostapi.toml
// names these functions kp.obj.*; that name is bound to the same table object,
// never to a second implementation.
void register_all(lua_State*);

// Handle plumbing, exposed for the struct layer.
//
// push_handle pushes a fresh handle userdata. to_handle returns the handle at
// `index`, or nullptr when the value there is not one -- it does not raise, so
// it is usable as a test. object_arg accepts either a handle or a plain numeric
// id, because Phasor scripts pass ids around as numbers and that habit should
// keep working; it returns false for anything else without raising.
void  push_handle(lua_State*, const Handle&);
Handle* to_handle(lua_State*, int index);
bool  object_arg(lua_State*, int index, std::uint32_t& id);

// Ask the engine what `id` currently names. False when the id does not resolve,
// which includes the case where the routine bridge is not usable yet -- an
// unanswerable question and a negative answer are the same thing to a caller
// that must not act on a stale handle.
bool resolve(lua_State*, std::uint32_t id, Handle& out);

// Whether the routine bridge can be called right now. False before the VM
// binding resolves, which is a real state: OnScriptLoad runs before the first
// tick of a loaded game.
bool ready();

}  // namespace kp::api::entity
