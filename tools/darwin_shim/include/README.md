# Darwin API shim (syntax checks only)

Declarations of the handful of Apple SDK interfaces the macOS runtime uses,
copied in shape from the macOS SDK headers. They exist so the Darwin
translation units can be type-checked on a Linux CI host with
`-DKP_DARWIN_SHIM -Itools/darwin_shim/include`. They are never used for a
shipping build: `scripts/mac/build.sh` compiles against the real SDK with
Xcode's clang.
