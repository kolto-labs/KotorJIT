// Offline proof of the harness control plane: codec, ring, channel.
//
// Nothing here touches the game. The channel is started on a free loopback
// port inside this process, a client thread drives it over a real socket,
// and the main thread plays the part of the client-loop drain with a plain
// callback as the executor.
//
// Exits on its own failure counter, the kp_eventtest way.

#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <string>
#include <thread>
#include <vector>

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

#include "harness/channel.hpp"
#include "harness/chargen.hpp"
#include "harness/fields.hpp"
#include "harness/json.hpp"
#include "harness/ring.hpp"

using namespace kp::harness;

namespace {

int g_failures = 0;

void check(bool ok, const char* what) {
    std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", what);
    if (!ok) ++g_failures;
}

void section(const char* title) {
    std::printf("\n== %s ==\n", title);
}

// ------------------------------------------------------------------ json ----

void json_cases() {
    section("json codec");

    Json v = Json::object();
    v.set("null", Json::null());
    v.set("t", Json::boolean(true));
    v.set("f", Json::boolean(false));
    v.set("int", Json::integer(4471));
    v.set("neg", Json::integer(-12));
    v.set("oid", Json::unsigned_(2147483650u));
    v.set("big", Json::unsigned_(9007199254740991ull));
    v.set("float", Json::number(1.5));
    v.set("str", Json::string("k_pend_door01"));
    v.set("esc", Json::string("quote\" back\\ nl\n tab\t ctl\x01 utf8 \xc3\xa9"));
    Json arr = Json::array();
    arr.push(Json::integer(1));
    arr.push(Json::string("two"));
    arr.push(Json::null());
    Json inner = Json::object();
    inner.set("k", Json::boolean(true));
    arr.push(inner);
    v.set("arr", arr);
    v.set("empty_arr", Json::array());
    v.set("empty_obj", Json::object());

    const std::string once = v.dump();
    Json back;
    std::string error;
    check(Json::parse(once, back, error), "dump parses back");
    if (!error.empty()) std::printf("    %s\n", error.c_str());
    const std::string twice = back.dump();
    check(once == twice, "round trip is stable");

    check(back.get("int") != nullptr && back.get("int")->as_int() == 4471, "integer survives");
    check(back.get("oid") != nullptr && back.get("oid")->as_int() == 2147483650ll,
          "high-bit object id survives as a number");
    check(back.get("big") != nullptr && back.get("big")->as_int() == 9007199254740991ll,
          "2^53-1 survives");
    check(back.get("float") != nullptr && back.get("float")->as_number() == 1.5, "float survives");
    check(back.get("esc") != nullptr && back.get("esc")->as_string() ==
              "quote\" back\\ nl\n tab\t ctl\x01 utf8 \xc3\xa9",
          "escapes and UTF-8 survive");
    check(back.get("arr") != nullptr && back.get("arr")->size() == 4 &&
              back.get("arr")->elements()[3].get("k") != nullptr,
          "nested array and object survive");
    check(once.find("4471.0") == std::string::npos && once.find("\"int\":4471") != std::string::npos,
          "integral doubles print as integers");
    check(back.get("null") != nullptr && back.get("null")->is_null(), "null survives");
    check(back.get("t")->as_bool() && !back.get("f")->as_bool(true), "booleans survive");
    // Insertion order is kept, so the first key is still the first key.
    check(back.members().front().first == "null", "object keeps key order");

    Json parsed;
    check(Json::parse("  {\"id\": 12, \"cmd\": \"state\"}  \n", parsed, error) &&
              parsed.get("cmd")->as_string() == "state",
          "request line with whitespace parses");
    check(Json::parse("\"\\u00e9\\ud83d\\ude00\"", parsed, error) &&
              parsed.as_string() == "\xc3\xa9\xf0\x9f\x98\x80",
          "\\u escapes including a surrogate pair decode to UTF-8");
    check(Json::parse("-1.5e3", parsed, error) && parsed.as_number() == -1500.0, "exponent parses");
    check(Json::parse("[]", parsed, error) && parsed.is_array() && parsed.size() == 0, "empty array");

    const char* bad[] = {
        "{bad", "{\"a\":}", "[1,]", "{\"a\":1,}", "nul", "\"unterminated", "01", "1 2",
        "{\"a\":\"\\x\"}", "\"\\ud83d\"", "",
    };
    bool all_rejected = true;
    for (const char* b : bad) {
        Json out;
        std::string e;
        if (Json::parse(b, out, e)) {
            all_rejected = false;
            std::printf("    accepted: %s\n", b);
        }
    }
    check(all_rejected, "malformed inputs are rejected");

    std::string deep(200, '[');
    deep += std::string(200, ']');
    check(!Json::parse(deep, parsed, error), "nesting bomb is refused");

    check(Json::parse("{\"a\":1}", parsed, error) && parsed.get("missing") == nullptr &&
              parsed.get("a")->as_string().empty() && parsed.get("a")->as_bool(true),
          "typed reads on the wrong type fall back");
}

// ------------------------------------------------------------------ ring ----

void ring_cases() {
    section("event ring");

    EventRing r;
    check(r.last_seq() == 0 && r.oldest_seq() == 0 && r.size() == 0, "fresh ring is empty");

    EventField f[2] = {EventField::str("script", "k_pend_door01"),
                       EventField::unsigned_("object", 2147483650u)};
    const std::uint64_t first = r.push("OnRunScript", 10, f, 2);
    check(first == 1, "first seq is 1");

    std::vector<EventRecord> out;
    check(r.read_since(0, 10, out) == 1 && out[0].seq == 1 && out[0].server_tick == 10 &&
              std::strcmp(out[0].name, "OnRunScript") == 0 && out[0].field_count() == 2 &&
              std::strcmp(out[0].fields[0].text, "k_pend_door01") == 0 &&
              out[0].fields[1].i == 2147483650ll,
          "one record reads back with its fields");

    // Push well past capacity so the ring wraps more than once.
    const std::uint64_t total = EventRing::kCapacity * 2 + 123;
    for (std::uint64_t i = 2; i <= total; ++i) {
        EventField g = EventField::unsigned_("n", i);
        r.push("Tick", i, &g, 1);
    }
    check(r.last_seq() == total, "seq keeps counting past capacity");
    check(r.size() == EventRing::kCapacity, "size caps at capacity");
    check(r.oldest_seq() == total - EventRing::kCapacity + 1, "oldest seq is newest - capacity + 1");

    out.clear();
    const std::size_t n = r.read_since(0, EventRing::kCapacity + 50, out);
    bool ordered = n == EventRing::kCapacity;
    for (std::size_t i = 0; ordered && i < out.size(); ++i) {
        if (out[i].seq != r.oldest_seq() + i) ordered = false;
        if (out[i].fields[0].i != static_cast<std::int64_t>(out[i].seq)) ordered = false;
    }
    check(ordered, "read from before the tail yields the whole ring in order");

    out.clear();
    r.read_since(total - 5, 100, out);
    check(out.size() == 5 && out.front().seq == total - 4 && out.back().seq == total,
          "read_since returns records after the cursor");

    out.clear();
    r.read_since(total - 100, 3, out);
    check(out.size() == 3 && out[0].seq == total - 99, "limit is honoured");

    out.clear();
    check(r.read_since(total, 10, out) == 0, "cursor at newest reads nothing");

    EventField longtext = EventField::str("s", std::string(100, 'x'));
    check(std::strlen(longtext.text) == EventField::kTextCap - 1, "text fields truncate");

    r.clear();
    check(r.size() == 0 && r.last_seq() == total, "clear keeps the sequence counter");
}

// --------------------------------------------------------------- channel ----

// A blocking line client on a POSIX socket with a receive timeout, so a
// missing reply is a failed check rather than a hung test.
struct LineClient {
    int fd = -1;
    std::string buf;

