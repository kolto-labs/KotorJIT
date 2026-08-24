// Tokenising: turning one string into the pieces a command handler wants.
//
// Two functions, both straight from Phasor, and the reason they are worth a
// module of their own is that KOTOR's console hook hands a script a whole input
// line. Splitting it is the first thing any console-command script does, and
// every script that had to write its own splitter wrote a slightly different
// one -- the reference corpus contains at least two reimplementations that
// disagree with each other about empty fields.
//
//   tokenizestring(str, delims)   split at any character in delims
//   tokenizecmdstring(line)       command-line split, quotes kept together
//
// Both return a 1-based array. An empty result is an empty table, never nil,
// so `#tokenizestring(s, d)` is always valid and a caller never has to test
// before indexing.
//
// EMPTY FIELDS ARE DROPPED by tokenizestring. "a,,b" split on "," is two
// tokens, not three. This is stated rather than derived: Phasor's own C++
// splitter is not in this repository, and neither the inventory nor the
// mapping records the behaviour. Two things decided it. The reference corpus
// contains a script-side reimplementation of tokenizestring that drops empty
// parts, written by an author who believed they were matching the host. And
// dropping is what the call sites want -- splitting a comma-separated name
// list, or an address on '/', a trailing separator should not produce a token
// that is the empty string and then get treated as a name.
//
// tokenizecmdstring is the opposite, and deliberately: `""` on a command line
// is an explicit empty argument and survives as an empty token, while runs of
// unquoted whitespace collapse. A user who typed two quote marks meant
// something by them; a user who typed two spaces did not.
#pragma once

#include <string>
#include <string_view>
#include <vector>

struct lua_State;

namespace kp::api {

// Split at any character in `delims`. Empty fields are dropped.
//
// An empty `delims` yields the whole string as one token: there is no character
// to split at, so there is nothing to do. An empty `str` yields nothing at all.
std::vector<std::string> tokenize(std::string_view str, std::string_view delims);

// Command-line split. Whitespace separates; a double-quoted run is one token
// with the quotes removed and its contents kept verbatim, including spaces and
// including nothing at all.
//
// Two edge cases, chosen and stated because a command line is user input and
// user input is malformed:
//
//   * An unterminated quote takes the rest of the line. Discarding it would
//     silently drop what the user typed; erroring would make a typo fatal in
//     the middle of a game.
//   * A quote that is not at the start of a token is a literal character, so
//     `say a"b` is one token `a"b`. Quoting is a property of a whole argument,
//     which is what a shell does and what a player will expect.
std::vector<std::string> tokenize_command(std::string_view line);

// Installs kotor.tokenizestring and kotor.tokenizecmdstring into this state.
void register_strings(lua_State*);

}  // namespace kp::api
