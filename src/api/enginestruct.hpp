// The parts of the routine bridge that `routines.hpp` could not declare.
//
// `routines.hpp` is the agreed interface and is owned elsewhere, so it is not
// edited here. Its `VmBinding` covers the four scalar push/pop pairs and the
// dispatcher, which is enough for the ~600 routines that only move ints, floats,
// strings and object ids. The rest of the bridge needs four more things, and
// they live in this header:
//
//   1. The VM's own vector and engine-structure accessors. A vector is NOT
//      three float pushes; the VM has StackPushVector / StackPopVector and the
//      stack tags differ.
//   2. Lifetime for the four engine structures. What we pop, we own.
//   3. The recovered VALUES of defaulted parameters, because the bridge always
//      pushes the full declared parameter count. See below for why.
//   4. One place that converts raw __thiscall site addresses into the plain
//      function pointers `VmBinding` declares.
//
// WHY THE BRIDGE PUSHES EVERY DECLARED PARAMETER
// ==============================================
// NWScript defaults are a compiler feature. The compiler emits the default
// expression at the call site; the engine handler pops what its signature says.
// Read out of the K1 binary, handlers do not agree with each other:
//
//   ExecuteCommandSuppressStatusSummaryEntry (0x547E50)
//       pops its one int unconditionally, paramCount untouched
//   ExecuteCommandCreateItemOnObject (0x52F570)
//       `cmp DWORD PTR [esp+0x3c],0x3` -- it checks paramCount before pop three
//
// A bridge that pushed only what the script supplied would make every handler of
// the first kind pop whatever was underneath. So the bridge pushes all
// `param_count` values and passes `argc = param_count`, which is correct for
// both kinds. That makes the default VALUE load-bearing rather than cosmetic,
// which is what `find_default` is for. Where the value could not be recovered --
// OBJECT_SELF above all, which is the caller and not a constant -- the argument
// is required and the script gets an error naming it.
//
// WHY THESE ARE __thiscall AND `VmBinding`'s ARE NOT
// =================================================
// Every one of these is a real Aurora method: `this` in ECX, callee-cleans. They
// are declared with `hooks::ThiscallFn` so the compiler emits the right call and
// the right cleanup. `VmBinding`'s members, by contrast, are declared as plain
// function pointers with no attribute -- so they are cdecl, and the runtime must
// hand `bind()` cdecl shims rather than raw site addresses. `bind_sites()` below
// is that conversion, done once, here, so no caller has to know.
#pragma once

#include <cstdint>
#include <string>

#include <cstddef>
#include <cstdint>

#include "api/routines.hpp"
#include "hooks/thiscall.hpp"

struct lua_State;

namespace kp::api {

// The VM's own three-float vector. Layout confirmed against the recovered
// `Vector` struct, which is size-asserted at 0xC.
struct Vec3 {
    float x = 0.0f, y = 0.0f, z = 0.0f;
};

// CExoString, size-asserted at 8 in the recovered layouts. Declared here because
// the string accessors take one by pointer and a caller has to be able to make
// one. ALWAYS zero it before a pop: StackPopString assigns into it, and
// assigning into uninitialised bytes frees a pointer that was never allocated.
struct ExoString {
    const char*   text   = nullptr;
    std::uint32_t length = 0;
};

// The accessors `VmBinding` does not carry. All __thiscall on `virtual_machine`
// except `destroy_engine_structure`, which is a method of the command
// implementer, and `destroy_string`, which is CExoString's destructor.
struct VmEngineAccess {
    void* virtual_machine     = nullptr;   // CVirtualMachine*
    void* command_implementer = nullptr;   // CSWVirtualMachineCommands*

