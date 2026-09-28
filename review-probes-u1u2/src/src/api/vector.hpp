// kp.vec: a small 3D vector type for Lua scripts.
//
//   local p = kp.vec(nwscript.call("GetPosition", kp.obj.pc():id()))
//   local q = p + kp.vec(0, 0, 2)
//   local d = p:distance(q)                      -- 2
//   nwscript.call("SetFacingPoint", q)          -- still a vector to NWScript
//
// A vec is an ordinary table with numeric fields x, y and z, the same shape the
// routine bridge already reads and returns for an NWScript `vector`. That is
// the whole compatibility story: kp.vec adds a shared metatable and nothing
// the bridge has to know about, and a plain {x=, y=, z=} table still marshals
// exactly as before.
//
// CONSTRUCTION. kp.vec(x, y, z) takes exactly three finite numbers.
// kp.vec(t) copies x, y and z out of any table that has them, which is how a
// routine's plain vector result (or another vec) becomes a vec. Strings are
// not coerced, and NaN or infinity is an error at the call that produced it
// rather than a position that silently never matches anything.
//
// VALUES. Every operation returns a FRESH vec and never modifies its operands.
// The fields stay ordinary and writable (v.z = v.z + 1 is fine); because of
// that, every operation re-checks that x, y and z are finite numbers when it
// reads them.
//
// OPERATORS. a + b, a - b, a * n, n * a, a / n, -a, a == b, tostring(a).
// An operand that is not a vec may be any table with finite x, y, z. Scaling
// takes a finite number; vec * vec is an error (use dot or cross), as is
// dividing by zero. Equality compares coordinates exactly, and only between
// two vecs: Lua 5.1 consults __eq only when both sides share it, so a plain
// table is never == a vec.
//
// METHODS. length, lengthsq, normalize, dot, cross, distance, distancesq,
// lerp(b, t), copy, unpack. normalize() of the zero vector returns a fresh
// zero vector rather than NaNs. lerp does not clamp t.
//
// NAMES. None of these, nor `vec`, equals an NWScript routine name, compared
// case-insensitively (kp_vectortest checks this against the compiled
// catalogue). x, y and z match only the parameter names of routine Vector,
// and they are required: they are the field names the bridge marshals.
//
// The metatable is shared by every vec in a state and protected:
// getmetatable(v) returns "kp.vec" and setmetatable(v, ...) raises.
#pragma once

struct lua_State;

namespace kp::api {

// Installs kp.vec into this state.
void register_vector(lua_State*);

}  // namespace kp::api
