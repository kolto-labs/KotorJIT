#include "loaded_image.hpp"

#include <cstdio>
#include <cstring>

#include "pe_elf.hpp"

#if defined(_WIN32)
#include <windows.h>
#else
#include <sys/uio.h>
#include <unistd.h>
#endif

namespace kp::image {
namespace {

// A malformed or hostile header can claim a four-gigabyte image. We refuse
// rather than let a bad SizeOfImage decide how much memory to allocate.
constexpr std::size_t kMaxImageBytes = 512u * 1024u * 1024u;

}  // namespace

bool LoadedImage::read_vector(std::uintptr_t va, std::size_t len, std::vector<std::uint8_t>& out) const {
    out.clear();
    if (len == 0) return true;
    if (len > kMaxImageBytes) return false;
    out.resize(len);
    if (!read(va, out.data(), len)) {
        out.clear();
        return false;
    }
    return true;
}

bool BufferImage::read(std::uintptr_t va, void* out, std::size_t len) const {
    if (len == 0) return true;
    if (va < base_) return false;
    const std::uintptr_t off = va - base_;
    if (off > bytes_.size() || len > bytes_.size() - off) return false;
    std::memcpy(out, bytes_.data() + off, len);
    return true;
}

bool LiveImage::read(std::uintptr_t va, void* out, std::size_t len) const {
    if (len == 0) return true;
#if defined(_WIN32)
    // VirtualQuery first so an uncommitted or no-access region is rejected
    // before we touch it; ReadProcessMemory then reports any residual fault as
    // a return value instead of an exception.
    MEMORY_BASIC_INFORMATION mbi;
    if (VirtualQuery(reinterpret_cast<LPCVOID>(va), &mbi, sizeof mbi) == 0) return false;
    if (mbi.State != MEM_COMMIT) return false;
    if ((mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)) != 0) return false;

    SIZE_T got = 0;
    if (ReadProcessMemory(GetCurrentProcess(), reinterpret_cast<LPCVOID>(va), out, len, &got) == 0)
        return false;
    return got == len;
#else
    iovec local{out, len};
    iovec remote{reinterpret_cast<void*>(va), len};
    const ssize_t got = process_vm_readv(getpid(), &local, 1, &remote, 1, 0);
    return got >= 0 && static_cast<std::size_t>(got) == len;
#endif
}

std::vector<std::uint8_t> read_file(const std::string& path) {
    std::vector<std::uint8_t> out;
    std::FILE* f = std::fopen(path.c_str(), "rb");
    if (f == nullptr) return out;

    std::vector<std::uint8_t> chunk(1u << 20);
    for (;;) {
        const std::size_t n = std::fread(chunk.data(), 1, chunk.size(), f);
        if (n != 0) out.insert(out.end(), chunk.begin(), chunk.begin() + n);
        if (n != chunk.size()) break;
    }
    if (std::ferror(f) != 0) out.clear();
    std::fclose(f);
    return out;
}

namespace {

std::unique_ptr<BufferImage> map_pe(const std::vector<std::uint8_t>& file) {
    pe::Headers h;
    if (!pe::read_headers(file.data(), file.size(), h)) return nullptr;
    if (h.size_of_image == 0 || h.size_of_image > kMaxImageBytes) return nullptr;

    std::vector<std::uint8_t> mem(h.size_of_image, 0);
    const std::size_t hdr = h.size_of_headers < file.size() ? h.size_of_headers : file.size();
    std::memcpy(mem.data(), file.data(), hdr < mem.size() ? hdr : mem.size());

    for (const pe::SectionHeader& s : h.sections) {
        if (s.virtual_address >= mem.size()) continue;
        std::size_t n = s.size_of_raw_data;
        if (s.pointer_to_raw_data >= file.size()) continue;
        if (n > file.size() - s.pointer_to_raw_data) n = file.size() - s.pointer_to_raw_data;
        if (n > mem.size() - s.virtual_address) n = mem.size() - s.virtual_address;
        std::memcpy(mem.data() + s.virtual_address, file.data() + s.pointer_to_raw_data, n);
    }
    return std::make_unique<BufferImage>(std::move(mem), h.image_base);
}

std::unique_ptr<BufferImage> map_elf(const std::vector<std::uint8_t>& file) {
    elf::Headers h;
    if (!elf::read_headers(file.data(), file.size(), h)) return nullptr;
    if (h.loads.empty()) return nullptr;

    std::uintptr_t lo = h.loads.front().vaddr;
    std::uintptr_t hi = 0;
    for (const elf::Segment& p : h.loads) {
        if (p.vaddr < lo) lo = p.vaddr;
        const std::uintptr_t end = p.vaddr + p.memsz;
        if (end > hi) hi = end;
    }
    if (hi <= lo || hi - lo > kMaxImageBytes) return nullptr;

    std::vector<std::uint8_t> mem(hi - lo, 0);
    for (const elf::Segment& p : h.loads) {
        std::size_t n = p.filesz;
        if (p.offset >= file.size()) continue;
        if (n > file.size() - p.offset) n = file.size() - p.offset;
        const std::size_t at = p.vaddr - lo;
        if (at >= mem.size()) continue;
        if (n > mem.size() - at) n = mem.size() - at;
        std::memcpy(mem.data() + at, file.data() + p.offset, n);
    }
    return std::make_unique<BufferImage>(std::move(mem), lo);
}

}  // namespace

std::unique_ptr<BufferImage> make_linear_elf_image(const std::vector<std::uint8_t>& file) {
    elf::Headers h;
    if (!elf::read_headers(file.data(), file.size(), h)) return nullptr;

    const std::uintptr_t delta = h.loads.front().vaddr - h.loads.front().offset;
    for (const elf::Segment& p : h.loads) {
        if (p.vaddr - p.offset != delta) return nullptr;
    }
    if (file.size() > kMaxImageBytes) return nullptr;
    return std::make_unique<BufferImage>(file, delta);
}

std::unique_ptr<BufferImage> map_file_image(const std::vector<std::uint8_t>& file) {
    if (pe::looks_like(file.data(), file.size())) return map_pe(file);
    if (elf::looks_like(file.data(), file.size())) return map_elf(file);
    return nullptr;
}

}  // namespace kp::image
