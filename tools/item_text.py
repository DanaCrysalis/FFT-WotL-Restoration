"""The effect lines of the WotL items' descriptions, written from their data the way IC words its own items'.

  python tools/item_text.py         prints every WotL item's effect line (tools/build_data.py uses effects())

IC's descriptions are a flavour sentence, then what the item does ("While equipped, raises speed and grants immunity
to Stop.", "When attacking, has a chance of inflicting Blindness.", "<color=151>Range:</color> 8"). The flavour
sentences are the mod's own (tools/build_data.py, WOTL_ITEMS); the effect lines come from here, so they always say
what the data does. Sources, all IC's (checked against its own items' descriptions, 2026-09-25):
  equipment bonus rows (0x1A bytes): +0 PA, +1 MA, +2 Speed, +3 Move, +4 Jump, +5..+9 permanent statuses,
    +0xA..+0xE immunities, +0xF..+0x13 statuses at the start of battle, +0x14 absorb, +0x15 nullify, +0x16 halve,
    +0x17 weak, +0x18 strengthen elements (0x80 fire, 0x40 lightning, 0x20 ice, 0x10 wind, 0x08 earth, 0x04 water,
    0x02 holy, 0x01 dark);
  weapon data (8 bytes): range, attack flags, formula (2: casts ability [7]), -, WP, evade, element, [7] = effect
    row (ItemOptionsData, table at RVA 0x80FBA0, 6 bytes: 0x80 inflict / 0x10 cancel, then 5 status bytes);
  status bits: the order of IC's own descriptions (Blind Knife row 8 = Blindness, Mage Masher 9 = Silence, ...).
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')

STATUS = [   # (byte, bit) -> IC's name
    ['', 'Crystal', 'KO', 'Undead', 'Charging', 'Jump', 'Defending', 'Performing'],
    ['Stone', 'Traitor', 'Blindness', 'Confusion', 'Silence', 'Vampire', 'Cursed', 'Treasure'],
    ['Oil', 'Float', 'Reraise', 'Invisibility', 'Berserk', 'Chicken', 'Toad', 'Critical'],
    ['Poison', 'Regen', 'Protect', 'Shell', 'Haste', 'Slow', 'Stop', 'Wall'],
    ['Faith', 'Atheist', 'Charmed', 'Sleep', 'Immobilize', 'Disable', 'Reflect', 'Doom'],
]
ELEMENTS = ['fire', 'lightning', 'ice', 'wind', 'earth', 'water', 'holy', 'dark']
SPELLS = {0x2A: 'Gravity'}                               # abilities the WotL weapons cast (Ability-en)
# ItemOptionsData rows the WotL weapons use (IC's = WotL's table; row = RVA 0x80FBA0 + 6 * id)
OPTIONS = {0x09: ('inflict', 'Blindness'), 0x0B: ('inflict', 'Doom'), 0x12: ('inflict', 'Slow'),
           0x2C: ('inflict', 'Stop'), 0x29: ('inflict', 'KO')}
RANGED = {0x0A: 'Range', 0x0C: 'Basic range', 0x0B: 'Range', 0x0F: 'Range', 0x10: 'Range'}   # gun, bow, crossbow, polearm, pole

def statuses(block):
    return [STATUS[b][bit] for b in range(5) for bit in range(8) if block[b] & (0x80 >> bit)]

def elements(mask):
    return [ELEMENTS[bit] for bit in range(8) if mask & (0x80 >> bit)]

def join(words):
    return words[0] if len(words) == 1 else ', '.join(words[:-1]) + ' and ' + words[-1]

def element_list(mask):
    return 'all elements' if mask == 0xFF else join(elements(mask))

def immunities(block):
    names = statuses(block)
    return 'most status ailments' if len(names) > 8 else join(names)   # IC's Ribbon wording

def effects(it):
    """it: a research/items/wotl_items.json row. Returns the effect sentences (without the flavour)."""
    common = bytes.fromhex(it['common']); sub = bytes.fromhex(it['sub'])
    lines = []
    if it['kind'] == 'weapon':
        formula, element, extra = sub[2], sub[6], sub[7]
        if formula == 2 and extra:
            lines.append('When attacking, has a chance of casting %s.' % SPELLS[extra])
        elif extra:
            kind, status = OPTIONS[extra]
            lines.append('When attacking, has a chance of inflicting %s.' % status)
    if it['attr']:
        a = bytes.fromhex(it['attr'])
        raises = [n for n, v in zip(('physical attack power', 'magick attack power', 'speed', 'movement', 'jump'), a[:5]) if v]
        if raises[:2] == ['physical attack power', 'magick attack power']:
            raises[:2] = ['physical and magick attack power']
        clauses = []
        if raises: clauses.append('raises ' + join(raises))
        if statuses(a[5:10]): clauses.append('grants ' + join(statuses(a[5:10])))
        if statuses(a[10:15]): clauses.append('grants immunity to ' + immunities(a[10:15]))
        for byte, verb in ((0x14, 'absorbs damage from %s'), (0x15, 'nullifies damage from %s'),
                           (0x16, 'halves damage from %s'), (0x17, 'increases damage taken from %s')):
            if a[byte]: clauses.append(verb % element_list(a[byte]))
        if a[0x18]:
            clauses.append('strengthens all elemental attacks' if a[0x18] == 0xFF else
                           'strengthens %s attacks' % join(elements(a[0x18])))
        if clauses:
            lines.append('While equipped, ' + join(clauses) + '.')
        if statuses(a[15:20]):
            lines.append('Also grants %s at the start of battle.' % join(statuses(a[15:20])))
    if it['kind'] == 'weapon' and common[5] in RANGED:
        lines.append('<color=151>%s:</color> %d' % (RANGED[common[5]], sub[0]))
    return lines

def items():
    return json.load(open(os.path.join(ROOT, 'research', 'items', 'wotl_items.json')))

if __name__ == '__main__':
    for it in items():
        sub = bytes.fromhex(it['sub'])
        extra = ' WP %d, element %s' % (sub[4], '/'.join(elements(sub[6])) or '-') if it['kind'] == 'weapon' else ''
        print('%3x %-17s%s | %s' % (it['ic_id'], it['name'], extra, ' / '.join(effects(it))))
