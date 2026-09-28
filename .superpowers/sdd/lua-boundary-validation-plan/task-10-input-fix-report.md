# Task 10 input reliability fix, round 2

## Defect and correction

The supplied read-only diagnostic `/tmp/kp-console-history-race.md` identified two independent ways rapid physical input could disappear before reaching Console: reconstructing history from current-frame Ctrl instead of keydown-time modifiers, and InputTextMultiline processing an arrow before a simultaneous Enter in its else-if branch. Multiline Enter also deactivated the editor despite the single-line-only EnterKeepActive setting.

Added `src/devtools/editor_input.hpp/.cpp`, a platform-independent editor adapter shared by the Windows overlay and a headless pinned-ImGui test. Keyboard meaning is captured at receipt with its modifiers and placed into one bounded, sequenced queue. Text, SelectAll, history, completion, newline, paste and Submit run against the actual widget callback buffer in that order. Submit only calls the existing Console enqueue API; Lua remains exclusively in the engine pump. Submission does not forward Enter into the widget, so multiline editing remains active.

Normal navigation/edit shortcuts retain native ImGui behavior, with keydown/release frame barriers so later text or Submit cannot overtake them. Raw actions remain queued until the real active widget callback confirms their delivery; focus/reactivation cannot discard them. No vendor source changes, typing sleeps, repeated driver injection or disabling of ImGui event trickling were used.

## Safety and scope

Editor event count is bounded to 1024 and queued text to 64 KiB. Overflow and edit-capacity rejection are visible and block further editor actions until explicit close/reopen, preventing later Enter from executing an unintended partial command. Rejected Console submissions retain the draft and discard following queued editor actions. Close/focus-loss clears pending actions; accepted engine requests remain owned by Console. Submit/history/paste/completion autorepeat is ignored; ordinary editing/navigation repeat is preserved. Existing F12/Escape, engine-thread command execution, DirectInput suppression and closed-render fast path remain in place.

The helper uses the pinned ImGui core and its active-widget identity accessor, with no modifications to upstream files. Native navigation may consume more than one widget frame because the release barrier is deliberate event serialization, not a driver timing workaround. Clipboard contents are read at ordered paste execution. Existing platform/runtime limitations remain; this does not add another platform, interpreter, browser transport or restart lifecycle.

## Tests and build

Added native32 `kp_editorinputtest` using the actual vendored ImGui core and the same adapter as the overlay. It covers all frame partitions of SelectAll/history/Enter, prior-frame Ctrl followed by captured Up and released Ctrl, 20 rapid recall cycles including deactivation/reactivation, multiline draft history restoration, Ctrl+Enter, mixed text before/after submissions, completion with following text, clipboard paste ordering, native navigation and Shift selection, raw navigation reactivation, rejected submissions, close/focus clearing, Enter repeat suppression, event overflow and edit/paste capacity rejection/recovery.

`kp_consoletest` and `kp_editorinputtest` passed together (0.06 seconds total in the final run). Native32 shipping `kphasor` and MinGW `kphasor_dll` built. Build receipt `/tmp/kp-inputround2-build4.log`; configure receipt `/tmp/kp-inputround2-configure.log`. Source diff whitespace check passed.

Frozen DLL `/home/brunner56/kp-validation-20260922-build/kphasor-inputround2.dll`.

SHA256 `713aa3ac0b967a61089cf5f3a947fe102c8dd74aceccde6940d067630a0cca61`.

This is a review/live-test candidate, not a live acceptance claim. Controller owns the unchanged 20-recall physical stress, full UI, held-key/draft and gameplay isolation reruns. No game was launched by this implementation agent. Independent review has been requested before completion/commit.

## Independent review and live acceptance

Independent review passed specification and quality checks with no P0–P2 findings (`/tmp/kp-inputround2-review.md`). The supplementary Unicode limitation below is nonblocking. Controller verified the identical frozen SHA256 above in three source-unchanged live runs: unchanged 20-recall physical stress, run 133724, 26/26 steps; full console smoke, run 133825, 39/39 steps; held-key, history draft and gameplay restoration, run 133930, 28/28 steps. No artificial input delays were added to the recall stress. These controller-owned results complete this fix's live acceptance.

Supplementary Unicode characters delivered as UTF-16 surrogate pairs through Win32 WM_CHAR are not yet combined by the adapter. Such characters may be entered incorrectly; supplementary-plane text input remains outside this fix's validated coverage.
