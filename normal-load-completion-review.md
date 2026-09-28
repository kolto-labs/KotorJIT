# Independent normal-load completion review

Verdict: PASS for the bounded source correction. No actionable blocking findings.

Reviewed the three-file diff and surrounding load/step code, exact frozen hashes, implementation report, and host test receipt (0 failures). No build or game run performed by reviewer.

Hashes verified:
- engine_k1.cpp: 6d3c79de3eb38bacd2e7b6826d65589e1e6aa5456157f53b32aa3b8c34d28821
- fields.hpp: 37cf59e1a1482fb272157c6983b3ec6129be89ea9ed7c525fa04981a25f4d760
- kp_harnesstest.cpp: 20fb675528368cab9116725f65bba52b7cf32480fafbb7be0644391b94996cd2

The new Armed branch closes the previously demonstrated naturally-completed-load gap. Request observation is reset before setters; from-save=1 is read before dispatch and the server identity is captured. Completion requires that observation, the same nonzero server, running mode, a native module, and both known completion flags. It therefore rejects an unarmed old ready module and unreadable/pending values. A noncallable request leaves Idle. The branch returns after one retirement attempt.

Menu cleanup retains the verified native method and checks membership afterward. Known null succeeds, unreadable pointer refuses, a listed panel requires removal, and neither failed verification nor failed removal is reported Done. Placed retains the old forced-recovery sequence but now respects absence verification. The conservative phase classifier avoids labeling a listed menu as gameplay while preserving Error/Loading/Movie priority.

Tests meaningfully cover the predicate inputs, unknown versus null menu pointer, menu-visible phase, and prior stuck-load predicates. They do not execute native dispatch or prove GUI rendering; the report states that limitation correctly. Clean DLL build and serialized K1 regression plus K2 visible-world/F12 acceptance remain required. In particular, verify main_menu=0 and actual world pixels rather than VM/PC readiness alone.

Residual scope boundary: server pointer identity is not a general native load epoch and cannot prove immunity to same-address reuse or unrelated cancellation/reload initiated outside this request. This bounded fix does not claim that stronger lifecycle contract. Existing Sent/Placed recovery behavior is preserved, including its pre-existing field assumptions. No new native binding, raw GUI flag write, or unverified ABI was introduced.