    // StackPushVector takes a Vector BY VALUE. Passing three floats instead is
    // not an approximation: the K1 thunk at 0x5D1050 reads its arguments from
    // [esp+4], [esp+8] and [esp+0xC] and returns with `ret 0xC`, which is
    // exactly the layout and the cleanup of three stacked floats. Spelling it
    // this way avoids relying on GCC and MSVC agreeing about how a 12-byte
    // struct is passed under __thiscall, which is the one case
    // hooks/thiscall.hpp explicitly does not vouch for.
    hooks::ThiscallFn<int, float, float, float> push_vector = nullptr;
    hooks::ThiscallFn<int, Vec3*>               pop_vector  = nullptr;

    // The type argument is the bare engine-structure id, 0..3. The VM adds the
    // 0x10 that turns it into a stack tag; passing the tag would fail the
    // comparison at 0x5D265D and pop nothing.
    hooks::ThiscallFn<int, std::uint32_t, void*>  push_engine_structure = nullptr;
    hooks::ThiscallFn<int, std::uint32_t, void**> pop_engine_structure  = nullptr;

    // OPTIONAL, and their absence is a leak rather than a crash.
    //
    // Both popping paths hand back memory we own. StackPopEngineStructure calls
    // the implementer's CopyGameDefinedStructure (vtable slot 8, +0x20) and
    // gives us the copy. StackPopString calls CExoString::operator=, which
    // allocates. Without these two the bridge still works and still returns
    // correct values; it just never gives the memory back, and says so once in
    // the log rather than silently.
    hooks::ThiscallFn<void, std::uint32_t, void*> destroy_engine_structure = nullptr;
    hooks::ThiscallFn<void>                       destroy_string = nullptr;

    // Snapshot identity plus layout for validating the live dispatcher table
    // before touching the VM stack. A changed table needs a trusted recapture.
    void* const* commands = nullptr;
    std::uint32_t command_count = 0;
    std::uint32_t commands_offset = 0x0C;
    std::uint32_t wrapper_internal_offset = 0;
};

void                  bind_engine_access(const VmEngineAccess&);
const VmEngineAccess& engine_access();
// routine < 0 checks context only (capture and kp.as); otherwise also checks
// the selected live command slot. Never calls into the engine.
bool vm_binding_live(int routine = -1);

// Addresses straight out of data/addresses/<build>.json, by site name. The
// runtime resolves the names; this turns them into everything the bridge needs
// and calls both `kp::api::bind()` and `bind_engine_access()`.
//
// Required sites: vm.execute_command, vm.stack_{push,pop}_{integer,float,
// string,object}. Everything else degrades: without the vector pair, vector
// routines refuse; without the engine-structure pair, the 100-odd routines that
// take or return one refuse; without the two destructors, results leak.
struct VmSites {
    void* command_implementer = nullptr;   // CSWVirtualMachineCommands*
    void* virtual_machine     = nullptr;   // CVirtualMachine*

    // Per-build object layout from field sites. Stack accessors receive the
    // wrapper base and find CVirtualMachineInternal at this offset.
    std::uint32_t wrapper_internal_offset = 0;
    std::uint32_t command_implementer_offset = 0;
    bool layout_resolved = false;

    std::uintptr_t execute_command    = 0;   // vm.execute_command
    std::uintptr_t stack_push_integer = 0;   // vm.stack_push_integer
    std::uintptr_t stack_pop_integer  = 0;   // vm.stack_pop_integer
    std::uintptr_t stack_push_float   = 0;   // vm.stack_push_float
    std::uintptr_t stack_pop_float    = 0;   // vm.stack_pop_float
    std::uintptr_t stack_push_string  = 0;   // vm.stack_push_string
    std::uintptr_t stack_pop_string   = 0;   // vm.stack_pop_string
    std::uintptr_t stack_push_object  = 0;   // vm.stack_push_object
    std::uintptr_t stack_pop_object   = 0;   // vm.stack_pop_object

    std::uintptr_t stack_push_vector  = 0;   // vm.stack_push_vector
    std::uintptr_t stack_pop_vector   = 0;   // vm.stack_pop_vector
    std::uintptr_t stack_push_engine_structure = 0;  // vm.stack_push_engine_structure
    std::uintptr_t stack_pop_engine_structure  = 0;  // vm.stack_pop_engine_structure

