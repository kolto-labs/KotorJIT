// The K2 adapter: the same body as K1, parameterised by the TSL layout.
//
// What the corpus settles for K2 (GOG Aspyr swkotor2.exe, binary 22, with the
// mac decompile as cross-check) is recorded here; what it does not settle is
// left at -1 so the method that needs it reports unsupported by name instead
// of reading a K1 offset into a K2 object. Which engine functions resolve is a
// per-build data question: k2_gog_aspyr is symbol-sourced, and the adapter
// binds only what its verified table carries while listing the rest through
// missing_sites().
//
// Native ELF: every method call is stack-`this` cdecl there (amendment 6);
// GameAdapter picks that from the table's platform, so nothing in this file
// is platform-specific.
#include "harness/fields.hpp"

namespace kp::harness {

const Layout& k2_layout() {
    static const Layout l = [] {
        Layout k;
        // CAppManager and the two app objects match K1: K2 mac main.cpp reads
        // the server at +8, and the ELF client-loop wrapper reads internal at +4
        // (fill-client-loop: mov eax,[eax+4] at 0x819f56c).
        k.mgr_client = 4;
        k.mgr_server = 8;
        k.mgr_stats  = 0x14;
        k.app_internal = 4;

        // CSWGuiDialog: HandleSelectReply jumps through vtable +0x70 on K2 gog
        // (swguidialog.cpp:161-305), one slot past K1.
        k.panel_select_reply_slot = 0x70 / 4;
        // GameObjectMethods slot order is not read for K2; assumed as K1.
        k.gameobject_as_sws_slot = 4;

        // CGuiInGame (K2 gog guiingame.cpp UpdateDialog 0x4dd7f0): dialog panel
        // +0x3c, selection idx +0xe0, count +0xe4, pending +0xe8, isReply +0xec.
        k.gui_dialog_panel = 0x3c;
        k.gui_selection_pending = 0xe8;
        k.container_take_all = -1;
        k.container_mode = -1;

        // CSWGuiDialog: entry index +0x68, visible count +0x70, link map
        // +0x26e4, owner +0x275c (fill-reply-choice, K2 gog).
        k.panel_entry = 0x68;
        k.panel_visible_count = 0x70;

        // CSWSDialog (K2 gog HandleReply 0x757420): entries +0x8 stride 0x10c,
        // link_entry_count +0x104, link_entries +0x108 stride 0x68, link index
        // +0x10, replies +0x10 stride 0x110, current entry +0x74, chosen +0x78.
        // The node header's strref offset was not read for K2.
        k.dialog_entry_stride = 0x10c;
        k.dialog_link_count = 0x104;
        k.dialog_links = 0x108;
        k.dialog_link_index = 0x10;
        k.dialog_link_stride = 0x68;
        k.dialog_text_strref = -1;

        // CSWGlobalVariableTable: hash modulus 0x93d (TSL mac
        // globalvartables.cpp FindIdentifierIndex), so the typed arrays after
        // the identifiers sit at K2-specific offsets the table must carry
        // (gvt.bools / gvt.numbers / gvt.strings). Counts not located.
        k.gvt_slot_count = 0x93d;
        k.gvt_identifier_stride = 0x18;
        k.gvt_name_len = 0x16;
        k.gvt_bool_count = -1;
        k.gvt_number_count = -1;
        k.gvt_string_count = -1;

        // SJournalEntry stride 0x38 with the tag at +0x18 (TSL mac
        // nwsjournal.cpp GetState); the state offset is unconfirmed. The
        // CSWSJournal header {data, size, capacity} is shared code.
        k.journal_data = 0;
        k.journal_size = 4;
        k.journal_entry_stride = 0x38;
        k.journal_tag = 0x18;
        k.journal_state = -1;

        // CWorldTimer is shared libsource, but timer.paused was never read for
        // K2 and the K2 bindings do not resolve it. Left unknown: fixed_step
        // needs each timer's prior pause state to bracket without unpausing a
        // timer the engine had paused, and a K1 offset read into a K2 object is
        // a guess. set_fixed_step reports unsupported by name until a K2
        // timer.paused row exists.
        k.timer_paused = -1;

        // CExoMoviePlayer internals not read for K2; the adapter prefers the
        // client.is_movie_playing call (K2 gog CClientExoApp::IsMoviePlaying
        // 0x0040D620) and only falls back to this chain when that is absent.
        k.movie_internal = -1;
        k.movie_playing = -1;
        return k;
    }();
    return l;
}

std::unique_ptr<EngineAdapter> make_k2_adapter(const hooks::AddressTable& table, std::uintptr_t image_base) {
    return std::make_unique<GameAdapter>("k2", k2_layout(), table, image_base);
}

}  // namespace kp::harness
