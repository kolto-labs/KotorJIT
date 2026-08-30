// Calling the game's own engine routines from Lua.
//
// The game dispatches every NWScript routine through one runtime array of
// function pointers indexed by routine id:
//
//   VirtualMachineErrorCodes ExecuteCommand(this, int command_id, int argc) {
//     if (command_id < 0x304 && commands[command_id])
//       return commands[command_id](this, command_id, argc);
//     return COMMAND_NOT_FOUND;
//   }
//
// So calling a routine is: push its arguments onto the VM stack in reverse,
// invoke the dispatcher with the id and argument count, and pop the result. No
// per-routine hook, no new bytecode, and no patched nwscript.nss -- one generic
// bridge covers 769 of 772 routines on KOTOR 1 and 803 documented ones on
// KOTOR 2. AssignCommand, DelayCommand, and ActionDoCommand take a script
// closure and are refused; kotor.registertimer replaces DelayCommand.
//
// Argument order matters and is easy to get wrong. The VM stack is a stack:
// the routine pops its first declared parameter first, so we push the LAST
// declared parameter first. Getting this backwards produces routines that
// "work" for symmetric signatures and silently corrupt everything else.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

struct lua_State;

namespace kp::api {

enum class Type { Void, Int, Float, String, Object, Vector, Effect, Event, Location, Talent };

// The four engine structures KOTOR's VM knows, by their VM type id. NWN has a
// fifth, itemproperty; KOTOR does not, and assuming otherwise would push a type
// id the VM rejects.
enum class EngineStruct { Effect = 0, Event = 1, Location = 2, Talent = 3 };

struct Param {
    Type        type;
    const char* name;
    bool        has_default;
};

struct Routine {
    std::uint16_t id;
    const char*   name;
    Type          returns;
    const Param*  params;
    std::uint8_t  param_count;
    std::uint8_t  required_count;   // params before the first defaulted one
};

// The generated table for the running game.
const std::vector<Routine>& table();
const Routine* find(const std::string& name);
const Routine* find(std::uint16_t id);

// Bound to the game's VM once the address table has resolved. Kept as function
// pointers rather than direct calls so the bridge stays build-agnostic.
struct VmBinding {
    void* command_implementer = nullptr;   // CSWVirtualMachineCommands*
    void* virtual_machine     = nullptr;   // CVirtualMachine*

    // __thiscall, all of them. The trampoline layer supplies shims.
    int (*execute_command)(void* self, int id, int argc) = nullptr;
    int (*push_int)(void* vm, int v)            = nullptr;
    int (*push_float)(void* vm, float v)        = nullptr;
    int (*push_string)(void* vm, const void* s) = nullptr;
    int (*push_object)(void* vm, std::uint32_t) = nullptr;
    int (*pop_int)(void* vm, int* out)          = nullptr;
    int (*pop_float)(void* vm, float* out)      = nullptr;
    int (*pop_string)(void* vm, void* out)      = nullptr;
    int (*pop_object)(void* vm, std::uint32_t*) = nullptr;

    bool usable() const {
        return command_implementer && virtual_machine && execute_command
            && push_int && pop_int;
    }
};

void bind(const VmBinding&);
const VmBinding& binding();

// Register `kotor.<RoutineName>` for every routine in the table onto a script's
// state. Registration is by name, so a script calls kotor.GetModule() rather
// than remembering that GetModule is id 242.
void register_all(lua_State*);

// Call one routine with arguments already on the Lua stack starting at
// `first_arg`. Returns the number of values pushed back (0 or 1).
//
// Errors are raised as Lua errors, which the host's pcall turns into a script
// error rather than a crash. Calling a routine before the VM is bound, or with
// too few arguments, is a script bug and should read like one.
int call(lua_State*, const Routine&, int first_arg);

}  // namespace kp::api