    bool connect_to(unsigned short port) {
        fd = ::socket(AF_INET, SOCK_STREAM, 0);
        if (fd < 0) return false;
        timeval tv{};
        tv.tv_sec = 5;
        ::setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
        sockaddr_in sa{};
        sa.sin_family = AF_INET;
        sa.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        sa.sin_port = htons(port);
        return ::connect(fd, reinterpret_cast<sockaddr*>(&sa), sizeof sa) == 0;
    }
    bool send_line(const std::string& s) {
        const std::string line = s + "\n";
        return ::send(fd, line.data(), line.size(), 0) == static_cast<ssize_t>(line.size());
    }
    bool send_raw(const std::string& s) {
        return ::send(fd, s.data(), s.size(), 0) == static_cast<ssize_t>(s.size());
    }
    // Empty on timeout or EOF.
    std::string read_line() {
        while (true) {
            const std::size_t nl = buf.find('\n');
            if (nl != std::string::npos) {
                std::string line = buf.substr(0, nl);
                buf.erase(0, nl + 1);
                return line;
            }
            char tmp[1024];
            const ssize_t got = ::recv(fd, tmp, sizeof tmp, 0);
            if (got <= 0) return std::string();
            buf.append(tmp, static_cast<std::size_t>(got));
        }
    }
    bool eof() {
        char tmp[16];
        const ssize_t got = ::recv(fd, tmp, sizeof tmp, 0);
        return got == 0;
    }
    void close() {
        if (fd >= 0) ::close(fd);
        fd = -1;
    }
};

// The executor stands in for commands.cpp: parse, answer, and record which
// thread it ran on.
std::thread::id g_drain_thread;
std::atomic<int> g_off_thread{0};
std::atomic<int> g_executed{0};

std::string executor(const std::string& line) {
    if (std::this_thread::get_id() != g_drain_thread) g_off_thread.fetch_add(1);
    g_executed.fetch_add(1);
    Json req;
    std::string error;
    Json reply = Json::object();
    if (!Json::parse(line, req, error) || !req.is_object()) {
        reply.set("id", Json::null());
        reply.set("ok", Json::boolean(false));
        reply.set("error", Json::string(error.empty() ? "not an object" : error));
        return reply.dump();
    }
    const Json* id = req.get("id");
    reply.set("id", id != nullptr ? *id : Json::null());
    reply.set("ok", Json::boolean(true));
    Json result = Json::object();
    const Json* cmd = req.get("cmd");
    result.set("cmd", cmd != nullptr ? *cmd : Json::null());
    reply.set("result", result);
    return reply.dump();
}

// One drain pass, shaped like the real one: take the batch, run, push.
std::size_t pump(Channel& ch, std::size_t max) {
    std::vector<Request> batch;
    ch.take_requests(max, batch);
    std::vector<std::pair<std::uint64_t, std::string>> replies;
    for (const Request& rq : batch) replies.emplace_back(rq.client, executor(rq.line));
    for (auto& r : replies) ch.push_reply(r.first, std::move(r.second));
    return batch.size();
}

struct ClientResults {
    bool connected = false;
    std::string reply1, reply_bad, reply2, reply_crlf;
    bool second_refused = false;
    bool second_eof = false;
    bool after_reconnect_ok = false;
    bool stale_not_delivered = true;
    bool twelve_queued = false;
    std::uint64_t first_gen = 0;
};

void channel_cases() {
    section("channel");

    Channel ch;
    ChannelOptions opts;
    opts.bind = "127.0.0.1";
    opts.port = 0;
    std::string error;
    check(ch.start(opts, error), "channel starts on a free loopback port");
    if (!error.empty()) std::printf("    %s\n", error.c_str());
    check(ch.port() != 0, "port is reported");

    Channel refused;
    ChannelOptions outside;
    outside.bind = "0.0.0.0";
    std::string refuse_error;
    check(!refused.start(outside, refuse_error) && !refuse_error.empty(),
          "a bind outside loopback is refused");

    g_drain_thread = std::this_thread::get_id();
    std::atomic<bool> done{false};
    std::atomic<bool> phase_reconnect{false};
    std::atomic<bool> hold_pump{false};
    ClientResults res;

    std::thread client([&] {
        LineClient c;
        res.connected = c.connect_to(ch.port());
        if (!res.connected) { done = true; return; }

        c.send_line("{\"id\":1,\"cmd\":\"ping\"}");
        res.reply1 = c.read_line();
        c.send_line("{bad json");
        res.reply_bad = c.read_line();
        c.send_line("{\"id\":2,\"cmd\":\"state\"}");
        res.reply2 = c.read_line();
        c.send_raw("{\"id\":3,\"cmd\":\"status\"}\r\n");
        res.reply_crlf = c.read_line();

        // A second connection while the first is up: one error line, then EOF.
        LineClient second;
        if (second.connect_to(ch.port())) {
            const std::string line = second.read_line();
            res.second_refused = line.find("busy") != std::string::npos;
            res.second_eof = second.eof();
            second.close();
        }

        // Twelve at once: the drain takes eight, then four. The pump is held
        // until all twelve are queued so the split does not depend on how
        // the bytes happened to arrive.
        hold_pump = true;
        for (int i = 10; i < 22; ++i)
            c.send_line("{\"id\":" + std::to_string(i) + ",\"cmd\":\"ping\"}");
        for (int spins = 0; spins < 5000 && ch.pending_requests() < 12; ++spins)
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        res.twelve_queued = ch.pending_requests() == 12;
        hold_pump = false;
        for (int i = 10; i < 22; ++i) c.read_line();

        res.first_gen = ch.current_client();
        c.close();

        // Reconnect: served again, and a reply for the old generation must not
        // leak into this connection.
        phase_reconnect = true;
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
        LineClient again;
        if (again.connect_to(ch.port())) {
            again.send_line("{\"id\":99,\"cmd\":\"ping\"}");
            const std::string line = again.read_line();
            res.after_reconnect_ok = line.find("\"id\":99") != std::string::npos;
            // Nothing else should arrive: a short wait then no bytes.
            timeval tv{};
            tv.tv_usec = 200000;
            ::setsockopt(again.fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
            const std::string extra = again.read_line();
            res.stale_not_delivered = extra.empty();
            again.close();
        }
        done = true;
    });

    bool saw_eight = false;
    bool saw_four = false;
    bool pushed_stale = false;
    while (!done.load()) {
        if (hold_pump.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
            continue;
        }
        const std::size_t n = pump(ch, 8);
        if (n == 8) saw_eight = true;
        if (n == 4) saw_four = true;
        if (phase_reconnect.load() && !pushed_stale && res.first_gen != 0) {
            ch.push_reply(res.first_gen, "{\"id\":\"stale\"}");
            pushed_stale = true;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    client.join();

    check(res.connected, "client connected");
    check(res.reply1.find("\"id\":1") != std::string::npos && res.reply1.find("\"ok\":true") != std::string::npos,
          "first request answered");
    check(res.reply_bad.find("\"ok\":false") != std::string::npos, "malformed line gets an error reply");
    check(res.reply2.find("\"id\":2") != std::string::npos, "connection survives the malformed line");
    check(res.reply_crlf.find("\"id\":3") != std::string::npos, "CRLF framing accepted");
    check(res.second_refused, "second client is refused with an error line");
    check(res.second_eof, "second client is closed after the refusal");
    check(res.twelve_queued, "twelve lines queued while the drain was held");
    check(saw_eight && saw_four, "take_requests caps a batch at max and keeps the rest");
    check(res.after_reconnect_ok, "a new client after disconnect is served");
    check(res.stale_not_delivered, "a reply for a gone client is dropped, not delivered to the next");
    check(g_executed.load() >= 16, "every request reached the executor");
    check(g_off_thread.load() == 0, "requests executed on the draining thread only");
    check(ch.accepted_count() == 2, "two connections accepted in total");

    ch.stop();
    check(!ch.running(), "channel stops");
}

// A client that sends and never reads used to grow the request queue without
// limit; the ceiling drops the connection instead. Nothing drains here, which
// is the case that used to be unbounded.
void channel_limit_cases() {
    section("channel limits");

    Channel ch;
    ChannelOptions opts;
    opts.bind = "127.0.0.1";
    opts.port = 0;
    std::string error;
    if (!ch.start(opts, error)) {
        check(false, "limit channel starts");
        return;
    }

    LineClient c;
    if (!c.connect_to(ch.port())) {
        check(false, "limit client connected");
        ch.stop();
        return;
    }
    for (int spins = 0; spins < 5000 && !ch.client_connected(); ++spins)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));

    // Well past the queue ceiling, in chunks, with a send timeout so a peer
    // that has already been dropped cannot hold this thread. MSG_NOSIGNAL for
    // the same reason the listener uses it: the drop lands mid-flood.
    std::string flood;
    for (int i = 0; i < 6000; ++i)
        flood += "{\"id\":" + std::to_string(i) + ",\"cmd\":\"ping\"}\n";
    timeval snd{};
    snd.tv_sec = 1;
    ::setsockopt(c.fd, SOL_SOCKET, SO_SNDTIMEO, &snd, sizeof snd);
    std::size_t at = 0;
    while (at < flood.size()) {
        const std::size_t chunk = flood.size() - at < 4096 ? flood.size() - at : 4096;
        const ssize_t sent = ::send(c.fd, flood.data() + at, chunk, MSG_NOSIGNAL);
        if (sent <= 0) break;
        at += static_cast<std::size_t>(sent);
    }

    bool dropped = false;
    for (int spins = 0; spins < 5000 && !dropped; ++spins) {
        if (!ch.client_connected()) dropped = true;
        else std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    check(dropped, "a client that floods the request queue is dropped, not queued without limit");
    check(ch.pending_requests() == 0, "the queue goes with the connection");

    c.close();
    ch.stop();
    check(!ch.running(), "limit channel stops");
}

// ------------------------------------------------- phase and save unpack ---
//
// The two pure predicates the load path leans on, exercised without a game.
// The phase tuple is the one a live K1 boot reports at the main menu: no
// server, the main-menu panel present, area_not_ready set, and a load_error
// word read out of a stats block no server has written yet.

void predicate_cases() {
    section("phase classifier");

    PhaseDetail menu;
    menu.server_mode = -1;
    menu.loading_module = -1;
    menu.area_not_ready = 1;
    menu.input_class = 2;
    menu.main_menu = 1;
    menu.game_over = 0;
    menu.pause = -1;
    menu.movie = 0;
    menu.load_error = 1348221507;
    menu.move_pending = -1;
    check(classify_phase(menu, false, -1, -1, -1) == Phase::Menu,
          "main menu with a garbage load_error is menu, not error");

    PhaseDetail no_panel = menu;
    no_panel.main_menu = 0;
    check(classify_phase(no_panel, false, -1, -1, -1) == Phase::Menu,
          "no server is menu even without the panel");

    PhaseDetail failed;
    failed.server_mode = 2;
    failed.loading_module = 0;
    failed.area_not_ready = 0;
    failed.main_menu = 0;
    failed.load_error = 3;
    check(classify_phase(failed, true, 0, -1, -1) == Phase::Error,
          "load_error with a server is still error");

    PhaseDetail loading;
    loading.server_mode = 1;
    loading.loading_module = 1;
    loading.main_menu = 0;
    loading.load_error = 0;
    check(classify_phase(loading, true, 1, -1, -1) == Phase::Loading, "loading a module is loading");

    // Live tuple from run 20260909-055643, a save loaded far enough that the
    // server runs the module while the main-menu panel is still listed. The
    // client has not finished the area, so this is Loading, and reading the
    // stale panel as the menu is what it must not do.
    PhaseDetail after_load;
    after_load.server_mode = 2;
    after_load.loading_module = 0;
    after_load.area_not_ready = 1;
    after_load.input_class = 0;
    after_load.main_menu = 1;
    after_load.game_over = 0;
    after_load.pause = 0;
    after_load.movie = 0;
    after_load.load_error = 0;
    after_load.move_pending = 0;
    check(classify_phase(after_load, true, 0, -1, -1) == Phase::Loading,
          "a loaded module with the menu panel still listed is loading, not menu");

    PhaseDetail in_menu_with_server = after_load;
    in_menu_with_server.server_mode = 0;
    in_menu_with_server.area_not_ready = 0;
    check(classify_phase(in_menu_with_server, true, 0, -1, -1) == Phase::Menu,
          "the panel with no module running is menu");

    PhaseDetail play;
    play.server_mode = 2;
    play.loading_module = 0;
    play.area_not_ready = 0;
    play.input_class = 0;
    play.main_menu = 0;
    play.game_over = 0;
    play.pause = 0;
    play.movie = 0;
    play.load_error = 0;
    check(classify_phase(play, true, 0, 1, 0) == Phase::Gameplay, "in game is gameplay");

    play.main_menu = 1;
    check(classify_phase(play, true, 0, 1, 0) == Phase::Menu,
          "running module beneath listed main menu is not visible gameplay");
    play.movie = 1;
    check(classify_phase(play, true, 0, 1, 0) == Phase::Movie,
          "movie retains priority over listed main menu");
    play.movie = 0;
    play.area_not_ready = 1;
    check(classify_phase(play, true, 0, 1, 0) == Phase::Loading,
          "loading retains priority over listed main menu");

    section("stuck-load predicate");

    // The tuple measured live on 2026-09-09 with the headless load stuck:
    // server_mode 2, area_not_ready 1, no control object, module loaded.
    check(area_loaded_due(2, 1, kInvalidObjectId, true),
          "a loaded module with no control object is the stuck load");
    check(!area_loaded_due(2, 0, kInvalidObjectId, true),
          "an area already on screen is not stuck");
    check(!area_loaded_due(1, 1, kInvalidObjectId, true),
          "server_mode 1 is still loading: RunModule has not been through");
    check(!area_loaded_due(2, 1, 0x00000005, true),
          "a client that already has its creature needs nothing sent");
    check(!area_loaded_due(2, 1, kInvalidObjectId, false),
          "no module means the load has not got that far");
    check(!area_loaded_due(-1, 1, kInvalidObjectId, true) &&
              !area_loaded_due(2, -1, kInvalidObjectId, true) &&
              !area_loaded_due(2, 1, -1, true),
          "a field this build cannot read refuses rather than guesses");

    section("normal load completion guards");
    check(main_menu_pointer_absent(std::uintptr_t(0)), "native cleared menu is already absent");
    check(!main_menu_pointer_absent(std::nullopt), "unreadable menu is not proven absent");
    check(!main_menu_pointer_absent(std::uintptr_t(0x1234)), "nonnull menu needs native panel check");
    check(normal_load_completed(true, true, 2, true, 0, 0),
          "issued load can complete normally without injected AreaLoaded");
    check(!normal_load_completed(false, true, 2, true, 0, 0),
          "old running module without observed request flag cannot complete");
    check(!normal_load_completed(true, false, 2, true, 0, 0),
          "replaced server cannot complete an old request");
    check(!normal_load_completed(true, true, 2, false, 0, 0),
          "normal completion requires actual module");
    for (int state : {-1, 1, 3}) {
        check(!normal_load_completed(true, true, 2, true, state, 0),
              "unknown or pending client area refuses completion");
        check(!normal_load_completed(true, true, 2, true, 0, state),
              "unknown or pending server save flag refuses completion");
    }
    for (int mode : {-1, 0, 1, 3})
        check(!normal_load_completed(true, true, mode, true, 0, 0),
              "only running server mode completes normal load");

    section("save ERF members");

    // A two-member MOD ERF built by hand: one .sav and one .res, laid out the
    // way the engine writes them.
    std::vector<std::uint8_t> erf(0x100, 0);
    std::memcpy(erf.data(), "MOD V1.0", 8);
    auto put32 = [](std::vector<std::uint8_t>& b, std::size_t at, std::uint32_t v) {
        std::memcpy(b.data() + at, &v, 4);
    };
    auto put16 = [](std::vector<std::uint8_t>& b, std::size_t at, std::uint16_t v) {
        std::memcpy(b.data() + at, &v, 2);
    };
    put32(erf, 16, 2);        // entry count
    put32(erf, 24, 0x40);     // key list
    put32(erf, 28, 0x80);     // resource list
    std::memcpy(erf.data() + 0x40, "end_m01aa", 9);
    put16(erf, 0x40 + 20, 0x809);
    std::memcpy(erf.data() + 0x58, "INVENTORY", 9);
    put16(erf, 0x58 + 20, 0x000);
    put32(erf, 0x80, 0xf0); put32(erf, 0x84, 4);
    put32(erf, 0x88, 0xf4); put32(erf, 0x8c, 4);
    std::memcpy(erf.data() + 0xf0, "SAVE", 4);
    std::memcpy(erf.data() + 0xf4, "INVN", 4);

    std::vector<SaveErfMember> members;
    std::string err;
    const bool parsed = save_erf_members(erf, &members, &err);
    check(parsed && members.size() == 2, "two members parsed");
    check(parsed && members[0].name == "end_m01aa.sav" && members[0].offset == 0xf0 &&
              members[0].size == 4,
          "sav member named and located");
    check(parsed && members[1].name == "INVENTORY.res", "restype 0 is written as .res");

    std::vector<std::uint8_t> unknown = erf;
    put16(unknown, 0x40 + 20, 0x7d0);
    check(!save_erf_members(unknown, &members, &err) &&
              err.find("unmapped restype") != std::string::npos,
          "an unmapped restype is refused, not guessed");

    std::vector<std::uint8_t> past = erf;
    put32(past, 0x84, 0xffff);
    check(!save_erf_members(past, &members, &err) && err.find("past the file") != std::string::npos,
          "a member running past the file is refused");

    std::vector<std::uint8_t> not_erf(64, 0);
    check(!save_erf_members(not_erf, &members, &err), "non-ERF bytes are refused");

    // Offsets and sizes are u32 read out of the file, and std::size_t is 32
    // bits on the -m32 build the DLL ships as: offset + size wraps there, so a
    // member at 0xffffff00 of size 0x200 summed to 0x100, passed, and then read
    // from bytes.data() + 0xffffff00. Every span is checked by subtraction now.
    // These three run on the 64-bit test build too, where the old sums did not
    // wrap and the refusal came from the size compare instead; they are here so
    // the -m32 build has the same cases covered by the same source.
    std::vector<std::uint8_t> wrap_member = erf;
    put32(wrap_member, 0x80, 0xffffff00u);
    put32(wrap_member, 0x84, 0x200);
    check(!save_erf_members(wrap_member, &members, &err) &&
              err.find("past the file") != std::string::npos,
          "an ERF member whose offset plus size wraps is refused");

    std::vector<std::uint8_t> wrap_keys = erf;
    put32(wrap_keys, 24, 0xfffffff0u);
    check(!save_erf_members(wrap_keys, &members, &err) &&
              err.find("truncated") != std::string::npos,
          "an ERF key list offset that wraps is refused");

    std::vector<std::uint8_t> wrap_res = erf;
    put32(wrap_res, 28, 0xfffffff8u);
    check(!save_erf_members(wrap_res, &members, &err),
          "an ERF resource list offset that wraps is refused");
}

// ------------------------------------------------- checked arithmetic -------
//
// The save parser and the adapter both add an offset out of a file or out of
// engine memory to a base. On the 32-bit build those sums wrap, and a wrapped
// sum is a small address that probes readable. These cases pin the refusals.

void bounds_cases() {
    section("checked arithmetic");

    // A GFF whose top-level struct carries one CExoString field, LASTMODULE.
    auto put32 = [](std::vector<std::uint8_t>& b, std::size_t at, std::uint32_t v) {
        std::memcpy(b.data() + at, &v, 4);
    };
    std::vector<std::uint8_t> gff(0x200, 0);
    std::memcpy(gff.data(), "RES V3.2", 8);
    put32(gff, 8, 0x38);    put32(gff, 12, 1);    // struct list
    put32(gff, 16, 0x50);   put32(gff, 20, 1);    // field list
    put32(gff, 24, 0x70);   put32(gff, 28, 1);    // label list
    put32(gff, 32, 0x100);  put32(gff, 36, 0x20); // field data
    put32(gff, 40, 0x180);  put32(gff, 44, 0);    // field indices
    put32(gff, 0x38, 0xffffffffu);                // struct type
    put32(gff, 0x3c, 0);                          // one field: index 0
    put32(gff, 0x40, 1);                          // field count
    put32(gff, 0x50, 10);                         // field type: CExoString
    put32(gff, 0x54, 0);                          // label index
    put32(gff, 0x58, 0);                          // data offset within the block
    std::memcpy(gff.data() + 0x70, "LastModule", 10);
    put32(gff, 0x100, 9);
    std::memcpy(gff.data() + 0x104, "end_m01aa", 9);

    check(savenfo_last_module(gff) == "end_m01aa", "LASTMODULE is read from a well-formed savenfo");

    // data_off + f_data was 32-bit arithmetic on every build, not just -m32:
    // 0xfffffff0 + 0x20 wrapped to 0x10 and the parser returned 80 bytes of
    // whatever lived there as the module name. This case fails without the fix
    // on the native test build.
    std::vector<std::uint8_t> wrap_data = gff;
    put32(wrap_data, 32, 0xfffffff0u);
    put32(wrap_data, 0x58, 0x20);
    check(savenfo_last_module(wrap_data).empty(),
          "a savenfo whose data offset wraps reads as no module, not as bytes at a low address");

    // The next three wrap only where std::size_t is 32 bits; on this build the
    // old code refused them by size compare. Same source, both widths.
    std::vector<std::uint8_t> wrap_label = gff;
    put32(wrap_label, 24, 0xfffffff0u);  // label_off + index * 16 wraps
    check(savenfo_last_module(wrap_label).empty(), "a savenfo whose label offset wraps is refused");

    std::vector<std::uint8_t> wrap_field = gff;
    put32(wrap_field, 16, 0xfffffff8u);  // field_off + index * 12 wraps
    check(savenfo_last_module(wrap_field).empty(), "a savenfo whose field offset wraps is refused");

    std::vector<std::uint8_t> huge_string = gff;
    put32(huge_string, 0x100, 0xfffffff0u);
    check(savenfo_last_module(huge_string).empty(), "a CExoString longer than the file is refused");

    // The adapter's own base-plus-offset.
    const std::uintptr_t top = ~std::uintptr_t(0);
    check(at_offset(0x1000, 0x24).value_or(0) == 0x1024, "a plain field offset resolves");
    check(!at_offset(0, 0x24).has_value(), "a null base has no address");
    check(!at_offset(0x1000, -1).has_value(), "an unresolved offset (-1) has no address");
    check(!at_offset(top - 4, 0x24).has_value(), "a base plus offset that would wrap is refused");
    check(at_index(0x1000, 3, 0x10).value_or(0) == 0x1030, "an indexed read resolves");
    check(!at_index(0x1000, -1, 0x10).has_value(), "a negative index is refused");
    check(!at_index(0x1000, 0, 0).has_value(), "a zero stride is refused");
    check(!at_index(0x1000, 0x40000000, 0x40).has_value(),
          "an index times stride that would wrap is refused");

    // A number outside the int64 range is a value a client can send; converting
    // it is undefined behaviour, so as_int answers with its fallback instead.
    Json big;
    std::string error;
    check(Json::parse("1e20", big, error) && big.as_int(-7) == -7,
          "a JSON number past int64 falls back rather than converting");
    check(Json::parse("-1e30", big, error) && big.as_int(-7) == -7,
          "a large negative JSON number falls back too");
    check(Json::parse("2147483647", big, error) && big.as_int() == 2147483647,
          "a number inside the range still converts");
}

void chargen_pair_cases() {
    section("chargen panel pair");

    const std::uintptr_t main = 0x1000;
    const std::uintptr_t child = 0x2000;
    const auto classify = [](std::initializer_list<std::uintptr_t> added,
                             std::initializer_list<std::uintptr_t> routes) {
        return classify_chargen_panel_pair(added, routes);
    };
    const auto forward = classify({main, child}, {child, 0});
    check(forward && forward.main == main && forward.child == child,
          "main then child is identified by the route link");
    const auto reverse = classify({child, main}, {0, child});
    check(reverse && reverse.main == main && reverse.child == child,
          "child then main is identified by the route link");
    check(!classify({main}, {child}), "one added panel is rejected");
    check(!classify({main, child, 0x3000}, {child, 0, 0}),
          "more than two added panels is rejected");
    check(!classify({main, 0}, {0, main}), "null panel is rejected");
    check(!classify({main, main}, {main, main}), "equal panels are rejected");
    check(!classify({main, child}, {0x3000, 0x4000}),
          "unlinked pair is rejected");
    check(!classify({main, child}, {child}), "incomplete route evidence is rejected");
}

}  // namespace

int main() {
    json_cases();
    ring_cases();
    channel_cases();
    channel_limit_cases();
    predicate_cases();
    bounds_cases();
    chargen_pair_cases();

    std::printf("\n%d failure(s)\n", g_failures);
    return g_failures == 0 ? 0 : 1;
}
