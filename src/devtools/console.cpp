#include "devtools/console.hpp"
extern "C" {
#include <lauxlib.h>
#include <lua.h>
#include <luajit.h>
#include <lualib.h>
}
#include <algorithm>
#include <cstdio>
#include <unordered_set>
namespace kp::devtools {
namespace {
thread_local Console *running = nullptr;
std::string value(lua_State *L, int i) {
  switch (lua_type(L, i)) {
  case LUA_TNIL:
    return "nil";
  case LUA_TBOOLEAN:
    return lua_toboolean(L, i) ? "true" : "false";
  case LUA_TSTRING: {
    size_t n;
    const char *p = lua_tolstring(L, i, &n);
    return std::string(p, std::min(n, size_t(8192)));
  }
  case LUA_TNUMBER: {
    char b[64];
    std::snprintf(b, sizeof b, "%.17g", lua_tonumber(L, i));
    return b;
  }
  default: {
    char b[80];
    std::snprintf(b, sizeof b, "%s: %p", luaL_typename(L, i),
                  lua_topointer(L, i));
    return b;
  }
  }
}
int print(lua_State *L) {
  std::string s;
  for (int i = 1; i <= lua_gettop(L); ++i) {
    if (i > 1)
      s += '\t';
    // Match stock print's global tostring behavior, including metamethods.
    lua_getglobal(L, "tostring");
    lua_pushvalue(L, i);
    lua_call(L, 1, 1);
    size_t n;
    const char *p = lua_tolstring(L, -1, &n);
    if (!p)
      return luaL_error(L, "tostring must return a string to print");
    s.append(p, std::min(n, size_t(8192)));
    lua_pop(L, 1);
  }
  if (running)
    running->output("stdout", s + "\n");
  return 0;
}
int file_write(lua_State *L) {
  bool out = lua_rawequal(L, 1, lua_upvalueindex(2));
  bool err = lua_rawequal(L, 1, lua_upvalueindex(3));
  if (!out && !err) {
    lua_pushvalue(L, lua_upvalueindex(1));
    lua_insert(L, 1);
    lua_call(L, lua_gettop(L) - 1, LUA_MULTRET);
    return lua_gettop(L);
  }
  std::string s;
  for (int i = 2; i <= lua_gettop(L); ++i) {
    size_t n;
    const char *p = luaL_checklstring(L, i, &n);
    s.append(p, std::min(n, size_t(8192)));
  }
  if (running)
    running->output(err ? "stderr" : "stdout", s);
  lua_pushvalue(L, 1);
  return 1;
}
int write(lua_State *L) {
  int n = lua_gettop(L);
  lua_getglobal(L, "io");
  lua_getfield(L, -1, "output");
  lua_call(L, 0, 1);
  if (!lua_rawequal(L, -1, lua_upvalueindex(2))) {
    lua_settop(L, n);
    lua_pushvalue(L, lua_upvalueindex(1));
    lua_insert(L, 1);
    lua_call(L, n, LUA_MULTRET);
    return lua_gettop(L);
  }
  lua_settop(L, n);
  std::string s;
  for (int i = 1; i <= n; ++i) {
    size_t len;
    const char *p = luaL_checklstring(L, i, &len);
    s.append(p, std::min(len, size_t(8192)));
  }
  if (running)
    running->output("stdout", s);
  lua_pushvalue(L, lua_upvalueindex(2));
  return 1;
}
int traceback(lua_State *L) {
  const char *s = lua_tostring(L, 1);
  luaL_traceback(L, L, s ? s : "non-string error", 1);
  return 1;
}
void budget(lua_State *L, lua_Debug *) {
  if (running && running->interrupted())
    luaL_error(L, "console cancelled or instruction budget exhausted");
}
void replace(lua_State *L, int table, const char *key, lua_CFunction fn) {
  lua_getfield(L, table, key);
  lua_pushcfunction(L, fn);
  lua_setfield(L, table, key);
}
} // namespace
Console::~Console() { reset(); }
Console &console() {
  static Console c;
  return c;
}
std::uint64_t Console::submit(std::string code) {
  std::uint64_t id = 0;
  {
    std::lock_guard lock(mutex_);
    if (queue_.size() < 16 && code.size() <= 16384) {
      id = ++submitted_;
      queue_.push_back({id, std::move(code)});
    }
  }
  if (!id)
    output(
        "error",
        "Submission rejected: queue full (16) or command exceeds 16384 bytes.");
  return id;
}
Status Console::status() {
  std::lock_guard lock(mutex_);
  return {submitted_, completed_, active_.load() != 0, queue_.size()};
}
void Console::output(std::string kind, std::string text) {
  if (text.size() > 8192)
    text = text.substr(0, 8192) + " [truncated]";
  std::lock_guard lock(mutex_);
  bytes_ += text.size();
  lines_.push_back({std::move(kind), std::move(text), active_.load()});
  while (lines_.size() > 512 || bytes_ > 262144) {
    bytes_ -= lines_.front().text.size();
    lines_.pop_front();
  }
}
std::vector<Line> Console::snapshot() {
  std::lock_guard lock(mutex_);
  return {lines_.begin(), lines_.end()};
}
std::vector<std::string> Console::complete(const std::string &prefix) {
  std::lock_guard lock(mutex_);
  std::vector<std::string> r;
  for (auto &n : names_)
    if (n.rfind(prefix, 0) == 0 && r.size() < 64)
      r.push_back(n);
  return r;
}
bool Console::interrupted() {
  instructions_ += 1000;
  return cancelled_.load() || instructions_ >= 1000000;
}
void Console::reset() {
  if (state_)
    lua_close(state_);
  state_ = nullptr;
}
void Console::pump(const std::function<void(lua_State *)> &init) {
  static thread_local bool busy = false;
  if (busy)
    return;
  if (!state_) {
    state_ = luaL_newstate();
    if (state_) {
      luaL_openlibs(state_);
      if (init)
        init(state_);
      lua_getglobal(state_, "io");
      io_ref_ = luaL_ref(state_, LUA_REGISTRYINDEX);
      index();
    }
  }
  std::string code;
  {
    std::lock_guard lock(mutex_);
    if (queue_.empty())
      return;
    active_ = queue_.front().first;
    code = std::move(queue_.front().second);
    queue_.pop_front();
  }
  busy = true;
  if (state_) {
    execute(code);
    index();
  } else
    output("error", "Cannot allocate Lua state");
  {
    std::lock_guard lock(mutex_);
    completed_ = active_;
    active_ = 0;
  }
  busy = false;
}
void Console::execute(const std::string &code) {
  auto *L = state_;
  const int base = lua_gettop(L);
  output("input", "> " + code);
  // Routing is scoped to this execution, then exact previous globals restored.
  replace(L, LUA_GLOBALSINDEX, "print", print);
  const int oldprint = lua_gettop(L);
  lua_rawgeti(L, LUA_REGISTRYINDEX, io_ref_);
  const int io = lua_gettop(L);
  lua_getfield(L, io, "write");
  const int oldwrite = lua_gettop(L);
  lua_pushvalue(L, oldwrite);
  lua_getfield(L, io, "stdout");
  lua_pushcclosure(L, write, 2);
  lua_setfield(L, io, "write");
  luaL_getmetatable(L, LUA_FILEHANDLE);
  const int filemeta = lua_gettop(L);
  lua_getfield(L, filemeta, "write");
  const int oldfilewrite = lua_gettop(L);
  lua_pushvalue(L, oldfilewrite);
  lua_getfield(L, io, "stdout");
  lua_getfield(L, io, "stderr");
  lua_pushcclosure(L, file_write, 3);
  lua_setfield(L, filemeta, "write");
  lua_pushcfunction(L, traceback);
  const int handler = lua_gettop(L);
  std::string expr = "return " + code;
  int rc = luaL_loadbuffer(L, expr.data(), expr.size(), "=devtools");
  if (rc) {
    lua_pop(L, 1);
    rc = luaL_loadbuffer(L, code.data(), code.size(), "=devtools");
  }
  cancelled_ = false;
  instructions_ = 0;
  running = this;
  // Disable JIT on the whole state and flush traces: compiled loops bypass
  // hooks.
  luaJIT_setmode(L, 0, LUAJIT_MODE_ENGINE | LUAJIT_MODE_OFF);
  luaJIT_setmode(L, 0, LUAJIT_MODE_ENGINE | LUAJIT_MODE_FLUSH);
  lua_sethook(L, budget, LUA_MASKCOUNT, 1000);
  if (!rc)
    rc = lua_pcall(L, 0, LUA_MULTRET, handler);
  lua_sethook(L, nullptr, 0, 0);
  running = nullptr;
  if (rc)
    output("error", value(L, -1));
  else {
    int n = lua_gettop(L) - handler;
    if (!n)
      output("result", "ok (no return values)");
    for (int i = handler + 1; i <= lua_gettop(L); ++i)
      output("result", std::string(luaL_typename(L, i)) + ": " + value(L, i));
  }
  lua_pushvalue(L, oldprint);
  lua_setglobal(L, "print");
  lua_pushvalue(L, oldwrite);
  lua_setfield(L, io, "write");
  lua_pushvalue(L, oldfilewrite);
  lua_setfield(L, filemeta, "write");
  lua_settop(L, base);
}
void Console::index() {
  std::vector<std::string> names;
  std::unordered_set<const void *> visited;
  unsigned inspected = 0;
  auto *L = state_;
  int base = lua_gettop(L);
  auto walk = [&](auto &&self, int t, std::string prefix, int depth) -> void {
    if (!visited.insert(lua_topointer(L, t)).second)
      return;
    unsigned table_inspected = 0;
    lua_pushnil(L);
    while (lua_next(L, t) != 0) {
      ++inspected;
      ++table_inspected;
      if (lua_type(L, -2) == LUA_TSTRING) {
        std::string key = lua_tostring(L, -2);
        if (key.size() < 100 &&
            key.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQR"
                                  "STUVWXYZ0123456789_") == std::string::npos) {
          auto name = prefix + key;
          names.push_back(name);
          if (depth < 2 && key != "_G" && key != "package" &&
              lua_istable(L, -1) && names.size() < 4096)
            self(self, lua_gettop(L), name + ".", depth + 1);
        }
      }
      lua_pop(L, 1);
      if (names.size() >= 4096 || inspected >= 16384 ||
          table_inspected >= 256) {
        lua_pop(L, 1);
        break;
      }
    }
  };
  walk(walk, LUA_GLOBALSINDEX, "", 0);
  lua_settop(L, base);
  std::sort(names.begin(), names.end());
  names.erase(std::unique(names.begin(), names.end()), names.end());
  std::lock_guard lock(mutex_);
  names_ = std::move(names);
}
} // namespace kp::devtools
