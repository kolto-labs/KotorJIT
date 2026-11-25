#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>

struct lua_State;
namespace kp::api::model {
using Address = std::uint64_t;
enum class Abi { Win32, Darwin32, Darwin64 };
struct Site { Address va; const char* bytes; };
struct Profile {
    const char* name; const char* sha256; Abi abi; unsigned width;
    Address preferred_base, manager_slot;
    unsigned manager_client, client_internal, internal_array, type_offset;
    unsigned effective_offset, base_offset, guard_offset, scale_slot;
    std::array<Site, 5> sites; // Conversion, creature, model, setter, optional server lookup.
    unsigned manager_server = 0, server_array = 0;
    // Universal Mach-O fat container SHA-256 when distinct from sliced `sha256`.
    const char* container_sha256 = nullptr;
};
const std::array<Profile, 4>& profiles();
const Profile* profile_for(const std::string& sha);
const char* abi_name(Abi);
// An eventual Darwin loader supplies exact image identity, slide, fallible reads
// and this OS/width-specific adapter. Call only on the engine's script thread.
struct Backend {
    virtual ~Backend() = default;
    virtual Abi abi() const = 0;
    virtual unsigned width() const = 0;
    virtual bool read(Address, void*, std::size_t) const = 0;
    virtual std::uint32_t convert(Address function, Address client, std::uint32_t id) = 0;
    virtual Address creature(Address function, Address client, std::uint32_t id) = 0;
    virtual Address model(Address function, Address creature) = 0;
    virtual Address server_object(Address function, Address server, std::uint32_t id) = 0;
    virtual bool set_scale(Address function, Address model, float scale) = 0;
    virtual void log(const std::string&) = 0;
};
struct Identity {
    std::uint64_t epoch = 0;
    std::uint32_t id = 0;
    Address owner = 0, object = 0;
};
struct Capture {
    std::uint64_t epoch = 0;
    std::uint32_t id = 0, client_id = 0;
    Address client = 0, creature = 0, model = 0;
    float base = 0, effective = 0;
    Identity ownership;
};
class Operations {
public:
    bool bind(const std::string& verified_sha, Address loaded_base, Backend*,
              const std::array<Address, 5>* generated_sites, std::string& error);
    void unbind();
    bool available() const { return backend_ != nullptr; }
    const Profile* profile() const { return profile_; }
    Address image_base() const { return loaded_base_; }
    bool refresh(const Capture&, Capture&, std::string& error);
    bool identify(std::uint32_t id, Identity&, std::string& error);
    bool matches(const Identity&, std::string& error);
    bool snapshot(std::uint32_t id, Capture&, std::string& error, const Identity* ownership = nullptr);
    bool resize(const Capture&, float scale, Capture& after, std::string& error);
    bool restore(const Capture& captured, Capture& after, std::string& error);
private:
    bool guards(std::string& error) const;
    bool actor(std::uint32_t id, Capture&, std::string& error);
    bool pointer(Address address, Address& value) const;
    Address site(unsigned index) const;
    bool same(const Capture&, const Capture&) const;
    const Profile* profile_ = nullptr;
    std::array<Site, 5> sites_{};
    Backend* backend_ = nullptr;
    Address loaded_base_ = 0;
    std::uint64_t epoch_ = 0;
};
Operations& operations();
// Native adapter uses host OS AND pointer width. Unsupported hosts never call
// engine addresses. A future Darwin loader must supply a fallible reader.
using Reader = bool (*)(Address, void*, std::size_t, void*);
using Logger = void (*)(const std::string&, void*);
Backend* native_backend(Reader, Logger, void* context);
bool bind_native(const std::string& verified_sha, Address loaded_base, Reader, Logger, void*,
                 const std::array<Address, 5>* generated_sites, std::string&);
void register_all(lua_State*);
// Shared native consumers validate the same protected capture allocation.
const Capture& checked_capture(lua_State*, int index);
} // namespace kp::api::model
