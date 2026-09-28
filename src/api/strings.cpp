#include "api/strings.hpp"

#include "api/output.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
}

namespace kp::api {

namespace {

// The whitespace a command line separates on. Space and tab are what a player
// types; the rest arrive when a line was pasted or assembled from a file.
bool is_space(char c) {
    return c == ' ' || c == '\t' || c == '\r' || c == '\n' || c == '\v' || c == '\f';
}

// Push a vector as a 1-based Lua array.
void push_array(lua_State* L, const std::vector<std::string>& tokens) {
    lua_createtable(L, int(tokens.size()), 0);
    for (std::size_t i = 0; i < tokens.size(); ++i) {
        lua_pushlstring(L, tokens[i].c_str(), tokens[i].size());
        lua_rawseti(L, -2, int(i) + 1);
    }
}

// The argument check is spelled out rather than left to luaL_checkstring
// because that one accepts a number: tokenizestring(42, ",") would silently
// become tokenizestring("42", ","). Phasor raises "expected string, got
// <type>" on a non-string, and a splitter that quietly stringifies its input is
// how a nil-turned-"nil" gets tokenised into a command nobody typed.
const char* check_string(lua_State* L, int index, std::size_t* len) {
    if (lua_type(L, index) != LUA_TSTRING)
        luaL_argerror(L, index, lua_pushfstring(L, "expected string, got %s",
                                                luaL_typename(L, index)));
    return lua_tolstring(L, index, len);
}

int l_tokenizestring(lua_State* L) {
    const int argc = lua_gettop(L);
    if (argc != 2)
        return luaL_error(L, "kp.tokenizestring expects 2 arguments (got %d)", argc);

    std::size_t str_len = 0, delim_len = 0;
    const char* str   = check_string(L, 1, &str_len);
    const char* delim = check_string(L, 2, &delim_len);

    push_array(L, tokenize(std::string_view(str, str_len),
                           std::string_view(delim, delim_len)));
    return 1;
}

int l_tokenizecmdstring(lua_State* L) {
    const int argc = lua_gettop(L);
    if (argc != 1)
        return luaL_error(L, "kp.tokenizecmdstring expects 1 argument (got %d)", argc);

    std::size_t len = 0;
    const char* line = check_string(L, 1, &len);

    push_array(L, tokenize_command(std::string_view(line, len)));
    return 1;
}

}  // namespace

std::vector<std::string> tokenize(std::string_view str, std::string_view delims) {
    std::vector<std::string> tokens;
    if (str.empty()) return tokens;
    if (delims.empty()) { tokens.emplace_back(str); return tokens; }

    std::size_t start = 0;
    while (start < str.size()) {
        const std::size_t pos = str.find_first_of(delims, start);
        if (pos == std::string_view::npos) {
            tokens.emplace_back(str.substr(start));
            break;
        }
        // The guard is the empty-field rule: a separator sitting directly on
        // the previous one contributes nothing.
        if (pos > start) tokens.emplace_back(str.substr(start, pos - start));
        start = pos + 1;
    }
    return tokens;
}

std::vector<std::string> tokenize_command(std::string_view line) {
    std::vector<std::string> tokens;
    std::size_t i = 0;
    while (i < line.size()) {
        if (is_space(line[i])) { ++i; continue; }

        if (line[i] == '"') {
            const std::size_t open = i + 1;
            const std::size_t close = line.find('"', open);
            if (close == std::string_view::npos) {
                // Unterminated. Everything after the quote is the last token,
                // which is what the user typed even if it is not what they
                // meant.
                tokens.emplace_back(line.substr(open));
                break;
            }
            tokens.emplace_back(line.substr(open, close - open));
            i = close + 1;
            continue;
        }

        std::size_t end = i;
        while (end < line.size() && !is_space(line[end])) ++end;
        tokens.emplace_back(line.substr(i, end - i));
        i = end;
    }
    return tokens;
}

void register_strings(lua_State* L) {
    push_kp_table(L);
    lua_pushcfunction(L, l_tokenizestring);     lua_setfield(L, -2, "tokenizestring");
    lua_pushcfunction(L, l_tokenizecmdstring);  lua_setfield(L, -2, "tokenizecmdstring");
    lua_pop(L, 1);
}

}  // namespace kp::api
