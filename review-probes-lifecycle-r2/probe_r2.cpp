// Round-2 reviewer probes for Lua lifecycle L1+L2. Scratch only; not part of the repo.
// Reuses the round-1 scaffold (Case, note/bind/unbind/nested_dispatch, show).
#include "/home/brunner56/kp-live-20260922/review-probes-lifecycle-r2/probe_r2_scaffold.inc"

const events::EventContract kSave = ev("OnSave");

const char* rs(const lua::RequestResult* r) {
    if (!r) return "nil";
    return r->status == lua::RequestStatus::Ok ? "OK" : r->status == lua::RequestStatus::Error ? "ERROR" : "PENDING";
}

// N1: the staging_chunk skip must not cost the NEW generation anything once
// it is committed; other scripts keep receiving the nested event; the old
// generation's OnScriptUnload (between chunk and commit) still runs and its
// nested dispatch still reaches the old generation.
void n1_skip_does_not_drop_new_events() {
    std::puts("N1 staged skip vs events the new generation should get");
    Case c("n1");
    c.write("a", "function OnTick() note('old-tick') end\n"
                 "function OnScriptUnload() note('old-unload'); nested_dispatch() end\n");
    c.write("b", "function OnTick() note('b-tick') end\n");
    c.load_all();
    c.write("a", "function OnTick() note('new-tick') end\n"
                 "bind('OnSave', function() note('new-save') end)\n"
                 "nested_dispatch()\n"          // during the chunk: a skipped, b runs
                 "function OnScriptLoad() note('new-load'); nested_dispatch() end\n");
    g_notes.clear();
    std::string err;
    const bool ok = c.host->reload_one("a", err);
    std::printf("  OBSERVE reload ok=%d err=%s\n", ok, err.c_str());
    std::printf("  OBSERVE sequence:");
    for (auto& n : g_notes) std::printf(" %s", n.c_str());
    std::printf("\n");
    // Expected: b-tick (chunk nested), old-unload, old-tick + b-tick (unload's
    // nested dispatch, old still current), new-load, new-tick + b-tick.
    g_notes.clear();
    c.tick();
    const events::Outcome o = c.host->dispatch(kSave, {});
    std::printf("  OBSERVE after commit: new-tick=%u old-tick=%u b-tick=%u new-save=%u save.called=%u\n",
                count("new-tick"), count("old-tick"), count("b-tick"), count("new-save"), o.called);
    show(c, "a", "n1-final");
}

// N2: a reload whose new version throws at top level while events fire
// (nested dispatch before the throw, and a poll-driven reload between ticks).
void n2_toplevel_error_while_events_fire() {
    std::puts("N2 new version throws at top level while events fire");
    Case c("n2");
    c.write("a", "function OnTick() note('old-tick') end\n"
                 "T = kp.registertimer(1, 'Tm')\nfunction Tm() note('old-timer') return true end\n"
                 "function OnScriptUnload() note('old-unload') end\n");
    c.load_all();
    const unsigned created0 = g_created, closed0 = g_closed;
    c.write("a", "bind('OnTick', function() note('staged-tick') end)\n"
                 "function OnTick() note('staged-global-tick') end\n"
                 "nested_dispatch(); nested_dispatch()\n"
                 "error('boom at top level')\n");
    g_notes.clear();
    std::vector<std::string> errs;
    // Poll path, interleaved with ticks, 3 times (file unchanged after first).
    for (int i = 0; i < 3; ++i) { c.poll(&errs); c.tick(); }
    std::printf("  OBSERVE poll errors=%zu first=%.80s\n", errs.size(), errs.empty() ? "-" : errs[0].c_str());
    std::printf("  OBSERVE old-tick=%u staged-tick=%u staged-global-tick=%u old-unload=%u\n",
                count("old-tick"), count("staged-tick"), count("staged-global-tick"), count("old-unload"));
    lua::Script* s = c.host->find("a");
    std::printf("  OBSERVE bound(OnTick)=%d errors=%u\n", s && s->bound("OnTick"), s ? s->error_count() : 99);
    show(c, "a", "n2-after");
    std::printf("  OBSERVE states created=%u closed=%u during N2 (staged state closed once)\n",
                g_created - created0, g_closed - closed0);
    // Fix the file: the next poll must pick it up (stamp was set on failure).
    c.write("a", "function OnTick() note('fixed-tick') end\n");
    g_notes.clear();
    c.poll(&errs); c.tick();
    std::printf("  OBSERVE after fix: fixed-tick=%u old-tick=%u old-unload=%u\n",
                count("fixed-tick"), count("old-tick"), count("old-unload"));
    show(c, "a", "n2-fixed");
}

