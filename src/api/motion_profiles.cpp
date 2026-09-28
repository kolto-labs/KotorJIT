#include "api/motion.hpp"
// One profile: K1 GOG 1.03 (image SHA256 9c10e045...91435). Every other build
// binds nothing. Offsets mirror data/adjudication/k1_gog_103_motion_bindings.json.
// Every span was read from the reference raw image and matches both the M0
// receipt and its independent verification. tools/kp_motiontest.cpp keeps the
// three in step: it diffs this table against the bindings JSON, re-reads every
// span and slot from the image when present, and cross-checks the existing
// data/addresses/k1_gog_103.json rows.
namespace kp::api::motion {
const std::array<Profile,1>& profiles() {
    static const std::array<Profile,1> p{{
        {"windows-k1-gog","9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435",Abi::Win32,4,
         /*preferred_base*/0x400000,
         /*manager_slot*/0x7a39fc, /*manager_server*/0x8, /*server_internal*/0x4, /*internal_array*/0x1005c,
         /*get_placeable*/0x4ae7a0, /*set_position*/0x4cd1a0, /*placeable_vtable*/0x7494d0, /*placeable_type*/9,
         /*id*/0x4, /*type*/0x8,
         /*area_id*/0x8c, /*position*/0x90, /*orientation*/0x9c,
         /*push_gate*/0x1f8, /*dirty*/0x1fc,
         /*aabb_marker*/0x344, /*quaternion*/0x428,
         {{
           // Server lookup chain and the typed getter.
           {0x4cd1cf,"a1fc397a00"},                        // mov eax,[g_pAppManager]
           {0x4cd1d8,"8b4808"},                            // mov ecx,[eax+8]: app -> server
           {0x4aed70,"8b41048b805c000100c3"},              // [[server+4]+0x1005c]: object array
           {0x4ae7a0,"8b4904e9283100009090909090909090"},  // GetPlaceableByGameObjectID: mov ecx,[ecx+4]; jmp 0x4b18d0
           {0x4b18d5,"8b895c000100"},                      // internal: mov ecx,[ecx+0x1005c]
           {0x4b18fe,"8a4108"},                            // internal: mov al,[ecx+8] (type byte)
           {0x4b1901,"3a0538667400"},                      // internal: cmp al,[0x746638]
           {0x4b190b,"ff5248"},                            // internal: call [edx+0x48] (AsSWSPlaceable)
           // Placeable identity.
           {0x746638,"09"},                                // placeable type constant
           {0x587803,"8a0d38667400"},                      // placeable ctor: mov cl,[0x746638]
           {0x587824,"c706d0947400"},                      // placeable ctor: mov [esi],0x7494d0
           {0x4d7d70,"894804"},                            // CGameObject ctor: mov [eax+4],ecx (id)
           {0x4d7d73,"885008"},                            // CGameObject ctor: mov [eax+8],dl (type)
           // CSWSObject fields.
           {0x4cb139,"8b968c000000"},                      // GetArea: mov edx,[esi+0x8c]
           {0x4cd1e0,"8b968c000000"},                      // SetPosition: mov edx,[esi+0x8c]
           {0x4cd1a0,"538b5c240856578bf18dbe9000000053"},  // SetPosition head, incl. lea edi,[esi+0x90]
           {0x4cd177,"8d819c000000"},                      // SetOrientation: lea eax,[ecx+0x9c]
           {0x4b1098,"8b86f8010000"},                      // AI master: mov eax,[esi+0x1f8] (push gate)
           {0x4cd1c8,"838efc01000002"},                    // SetPosition: or [esi+0x1fc],2
           {0x4cd18b,"8389fc01000004"},                    // SetOrientation: or [ecx+0x1fc],4
           // CSWSPlaceable fields.
           {0x5879b4,"c78644030000ffffffff"},              // ctor: mov [esi+0x344],-1
           {0x58495f,"8b8644030000"},                      // RemoveFromArea: mov eax,[esi+0x344]
           {0x5853cf,"8d8e28040000"},                      // SetOrientation(quat): lea ecx,[esi+0x428]
           // M2: CSWSObject::SetPosition 0x4CD1A0 call shape (thiscall, ret 0x10).
           // The head span above (0x4cd1a0) pins mov ebx,[esp+8] (pos) and
           // mov esi,ecx. Bytes read from the reference raw image.
           {0x4cd1b1,"e8cad7fdff"},                        // call 0x4aa980: exact 3-float equality -> early return
           {0x4cd1bd,"8b44241c5533ed3bc57507"},            // mov eax,[esp+0x1c] (a4); push ebp; xor ebp,ebp; cmp eax,ebp; jne
           {0x4cd202,"8b0b890f8b53048957048b4308894708"},  // copy pos -> [edi] = this+0x90 (3 dwords)
           {0x4cd212,"8b44241885c0"},                      // mov eax,[esp+0x18] (a2); test eax,eax
           {0x4cd238,"5d5f5e5bc21000"},                    // pop ebp/edi/esi/ebx; ret 0x10 (early return enters at 0x4cd239)
         }},
         {{
           {0x749518,0x641db0}, // placeable vtable +0x48 -> mov eax,ecx; ret (AsSWSPlaceable)
           {0x7494e0,0x641db0}, // placeable vtable +0x10 -> same (AsSWSObject)
           {0x749500,0x63e7f0}, // placeable vtable +0x30 -> xor eax,eax; ret (not a creature)
           {0x749548,0x587ba0}, // placeable vtable +0x78 -> CSWSPlaceable::EventHandler (event.placeable)
         }}}
    }};
    return p;
}
const Profile* profile_for(const std::string& sha) {
    for (const auto& p: profiles()) if (sha == p.sha256) return &p;
    return nullptr;
}
const char* failure_name(Failure f) {
    switch (f) {
    case Failure::None: return "none";
    case Failure::Unsupported: return "unsupported";
    case Failure::Guard: return "guard";
    case Failure::Chain: return "chain";
    case Failure::Identity: return "identity";
    case Failure::Value: return "value";
    case Failure::Stale: return "stale";
    case Failure::Collision: return "collision";
    case Failure::Bounds: return "bounds";
    case Failure::Owned: return "owned";
    case Failure::NotOwner: return "not_owner";
    case Failure::Conflict: return "conflict";
    case Failure::Mutation: return "mutation";
    }
    return "unsupported";
}
} // namespace kp::api::motion
