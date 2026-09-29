// Engine object layouts that differ between the two engine ABIs.
//
// The i386 values are the long-standing ones (Windows PE builds, K2 ELF). The
// x86_64 values describe both macOS Steam builds and are not typed in from
// anywhere: tools/mac/gen_mac_tables.py reads every one of them back out of
// the machine code of both retail images and refuses to generate the address
// tables if any disagrees with this header (see kX64Layout in that tool and
// data/adjudication/mac_x64_bindings.json for the instruction each comes from).
#pragma once

#include <cstddef>
#include <cstdint>

#include "platform/target.hpp"

namespace kp::api::layout {

struct EngineLayout {
    // CExoString { char* text; uint32 length; }
    std::size_t exostring_length;
    // CExoArrayList<T> { T* data; int32 size; int32 capacity; }
    std::size_t arraylist_size_field;
    std::size_t arraylist_bytes;
    // CScriptEvent: uint16 type at 0, then four CExoArrayLists.
    std::size_t script_event_bytes;
    std::size_t script_event_ints;
    std::size_t script_event_floats;
    std::size_t script_event_strings;
    std::size_t script_event_objects;
    std::size_t object_id_bytes;       // element size of the object list and of an id in memory
    // CGameObject { vtable; id; uint8 type; ... }
    std::size_t game_object_id;
    // CSWVirtualMachineCommands { vtable; int has_caller; id caller; commands*; ... }
    std::size_t commands_has_caller;
    std::size_t commands_caller_id;
    std::size_t commands_table;
    // One ExecuteCommand table entry: a plain function pointer on MSVC i386,
    // an Itanium pointer-to-member { ptr, adj } on x86_64.
    std::size_t command_entry_bytes;
    // Where the CGameObject subobject sits inside CSWSArea / CSWSModule (the
    // `this` their EventHandler receives). i386: area embeds it at 284; the
    // i386 module value is a pointer field (see events/payload.cpp).
    std::size_t area_game_object;
    std::size_t module_game_object;
    bool module_game_object_is_pointer;
};

inline constexpr EngineLayout kI386{
    /*exostring_length*/ 4,
    /*arraylist_size_field*/ 4, /*arraylist_bytes*/ 12,
    /*script_event_bytes*/ 0x34, /*ints*/ 0x04, /*floats*/ 0x10, /*strings*/ 0x1C, /*objects*/ 0x28,
    /*object_id_bytes*/ 4,
    /*game_object_id*/ 4,
    /*commands_has_caller*/ 4, /*commands_caller_id*/ 8, /*commands_table*/ 0x0C,
    /*command_entry_bytes*/ 4,
    /*area_game_object*/ 284, /*module_game_object*/ 28, /*module_game_object_is_pointer*/ true,
};

inline constexpr EngineLayout kX64{
    /*exostring_length*/ 8,
    /*arraylist_size_field*/ 8, /*arraylist_bytes*/ 16,
    /*script_event_bytes*/ 0x48, /*ints*/ 0x08, /*floats*/ 0x18, /*strings*/ 0x28, /*objects*/ 0x38,
    /*object_id_bytes*/ 8,
    /*game_object_id*/ 8,
    /*commands_has_caller*/ 8, /*commands_caller_id*/ 0x10, /*commands_table*/ 0x18,
    /*command_entry_bytes*/ 16,
    /*area_game_object*/ 0x158, /*module_game_object*/ 0x28, /*module_game_object_is_pointer*/ false,
};

inline constexpr const EngineLayout& kEngine = abi::kX64 ? kX64 : kI386;

}  // namespace kp::api::layout
