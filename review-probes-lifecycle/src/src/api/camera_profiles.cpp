#include "api/camera.hpp"
// One profile: K1 GOG 1.03 (image SHA256 9c10e045...91435). Every other build
// binds nothing. Offsets mirror data/adjudication/k1_gog_103_camera_bindings.json
// and the regenerated data/addresses/k1_gog_103.json; tools/camera_profile_consistency_test.py
// keeps the three in step and checks every span against the reference image.
// Labels (/*name*/) are parsed by that test; keep one constant per label.
namespace kp::api::camera {
const std::array<Profile,1>& profiles() {
    static const std::array<Profile,1> p{{
        {"windows-k1-gog","9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435",Abi::Win32,4,
         /*preferred_base*/0x400000,
         /*manager_slot*/0x7a39fc, /*manager_client*/0x4, /*client_internal*/0x4,
         /*internal_module*/0x18, /*internal_options*/0x4, /*options_mode*/0x6d,
         /*module_camera*/0x40, /*camera_behavior*/0x18c,
         /*module_vtable*/0x751848, /*camera_vtable*/0x741b20, /*chase_vtable*/0x75165c,
         /*chase_type_id*/0x106a, /*pending_style*/0x7a242c,
         /*dist*/0x110, /*speed*/0x114, /*pitch*/0x11c, /*height*/0x120,
         /*dolly*/0x84, /*base_distance*/0x88, /*base_view_angle*/0x8c, /*style_row*/0x5c,
         /*raw_28*/0x28, /*raw_38*/0x38, /*raw_50*/0x50,
         {{
           // Pointer chain.
           {0x64b991,"a1fc397a00"},        // mov eax,[g_pAppManager]
           {0x64b996,"8b4804"},            // mov ecx,[eax+4]: app -> client
           {0x5ed530,"8b4904e928720500"},  // GetModule: client -> internal, jmp 0x644760
           {0x644760,"8b4118c3"},          // mov eax,[ecx+0x18]: internal -> module
           {0x643f7e,"c70648187500"},      // module ctor stores vtable 0x751848
           {0x64b9b0,"8b7040"},            // mov esi,[eax+0x40]: module -> camera
           {0x45d846,"c706201b7400"},      // camera ctor stores vtable 0x741b20
           {0x45c160,"83c104"},            // camera -> embedded Gob (+4)
           {0x43f5a0,"8b8988010000"},      // Gob+0x188: active behaviour (camera+0x18c)
           {0x5ed700,"8b41048b4004c3"},    // GetClientOptions: [[client+4]+4]
           {0x61b6f6,"88416d"},            // SetCameraMode: mov [ecx+0x6d],al
           // Chase behaviour identity.
           {0x639fee,"c7065c167500"},      // OnAStick ctor stores vtable 0x75165c
           {0x63a310,"b86a100000c3"},      // TypeId: mov eax,0x106a; ret
           // Chase fields.
           {0x637a50,"8d8710010000"},      // m_fDist   lea eax,[edi+0x110]
           {0x637a7b,"8d9714010000"},      // m_fSpeed  lea edx,[edi+0x114]
           {0x637aa6,"8d8f1c010000"},      // m_fPresetPitch lea ecx,[edi+0x11c]
           {0x637ad1,"81c720010000"},      // m_fHeight add edi,0x120
           {0x63bcb8,"8b8684000000"},      // Control: mov eax,[esi+0x84] (dolly)
           {0x63bcc3,"d9868c000000"},      // Control: fld [esi+0x8c]
           {0x63bcd8,"d88e88000000"},      // Control: fmul [esi+0x88]
           {0x63838d,"899688000000"},      // SetCameraStyle: mov [esi+0x88],edx
           {0x638393,"89868c000000"},      // SetCameraStyle: mov [esi+0x8c],eax
           {0x638095,"39465c"},            // SetCameraStyle: cmp [esi+0x5c],eax
           {0x638fb3,"a12c247a00"},        // mov eax,[0x7a242c] (pending style)
           {0x637c2d,"8d4638"},            // ResetLastPosition: lea eax,[esi+0x38]
           {0x637c43,"8d4e50"},            // ResetLastPosition: lea ecx,[esi+0x50]
           {0x637c4e,"8d4e28"},            // ResetLastPosition: lea ecx,[esi+0x28]
           // Property-name literals parsed by OnAStick::Message.
           {0x7437dc,"6d5f664469737400"},             // "m_fDist"
           {0x7437d0,"6d5f66537065656400"},           // "m_fSpeed"
           {0x7514f8,"6d5f66507265736574506974636800"}, // "m_fPresetPitch"
           {0x7437c4,"6d5f6648656967687400"},         // "m_fHeight"
         }},
         {{
           {0x741b80,0x45c160}, // camera vtable +0x60 -> Camera::BehaviorMessage
           {0x751664,0x63bcb0}, // chase vtable +0x8  -> Control
           {0x751668,0x637a30}, // chase vtable +0xc  -> Message
           {0x75166c,0x63a310}, // chase vtable +0x10 -> TypeId (0x106a)
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
    case Failure::Value: return "value";
    }
    return "unsupported";
}
} // namespace kp::api::camera
