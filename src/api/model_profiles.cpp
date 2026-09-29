#include "api/model.hpp"
namespace kp::api::model {
const std::array<Profile,4>& profiles() {
    static const std::array<Profile,4> p{{
        {"macos-k1-i386", "aa6283733d3c738d11d12453f77dfc6b7e87f95326a07ee97daab1a37734b032", Abi::Darwin32,4,
         0x1000,0x481190,4,4,0x14,8,0x1b4,0x1b8,0x58,0xd0,
         {{{0x1eac0,"5589e58b45088b40048945085de94e11"},{0x1e5a0,"5589e58b45088b40048945085de9ba3d"},
           {0x73134,"5589e5565383ec108b5d088b45100fb6"},{0x328524,"5589e5565383ec108b7508f30f104d0c"}}}},
        {"macos-k2-i386", "f14f285b1b6ed7e4bf000fe19ebcd0d6528d1d3e86d2832be6092761557c130d", Abi::Darwin32,4,
         0x1000,0x5edcb8,4,4,0x14,8,0x1e0,0x1e4,0x84,0xd0,
         {{{0x1c0ade,"5589e583ec088b450c8b4d088b490489"},{0x1c0350,"5589e583ec088b450c8b4d088b490489"},
           {0x28693e,"5589e5535683ec108b75088b466885c0"},{0xb0324,"5589e553575683ec0c8b750883be8400"}}}},
        {"macos-k2-x86_64", "469067c416f1a3ff391df73c7ace2d44a8d0a246253e8ad5752f6413ea033be4", Abi::Darwin64,8,
         0x100000000ULL,0x1005d18a0ULL,8,8,0x28,0x10,0x264,0x268,0x98,0x1a0,
         {{{0x1001a37d8ULL,"554889e5488b7f085de9b841feff5548"},{0x1001a33aeULL,"554889e5488b7f085de928affdff5548"},
           {0x10026097eULL,"554889e54156534189f64889fb488bbb"},{0x1000a4a98ULL,"554889e54157415653500f28c84989ff"},
           // [4] server-object lookup: CServerExoApp::GetGameObject(ulong long)
           // @0x1002f9cd8 (own symbol). Reads ->internal (+0x10) ->object array
           // (+0x10098) and resolves the id. Same (this,id)->CGameObject* ABI as
           // the client creature getter. Bytes verified against the K2 x86_64
           // slice; see data/adjudication/mac_x64_bindings.json / mac-model-memory.md.
           {0x1002f9cd8ULL,"554889e54883ec10488b470848c745f8"}}},
         /*manager_server*/0x10,/*server_array*/0x10098},
        {"windows-k1-gog", "9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435", Abi::Win32,4,
         0x400000,0x7a39fc,4,4,0x14,8,0x1b4,0x1b8,0x58,0xcc,
         {{{0x5eda50,"8b4904e9685000009090909090909090"},{0x5ed5b0,"8b4904e9c83b00009090909090909090"},
           {0x6179c0,"568bf18b4e6885c9750633c05ec20800"},{0x444d90,"568bf18b465885c0750632c05ec20800"},
           {0x4ae750,"8b4904e9a82f00009090909090909090"}}},8,0x1005c}
    }};
    return p;
}
const Profile* profile_for(const std::string& sha) {
    for (const auto& p: profiles()) if (sha == p.sha256) return &p;
    return nullptr;
}
const char* abi_name(Abi abi) {
    switch(abi) { case Abi::Win32:return "windows-i386-thiscall";
    case Abi::Darwin32:return "darwin-i386-stack-this"; case Abi::Darwin64:return "darwin-x86_64-sysv"; }
    return "unknown";
}
}
