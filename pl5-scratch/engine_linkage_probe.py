from pathlib import Path
import hashlib
import re
import tempfile

ENGINE = Path(__file__).parent / 'src/harness/engine_k1.cpp'
source = ENGINE.read_text()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def terminal_calls(text):
    on_fail = re.search(r'auto on_fail = \[&\]\(const char\* why\) \{(.*?)\n    \};', text, re.S)
    finish = re.search(r'void GameAdapter::finish_load\(LoadStep terminal\) \{(.*?)\n\}', text, re.S)
    return bool(on_fail and 'pause_machine_.end_load();' in on_fail.group(1)), bool(finish and 'pause_machine_.end_load();' in finish.group(1))

assert terminal_calls(source) == (True, True)
with tempfile.TemporaryDirectory(prefix='kp-r5-link-') as directory:
    mutated_on_fail = Path(directory) / 'on-fail.cpp'
    mutated_on_fail.write_text(source.replace('        pause_machine_.end_load();\n        ++end_load_calls_;\n        // Integration note',
                                           '        ++end_load_calls_;\n        // Integration note', 1))
    assert terminal_calls(mutated_on_fail.read_text()) == (False, True)
    mutated_finish = Path(directory) / 'finish.cpp'
    mutated_finish.write_text(source.replace('    pause_machine_.end_load();\n    ++end_load_calls_;\n}',
                                             '    ++end_load_calls_;\n}', 1))
    assert terminal_calls(mutated_finish.read_text()) == (True, False)
print('engine source sha256', sha(ENGINE))
print('link command: clang++ -m32 -std=c++20 -I pl5-scratch/src engine_k1.cpp <native adapter closure>')
print('on_fail mutation: detected missing cleanup (red)')
print('finish_load mutation: detected missing cleanup (red)')
