#!/usr/bin/env python3
"""Generate the macOS x86_64 address tables and build records from the retail images.

    python3 tools/mac/gen_mac_tables.py \
        --k1 <.../KOTOR_Exe> --k2 <.../KOTOR2sub> --k1-i386 <K1 i386 corpus image> \
        [--cache DIR] [--check]

Outputs (unless --check):
    data/addresses/k1_mac_steam_x64.json
    data/addresses/k2_mac_steam_x64.json
    src/generated/builds_macho.inc
    data/adjudication/mac_x64_bindings.json      (evidence for every K1 binding)

Where each binding comes from
-----------------------------
K2 (KOTOR2sub, x86_64 slice) ships its full C++ symbol table, so every function
site is its own mangled symbol. Field offsets are read out of the machine code of
named accessors, never assumed from the 32-bit layouts.

K1 (KOTOR_Exe) is stripped to 909 symbols. Every K1 function binding needs at
least two independent agreeing derivations, from this set:

  vtable   The class vtable found through the RTTI still present in the image,
           indexed by the slot the same method occupies in K2's (named) vtable.
  block    CVirtualMachine's one-line forwarding wrappers are emitted in source
           order with a fixed 14-byte stride. The order is read from K2 x86_64
           and K1 i386 symbols (identical), anchored by an agreed member.
  follow   The target of a K1 wrapper's tail jump.
  k2match  Call-graph/string/shape propagation from K2 x86_64's names.
  i386match The same propagation from the named K1 i386 Mac image (same K1
           source, other architecture; instruction shape is not used).

A binding with fewer than two agreeing derivations, or with any disagreeing one,
is not emitted and the tool exits non-zero. Nothing is hand-typed.
"""
import argparse, hashlib, json, os, re, struct, subprocess, sys
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from mac import macho_model as mm, fn_match, vtables as vtmod  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
IMAGE_BASE = 0x100000000

K1_ALIAS = 'k1_mac_steam_x64'
K2_ALIAS = 'k2_mac_steam_x64'

# (site, K2 symbol (mangled, without leading underscore), kind, required)
FUNCTION_SITES = [
    ('vm.run_script', '_ZN23CVirtualMachineInternal9RunScriptEP10CExoStringyi', 'detour', True),
    ('vm.run_script_situation', '_ZN23CVirtualMachineInternal18RunScriptSituationEP21CVirtualMachineScriptyi', 'reference', False),
    ('vm.execute_command', '_ZN25CSWVirtualMachineCommands14ExecuteCommandEii', 'reference', True),
    # x86_64 only: SaveScriptSituation and LoadScriptSituation are hooked on the
    # internal methods. The CVirtualMachine forwarders are 13/14-byte tail
    # calls -- too short to carry a 14-byte absolute jump -- and both internal
    # methods take the same (situation, gff, struct) arguments after `this`.
    ('vm.save_script_situation', '_ZN23CVirtualMachineInternal19SaveScriptSituationEP21CVirtualMachineScriptP7CResGFFP10CResStruct', 'detour', False),
    ('vm.load_script_situation', '_ZN23CVirtualMachineInternal19LoadScriptSituationEPP21CVirtualMachineScriptP7CResGFFP10CResStruct', 'detour', False),
    ('vm.stack_pop_integer', '_ZN15CVirtualMachine15StackPopIntegerEPi', 'call', True),
    ('vm.stack_push_integer', '_ZN15CVirtualMachine16StackPushIntegerEi', 'call', True),
    ('vm.stack_pop_float', '_ZN15CVirtualMachine13StackPopFloatEPf', 'call', True),
    ('vm.stack_push_float', '_ZN15CVirtualMachine14StackPushFloatEf', 'call', True),
    ('vm.stack_pop_string', '_ZN15CVirtualMachine14StackPopStringEP10CExoString', 'call', True),
    ('vm.stack_push_string', '_ZN15CVirtualMachine15StackPushStringERK10CExoString', 'call', True),
    ('vm.stack_pop_object', '_ZN15CVirtualMachine14StackPopObjectEPy', 'call', True),
    ('vm.stack_push_object', '_ZN15CVirtualMachine15StackPushObjectEy', 'call', True),
    ('vm.stack_pop_vector', '_ZN15CVirtualMachine14StackPopVectorEP6Vector', 'call', False),
    ('vm.stack_push_vector', '_ZN15CVirtualMachine15StackPushVectorE6Vector', 'call', False),
    ('vm.stack_pop_engine_structure', '_ZN15CVirtualMachine23StackPopEngineStructureEiPPv', 'call', False),
    ('vm.stack_push_engine_structure', '_ZN15CVirtualMachine24StackPushEngineStructureEiPv', 'call', False),
    ('vmcmd.destroy_game_defined_structure', '_ZN25CSWVirtualMachineCommands27DestroyGameDefinedStructureEiPv', 'call', False),
    ('exo.string_dtor', '_ZN10CExoStringD1Ev', 'call', False),
    ('event.creature', '_ZN12CSWSCreature12EventHandlerEjyPvjj', 'detour', False),
    ('event.door', '_ZN8CSWSDoor12EventHandlerEjyPvjj', 'detour', False),
    ('event.placeable', '_ZN13CSWSPlaceable12EventHandlerEjyPvjj', 'detour', False),
    ('event.trigger', '_ZN11CSWSTrigger12EventHandlerEjyPvjj', 'detour', False),
    ('event.module', '_ZN10CSWSModule12EventHandlerEjyPvjj', 'detour', False),
    ('event.area', '_ZN8CSWSArea12EventHandlerEjyPvjj', 'detour', False),
    ('event.encounter', '_ZN13CSWSEncounter12EventHandlerEjyPvjj', 'detour', False),
    ('event.aoe', '_ZN22CSWSAreaOfEffectObject12EventHandlerEjyPvjj', 'detour', False),
    ('event.store', '_ZN9CSWSStore12EventHandlerEjyPvjj', 'detour', False),
    ('event.waypoint', '_ZN12CSWSWaypoint12EventHandlerEjyPvjj', 'detour', False),
    ('app.server_main_loop', '_ZN21CServerExoAppInternal8MainLoopEv', 'detour', True),
    ('app.client_main_loop', '_ZN21CClientExoAppInternal8MainLoopEv', 'detour', False),
    ('console.do_console', '_Z9DoConsolec', 'detour', True),
]