// N3: delete-then-create races across two polls.
void n3_delete_create_races() {
    std::puts("N3 delete-then-create with two polls");
    {
        Case c("n3a");
        c.write("a", "function OnTick() note('v1') end\nfunction OnScriptUnload() note('unload') end\n");
        c.load_all();
        fs::remove(c.p("a"));
        c.poll();                                      // poll 1: absent once
        show(c, "a", "A poll1-absent");
        c.write("a", "function OnTick() note('v2') end\nfunction OnScriptUnload() note('unload') end\n");
        g_notes.clear();
        c.poll();                                      // poll 2: back, changed
        c.tick();
        show(c, "a", "A poll2-recreated");
        std::printf("  OBSERVE A unload=%u v1=%u v2=%u\n", count("unload"), count("v1"), count("v2"));
        // Counter reset: absent, present, absent must not add up to a drop.
        fs::remove(c.p("a")); c.poll();
        c.write("a", "function OnTick() note('v3') end\n"); c.poll();
        fs::remove(c.p("a")); c.poll();
        show(c, "a", "A absent-present-absent");
    }
    {
        Case c("n3b");
        c.write("a", "function OnTick() note('v1') end\nfunction OnScriptUnload() note('unload') end\n");
        c.load_all();
        fs::remove(c.p("a"));
        c.poll(); c.poll();                            // dropped on poll 2
        show(c, "a", "B dropped");
        std::printf("  OBSERVE B unload=%u\n", count("unload"));
        c.write("a", "function OnTick() note('v2') end\n");
        c.poll(); c.tick();
        show(c, "a", "B recreated");
        std::printf("  OBSERVE B v2=%u\n", count("v2"));
    }
    {
        Case c("n3c");   // delete, poll, recreate EMPTY, poll, fill, poll
        c.write("a", "function OnTick() note('v1') end\n");
        c.load_all();
        fs::remove(c.p("a")); c.poll();
        { std::ofstream(c.p("a"), std::ios::binary); }
        c.poll();
        show(c, "a", "C empty-after-absent");
        c.write("a", "function OnTick() note('v2') end\n");
        g_notes.clear(); c.poll(); c.tick();
        show(c, "a", "C filled");
        std::printf("  OBSERVE C v1=%u v2=%u\n", count("v1"), count("v2"));
    }
    {
        Case c("n3d");   // rename a.lua -> b.lua (script renamed by the user)
        c.write("a", "function OnTick() note('body') end\n");
        c.load_all();
        fs::rename(c.p("a"), c.p("b"));
        c.poll();
        g_notes.clear(); c.tick();
        std::printf("  OBSERVE D after rename poll1: held=%zu one tick ran body %u time(s)\n",
                    c.host->scripts().size(), count("body"));
        c.poll();
        g_notes.clear(); c.tick();
        std::printf("  OBSERVE D after poll2: held=%zu one tick ran body %u time(s)\n",
                    c.host->scripts().size(), count("body"));
    }
    {
        Case c("n3e");   // explicitly unloaded, deleted, recreated
        c.write("a", "function OnTick() note('v1') end\n");
        c.load_all();
        std::string e; c.host->unload_one("a", e);
        fs::remove(c.p("a")); c.poll();
        c.write("a", "function OnTick() note('v2') end\n"); c.poll();
        show(c, "a", "E unloaded+delete+recreate within window");
    }
}

// N4: coalescing against a non-tail entry reorders the caller's asks.
void n4_coalescing_order() {
    std::puts("N4 coalescing vs order of unload/reload");
    struct Seq { const char* tag; std::vector<lua::LifecycleOp> ops; };
    using O = lua::LifecycleOp;
    const std::vector<Seq> seqs = {
        {"reload,unload",          {O::Reload, O::Unload}},
        {"unload,reload,unload",   {O::Unload, O::Reload, O::Unload}},
        {"reload,unload,reload",   {O::Reload, O::Unload, O::Reload}},
        {"unload,load,unload",     {O::Unload, O::Load, O::Unload}},
    };
    for (const auto& q : seqs) {
        Case c("n4");
        c.write("a", "function OnTick() note('tick') end\n");
        c.load_all();
        std::vector<std::uint64_t> ids;
        for (O op : q.ops) ids.push_back(c.host->request(op, "a"));
        std::printf("  OBSERVE %-22s ids:", q.tag);
        for (auto id : ids) std::printf(" %llu", (unsigned long long)id);
        std::printf(" pending=%zu\n", c.host->pending_requests());
        c.host->service_requests();
        lua::Script* s = c.host->find("a");
        std::printf("  OBSERVE %-22s last ask=%s final=%s; result(last id)=%s\n", q.tag,
                    q.ops.back() == O::Unload ? "unload" : q.ops.back() == O::Reload ? "reload" : "load",
                    s ? st(s->state()) : "absent", rs(c.host->result(ids.back())));
    }
}

// N5: self-reload refusal is keyed on raising_self_, which also refuses a
// DIFFERENT script's request made during a nested dispatch inside a's OnScriptLoad.
void n5_raise_mark_scope() {
    std::puts("N5 raising_self_ scope");
    Case c("n5");
    c.write("a", "function OnScriptLoad() nested_dispatch() end\n");
    c.write("b", "function OnTick() if not DONE then DONE=true; RID = kp.scripts.reload('a') end end\n");
    c.load_all();   // a loads first (name order), its OnScriptLoad dispatches OnTick -> b? b not loaded yet
    std::string e;
    c.host->reload_one("a", e);   // now b is loaded; a's OnScriptLoad nested OnTick reaches b
    lua::Script* b = c.host->find("b");
    std::printf("  OBSERVE b's reload('a') from nested tick inside a's OnScriptLoad -> %s\n",
                run_lua(b->L(), "local r = kp.scripts.result(RID); return type(r)=='table' and ((r.ok and 'OK' or 'ERROR: ') .. (r.error or '')) or tostring(r)").c_str());
}
}  // namespace

int main(int argc, char** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    platform::set_log_sink(&sink, nullptr);
    g_root = argc > 1 ? fs::path(argv[1]) : fs::temp_directory_path() / "kp_probe_r2";
    std::error_code ec; fs::remove_all(g_root, ec); fs::create_directories(g_root);
    n1_skip_does_not_drop_new_events();
    n2_toplevel_error_while_events_fire();
    n3_delete_create_races();
    n4_coalescing_order();
    n5_raise_mark_scope();
    std::printf("created=%u closed=%u (must match)\n", g_created, g_closed);
    return 0;
}
