#pragma once
#include "devtools/history.hpp"
#include "imgui.h"
#include <array>
#include <cstdint>
#include <deque>
#include <functional>
#include <mutex>
namespace kp::devtools {
// Event-time keyboard semantics shared by Win32 delivery and headless ImGui
// tests. No Lua or game API is called here; Submit only enqueues source.
class EditorInput {
public:
  using Submit = std::function<bool(const std::string &)>;
  using Complete = std::function<std::vector<std::string>(const std::string &)>;
  using Notice = std::function<void(const std::string &)>;
  EditorInput(Submit submit, Complete complete, Notice notice);
  void
  text(std::string text); // UTF-8; paste is the same ordered text operation
  void key(ImGuiKey key, bool ctrl, bool shift, bool alt, bool repeat = false);
  void close(); // discard queued actions; visible edit text remains for review
  void
  prepare(); // render owner, after platform NewFrame, before ImGui NewFrame
  void draw(const char *label, ImVec2 size);
  std::string draft() const {
    return buffer_.data();
  } // owner-thread diagnostics
  bool pending();

private:
  enum class Kind {
    Text,
    SelectAll,
    Older,
    Newer,
    Submit,
    Newline,
    Paste,
    Complete,
    Raw
  };
  struct Event {
    Kind kind;
    std::string text;
    ImGuiKey key = ImGuiKey_None;
    bool ctrl = false, shift = false, alt = false;
    std::uint64_t sequence = 0;
  };
  void enqueue(Event event);
  static int callback(ImGuiInputTextCallbackData *data);
  void apply(ImGuiInputTextCallbackData *data);
  bool insert(ImGuiInputTextCallbackData *data, const std::string &text);
  Submit submit_;
  Complete complete_;
  Notice notice_;
  History history_;
  std::array<char, 16385> buffer_{};
  std::mutex mutex_;
  std::deque<Event> events_;
  std::size_t queued_bytes_ = 0;
  bool blocked_ = false, overflow_notice_ = false, barrier_ = false;
  std::uint64_t next_sequence_ = 0, raw_inflight_ = 0;
  ImGuiID widget_id_ = 0;
  ImGuiKey release_ = ImGuiKey_None;
};
} // namespace kp::devtools
