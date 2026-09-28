# Durable K2 net-layer binding independent review

PASS — no actionable findings in the two-file binding change.

Both frozen SHA256 values matched: adjudication input692f8e6627066db2701542c43453f8874641b299b7e42be3d9469caf7a276796; generated address table4e21a72a9754ae2b1a7babfe2d7fbf0d0b0c5a165efd0b92588a997923b38187.

The new CClientExoAppInternal::net_layer field specifies addr0,offset0x10,size4,owner CClientExoAppInternal. Evidence matches the exact SHA-bound original K2 GOG accessor previously independently disassembled: GetNetLayer0x40ccb0 loads app+4 then internal+0x10, returns pointerEAX. Corpus binary22 identifies that accessor. Neighbor GetSWCMessage corroborates owner chain and+0x150. The narrow acceptance-rule exception honestly states that no recovered types.h declaration was checked; it does not pretend otherwise or broaden other bindings. The site remains optional globally, with load_save enforcing its own operational requirement. No C++ hardcoded offset fallback was introduced.

Diff inspection confirms only the added field/evidence and matching counters/unresolved removal: input fields55→56 and accepted53→54 (independently recounted); generated adjudicated60→61,resolved183→184,by_adjudication60→61,by_field59→60; only client.net_layer removed from unresolved. Other sites and executable identity unchanged.

Read-only invocation of existing generator load_overlay and resolve for this field produced addr0,offset16,size4,owner/confidence exactly matching generated JSON. Overlay count61 matches adjudicated_bindings61. No database, regeneration or full recovery job required for this field-only consistency check.

The anticipated k2-net-layer-binding-report.md was absent and a bounded matching filename check found no alternative. This review does not depend on that missing report: source/evidence/generator consistency are independently checked. Parent reports copied-save and7physical-console checks on the experimental one-field table; this reviewer did not run or validate those live checks. Final exact-table replay remains controller-owned. Field resolution is not general K2 parity.

No source/index edits, builds or games. Only this requested review report written.
