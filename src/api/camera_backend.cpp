#include "api/camera.hpp"
#include <limits>
namespace kp::api::camera {
// Win32 i386 only: the one profile is the K1 GOG PE. Other hosts get no
// adapter, so bind fails closed. The adapter reads memory; it calls nothing.
#if defined(_WIN32) && defined(__i386__)
namespace {
class Native final : public Backend {
public:
    model::Reader reader = nullptr; void* context = nullptr;
    Abi abi() const override { return Abi::Win32; }
    unsigned width() const override { return sizeof(void*); }
    bool read(Address address, void* out, std::size_t size) const override {
        if (!reader || address > std::numeric_limits<std::uintptr_t>::max() ||
            size > std::numeric_limits<std::uintptr_t>::max() - address) return false;
        return reader(address, out, size, context);
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
    if (!read) { error = "unsupported: camera binding requires a fallible reader"; return false; }
    Backend* native = native_backend(read, context);
    if (!native) { error = "unsupported: no native camera adapter for host OS/architecture"; return false; }
    return operations().bind(sha, base, native, error);
}
}
