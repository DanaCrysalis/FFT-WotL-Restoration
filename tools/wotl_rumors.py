"""Extract War of the Lions' tavern rumors from the PSP ISO into research/wotl_rumors.json.

  python tools/wotl_rumors.py

Titles are fftpack file 43, messages 4130 + n; bodies are fftpack file 771, message n. A body starts with the
rumor's read actions as `F5 type F6 value` pairs, the same pairs IC keeps in Gossip Unknown14/Unknown1C: type 102
sets base = value * 10, any other type sets event variable (type + base) = value. E.g. The Haunted Mine (20):
(102,16), (6,1) -> var 0xA6 = 1, the flag vanilla's Beowulf trigger checks. IC's Gossip rows 0-21 are WotL's 0-21.
"""
import json, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from convert_wotl import decode

ISO = r"H:/FFT/ISOs/Final Fantasy Tactics - The War of the Lions (USA).iso"
PACK_LBA = 22592
TITLES_FILE, TITLE_FIRST, BODIES_FILE, COUNT = 43, 4130, 771, 26
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'research', 'wotl_rumors.json')

def pack_file(f, i):
    f.seek(PACK_LBA * 2048)
    n = struct.unpack('<I', f.read(4))[0]
    f.seek(PACK_LBA * 2048 + 8 + 4 * i)
    a, b = struct.unpack('<2I', f.read(8))
    f.seek(PACK_LBA * 2048 + a)
    return f.read(b - a)

def split_actions(body):
    pairs, i = [], 0
    while body[i:i + 1] == b'\xF5':
        pairs.append([body[i + 1], body[i + 3]]); i += 4
    return pairs, body[i:]

def paragraphs(text):
    import re
    return '\n\n'.join(' '.join(p.split()) for p in re.split(r'\n\s*\n', text) if p.strip())

if __name__ == '__main__':
    with open(ISO, 'rb') as f:
        titles = pack_file(f, TITLES_FILE).split(b'\xFE')
        bodies = pack_file(f, BODIES_FILE).split(b'\xFE')
    rumors = []
    for n in range(COUNT):
        actions, body = split_actions(bodies[n])
        rumors.append({'id': n, 'title': decode(titles[TITLE_FIRST + n]).strip(), 'actions': actions,
                       'text': paragraphs(decode(body))})
    json.dump(rumors, open(OUT, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    for r in rumors: print(r['id'], r['title'], r['actions'])
