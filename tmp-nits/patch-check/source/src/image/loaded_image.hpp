// An address space we can read, whether or not the game is running.
//
// Everything downstream -- header parsing, classification, hashing, dumping --
// reads through this one interface. That is what lets the same code that runs
// inside the game be exercised offline against a file in a buffer, which is the
// only way to develop against an encrypted target we cannot launch here.
//
// Reads are fallible by design. Inside a live process, a virtual address may be
// unmapped, uncommitted, or in the middle of being rewritten by the DRM stub. A
// failed read means "not ready", never a fault -- see LiveImage.
#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace kp::image {

class LoadedImage {
  public:
    virtual ~LoadedImage() = default;

    virtual std::uintptr_t base() const = 0;
    virtual bool read(std::uintptr_t va, void* out, std::size_t len) const = 0;

    // Convenience over read(). Returns false and leaves `out` empty if any part
    // of the range is unreadable; a partially filled buffer would be worse than
    // none, since the caller would hash or scan whatever happened to survive.
    bool read_vector(std::uintptr_t va, std::size_t len, std::vector<std::uint8_t>& out) const;
};

// A buffer standing in for an address space.
//
// Two constructions, because the two things a file can mean are different:
//   linear  -- va = base + file offset. The whole file is addressable, including
//              parts a loader would never map (ELF section headers live past the
//              last PT_LOAD).
//   mapped  -- the layout a loader would produce: headers plus sections at their
//              virtual addresses, gaps zeroed. This is what the runtime sees.
class BufferImage : public LoadedImage {
  public:
    BufferImage(std::vector<std::uint8_t> bytes, std::uintptr_t base)
        : bytes_(std::move(bytes)), base_(base) {}

    std::uintptr_t base() const override { return base_; }
    bool read(std::uintptr_t va, void* out, std::size_t len) const override;

    const std::vector<std::uint8_t>& bytes() const { return bytes_; }

  private:
    std::vector<std::uint8_t> bytes_;
    std::uintptr_t            base_;
};

// Reads the calling process's own memory without ever faulting. On Windows that
// is ReadProcessMemory against our own handle; on Linux, process_vm_readv. Both
// report an unmapped page as an error return instead of a signal, which is the
// property we need -- the alternative is SEH, which MinGW's C++ front end does
// not offer.
class LiveImage : public LoadedImage {
  public:
    explicit LiveImage(std::uintptr_t base) : base_(base) {}

    std::uintptr_t base() const override { return base_; }
    bool read(std::uintptr_t va, void* out, std::size_t len) const override;

  private:
    std::uintptr_t base_;
};

std::vector<std::uint8_t> read_file(const std::string& path);

// Lay a PE or ELF file out the way a loader would. Returns nullptr when the file
// is not a recognised 32-bit image.
std::unique_ptr<BufferImage> map_file_image(const std::vector<std::uint8_t>& file);

// The whole ELF file addressed linearly, so structures a loader never maps --
// section headers, the section name table -- are still readable. Returns nullptr
// unless every PT_LOAD shares one vaddr-minus-offset delta, because only then
// does `base + file offset` name the same byte the real VA does.
std::unique_ptr<BufferImage> make_linear_elf_image(const std::vector<std::uint8_t>& file);

}  // namespace kp::image