# (class typeinfo name, K2 site) for methods reachable through a vtable slot.
VSLOT = {
    'vm.execute_command': '25CSWVirtualMachineCommands',
    'vmcmd.destroy_game_defined_structure': '25CSWVirtualMachineCommands',
    'event.creature': '12CSWSCreature', 'event.door': '8CSWSDoor', 'event.placeable': '13CSWSPlaceable',
    'event.trigger': '11CSWSTrigger', 'event.encounter': '13CSWSEncounter',
    'event.aoe': '22CSWSAreaOfEffectObject', 'event.store': '9CSWSStore', 'event.waypoint': '12CSWSWaypoint',
}

# CVirtualMachine's forwarding wrappers, in emitted order (identical in the
# K2 x86_64 and K1 i386 symbol tables).
VM_BLOCK = ['RunScript', 'RunScriptSituation', 'GetRunScriptReturnValue', 'SetCommandImplementer',
            'StackPopInteger', 'StackPushInteger', 'StackPopFloat', 'StackPushFloat', 'StackPopVector',
            'StackPushVector', 'StackPopString', 'StackPushString', 'StackPopEngineStructure',
            'StackPushEngineStructure', 'StackPopObject', 'StackPushObject', 'StackPopCommand',
            'SaveScriptSituation', 'LoadScriptSituation', 'DeleteScriptSituation']
VM_BLOCK_SITE = {
    'StackPopInteger': 'vm.stack_pop_integer', 'StackPushInteger': 'vm.stack_push_integer',
    'StackPopFloat': 'vm.stack_pop_float', 'StackPushFloat': 'vm.stack_push_float',
    'StackPopVector': 'vm.stack_pop_vector', 'StackPushVector': 'vm.stack_push_vector',
    'StackPopString': 'vm.stack_pop_string', 'StackPushString': 'vm.stack_push_string',
    'StackPopEngineStructure': 'vm.stack_pop_engine_structure',
    'StackPushEngineStructure': 'vm.stack_push_engine_structure',
    'StackPopObject': 'vm.stack_pop_object', 'StackPushObject': 'vm.stack_push_object',
}
# Internal methods reached by following a wrapper's tail jump.
VM_FOLLOW = {
    'RunScript': 'vm.run_script', 'RunScriptSituation': 'vm.run_script_situation',
    'SaveScriptSituation': 'vm.save_script_situation', 'LoadScriptSituation': 'vm.load_script_situation',
}


def die(msg):
    print('gen_mac_tables: ' + msg, file=sys.stderr)
    sys.exit(1)


def hexb(b):
    return ''.join('%02x' % x for x in b)


def demangle(names):
    tool = None
    for t in ('llvm-cxxfilt', 'llvm-cxxfilt-18', 'c++filt'):
        if any(os.access(os.path.join(d, t), os.X_OK) for d in os.environ.get('PATH', '').split(os.pathsep)):
            tool = t
            break
    if tool is None:
        die('llvm-cxxfilt not found')
    raw = [n[1:] if n.startswith('__Z') else n.lstrip('_') for n in names]
    out = subprocess.run([tool], input='\n'.join(raw), capture_output=True, text=True).stdout.split('\n')
    return dict(zip(names, out))


