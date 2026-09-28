# Initial projectile byte observations

Read-only objdump of local K1 GOG executable, SHA256 9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435. Raw disassembly retained privately in this directory, not product artifacts.

LoadModel 0x6d2c50 saves ECX as receiver; reads receiver+0x68, allocates a 0xf0 wrapper when null; invokes wrapper vtable+0xc with first and second stack arguments, checks EAX, invokes wrapper vtable+8, and binds resulting object via vtable+0x74 to receiver. Returns EAX1 on success, ret0xc on all inspected exits. This supports thiscall with three stack slots and model ownership at0x68; it does NOT establish precise flag meanings, resource lifetime or callback-safe substitution.

Projectile receiver 0x6501b0 calls constructor0x6d57b0. At0x650699 writes receiver+0x1a1=2; calls0x6d2c30 with a decoded stack field, then0x6d4250(1). It later invokes SetProjectileType0x6d6ee0. Model-load dispatch appears virtual and needs constructor/vtable confirmation. Do not install a hook from these partial observations. Still resolve shooter identity, both hand/shot identifiers, misses, resource format and actual first-render timing.
