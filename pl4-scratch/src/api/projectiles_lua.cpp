#include "api/output.hpp"
#include "api/projectiles.hpp"
extern "C" {
#include "lauxlib.h"
#include "lua.h"
}
namespace kp::api::projectiles {
namespace {
void number(lua_State *L, const char *key, std::uint64_t n) {
  lua_pushnumber(L, static_cast<lua_Number>(n));
  lua_setfield(L, -2, key);
}
void boolean(lua_State *L, const char *key, bool b) {
  lua_pushboolean(L, b);
  lua_setfield(L, -2, key);
}
void string(lua_State *L, const char *key, const std::string &s) {
  lua_pushlstring(L, s.data(), s.size());
  lua_setfield(L, -2, key);
}
int failure(lua_State *L, const std::string &error) {
  lua_pushnil(L);
  lua_pushlstring(L, error.data(), error.size());
  return 2;
}
int status(lua_State *L) {
  auto s = service().status();
  lua_newtable(L);
  boolean(L, "supported", s.supported);
  boolean(L, "observing", s.observing);
  boolean(L, "enabled", s.enabled);
  number(L, "epoch", s.epoch);
  number(L, "version", s.version);
  number(L, "observed", s.observed);
  number(L, "replaced", s.replaced);
  number(L, "dropped", s.dropped);
  number(L, "capacity", 128);
  string(L, "model", text(s.model));
  string(L, "reason", s.reason);
  string(L, "build", s.build);
  return 1;
}
int configure(lua_State *L) {
  luaL_checktype(L, 1, LUA_TTABLE);
  lua_pushliteral(L, "model");
  lua_rawget(L, 1);
  if (lua_type(L, -1) != LUA_TSTRING)
    return luaL_error(L, "model string required");
  std::size_t size = 0;
  const char *value = lua_tolstring(L, -1, &size);
  std::string error;
  if (!service().configure(std::string(value, size), error))
    return failure(L, error);
  return status(L);
}
int observe(lua_State *L) {
  luaL_checktype(L, 1, LUA_TBOOLEAN);
  std::string error;
  if (!service().observe(lua_toboolean(L, 1) != 0, error))
    return failure(L, error);
  return status(L);
}
int disable(lua_State *L) {
  service().disable();
  return status(L);
}
int records(lua_State *L) {
  auto rows = service().records();
  lua_createtable(L, rows.size(), 0);
  int i = 0;
  for (const auto &r : rows) {
    lua_newtable(L);
    number(L, "sequence", r.sequence);
    number(L, "projectile_token", r.sequence);
    number(L, "epoch", r.epoch);
    number(L, "version", r.version);
    number(L, "source_client", r.source);
    number(L, "target_client", r.target);
    number(L, "ammo_row", r.row);
    number(L, "model_variant", r.variant);
    string(L, "original", text(r.original));
    string(L, "selected", text(r.selected));
    string(L, "reason", r.reason);
    boolean(L, "replaced", r.replaced);
    boolean(L, "load_ok", r.load_ok);
    lua_rawseti(L, -2, ++i);
  }
  return 1;
}
} // namespace
void register_all(lua_State *L) {
  push_kp_table(L);
  lua_newtable(L);
  lua_pushcfunction(L, configure);
  lua_setfield(L, -2, "configure");
  lua_pushcfunction(L, status);
  lua_setfield(L, -2, "status");
  lua_pushcfunction(L, observe);
  lua_setfield(L, -2, "observe");
  lua_pushcfunction(L, disable);
  lua_setfield(L, -2, "disable");
  lua_pushcfunction(L, records);
  lua_setfield(L, -2, "records");
  lua_setfield(L, -2, "projectiles");
  lua_pop(L, 1);
}
} // namespace kp::api::projectiles