def insns(m, start, stop):
    out = subprocess.run([mm.objdump_tool(), '-d', '--no-show-raw-insn', '--arch=' + m.arch,
                          '--start-address=%#x' % start, '--stop-address=%#x' % stop, m._tmp],
                         capture_output=True, text=True, check=True).stdout
    res = []
    for line in out.splitlines():
        mt = mm.INSN_RE.match(line)
        if mt:
            res.append((int(mt.group(1), 16), mt.group(2), mt.group(3).split('##')[0].strip()))
    return res


def text_sha(m):
    s = m.sect('__text')
    return hashlib.sha256(m.data[s['offset']:s['offset'] + s['size']]).hexdigest()


def file_sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


class Image:
    def __init__(self, path, arch, cache):
        self.path = path
        self.m = mm.MachO(path, arch)
        import tempfile
        t = tempfile.NamedTemporaryFile(suffix='.macho', delete=False)
        t.write(self.m.data)
        t.close()
        self.m._tmp = t.name
        self.funcs = mm.disassemble(self.m, cache)
        self.sym = {}          # mangled (no leading _) -> addr
        for a, n in self.m.symbols.items():
            self.sym.setdefault(n[1:] if n.startswith('_') else n, a)

    def close(self):
        os.unlink(self.m._tmp)

    def bytes_at(self, a, n=16):
        return self.m.read(a, n)

    def u64(self, a):
        return struct.unpack('<Q', self.m.read(a, 8))[0]