    // Not in any address table yet. Named here so the generator has a target.
    // On K1 they are CSWVirtualMachineCommands::DestroyGameDefinedStructure and
    // CExoString::~CExoString.
    std::uintptr_t destroy_game_defined_structure = 0;  // vmcmd.destroy_game_defined_structure
    std::uintptr_t exostring_dtor                 = 0;  // exo.string_dtor

    // Where the command array sits inside CSWVirtualMachineCommands. 0x0C on
    // both games: the K1 dispatcher at 0x52C0D0 reads `mov eax,[ecx+0xc]`, and
    // the size-asserted recovered layout puts `void* commands` at +0xC of a
    // 0x10-byte object. Carried as a field so a build where it moves is a data
    // change at the bind site rather than an edit to a .cpp.
    std::uint32_t commands_offset = 0x0C;
    // The dispatcher's own bound: `cmp edx,0x304` at 0x52C0D6.
    std::uint32_t commands_count = 0x304;
};

bool bind_sites(const VmSites&, std::string& error);

// The dispatcher bound. Stock K1 is `cmp edx, 0x304`. KPM patches that immediate
// to 1000 when it grows the table. Reading the live prologue is what keeps us
// from assuming 772 and missing the extra slots, or walking off a stock table.
std::uint32_t discover_command_count(const VmSites&);

// `81 FA imm32` = cmp edx, imm32. Stock K1 is 0x304; KPM writes 1000.
inline bool decode_execute_command_bound(const std::uint8_t* code, std::size_t len,
                                         std::uint32_t& out) {
    if (code == nullptr) return false;
    for (std::size_t i = 0; i + 6 <= len; ++i) {
        if (code[i] == 0x81 && code[i + 1] == 0xFA) {
            std::uint32_t imm = static_cast<std::uint32_t>(code[i + 2]) |
                                (static_cast<std::uint32_t>(code[i + 3]) << 8) |
                                (static_cast<std::uint32_t>(code[i + 4]) << 16) |
                                (static_cast<std::uint32_t>(code[i + 5]) << 24);
            if (imm > 0 && imm <= 2048) {
                out = imm;
                return true;
            }
        }
    }
    return false;
}

// ------------------------------------------------------- engine structures --
//
// A script holds an effect, event, location or talent as an opaque userdata and
// passes it back. It cannot read fields off it, because the engine gives us a
// pointer and no layout, and inventing one would be a wrong answer rather than
// an error.
//
// `owned` says whether __gc should destroy it. Everything popped off the VM
// stack is owned: the pop already made us a private copy.
void  open_engine_structs(lua_State*);
void  push_engine_struct(lua_State*, EngineStruct, void* handle, bool owned);
void* check_engine_struct(lua_State*, int index, EngineStruct);

// How many handles are alive, for leak reporting from a tool.
unsigned live_engine_structs();

// -------------------------------------------------------- default parameters --

enum class DefaultKind : std::uint8_t { Int, Float, String, Vector };

struct ParamDefault {
    std::uint16_t routine;
    std::uint8_t  index;
    DefaultKind   kind;
    int           i;         // Int
    float         x, y, z;   // Float uses x; Vector uses all three
    const char*   s;         // String
};

// The recovered default for one parameter, or null when the header's default
// was a compiler builtin we cannot evaluate. Null means the script must supply
// the argument.
const ParamDefault* find_default(std::uint16_t routine, std::uint8_t index);

// ----------------------------------------------------------- which game -----
//
// Two routine tables are generated and both are compiled in, because one binary
// serves both games. The choice is latched on first use: `table()` hands out
// `const Routine*` pointers that become Lua upvalues, so swapping tables after a
// script has registered would leave those pointing into the wrong one.
enum class Game { K1, K2 };

bool select_game(Game);   // false, and logs, once the table has been handed out
Game selected_game();

}  // namespace kp::api
