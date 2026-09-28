# Mach-O metadata parser foundation

SOURCE FROZEN. Four source paths: src/image/macho.hpp, src/image/macho.cpp, tools/kp_machotest.cpp, CMakeLists.txt. No index changes or games.

SDK-independent thin little-endian 32/64 parser takes complete on-disk bytes and returns raw CPU type/subtype, container bitness, file type/flags, preferred unslid segment VAs, file spans/protections and sections including zero-fill classification. uint64_t retains 64-bit addresses on 32-bit hosts. Output is unchanged on refusal. Bounds cover command count/size/alignment, segment file/VM extents, section tables, VM/file containment and relocation spans. Big-endian and fat images refuse explicitly. Unknown bounded commands are skipped; success is metadata parsing, not native loader admission. No ASLR, dyld binding, loader, ABI calls or runtime Mac support claim.

Format reference: https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/EXTERNAL_HEADERS/mach-o/loader.h (structure layout reference only; implementation uses explicit byte reads, not copied Apple structs).

Validation: standalone g++ C++20 -m32 -Wall -Wextra -Werror synthetic run PASS1095 checks. CMake configure/build kp_machotest and CTest -R ^kp_machotest$ PASS1/1. CMake-built host tool plus supplied private K1/K2 raw images PASS1099 checks: both cpu0x7, bits32, five segments. /tmp/kp-macho-real.log records paths and results. Initial pre-reconfigure build correctly lacked the new target; subsequent configure/build passed. ASan+UBSan linking attempted but unavailable due to missing /usr/lib64/libasan.so.8.0.0; no sanitizer result claimed. Scoped gitdiffcheck passed.

Synthetic-only fixtures are generated in code, no retail bytes copied. Cases cover thin32/64, >4GiB addresses, every fixture truncation, invalid count/size/alignment, mismatched segment and CPU widths, overflowing extents, virtual/file section containment, zero-fill, relocation bounds, unsupported magics, unchanged output on failure and unknown-command skip.

Next boundary: independent review, then explicit integration with Darwin image loading and exact runtime identity/ABI gates. Existing Format/detect_format remain PE/ELF only intentionally.