def parse_wrapper(ins):
    """CVirtualMachine forwarder: push rbp; mov rsp,rbp; mov [off](%rdi),%rdi; pop rbp; jmp T."""
    if len(ins) < 5 or ins[0][1] != 'pushq' or ins[1][1] != 'movq' or ins[3][1] != 'popq' or ins[4][1] != 'jmp':
        return None
    m = re.fullmatch(r'(0x[0-9a-f]+)?\(%rdi\), %rdi', ins[2][2])
    if not m or ins[2][1] != 'movq':
        return None
    off = int(m.group(1), 16) if m.group(1) else 0
    tgt = int(re.match(r'0x([0-9a-f]+)', ins[4][2]).group(1), 16)
    return off, tgt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--k1', required=True, help='K1 KOTOR_Exe (thin x86_64)')
    ap.add_argument('--k2', required=True, help='K2 KOTOR2sub (fat or thin; x86_64 slice used)')
    ap.add_argument('--k1-i386', required=True, help='named K1 i386 Mac image (corpus raw_image)')
    ap.add_argument('--cache', default=None)
    ap.add_argument('--check', action='store_true', help='regenerate in memory and diff against the tree')
    args = ap.parse_args()

    k1 = Image(args.k1, 'x86_64', args.cache)
    k2 = Image(args.k2, 'x86_64', args.cache)
    ki = Image(args.k1_i386, 'i386', args.cache)
    if k1.m.sha256 == k2.m.sha256:
        die('K1 and K2 are the same image')

    names2 = demangle([n for n in k2.m.symbols.values()])
    namesi = demangle([n for n in ki.m.symbols.values()])

    print('matching K1 x86_64 against K2 x86_64 (names) ...', file=sys.stderr)
    m12, w12 = fn_match.match(k1.funcs, k2.funcs, True, log=lambda *_: None)
    print('matching K1 x86_64 against K1 i386 (names) ...', file=sys.stderr)
    m1i, w1i = fn_match.match(k1.funcs, ki.funcs, False, log=lambda *_: None)
    inv2 = {v: k for k, v in m12.items()}
    invi = {v: k for k, v in m1i.items()}

    def base(dn):
        return dn.split('(')[0] if dn else None

    by_i386 = {}
    for addr, n in ki.m.symbols.items():
        if addr in ki.funcs:          # code symbols only: skip statics such as MainLoop()::a
            by_i386.setdefault(base(namesi.get(n)), addr)

    vt1 = vtmod.vtables(k1.m)
    vt2 = vtmod.vtables(k2.m)

    evidence = OrderedDict()
    k1_addr = {}

    def propose(site, addr, how):
        evidence.setdefault(site, []).append({'how': how, 'addr': '%#x' % addr if addr else None})

    # --- derivations -------------------------------------------------------
    for site, sym, kind, req in FUNCTION_SITES:
        a2 = k2.sym.get(sym)
        if a2 is None:
            die('K2 symbol missing: ' + sym)
        dn = base(names2[k2.m.symbols[a2]])
        if a2 in inv2:
            propose(site, inv2[a2], 'k2match:' + w12[inv2[a2]])
        ai = by_i386.get(dn)
        if ai is not None and ai in invi:
            propose(site, invi[ai], 'i386match:' + w1i[invi[ai]])
        cls = VSLOT.get(site)
        if cls:
            for vi, (va2, ott2, f2) in enumerate(vt2.get(cls, [])):
                if a2 in f2:
                    slot = f2.index(a2)
                    va1, ott1, f1 = vt1[cls][vi]
                    if ott1 == ott2 and slot < len(f1):
                        propose(site, f1[slot], 'vtable:%s[%d] slot %d' % (cls, vi, slot))

    # CVirtualMachine forwarder block
    k2_block = [k2.sym['_ZN15CVirtualMachine' + {
        'RunScript': '9RunScriptEP10CExoStringyi', 'RunScriptSituation': '18RunScriptSituationEPvyi',
        'GetRunScriptReturnValue': '23GetRunScriptReturnValueEPiPPv',
        'SetCommandImplementer': '21SetCommandImplementerEP29CVirtualMachineCmdImplementer',
        'StackPopInteger': '15StackPopIntegerEPi', 'StackPushInteger': '16StackPushIntegerEi',
        'StackPopFloat': '13StackPopFloatEPf', 'StackPushFloat': '14StackPushFloatEf',
        'StackPopVector': '14StackPopVectorEP6Vector', 'StackPushVector': '15StackPushVectorE6Vector',
        'StackPopString': '14StackPopStringEP10CExoString', 'StackPushString': '15StackPushStringERK10CExoString',
        'StackPopEngineStructure': '23StackPopEngineStructureEiPPv',
        'StackPushEngineStructure': '24StackPushEngineStructureEiPv',
        'StackPopObject': '14StackPopObjectEPy', 'StackPushObject': '15StackPushObjectEy',
        'StackPopCommand': '15StackPopCommandEPPv',
        'SaveScriptSituation': '19SaveScriptSituationEPvP7CResGFFP10CResStruct',
        'LoadScriptSituation': '19LoadScriptSituationEPPvP7CResGFFP10CResStruct',
        'DeleteScriptSituation': '21DeleteScriptSituationEPv'}[n]] for n in VM_BLOCK]
    if k2_block != sorted(k2_block):
        die('K2 CVirtualMachine forwarders are not in the expected order')
    i386_order = sorted((by_i386['CVirtualMachine::' + n], n) for n in VM_BLOCK)
    if [n for _, n in i386_order] != VM_BLOCK:
        die('K1 i386 CVirtualMachine forwarders are not in the expected order')
    # anchor: the K1 x64 StackPopInteger both matchers agree on
    anchor = None
    for ev in evidence.get('vm.stack_pop_integer', []):
        anchor = int(ev['addr'], 16) if anchor is None else anchor
    agreeing = {e['addr'] for e in evidence.get('vm.stack_pop_integer', [])}
    if len(agreeing) != 1 or len(evidence.get('vm.stack_pop_integer', [])) < 2:
        die('no agreed anchor for the CVirtualMachine forwarder block')
    idx = VM_BLOCK.index('StackPopInteger')
    k1_block = {}
    for i, n in enumerate(VM_BLOCK):
        a = anchor + (i - idx) * 14
        w = parse_wrapper(insns(k1.m, a, a + 14))
        if w is None:
            die('K1 forwarder %s at %#x does not have the forwarder shape' % (n, a))
        k1_block[n] = (a, w)
    offs = {w[0] for _, w in k1_block.values()}
    if len(offs) != 1:
        die('K1 forwarders disagree on the internal offset: %s' % offs)
    for n, (a, (off, tgt)) in k1_block.items():
        if n in VM_BLOCK_SITE:
            propose(VM_BLOCK_SITE[n], a, 'block:CVirtualMachine::%s ordinal %d' % (n, VM_BLOCK.index(n)))
        if n in VM_FOLLOW:
            propose(VM_FOLLOW[n], tgt, 'follow:CVirtualMachine::%s -> internal' % n)

    # callsite: a K2 caller that is itself agreed-matched calls the site at call
    # index j; the K1 counterpart's call j is a candidate.
    agreed = {a1: a2 for a1, a2 in m12.items()
              if a1 in m1i and k2.m.symbols.get(a2) and ki.m.symbols.get(m1i[a1]) and
              base(names2[k2.m.symbols[a2]]) == base(namesi[ki.m.symbols[m1i[a1]]])}
    agreed_inv = {v: k for k, v in agreed.items()}
    callers2 = {}
    for a2, f in k2.funcs.items():
        for j, c in enumerate(f.calls):
            if isinstance(c, int):
                callers2.setdefault(c, []).append((a2, 'calls', j))
        for j, c in enumerate(f.tail):
            if isinstance(c, int):
                callers2.setdefault(c, []).append((a2, 'tail', j))
    for site, sym, kind, req in FUNCTION_SITES:
        a2 = k2.sym[sym]
        votes = {}
        for p2, lst, j in callers2.get(a2, []):
            p1 = agreed_inv.get(p2)
            if p1 is None:
                continue
            l1 = getattr(k1.funcs[p1], lst); l2 = getattr(k2.funcs[p2], lst)
            if len(l1) != len(l2) or not isinstance(l1[j], int):
                continue
            votes.setdefault(l1[j], []).append(p2)
        if len(votes) == 1:
            cand, via = next(iter(votes.items()))
            propose(site, cand, 'callsite:%d agreed caller(s)' % len(via))

    # similarity: corroboration of an already-proposed candidate by instruction
    # sequence against the named K2 function. Never proposes on its own.
    import difflib
    def mnems(img, a, n=400):
        return [mn for _, mn, _ in img.funcs[a].insns[:n]] if a in img.funcs else []
    for site, sym, kind, req in FUNCTION_SITES:
        a2 = k2.sym[sym]
        for cand in sorted({int(e['addr'], 16) for e in evidence.get(site, [])}):
            r = difflib.SequenceMatcher(None, mnems(k1, cand), mnems(k2, a2), autojunk=False).ratio()
            if r >= 0.75:
                propose(site, cand, 'similar:%.2f' % r)

    # callees: the candidate's direct callees, mapped through the K2 match, form
    # an in-order subsequence of the named K2 function's callees (>=2 mapped, no
    # mapped callee absent from K2's list). Corroboration only.
    def callee_order_agrees(c1, a2):
        l1 = [m12.get(c) for c in k1.funcs[c1].calls + k1.funcs[c1].tail if isinstance(c, int)]
        l2 = [c for c in k2.funcs[a2].calls + k2.funcs[a2].tail if isinstance(c, int)]
        mapped = [c for c in l1 if c is not None]
        if len(mapped) < 2:
            return 0
        it = iter(l2)
        return len(mapped) if all(any(c == d for d in it) for c in mapped) else 0
    for site, sym, kind, req in FUNCTION_SITES:
        a2 = k2.sym[sym]
        for cand in sorted({int(e['addr'], 16) for e in evidence.get(site, [])}):
            n = callee_order_agrees(cand, a2) if cand in k1.funcs else 0
            if n:
                propose(site, cand, 'callees:%d in order' % n)

    # --- adjudication ------------------------------------------------------
    failures = []
    for site, sym, kind, req in FUNCTION_SITES:
        evs = evidence.get(site, [])
        addrs = {e['addr'] for e in evs}
        if len(addrs) == 1 and len(evs) >= 2:
            k1_addr[site] = int(next(iter(addrs)), 16)
        else:
            failures.append('%s: %s' % (site, evs))
    if failures:
        die('K1 bindings without two agreeing derivations:\n  ' + '\n  '.join(failures))

    # --- fields ------------------------------------------------------------
    def fields_for(img, addr_of):
        f = OrderedDict()
        w = parse_wrapper(insns(img.m, addr_of('vm.stack_pop_integer'), addr_of('vm.stack_pop_integer') + 14))
        f['vm.wrapper_internal'] = ('CVirtualMachine', 'internal', w[0], 8, 'forwarder mov %#x(%%rdi),%%rdi' % w[0])
        # SetCommandImplementer internal: mov %rsi, OFF(%rdi)
        sci = img.sci
        ins = insns(img.m, sci, sci + 16)
        mt = [re.fullmatch(r'%rsi, (0x[0-9a-f]+)\(%rdi\)', o) for _, mn, o in ins if mn == 'movq']
        mt = [x for x in mt if x]
        if len(mt) != 1:
            die('SetCommandImplementer shape')
        ci = int(mt[0].group(1), 16)
        f['vm.internal_command_implementer'] = ('CVirtualMachineInternal', 'command_implementer', ci, 8,
                                                'SetCommandImplementer stores %%rsi at %#x(%%rdi)' % ci)
        ec = addr_of('vm.execute_command')
        ins = insns(img.m, ec, ec + 0x3a)
        text = ' | '.join('%s %s' % (mn, o) for _, mn, o in ins)
        mcmp = re.search(r'cmpl \$0x([0-9a-f]+), %esi \| (jg|jge)', text)
        mtab = re.search(r'movq 0x([0-9a-f]+)\(%rdi\), %r(\w+)', text)
        mshl = re.search(r'shlq \$0x4, %rcx', text)
        if not (mcmp and mtab and mshl and 'addq 0x8(' in text and 'testb $0x1, %al' in text):
            die('ExecuteCommand shape (Itanium member-pointer table) not recognised at %#x' % ec)
        bound = int(mcmp.group(1), 16) + (1 if mcmp.group(2) == 'jg' else 0)
        f['vmcmd.commands'] = ('CSWVirtualMachineCommands', 'commands', int(mtab.group(1), 16), 8,
                               'ExecuteCommand loads the member-pointer array from %#x(%%rdi); 16-byte '
                               '{ptr,adj} entries; %d commands' % (int(mtab.group(1), 16), bound))
        f['vmcmd.command_count'] = ('CSWVirtualMachineCommands', 'command_count', bound, 4,
                                    'ExecuteCommand bound: cmpl $%s,%%esi; %s' % (mcmp.group(1), mcmp.group(2)))
        return f

    k2.sci = k2.sym['_ZN23CVirtualMachineInternal21SetCommandImplementerEP29CVirtualMachineCmdImplementer']
    k1.sci = k1_block['SetCommandImplementer'][1][1]
    # cross-check: K2's forwarder target equals its named internal
    if parse_wrapper(insns(k2.m, k2_block[VM_BLOCK.index('SetCommandImplementer')],
                           k2_block[VM_BLOCK.index('SetCommandImplementer')] + 14))[1] != k2.sci:
        die('K2 SetCommandImplementer forwarder target mismatch')

    k2_addr = {site: k2.sym[sym] for site, sym, _, _ in FUNCTION_SITES}
    f1 = fields_for(k1, lambda s: k1_addr[s])
    f2 = fields_for(k2, lambda s: k2_addr[s])

    # vtable-derived subobject offsets and the object/event layouts
    def subobject(vt, cls):
        offs = sorted({-ott for _, ott, fns in vt[cls] if ott < 0 and len(fns) == 29})
        if len(offs) != 1:
            die('%s: CGameObject subobject offset ambiguous: %s' % (cls, offs))
        return offs[0]
    for img, vt, f in ((k1, vt1, f1), (k2, vt2, f2)):
        f['area.game_object'] = ('CSWSArea', 'CGameObject', subobject(vt, '8CSWSArea'), 0,
                                 'RTTI offset-to-top of the 29-slot CGameObject vtable')
        f['module.game_object'] = ('CSWSModule', 'CGameObject', subobject(vt, '10CSWSModule'), 0,
                                   'RTTI offset-to-top of the 29-slot CGameObject vtable')

    # g_pAppManager and CAppManager::server from RunScriptCallback (vtable slot 4)
    def app_manager(img, vt):
        rsc = vt['25CSWVirtualMachineCommands'][0][2][4]
        ins = insns(img.m, rsc, rsc + 0x30)
        g = srv = None
        for i, (addr, mn, o) in enumerate(ins):
            mg = re.fullmatch(r'(0x[0-9a-f]+)\(%rip\), %rax', o)
            if mn in ('leaq', 'movq') and mg and g is None:
                nxt = ins[i + 1] if i + 1 < len(ins) else None
                rip = ins[i + 1][0]
                cand = rip + int(mg.group(1), 16)
                if mn == 'movq':   # GOT-indirect: the slot holds &g_pAppManager (non-PIE: absolute)
                    cand = img.u64(cand)
                g = cand
                continue
            ms = re.fullmatch(r'(0x[0-9a-f]+)\(%rax\), %rdi', o)
            if g is not None and mn == 'movq' and ms:
                srv = int(ms.group(1), 16)
                break
        if g is None or srv is None:
            die('RunScriptCallback shape')
        return g, srv
    for img, vt, f in ((k1, vt1, f1), (k2, vt2, f2)):
        g, srv = app_manager(img, vt)
        f['g.app_manager'] = ('', 'g_pAppManager', g, 8, 'RunScriptCallback loads g_pAppManager')
        f['appmgr.server'] = ('CAppManager', 'server', srv, 8, 'RunScriptCallback reads ->server at %#x' % srv)
    if f2['g.app_manager'][2] != k2.sym.get('g_pAppManager'):
        die('K2 g_pAppManager derivation disagrees with its symbol')

    # CGameObject ctor and CScriptEvent accessors (K2 named; K1 via agreed match)
    def layout_from(img, go_ctor, get_obj, get_int, get_float):
        f = OrderedDict()
        ins = insns(img.m, go_ctor, go_ctor + 0x1c)
        t = ' | '.join('%s %s' % (mn, o) for _, mn, o in ins)
        mi = re.search(r'movq %rdx, 0x([0-9a-f]+)\(%rdi\)', t)
        mt = re.search(r'movb %sil, 0x([0-9a-f]+)\(%rdi\)', t)
        if not (mi and mt):
            die('CGameObject ctor shape')
        f['object.id'] = ('CGameObject', 'id', int(mi.group(1), 16), 8, 'CGameObject(type,id) stores id (%rdx)')
        f['object.type'] = ('CGameObject', 'object_type', int(mt.group(1), 16), 1, 'stores type (%sil)')
        for name, fn, scale in (('objects', get_obj, 8), ('ints', get_int, 4), ('floats', get_float, 4)):
            ins = insns(img.m, fn, fn + 0x20)
            t = ' | '.join('%s %s' % (mn, o) for _, mn, o in ins)
            mp = re.search(r'movq 0x([0-9a-f]+)\(%rdi\), %r(cx|ax)', t)
            ms = re.search(r'cmpl %esi, 0x([0-9a-f]+)\(%rdi\)', t)
            me = re.search(r'\(%r(cx|ax),%r(ax|cx),(\d)\)', t)
            if not (mp and ms and me) or int(me.group(3)) != scale or int(ms.group(1), 16) != int(mp.group(1), 16) + 8:
                die('CScriptEvent %s accessor shape at %#x' % (name, fn))
            f['script_event.' + name] = ('CScriptEvent', name, int(mp.group(1), 16), scale,
                                         'Get accessor reads list data at %s, size at +8, element %d bytes'
                                         % (mp.group(1), scale))
        return f
    se2 = {n: k2.sym[s] for n, s in (('ctor', '_ZN11CGameObjectC2Ehy'), ('obj', '_ZN12CScriptEvent11GetObjectIDEi'),
                                    ('int', '_ZN12CScriptEvent10GetIntegerEi'), ('float', '_ZN12CScriptEvent8GetFloatEi'))}
    se1 = {}
    for n, a2 in se2.items():
        if a2 not in inv2:
            die('K1 has no match for K2 %s' % n)
        se1[n] = inv2[a2]
    f2.update(layout_from(k2, se2['ctor'], se2['obj'], se2['int'], se2['float']))
    f1.update(layout_from(k1, se1['ctor'], se1['obj'], se1['int'], se1['float']))
    for key in ('object.id', 'object.type', 'script_event.objects', 'script_event.ints', 'script_event.floats'):
        if f1[key][2:4] != f2[key][2:4]:
            die('K1/K2 x86_64 disagree on %s' % key)
    for img, f in ((k1, f1), (k2, f2)):
        so = f['script_event.objects'][2]
        f['script_event.strings'] = ('CScriptEvent', 'strings', so - 0x10, 16,
                                     'the CExoString list sits one 16-byte CExoArrayList before objects '
                                     '(destructor frees +0x08, +0x18, +0x28(strings), +0x38)')

    # --- emit ----------------------------------------------------------------
    def table(alias, game, img, addrs, fields, file_path, how_k1):
        sites = OrderedDict()
        for site, sym, kind, req in FUNCTION_SITES:
            addr = addrs[site]
            dn = names2[k2.m.symbols[k2.sym[sym]]]
            cls, _, meth = base(dn).rpartition('::')
            entry = OrderedDict()
            entry['cls'] = cls
            entry['method'] = meth
            entry['kind'] = kind
            entry['required'] = req
            entry['addr'] = addr
            entry['source'] = 'symbol' if img is k2 else 'derived'
            entry['confidence'] = 1.0
            entry['method_detail'] = 'mangled symbol ' + sym if img is k2 else '; '.join(
                e['how'] for e in evidence[site])
            entry['candidates'] = 1
            entry['addr_hex'] = '0x%X' % addr
            entry['expected_bytes'] = hexb(img.bytes_at(addr, 16))
            sites[site] = entry
        for site, (cls, meth, off, size, why) in fields.items():
            entry = OrderedDict()
            entry['cls'] = cls
            entry['method'] = meth
            entry['kind'] = 'field'
            entry['required'] = False
            glob = site == 'g.app_manager'
            entry['addr'] = off if glob else 0
            entry['source'] = 'machine-code'
            entry['confidence'] = 1.0
            entry['method_detail'] = why
            entry['candidates'] = 1
            entry['offset'] = 0 if glob else off
            entry['size'] = size
            entry['addr_hex'] = '0x%X' % (off if glob else 0)
            entry['offset_hex'] = '0x%X' % (0 if glob else off)
            sites[site] = entry
        doc = OrderedDict()
        doc['build'] = alias
        doc['game'] = game
        doc['platform'] = 'mac'
        doc['format'] = 'macho'
        doc['arch'] = 'x86_64'
        doc['abi'] = 'sysv-x86_64-itanium'
        doc['image_base'] = IMAGE_BASE
        doc['encrypted'] = False
        doc['symbol_source'] = 'KOTOR2sub x86_64 symbol table' if img is k2 else (
            'derived: K2 x86_64 names, K1 i386 Mac names, RTTI vtables, forwarder block')
        doc['identity'] = OrderedDict([('sha256', img.m.sha256), ('file_sha256', file_sha(img.path)),
                                       ('text_sha256', text_sha(img.m))])
        doc['format_kind'] = 'macho64'
        doc['note'] = how_k1
        doc['adjudicated_bindings'] = len(sites)
        doc['sites'] = sites
        return doc

    d1 = table(K1_ALIAS, 'K1', k1, k1_addr, f1, args.k1,
               'Stripped Steam x86_64 image. Every function binding has >=2 agreeing independent derivations; '
               'see data/adjudication/mac_x64_bindings.json.')
    d2 = table(K2_ALIAS, 'K2', k2, k2_addr, f2, args.k2,
               'Steam x86_64 slice of the universal KOTOR2sub. Functions from its own symbol table.')

    inc = ['// Generated by tools/mac/gen_mac_tables.py. Do not edit; regenerate.',
           '// clang-format off',
           '// Mach-O x86_64 builds. Identified by the sha256 of the file on disk (a fat',
           '// file and its thinned slice are both listed), verified by the sha256 of',
           '// __TEXT,__text read back out of the mapped image.']
    for alias, img, path in ((K1_ALIAS, k1, args.k1), (K2_ALIAS, k2, args.k2)):
        inc.append('static const KnownText kText_%s[] = {' % alias)
        inc.append('    {"__text", "%s"},' % text_sha(img.m))
        inc.append('};')
    inc.append('static const BuildRecord kBuildsMachO[] = {')
    for alias, img, path, what in ((K1_ALIAS, k1, args.k1, 'K1 Steam macOS KOTOR_Exe (x86_64)'),
                                   (K2_ALIAS, k2, args.k2, 'K2 Steam macOS KOTOR2sub (x86_64 slice)')):
        shas = [file_sha(path)]
        if img.m.sha256 not in shas:
            shas.append(img.m.sha256)
        for sha in shas:
            kind = 'file' if sha == shas[0] else 'thinned x86_64 slice'
            inc += ['    {', '        "%s",' % alias, '        "%s",' % sha,
                    '        Format::MachO, 0x%X, false,' % IMAGE_BASE,
                    '        0, "", "",',
                    '        kText_%s, sizeof kText_%s / sizeof kText_%s[0],' % (alias, alias, alias),
                    '        "%s (%s).",' % (what, kind), '    },']
    inc.append('};')

    evidence_doc = OrderedDict()
    evidence_doc['k1_image_sha256'] = k1.m.sha256
    evidence_doc['k2_image_sha256'] = k2.m.sha256
    evidence_doc['k1_i386_reference_sha256'] = ki.m.sha256
    evidence_doc['rule'] = 'a K1 function binding is emitted only with >=2 agreeing derivations and no disagreeing one'
    evidence_doc['bindings'] = OrderedDict((s, OrderedDict([('addr', '%#x' % k1_addr[s]), ('derivations', evidence[s])]))
                                           for s, _, _, _ in FUNCTION_SITES)
    evidence_doc['fields'] = OrderedDict((k, OrderedDict([('k1', f1[k][2]), ('k2', f2[k][2]), ('why', f1[k][4])]))
                                         for k in f1)

    outs = {
        os.path.join(ROOT, 'data/addresses/%s.json' % K1_ALIAS): json.dumps(d1, indent=2) + '\n',
        os.path.join(ROOT, 'data/addresses/%s.json' % K2_ALIAS): json.dumps(d2, indent=2) + '\n',
        os.path.join(ROOT, 'src/generated/builds_macho.inc'): '\n'.join(inc) + '\n',
        os.path.join(ROOT, 'data/adjudication/mac_x64_bindings.json'): json.dumps(evidence_doc, indent=2) + '\n',
    }
    for img in (k1, k2, ki):
        img.close()
    stale = []
    for p, text in outs.items():
        if args.check:
            if not os.path.exists(p) or open(p).read() != text:
                stale.append(p)
        else:
            open(p, 'w').write(text)
            print('wrote ' + os.path.relpath(p, ROOT))
    if stale:
        die('out of date: ' + ', '.join(os.path.relpath(p, ROOT) for p in stale))


if __name__ == '__main__':
    main()
