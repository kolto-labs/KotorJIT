"""Reviewed local-constant configurations; never accept arbitrary source patches."""
import difflib
import hashlib
import json
import ipaddress
import math
import re

# Each exact declaration belongs to the hash-checked stock script. Configuration
# can change only these literals, not callsites, guards, functions or comments.
RULES = {
    'multiplayer/10_avatar_sync.lua': {
        'LOCAL_NAME': ('"Player"', 'player_name'), 'LISTEN_PORT': ('39131', 'port'),
        'PEERS': ('{\n    -- One entry per other player. Symmetric: if A lists B, B must list A.\n    -- { host = "203.0.113.10", port = 39131 },\n}', 'peers')},
    'harness/10_world_probe.lua': {'RADIUS': ('60.0', 'radius')},
    'harness/20_dialog_state.lua': {'PARTNER_TAG': ('"end_trask"', 'tag')},
    'harness/30_move_to.lua': {'TARGET_TAG': ('"end_door05"', 'optional_tag'),
                              'RANGE': ('1.5', 'radius'),
                              'OFFSET': ('{ x = -3.0, y = 0.0, z = 0.0 }', 'vector')},
    'harness/40_attack_nearest.lua': {'RADIUS': ('40.0', 'radius')},
    'harness/50_doors.lua': {'TAG': ('"end_door05"', 'tag'), 'OPEN': ('false', 'bool')},
    'harness/60_area_dump.lua': {'OBJECT_TYPE': ('1', 'object_type'), 'MAX': ('40', 'count')},
    'harness/80_signal_event.lua': {'TARGET': ('"area"', 'tag'), 'EVENT': ('20', 'event')},
    'harness/90_run_script.lua': {'SCRIPT': ('"k_pend_door20"', 'resref'),
                                 'TARGET_TAG': ('"end_door08"', 'optional_tag')},
    'harness/100_module_transition.lua': {'DOOR_TAG': ('"end_door10"', 'tag'),
        'INSPECT': ('true', 'bool'), 'MODULE': ('"end_m01ab"', 'resref'),
        'WAYPOINT': ('"from_01a"', 'tag')},
    'harness/110_loot_container.lua': {'TAG': ('"metalbox"', 'tag')},
}


def literal(value, kind):
    if kind == 'player_name':
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9 _.\-]{1,32}', value):
            raise ValueError('bounded printable player name required')
        return json.dumps(value)
    if kind == 'peers':
        if not isinstance(value, list) or len(value) > 3:
            raise ValueError('PEERS supports at most three reviewed peers')
        rows, seen = [], set()
        for peer in value:
            if not isinstance(peer, dict) or set(peer) != {'host', 'port'} or not isinstance(peer['host'], str):
                raise ValueError('peer requires exactly IPv4 host and port')
            host = str(ipaddress.IPv4Address(peer['host']))
            port = literal(peer['port'], 'port')
            if (host, port) in seen:
                raise ValueError('duplicate peer')
            seen.add((host, port))
            rows.append('    { host = ' + json.dumps(host) + ', port = ' + port + ' },')
        return '{\n' + '\n'.join(rows) + '\n}'
    if kind == 'bool':
        if type(value) is not bool:
            raise ValueError('configuration boolean required')
        return 'true' if value else 'false'
    if kind == 'optional_tag' and value is None:
        return 'nil'
    if kind in {'tag', 'optional_tag', 'resref'}:
        limit = 16 if kind == 'resref' else 64
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,' + str(limit) + '}', value):
            raise ValueError('configuration requires a bounded tag/resref')
        return json.dumps(value)
    if kind == 'vector':
        if not isinstance(value, dict) or set(value) != {'x', 'y', 'z'}:
            raise ValueError('OFFSET requires exactly x, y, z')
        return '{ ' + ', '.join(axis + ' = ' + literal(value[axis], 'coordinate') for axis in ('x', 'y', 'z')) + ' }'
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('finite configuration number required')
    if kind == 'object_type' and (type(value) is not int or value not in {1, 2, 4, 8, 32, 64}):
        raise ValueError('unsupported object type configuration')
    bounds = {'radius': (0, 250), 'coordinate': (-1000, 1000), 'count': (1, 1000), 'event': (0, 255), 'port': (1, 65535)}
    if kind in bounds and not bounds[kind][0] <= value <= bounds[kind][1]:
        raise ValueError('configuration number outside reviewed bounds')
    if kind in {'count', 'event', 'port'} and type(value) is not int:
        raise ValueError('configuration integer required')
    return json.dumps(value)


def effective_source(entry, stock, configuration):
    """Return bytes and exact unified diff derived exclusively from allowed values."""
    if hashlib.sha256(stock).hexdigest() != entry['sha256']:
        raise ValueError('stock configuration source is stale')
    if not isinstance(configuration, dict) or set(configuration) != {'schema', 'path', 'values'} or type(configuration['schema']) is not int or configuration['schema'] != 1 or configuration['path'] != entry['path']:
        raise ValueError('wrong configuration schema or path')
    rules = RULES.get(entry['path'], {})
    values = configuration['values']
    if not isinstance(values, dict) or not values or not set(values) <= set(rules):
        raise ValueError('configuration contains unreviewed or empty fields')
    source = stock.decode('utf-8')
    effective = source
    replacements = {key: literal(value, rules[key][1]) for key, value in values.items()}
    if entry['path'] == 'harness/100_module_transition.lua' and set(values) & {'MODULE', 'WAYPOINT'}:
        old = 'local MODULE, WAYPOINT = "end_m01ab", "from_01a"'
        new = 'local MODULE, WAYPOINT = ' + replacements.pop('MODULE', '"end_m01ab"') + ', ' + replacements.pop('WAYPOINT', '"from_01a"')
        if effective.count(old) != 1:
            raise ValueError('transition declaration drift')
        effective = effective.replace(old, new, 1)
    for key, replacement in replacements.items():
        pattern = r'(?m)^(local[ \t]+' + re.escape(key) + r'[ \t]*=[ \t]*)' + re.escape(rules[key][0]) + r'(?=[ \t]*(?:--|$))'
        effective, count = re.subn(pattern, lambda match: match.group(1) + replacement, effective)
        if count != 1:
            raise ValueError('configuration declaration drift: ' + key)
    if effective == source:
        raise ValueError('configuration must change source; use stock evidence for defaults')
    delta = ''.join(difflib.unified_diff(source.splitlines(keepends=True), effective.splitlines(keepends=True),
                                       fromfile=entry['source_path'], tofile='configured/' + entry['path']))
    return effective.encode('utf-8'), delta.encode('utf-8')
