#include "devtools/editor_input.hpp"
#include "imgui.h"
#include "imgui_internal.h"
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <vector>
using kp::devtools::EditorInput;
void check(bool ok, const char *message) {
  if (!ok) {
    std::fprintf(stderr, "FAIL: %s\n", message);
    std::exit(1);
  }
}
std::string clipboard;
struct Harness {
  std::vector<std::string> submitted, notices;
  bool accept = true;
  EditorInput editor;
  Harness()
      : editor(
            [&](auto &s) {
              if (accept)
                submitted.push_back(s);
              return accept;
            },
            [](auto &prefix) {
              return prefix == "math.sqr"
                         ? std::vector<std::string>{"math.sqrt"}
                         : std::vector<std::string>{};
            },
            [&](auto &s) { notices.push_back(s); }) {
    ImGui::CreateContext();
    auto &io = ImGui::GetIO();
    io.IniFilename = nullptr;
    io.DisplaySize = {800, 600};
    io.DeltaTime = 1.f / 60;
    unsigned char *p;
    int w, h;
    io.Fonts->GetTexDataAsRGBA32(&p, &w, &h);
    ImGui::GetPlatformIO().Platform_GetClipboardTextFn = [](ImGuiContext *) {
      return clipboard.c_str();
    };
    ImGui::GetPlatformIO().Platform_SetClipboardTextFn =
        [](ImGuiContext *, const char *s) { clipboard = s; };
    frames(3);
  }
  ~Harness() { ImGui::DestroyContext(); }
  void frame() {
    editor.prepare();
    ImGui::NewFrame();
    ImGui::SetNextWindowPos({0, 0});
    ImGui::SetNextWindowSize({800, 600});
    ImGui::Begin("test");
    editor.draw("##editor", {700, 400});
    ImGui::End();
    ImGui::Render();
  }
  void frames(int n = 8) {
    for (int i = 0; i < n; ++i)
      frame();
  }
  void key(ImGuiKey k, bool ctrl = false, bool shift = false,
           bool repeat = false) {
    editor.key(k, ctrl, shift, false, repeat);
  }
  void seed() {
    editor.text("77+1");
    key(ImGuiKey_Enter);
    frames();
    check(submitted.size() == 1 && submitted.back() == "77+1", "seed accepted");
  }
};
int main() {
  // Every partition of SelectAll / HistoryOlder / Submit, including one frame.
  for (unsigned mask = 0; mask < 8; ++mask) {
    Harness h;
    h.seed();
    h.key(ImGuiKey_A, true);
    if (mask & 1)
      h.frame();
    h.key(ImGuiKey_UpArrow, true);
    if (mask & 2)
      h.frame();
    h.key(ImGuiKey_Enter);
    if (mask & 4)
      h.frame();
    h.frames();
    check(h.submitted.size() == 2 && h.submitted.back() == "77+1",
          "partitioned history and Enter ordered exactly once");
  }
  {
    Harness h;
    h.seed();
    ImGui::GetIO().AddKeyEvent(ImGuiMod_Ctrl, true);
    h.frame();
    h.key(ImGuiKey_UpArrow, true);
    ImGui::GetIO().AddKeyEvent(ImGuiMod_Ctrl, false);
    h.key(ImGuiKey_Enter);
    h.frames();
    check(h.submitted.size() == 2, "event-time ctrl survives later release");
    for (int i = 0; i < 20; ++i) {
      if (i % 3 == 0) {
        ImGui::ClearActiveID();
        h.frame();
      }
      h.key(ImGuiKey_A, true);
      h.key(ImGuiKey_UpArrow, true);
      h.key(ImGuiKey_Enter);
      h.frames(3);
      check(h.submitted.size() == std::size_t(i + 3) &&
                h.submitted.back() == "77+1",
            "20 rapid recalls through reactivation");
    }
  }
  {
    Harness h;
    h.seed();
    h.editor.text("local function draft()");
    h.key(ImGuiKey_Enter, true);
    h.editor.text("return 42\nend");
    h.frames();
    auto draft = h.editor.draft();
    check(draft == "local function draft()\nreturn 42\nend" &&
              h.submitted.size() == 1,
          "CtrlEnter newline without submit");
    h.key(ImGuiKey_UpArrow, true);
    h.key(ImGuiKey_DownArrow, true);
    h.frames();
    check(h.editor.draft() == draft, "multiline draft restored");
    h.accept = false;
    h.key(ImGuiKey_Enter);
    h.editor.text("must not attach to rejected draft");
    h.key(ImGuiKey_Enter);
    h.frames();
    check(h.editor.draft() == draft && h.submitted.size() == 1 &&
              !h.notices.empty(),
          "rejection preserves draft and drops later execution");
  }
  {
    Harness h;
    h.editor.text("first");
    h.key(ImGuiKey_Enter);
    h.editor.text("second");
    h.key(ImGuiKey_Enter);
    h.editor.text("third");
    h.frames();
    check(h.submitted == std::vector<std::string>{"first", "second"} &&
              h.editor.draft() == "third",
          "text after Submit belongs to following command");
    h.key(ImGuiKey_A, true);
    h.editor.text("math.sqr");
    h.key(ImGuiKey_Tab);
    h.editor.text("(81)");
    h.key(ImGuiKey_Enter);
    h.frames();
    check(h.submitted.back() == "math.sqrt(81)",
          "completion barrier with following text");
    clipboard = "pasted";
    h.key(ImGuiKey_V, true);
    h.key(ImGuiKey_Enter);
    h.editor.text("after paste");
    h.frames();
    check(h.submitted.back() == "pasted" && h.editor.draft() == "after paste",
          "ordered clipboard paste before Submit keeps widget ordering");
    h.key(ImGuiKey_A, true);
    h.editor.text("ab");
    h.key(ImGuiKey_LeftArrow);
    h.editor.text("X");
    h.key(ImGuiKey_Enter);
    h.frames();
    check(h.submitted.back() == "aXb",
          "real widget navigation before text and Submit");
    h.editor.text("left right");
    h.frames();
    ImGui::ClearActiveID();
    h.key(ImGuiKey_Home);
    h.editor.text("prefix ");
    h.key(ImGuiKey_Enter);
    h.frames(12);
    check(h.submitted.back() == "prefix left right",
          "navigation survives editor reactivation");
    h.editor.text("ab");
    h.key(ImGuiKey_LeftArrow, false, true);
    h.editor.text("X");
    h.key(ImGuiKey_Enter);
    h.frames(12);
    check(h.submitted.back() == "aX",
          "selection snapshots preserve Shift at keydown");
  }
  {
    Harness h;
    h.editor.text("pending must not execute");
    h.key(ImGuiKey_Enter);
    h.editor.close();
    ImGui::GetIO().ClearEventsQueue();
    ImGui::GetIO().ClearInputKeys();
    h.frames();
    check(h.submitted.empty(), "close or focus loss discards pending actions");
    h.editor.text("fresh");
    h.key(ImGuiKey_Enter);
    h.key(ImGuiKey_Enter, false, false, true);
    h.frames();
    check(h.submitted == std::vector<std::string>{"fresh"},
          "submit autorepeat suppressed");
    for (int i = 0; i < 1025; ++i)
      h.editor.text("x");
    h.key(ImGuiKey_Enter);
    h.frames();
    check(h.submitted.size() == 1 && !h.notices.empty(),
          "overflow blocks unintended partial execution");
    h.editor.close();
    h.key(ImGuiKey_A, true);
    h.editor.text("recovered");
    h.key(ImGuiKey_Enter);
    h.frames();
    check(h.submitted.back() == "recovered",
          "reopen recovers blocked input queue");
    h.editor.text(std::string(16384, 'x'));
    h.editor.text("overflow");
    h.frames();
    h.key(ImGuiKey_Enter);
    h.frames();
    check(h.submitted.back() == "recovered",
          "edit capacity failure cannot execute truncated draft later");
    h.editor.close();
    h.key(ImGuiKey_A, true);
    h.editor.text("capacity recovered");
    h.key(ImGuiKey_Enter);
    h.frames();
    check(h.submitted.back() == "capacity recovered",
          "capacity block cleared only by explicit reopen");
    clipboard = std::string(20000, 'x');
    h.key(ImGuiKey_V, true);
    h.key(ImGuiKey_Enter);
    h.frames();
    check(h.submitted.back() == "capacity recovered",
          "oversized paste cannot execute a partial command");
  }
  std::puts(
      "editor input: actual pinned ImGui frame partitions, history, "
      "reactivation, text/paste barriers, rejection and close/overflow passed");
}
