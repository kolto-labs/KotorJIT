#include "api/motion.hpp"
#include <limits>
// Native adapter: Windows i386 only (the one profile is K1 GOG). Every other
// host gets no adapter, so no engine address is ever called there.
namespace kp::api::motion {
#if defined(_WIN32) && defined(__i386__)
namespace {
class Native final : public Backend {
public:
    model::Reader reader = nullptr; void* context = nullptr;
    Abi abi() const override { return Abi::Win32; }
    unsigned width() const override { return 4; }
    bool read(Address address, void* out, std::size_t size) const override {
        if (!reader || address > std::numeric_limits<std::uintptr_t>::max() ||
            size > std::numeric_limits<std::uintptr_t>::max() - address) return false;
        return reader(address, out, size, context);
    }
    // CServerExoApp::GetPlaceableByGameObjectID: thiscall(this, uint32), ret 4.
    Address placeable(Address f, Address server, std::uint32_t id) override {
        using Call = void*(__attribute__((thiscall)) *)(void*, std::uint32_t);
        void* result = reinterpret_cast<Call>(static_cast<std::uintptr_t>(f))(
            reinterpret_cast<void*>(static_cast<std::uintptr_t>(server)), id);
        return reinterpret_cast<std::uintptr_t>(result);
    }
    // CSWSObject::SetPosition: thiscall(this, const Vector*, a2, a3, a4), ret 0x10.
    // M0 verification: a4 at [esp+0x1c] after 3 pushes, a2 at [esp+0x18]
    // after 4, a3 never read. The engine copies the 3 floats; the local
    // vector only has to outlive the call.
    void set_position(Address f, Address object, const std::array<float, 3>& pos,
                      std::int32_t a2, std::int32_t a3, std::int32_t a4) override {
        using Call = void(__attribute__((thiscall)) *)(void*, const float*, std::int32_t, std::int32_t, std::int32_t);
        float vector[3] = {pos[0], pos[1], pos[2]};
        reinterpret_cast<Call>(static_cast<std::uintptr_t>(f))(
            reinterpret_cast<void*>(static_cast<std::uintptr_t>(object)), vector, a2, a3, a4);
    }
};
}
#endif
Backend* native_backend(model::Reader read, void* context) {
#if defined(_WIN32) && defined(__i386__)
    static Native native; native.reader = read; native.context = context; return &native;
#else
    (void)read; (void)context; return nullptr;
#endif
}
bool bind_native(const std::string& sha, Address base, model::Reader read, void* context, std::string& error) {
    operations().unbind();
    if (!read) { error = "unsupported: motion binding requires a fallible reader"; return false; }
    Backend* native = native_backend(read, context);
    if (!native) { error = "unsupported: no native motion adapter for host OS/architecture"; return false; }
    return operations().bind(sha, base, native, error);
}
} // namespace kp::api::motion
