#include "devtools/editor_input.hpp"
#include "imgui_internal.h"
#include <algorithm>
#include <cctype>
namespace kp::devtools {
EditorInput::EditorInput(Submit submit, Complete complete, Notice notice)
    : submit_(std::move(submit)), complete_(std::move(complete)),
      notice_(std::move(notice)) {}
void EditorInput::enqueue(Event event) {
  std::lock_guard lock(mutex_);
  if (blocked_)
    return;
  if (events_.size() >= 1024 || queued_bytes_ + event.text.size() > 65536) {
    events_.clear();
    queued_bytes_ = 0;
    blocked_ = true;
    overflow_notice_ = true;
    return;
  }
  event.sequence = ++next_sequence_;
  queued_bytes_ += event.text.size();
  events_.push_back(std::move(event));
}
void EditorInput::text(std::string text) {
  enqueue({Kind::Text, std::move(text)});
}
void EditorInput::key(ImGuiKey key, bool ctrl, bool shift, bool alt,
                      bool repeat) {
  Kind kind = Kind::Raw;
  if (key == ImGuiKey_Enter || key == ImGuiKey_KeypadEnter)
    kind = ctrl ? Kind::Newline : Kind::Submit;
  else if ((ctrl && key == ImGuiKey_V) || (shift && key == ImGuiKey_Insert))
    kind = Kind::Paste;
  else if (key == ImGuiKey_Tab)
    kind = Kind::Complete;
  else if (ctrl && key == ImGuiKey_A)
    kind = Kind::SelectAll;
  else if (ctrl && key == ImGuiKey_UpArrow)
    kind = Kind::Older;
  else if (ctrl && key == ImGuiKey_DownArrow)
    kind = Kind::Newer;
  if (repeat && kind != Kind::Raw && kind != Kind::Newline)
    return;
  enqueue({kind, {}, key, ctrl, shift, alt});
}
void EditorInput::close() {
  std::lock_guard lock(mutex_);
  events_.clear();
  queued_bytes_ = 0;
  blocked_ = false;
  overflow_notice_ = false;
  // release_ is consumed on the render owner when the editor next opens.
}
bool EditorInput::pending() {
  std::lock_guard lock(mutex_);
  return !events_.empty() || overflow_notice_;
}
void EditorInput::prepare() {
  auto &io = ImGui::GetIO();
  barrier_ = false;
  if (release_ != ImGuiKey_None) {
    io.AddKeyEvent(release_, false);
    release_ = ImGuiKey_None;
    raw_inflight_ = 0;
    io.AddKeyEvent(ImGuiMod_Ctrl, false);
    io.AddKeyEvent(ImGuiMod_Shift, false);
    io.AddKeyEvent(ImGuiMod_Alt, false);
    barrier_ = true;
    return;
  }
  std::lock_guard lock(mutex_);
  if (ImGui::GetActiveID() != widget_id_ || !widget_id_ || events_.empty() ||
      events_.front().kind != Kind::Raw)
    return;
  const auto &event = events_.front();
  raw_inflight_ = event.sequence;
  io.AddKeyEvent(ImGuiMod_Ctrl, event.ctrl);
  io.AddKeyEvent(ImGuiMod_Shift, event.shift);
  io.AddKeyEvent(ImGuiMod_Alt, event.alt);
  io.AddKeyEvent(event.key, true);
  release_ = event.key;
}
void EditorInput::draw(const char *label, ImVec2 size) {
  widget_id_ = ImGui::GetID(label);
  if (pending() && ImGui::GetActiveID() != widget_id_)
    ImGui::SetKeyboardFocusHere();
  ImGui::InputTextMultiline(label, buffer_.data(), buffer_.size(), size,
                            ImGuiInputTextFlags_CallbackAlways, callback, this);
}
int EditorInput::callback(ImGuiInputTextCallbackData *data) {
  static_cast<EditorInput *>(data->UserData)->apply(data);
  return 0;
}
bool EditorInput::insert(ImGuiInputTextCallbackData *data,
                         const std::string &text) {
  int first = std::min(data->SelectionStart, data->SelectionEnd);
  int count = std::abs(data->SelectionEnd - data->SelectionStart);
  if (text.size() + std::size_t(data->BufTextLen - count) >=
      std::size_t(data->BufSize)) {
    notice_("Editor capacity exceeded: insertion and later actions rejected. "
            "Close and reopen before continuing.");
    std::lock_guard lock(mutex_);
    events_.clear();
    queued_bytes_ = 0;
    blocked_ = true;
    return false;
  }
  if (count)
    data->DeleteChars(first, count);
  data->InsertChars(data->CursorPos, text.data(), text.data() + text.size());
  return true;
}
void EditorInput::apply(ImGuiInputTextCallbackData *data) {
  if (barrier_)
    return;
  bool report_overflow = false;
  {
    std::lock_guard lock(mutex_);
    report_overflow = overflow_notice_;
    overflow_notice_ = false;
    // A native editing shortcut remains queued until the real widget callback
    // confirms delivery. Inactive/reactivating frames cannot consume it.
    if (raw_inflight_ && !events_.empty() &&
        events_.front().sequence == raw_inflight_ &&
        ImGui::IsKeyPressed(events_.front().key, false)) {
      events_.pop_front();
      raw_inflight_ = 0;
    }
  }
  if (report_overflow)
    notice_("Editor input queue overflow: queued actions discarded. Close and "
            "reopen the console before continuing.");
  for (unsigned processed = 0; processed < 1024; ++processed) {
    Event event;
    {
      std::lock_guard lock(mutex_);
      if (blocked_ || events_.empty() || events_.front().kind == Kind::Raw)
        return;
      event = std::move(events_.front());
      events_.pop_front();
      queued_bytes_ -= event.text.size();
    }
    switch (event.kind) {
    case Kind::Text:
      if (!insert(data, event.text))
        return;
      break;
    case Kind::Newline:
      if (!insert(data, "\n"))
        return;
      break;
    case Kind::Paste: {
      if (const char *clipboard = ImGui::GetClipboardText()) {
        std::size_t length = 0;
        while (length < buffer_.size() && clipboard[length])
          ++length;
        if (!insert(data, std::string(clipboard, length)))
          return;
      }
      break;
    }
    case Kind::SelectAll:
      data->SelectionStart = 0;
      data->SelectionEnd = data->BufTextLen;
      data->CursorPos = data->BufTextLen;
      break;
    case Kind::Older:
    case Kind::Newer: {
      auto recalled = history_.navigate(
          event.kind == Kind::Older, std::string(data->Buf, data->BufTextLen));
      if (recalled) {
        data->DeleteChars(0, data->BufTextLen);
        data->InsertChars(0, recalled->c_str());
      }
      break;
    }
    case Kind::Submit: {
      if (!data->BufTextLen)
        break;
      const std::string code(data->Buf, data->BufTextLen);
      const bool accepted = submit_(code);
      history_.submitted(code, accepted);
      if (accepted)
        data->DeleteChars(0, data->BufTextLen);
      else {
        notice_("Submission rejected: draft retained; later queued editor "
                "actions discarded.");
        std::lock_guard lock(mutex_);
        events_.clear();
        queued_bytes_ = 0;
        return;
      }
      break;
    }
    case Kind::Complete: {
      int start = data->CursorPos;
      while (start > 0 &&
             (std::isalnum(static_cast<unsigned char>(data->Buf[start - 1])) ||
              data->Buf[start - 1] == '_' || data->Buf[start - 1] == '.'))
        --start;
      auto matches =
          complete_(std::string(data->Buf + start, data->CursorPos - start));
      if (matches.size() == 1) {
        data->SelectionStart = start;
        data->SelectionEnd = data->CursorPos;
        if (!insert(data, matches[0]))
          return;
      } else
        for (auto &match : matches)
          notice_(match);
      break;
    }
    case Kind::Raw:
      break;
    }
  }
}
} // namespace kp::devtools
