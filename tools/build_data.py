"""Build the War of the Lions event data WotL Restoration ships, into FFTIVC/data/enhanced/ (served by
fftivc.utility.modloader). BuildLinked.ps1 runs it before publishing.

  python tools/build_data.py

The mod's hand-made tables (charaname, job, jobcommand, ability, uijobabilityhelp and charshape) stay the source of
truth: charshape.nxd is read back from FFTIVC and only gains rows, every other table written here is built from the
vanilla copies in research/vanilla/nxd.

Outputs:
  script/enhanced/event578.e, event579.e       the entry stub and the converted scene (tools/convert_event.py)
  nxd/text/scenario/scenario9159.en.pzd          the scene's text
  nxd/{enhancedworldevent,enhancedbattleevent,scenarioid,scionfiles,eventid,charshape,characontrolid}.nxd
                                                 trigger, stub -> scene rule, scenario -> text file, event flags,
                                                 render parameters for the gift box's sprite set
  system/ffto/g2d/tex_1279.bin                   texture for event sprite sheet 0x8E (the birthday poses)
  WotL scene groups (WOTL_SCENES below: Delita and Ovelia at Bervenia 535/536, Balthier 518-524): their scripts,
  one scenario text file each, rows in the same nxd tables plus speaker.en, sortieconfirm, characontrolid and
  entryno, and the textures of the WotL event sprite sheets they load
  nxd/gossip.en.nxd                              the tavern rumors IC dropped (RUMORS below)

ReMixed's scene is War of the Lions' Agrias's Birthday, and IC still carries WotL's (unused) setup for it:
event records 578 (stub, battle-event rules key 163) -> 579 (scene), map 96, and the cast in ENTD 527
(fftpack/event_btlevt_bin_entrydata_add_ent.bin): Agrias, Mustadio, Ramza, the gift box and three townsfolk,
with the same unit ids ReMixed's script uses. So nothing is added to the exe or the ENTD files; the port supplies
what IC removed: the scripts, the text, the trigger and the stub -> scene rule.

Every vanilla world trigger starts a placeholder "stub" event with a confirm prompt, whose battle-event rule
(var 509 == 1) then starts the real scene N+1 (e.g. 464 -> 465, Beowulf's tavern scene on the same map).

Vanilla inputs live in research/vanilla (checked against the installed game's pack CRCs on 2026-09-24).
The exe-side half (the birthday reward) is AgriasBirthday.cs.
"""
import json, os, shutil, sqlite3, struct, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
RES = os.path.join(ROOT, 'research')
BUILD = os.path.join(ROOT, 'build')
OUT = os.path.join(ROOT, 'FFTIVC', 'data', 'enhanced')
FF16TOOLS = r'H:\FFT\win-x64\FF16Tools.CLI.exe'

sys.path.insert(0, os.path.dirname(__file__))
from evdis import disasm
from convert_wotl import convert as convert_wotl, SHEET_TEXTURES
import panel_ui

# Scene-only maps a ported WotL battle is fought on: they get IC's battle surface (tools/panel_ui.py), without which
# the grid never shows and the cursor stays at one height. 45: the chapel ruins battle (532).
# ---- WotL maps IC has only the classic half of ----
# WotL's map 127 (Limberry Castle Inner Court, Argath's battle) is Fort Besselat - South Wall (66) under another name:
# IC's own per-map file lists (exe 0x685450 / 0x685050) already point map 127 at map 66's classic files, and its GNS
# is map 66's. What IC lacks is the HD half (bg/meshes/map_127_mesh.bin, bg/textures/127/, the RefinedBg* rows) and
# a Map row with names. The copy ships map 66's HD half under 127 (mesh header id rewritten; the textures load from
# bg/textures/<map id>/, so they are copied) and gives map 127 its own names. New files are fine for these paths;
# fftpack files could not be added (fftivc.utility.modloader only replaces existing indices), but none are needed.
# map: (source map, title PlaceName (key, text), region PlaceName key, spot PlaceName (key, text))
MAP_COPIES = {127: (66, (11850, 'Limberry Castle Inner Court'), 1050, (33250, 'Inner Court'))}
MAP_COPY_TABLES = ('RefinedBgAnim', 'RefinedBgMeshNode', 'RefinedBgMeshPolygon', 'RefinedBgMeshPolygonCond',
                   'RefinedBgSystemTexture', 'RefinedBgTexture')

# ---- Multi-stage battle chains (IC's continuous battles) a port adds a stage to ----
# ContinuousSortieConfirm (nxd 289) row per stage: the confirm before stage N plays the chain's minimap (a component
# of ui/ffto/battle/ffto_battle_continuous_map.uib, tools/continuous_map.py) from stage N-1's point to stage N's.
# Its timeline keys (ContinuousBattleTimeline): Unknown8 [PointN-1 = blink the next point], Unknown10 [PositionN-1],
# Unknown18 [PositionN], Unknown20 [MoveN], Unknown44 StayN-1, Unknown48 [the PointN node]; Unknown30 / Unknown34 /
# Unknown38 the place (region, spot, [spot]), Unknown68 the stage. A stub's EventId SortieConfirmUnionId '289:<row>'.
# Limberry (MapE): Gate 385 (row 16) -> Keep 390 (17) -> Inner Court 537 (18, was the undercroft's) -> Undercroft
# 395 (new row 26, stage 4).
# row: (template row, as vanilla, {column: value}, [stub events that confirm it])
CONTINUOUS_STAGES = {
    18: (18, {'Unknown34': 33250, 'Unknown38': '[33250]'}, [537]),
    26: (18, {'Unknown8': '[13]', 'Unknown10': '[21]', 'Unknown18': '[22]', 'Unknown20': '[28]', 'Unknown44': 36,
              'Unknown48': '[42]', 'Unknown68': 4}, [395]),
}

PANEL_MAPS = [45]

SOURCE_EVENT = 159               # ReMixed's event number (build/event159.e from convert_event.py)
STUB_EVENT = 578                 # WotL's own Agrias's Birthday records (dormant in IC)
SCENE_EVENT = 579
STUB_RULES_KEY = 163             # record 578's battle-event rules key; no vanilla rows
SORTIE_CONFIRM = '7:139'         # the generic "event" confirm vanilla side scenes use (stub 464's)
SCENARIO_KEY = 9159               # ScenarioId key; also names the text file scenario9159
SCION_FILE_ID = 2165              # ScionFiles key (vanilla max 2164)
TEXT_ID_BASE = 381590             # must match convert_event.py

# Speaker codes (pzd Speaker.Value), from vanilla lines spoken by each character.
SPEAKERS = {0x22: 1030600,        # Mustadio
            0x34: 1030100,        # Agrias
            0x03: 1010103}        # Ramza (chapter 2 onwards)
SYSTEM_SPEAKER = 1                # Speaker table row with no name (5005000 is "Girl", 5005001 "Narration")

# The reward line: ReMixed printed the item through a text variable. The reward is WotL's Tynar Rouge (a WotL item,
# ItemExpansion.cs) plus ReMixed's HP/MP boost; if the expansion cannot arm (a game update), AgriasBirthday.cs gives
# ReMixed's Septieme Sens instead and logs it.
REWARD_LINE = "Received the Tynar Rouge! Agrias's HP and MP increased!"

# ---- War of the Lions items (ItemExpansion.cs, research/ITEM_EXPANSION.md) ----
# Their data is WotL's own (tools/wotl_items.py -> ItemData.g.cs; every item is enabled in ItemExpansion.cs). Here are
# their text rows (Item-*, keyed by item id, build_nxd): a copy of the last vanilla item of the same UI category (so
# IsRandomDamage and the other flags follow it), the item's names, its category, a SortOrder after that category's
# last, and a description: the mod's own flavour sentence, then the effect lines tools/item_text.py writes from the
# item's data (so they always say what it does). The text is the mod's own, not WotL's (English in every language,
# as the rest of the mod). Icons: tools/item_icons.py, staged by WotL id.
# IC id: (name, singular, plural, flavour)
WOTL_ITEMS = {
    # Fell Swords (WotL 0x100-0x104, moved: IC's bonus items hold those ids). Type 0x23, which no IC job equips.
    0x116: ('Chaosbringer', 'Chaosbringer', 'Chaosbringer',
            'A fell sword steeped in darkness, whose blade seems to drink in the light around it.'),
    0x117: ('Deathbringer', 'Deathbringer', 'Deathbringer',
            'A fell sword steeped in darkness. It is said to toll the knell of any foe it wounds.'),
    0x118: ('Arondight', 'Arondight', 'Arondight',
            'The fell sword of a knight who betrayed his liege, its blade tarnished by his sins.'),
    0x119: ('Balmung', 'Balmung', 'Balmung',
            'A fell sword of legend, said to have slain a dragon that once plagued the northern lands.'),
    0x11A: ('Valhalla', 'Valhalla', 'Valhalla',
            'The mightiest of the fell swords, which sends those it strikes to the hall of the fallen.'),
    0x105: ('Moonblade', 'Moonblade', 'Moonblade',
            'A sword whose blade shines with the pale light of the full moon.'),
    0x106: ('Onion Sword', 'onion sword', 'onion swords',
            'A sword of legendary might that only a true Onion Knight can wield.'),
    0x107: ('Ras Algethi', 'Ras Algethi', 'Ras Algethi',
            'A finely crafted pistol favoured by a certain sky pirate, named for a star that shines in the northern '
            'sky.'),
    0x108: ('Fomalhaut', 'Fomalhaut', 'Fomalhaut',
            'A pistol of exquisite make, named for the brightest star of the southern autumn sky.'),
    0x109: ('Francisca', 'francisca', 'franciscas',
            'A throwing axe of antique design, balanced to fly true.'),
    0x10A: ('Golden Axe', 'golden axe', 'golden axes',
            'An axe forged from gold, as heavy as it is dazzling.'),
    0x10B: ('Orochi', 'Orochi', 'Orochi',
            'A ninja blade named for an eight-headed serpent, its edge wreathed in shadow.'),
    0x10C: ('Moonsilk Blade', 'moonsilk blade', 'moonsilk blades',
            'A ninja blade as fine as spun silk, which glints like moonlight.'),
    0x10D: ('Nirvana', 'Nirvana', 'Nirvana',
            'A staff imbued with holy light, said to lead those who wield it to enlightenment.'),
    0x10E: ('Dreamwaker', 'dreamwaker', 'dreamwakers',
            'A staff carved from a tree said to grow where all dreams come to an end.'),
    0x10F: ('Stardust Rod', 'stardust rod', 'stardust rods',
            'A rod whose tip glitters with the dust of fallen stars.'),
    0x110: ('Crown Scepter', 'crown scepter', 'crown scepters',
            'A royal scepter set with jewels, the symbol of a sovereign\'s authority.'),
    0x111: ('Vesper', 'Vesper', 'Vesper',
            'A flail named for the evening star, its spiked head forged from blackened iron.'),
    0x112: ('Sagittarius Bow', 'Sagittarius bow', 'Sagittarius bows',
            'A bow named for the archer among the constellations.'),
    0x113: ('Durandal', 'Durandal', 'Durandal',
            'A knight\'s sword blessed with holy light, said to be impossible to break.'),
    0x114: ('Gae Bolg', 'Gae Bolg', 'Gae Bolg',
            'A barbed spear of legend whose wounds are said never to heal.'),
    0x115: ('Gungnir', 'Gungnir', 'Gungnir',
            'The spear of a god of war, crackling with the power of lightning.'),
    0x120: ('Onion Shield', 'onion shield', 'onion shields',
            'A shield of legendary might that only a true Onion Knight can bear.'),
    0x121: ('Reverie Shield', 'reverie shield', 'reverie shields',
            'A shield that shimmers like a daydream, warding off elemental magicks.'),
    0x124: ('Vanguard Helm', 'vanguard helm', 'vanguard helms',
            'A sturdy helm worn by those who lead the charge into battle.'),
    0x125: ('Onion Helm', 'onion helm', 'onion helms',
            'A helm of legendary might that only a true Onion Knight can wear.'),
    0x126: ('Acacia Hat', 'acacia hat', 'acacia hats',
            'A hat woven from acacia fibres that keeps the mind of its wearer clear.'),
    0x127: ('Brass Coronet', 'brass coronet', 'brass coronets',
            'A simple coronet of brass that sharpens the wearer\'s magickal focus.'),
    0x12C: ('Grand Armor', 'suit of grand armor', 'suits of grand armor',
            'Massive armor forged for the greatest of knights.'),
    0x12D: ('Onion Armor', 'suit of onion armor', 'suits of onion armor',
            'Armor of legendary might that only a true Onion Knight can wear.'),
    0x12E: ('Minerva Bustier', 'Minerva bustier', 'Minerva bustiers',
            'A bustier said to have belonged to a goddess of wisdom, which turns aside the elements.'),
    0x12F: ('Mirage Vest', 'mirage vest', 'mirage vests',
            'A vest woven from threads that bend the light around the one who wears it.'),
    0x130: ('Brave Suit', 'brave suit', 'brave suits',
            'Clothing that fills the one who wears it with courage.'),
    0x131: ("Sage's Robe", "sage's robe", "sage's robes",
            'A robe worn by sages, woven with wards against every element.'),
    0x134: ('Gaius Caligae', 'pair of Gaius caligae', 'pairs of Gaius caligae',
            'Hobnailed sandals once worn by the soldiers of an ancient empire.'),
    0x135: ("Brigand's Gloves", "pair of brigand's gloves", "pairs of brigand's gloves",
            'Gloves favoured by bandits for quick hands and quicker escapes.'),
    0x136: ('Onion Gloves', 'pair of onion gloves', 'pairs of onion gloves',
            'Gloves of legendary might that only a true Onion Knight can wear.'),
    0x137: ('Empyreal Armband', 'empyreal armband', 'empyreal armbands',
            'An armband blessed by the heavens that keeps its wearer\'s steps unhindered.'),
    0x138: ('Tynar Rouge', 'Tynar Rouge', 'Tynar Rouges',
            'A lip rouge made from the petals of the tynar flower, treasured by the noblewomen of Ivalice.'),
    0x139: ("Sage's Ring", "sage's ring", "sage's rings",
            'A ring worn by sages that commands the power of every element.'),
}
# SortOrders already shipped (1.16.0-1.17.0) stay; the rest follow their category's last, in id order.
WOTL_SORT = {0x138: 5505, 0x107: 807, 0x12F: 4016}
FELL_SWORD_CATEGORY = 35      # UIItemCategory row the mod adds (a copy of Knight's Sword, 4): IC's rows stop at 34
ITEM_LANGUAGES = ('en', 'fr', 'de', 'ja')
WOTL_LAST_ITEM = 0x13B                          # ItemSites.MaxItemId: rows 261..this are all shipped (see build_nxd)

# ---- World-map trigger (EnhancedWorldEvent) ----
# ReMixed's block, placed in every town. Type 1: var == v (var in Unknown10), 2: var >= v, 4: character in roster,
# 25: play event [id, mode]. Values are u16; 50000 is stored as the equivalent signed short.
# WotL's trigger (tools/wotl_triggers.py): the twelve towns other than Lionel, Zeltennia and Dorter
TOWNS = (0, 1, 2, 4, 6, 7, 8, 10, 11, 12, 13, 14)
def s16(v): return v - 0x10000 if v >= 0x8000 else v
TRIGGER = [
    (2, [0x6F, 13], 0),           # chapter 4
    (4, [0x1E], 0),               # Agrias
    (1, [0], 0x2F9),              # not seen yet (the scene sets it, and 0xB6)
    (4, [0x16], 0),               # Mustadio
    (2, [0x2C, s16(50000)], 0),   # gil >= 50,000
    (1, [6], 0x2E),               # month 6 ...
    (1, [22], 0x2F),              # ... day 22 = Cancer 1 (WotL: date >= and <= 6/22)
    (4, [0x78], 0),               # Lavian
    (4, [0x79], 0),               # Alicia
    (25, [STUB_EVENT, 2], 0),     # start the stub (-> scene)
]

# ---- War of the Lions scene groups ----
# Each group: its events and stubs (placeholder scripts), a scenario (text file) of its own, speakers by unit, EventId
# rows copied from vanilla ones (+ changes), WotL's battle-event rules (tools/wotl_rules.py) as IC rows
# (type, CharaControlId, UnknownC, Unknown10, Unknown14), and world triggers (town, steps) (tools/wotl_triggers.py).
# Optional: new Speaker rows, a SortieConfirm row copied from a vanilla one (for a battle stub), CharaControlId rows
# (units the rules name), EntryNo values for its battle casts.
WOTL_SCENES = [
    # Delita and Ovelia at Bervenia ("Tietra..."): 535 stub (rules key 153) -> 536 scene, map 126, cast ENTD 518
    # (Ovelia, Delita, Argath's unit id 7 silent). WotL plays it at Bervenia when story var 0x6E == 43 (after the
    # fight with Meliadoul there). It sets 0x2F2 (seen) and unlocks the rumors Rash of Thefts and Lionel's New Liege
    # Lord (WotL vars 0x2E7/0x2EA, renumbered below).
    # WotL stages both parts on its own map 126, which IC ships without an HD background (enhanced maps stop at 116:
    # the scene drew over empty space). Stand-ins: the opening (the setup record's map, patched in Mod.cs _eventRecords)
    # plays on map 20, Zeltennia Castle Keep (Ovelia's home in chapter 4, IC's own Delita/Ovelia scene 429; WotL's
    # first positions are that scene's); the second part (ChangeMap) on map 2, Lesalia Castle Postern, the first
    # Zalmour battle's map, which the user matched to WotL's footage (10x11 tiles: all of WotL's positions fit).
    dict(name='Bervenia', events=[536], stubs=[535], scenario_key=9536, scion_file_id=2167, text_base=382100,
         # title: Caption 1200 = "Zeltennia Castle Keep", as IC's own event 201 shows on map 20 (WotL's ShowMapTitle
         # named its map 126, which IC lacks)
         map_map={126: 2}, title=1200,
         speakers={0x05: 1020102, 0x0C: 1030701, 0x03: 1010103},      # chapter 4 Delita/Ovelia (IC events 376, 429)
         event_ids={535: (464, {}), 536: (465, {'Unknown4': 536})},
         rules={153: [[(1, 0, 509, 0, [1]), (25, 0, 0, 536, [])]]},
         # WotL's trigger: story var 0x6E == 43 exactly (1.9.0-1.22.1 allowed 43 or later for testing)
         triggers=[(13, [(1, [43], 0x6E), (1, [0], 0x2F2), (25, [535, 2], 0)])]),

    # Balthier: 518 stub (rules key 148, Dorter) -> 519 battle start -> [520 Balthier and Ramza talk on Balthier's
    # first turn, 521 Balthier falls -> game over, 522 victory -> next 523] -> 523 stub (rules key 149) -> 524
    # recruitment scene (ENTD 528 has Balthier with the join-after-event flag). Map 32, cast ENTD 514/528. His name,
    # Sky Pirate job, CharShape 0xA2 and portrait are this mod's.
    dict(name='Balthier', events=[519, 520, 521, 522, 524], stubs=[518, 523],
         scenario_key=9518, scion_file_id=2166, text_base=382000,
         speakers={0xA2: 1162000, 0x03: 1010103},
         new_speakers=[(1162000, 'Balthier')],   # vanilla has no Speaker row for him
         sortie=(375, 11),                       # new SortieConfirm row, a copy of vanilla row 11 (the Dorter battle)
         # Battle-rule unit fields (CharaControlId) are keys of the CharaControlId table, whose Unknown8 is the unit id;
         # vanilla has rows 0-52, 100-103, 128-139 and a few specials, none for 0xA2, and a missing row crashes the event
         # setup (RVA 0x2FC2E3 in 0x2FB7C8, table 0xDA).
         chara_control_ids=[0xA2],
         # EntryNo (per ENTD): story battles have [0, N, 0] / [130, 145, 130], N rising through the story (mid chapter 4
         # battles: 5,600-5,900); see ENTD_ADD_FIRST for the rows every WotL cast gets.
         entry_no={514: '[0,5900,0]'},
         # the stub as vanilla Dorter stub 33 (confirm prompt, pointed at the new sortie row), the battle's events
         # tagged with their battle (519) like vanilla 34/35/135, the scene tagged with itself like 465
         event_ids={518: (33, {}), 519: (34, {'Unknown4': 519}), 520: (35, {'Unknown4': 519}),
                    521: (135, {'Unknown4': 519}), 524: (465, {'Unknown4': 524})},
         # vars 0x7D/0x80 are the battle's own scratch flags (520 sets 0x7D)
         rules={148: [[(1, 0, 509, 0, [1]), (25, 0, 0, 519, [])],
                      [(1, 0, 0x7D, 0, [0]), (1, 0, 0x80, 0, [0]), (4, 0xA2, 0, 0, []), (5, 0xA2, 0, 0, [1]),
                       (4, 0x03, 0, 0, []), (5, 0x03, 0, 0, [1]), (11, 0xA2, 0, 0, []), (25, 0, 0, 520, [])],
                      [(1, 0, 0x80, 0, [0]), (4, 0xA2, 0, 0, []), (6, 0xA2, 0, 0, [0]), (25, 0, 0, 521, [])],
                      [(1, 0, 0x80, 0, [0]), (22, 0, 0, 0, []), (25, 0, 0, 522, [])]],
                149: [[(1, 0, 509, 0, [1]), (25, 0, 0, 524, [])]]},
         # WotL's Dorter trigger: chapter 4 (story var 0x6F >= 13), not recruited yet (0x2F0, 524 sets it), and both
         # rumors read (0x2FA: Rash of Thefts at Gollund, 0x2FB: A Call for Guards at Dorter; see RUMORS)
         triggers=[(9, [(2, [0x6F, 13], 0), (1, [0], 0x2F0), (1, [1], 0x2FA), (1, [1], 0x2FB), (25, [518, 1], 0)])]),

    # Luso: 525 stub (rules key 150, Zeklaus Desert) -> 526 battle start ("Protect Luso!") -> [527 Luso falls ->
    # game over, 528 victory -> next 529] -> 529 stub (rules key 151) -> 530 recruitment scene (ENTD 517: Luso with
    # the join-after-event flag, and Ramza as his chapter 3 sprite 0x02). Map 76 (Zeklaus Desert), casts ENTD
    # 515/517. His name, Game Hunter job, CharShape 0xA3 and portrait are this mod's.
    dict(name='Luso', events=[526, 527, 528, 530], stubs=[525, 529],
         scenario_key=9525, scion_file_id=2168, text_base=382200,
         speakers={0xA3: 1163000, 0x02: 1010103},
         new_speakers=[(1163000, 'Luso')],
         sortie=(376, 13),                       # a copy of vanilla row 13, the Zeklaus Desert panel (map 76)
         chara_control_ids=[0xA3],
         # a late chapter 3 battle (vanilla ones around events 249-298: 4,600-6,600)
         entry_no={515: '[0,5700,0]'},
         event_ids={525: (39, {}), 526: (34, {'Unknown4': 526}), 527: (135, {'Unknown4': 526}),
                    530: (465, {'Unknown4': 530})},
         rules={150: [[(1, 0, 509, 0, [1]), (25, 0, 0, 526, [])],
                      [(1, 0, 0x80, 0, [0]), (4, 0xA3, 0, 0, []), (6, 0xA3, 0, 0, [0]), (25, 0, 0, 527, [])],
                      [(1, 0, 0x80, 0, [0]), (22, 0, 0, 0, []), (25, 0, 0, 528, [])]],
                151: [[(1, 0, 509, 0, [1]), (25, 0, 0, 530, [])]]},
         # 526 shows objective 40 (DisplayConditions 0x30 = 8 + 40), a protection mission IC left unnamed; WotL drew
         # its objectives as images, so the name is written here in IC's style ("Protect Argath!")
         objectives={40: 'Protect Luso!'},
         # WotL's trigger: Zeklaus Desert while story var 0x6E == 37 (late chapter 3: events 255-260), not recruited
         # yet (0x2F0 is Balthier's; Luso's is 0x2EF, 530 sets it)
         triggers=[(28, [(1, [37], 0x6E), (1, [0], 0x2EF), (25, [525, 1], 0)])]),

    # Ovelia's prayer at Zeltennia's chapel ruins (an interlude, triggered at Yardrow like IC's own Delita/Ovelia
    # interludes): 531 stub (rules key 152) -> 532 scene and battle start (an assassin's thrown blade grazes Delita;
    # "Protect Ovelia!") -> [533 Ovelia falls -> game over, 534 victory scene, back to the world map]. Map 45
    # (Zeltennia Castle - Chapel Ruins, at night), cast ENTD 516: Delita (player controlled, the only unit you move),
    # Ovelia (guest), two Assassins (ninjas, 0x80/0x81) and the blade prop (sprite set 0xA9, CharShape 169 above).
    # No formation: ENTD 516 keeps the scene-style EntryNo row ([]), as vanilla's prologue battle (ENTD 387, preset
    # units) has, and the stub uses the generic event rows like a scene stub.
    # IC uses map 45 for scenes only, and its HD mesh (bg/meshes/map_045_mesh.bin) had no GT_n_panel_ui
    # object, the battle surface every IC battle map has: the grid never shows and the cursor stays at one height
    # (units move fine, from the classic terrain). 1.15.0 builds one (PANEL_MAPS, tools/panel_ui.py).
    dict(name='ChapelRuins', events=[532, 533, 534], stubs=[531], scenario_key=9531, scion_file_id=2169, text_base=382300,
         # title: Caption 1300 = PlaceName 14500 "Zeltennia Castle - Chapel Ruins", which IC's own events 255 and 300
         # show on map 45
         title=1300,
         # Delita and Ovelia as in IC's event 255 (the chapel ruins, story var 0x6E 37, just before this scene)
         speakers={0x05: 1020101, 0x0C: 1030701, 0x80: 1164000, 0x81: 1164000},
         new_speakers=[(1164000, 'Assassin')],     # WotL's speaker tag; IC has no generic "Assassin" row
         event_ids={531: (464, {}), 532: (34, {'Unknown4': 532}), 533: (135, {'Unknown4': 532})},
         rules={152: [[(1, 0, 509, 0, [1]), (25, 0, 0, 532, [])],
                      [(1, 0, 0x80, 0, [0]), (4, 0x0C, 0, 0, []), (6, 0x0C, 0, 0, [0]), (25, 0, 0, 533, [])],
                      [(1, 0, 0x80, 0, [0]), (22, 0, 0, 0, []), (25, 0, 0, 534, [])]]},
         # 532 shows objective 36 (DisplayConditions 0x2C = 8 + 36), unnamed in IC
         objectives={36: 'Protect Ovelia!'},
         # WotL's trigger: Yardrow while story var 0x6E == 39 (after IC event 270), not seen yet (0x2F1, 534 sets
         # it)
         triggers=[(7, [(1, [39], 0x6E), (1, [0], 0x2F1), (25, [531, 2], 0)])]),

    # Wiegraf mourns Milleuda at her grave; Loffrey recruits him for the Knights Templar. 516 stub (rules key 147) ->
    # 517 scene (sets its seen flag 0x2EE and 0x1AD, one of WotL's own per-scene flags 0x1AB-0x1B8, which IC's
    # scripts never read). Map 77 (Lenalian Plateau), cast ENTD 513. Sheets 0x07, 0x0D, 0x81 (the last two have
    # WotL-only rows, see SHEET_TEXTURES).
    dict(name='LenalianPlateau', events=[517], stubs=[516], scenario_key=9516, scion_file_id=2170, text_base=382400,
         # title: IC has no Caption row for PlaceName 17600 "Lenalian Plateau" (map 77's), so it gets new Caption 1310
         title=1310, captions={1310: 17600},
         # Wiegraf as the Corpse Brigade's leader (IC's chapter 1-2 scenes; 1070101 is the Templar), Loffrey's only row
         speakers={0x20: 1070100, 0x25: 1070700},
         event_ids={516: (464, {}), 517: (465, {'Unknown4': 517})},
         rules={147: [[(1, 0, 509, 0, [1]), (25, 0, 0, 517, [])]]},
         # WotL's trigger: Balias Swale while story var 0x6E == 29 (after IC event 190, chapter 2), not seen yet
         # (0x2EE)
         triggers=[(39, [(1, [29], 0x6E), (1, [0], 0x2EE), (25, [516, 2], 0)])]),

    # Delita and Ovelia at Zeirchele Falls on the road to Zeltennia; Northern Sky scouts attack. 512 stub (rules key
    # 146) -> 513 scene and battle start ("Protect Ovelia!", objective 7, named in IC) -> [514 Ovelia falls -> game
    # over, 515 victory scene, back to the world map]. Map 83 (Zeirchele Falls), cast ENTD 512: Delita (player
    # controlled, the only unit you move), Ovelia (guest), three Northern Sky scouts; no formation, as the chapel ruins.
    # WotL has no world trigger for it: its event 195 (the end of the chapter 2 Lionel Castle chain 191-195, triggered
    # at Lionel Castle while 0x6E == 29) chains straight into 512 (record +0x12 = 512, +0x14 = 0x81, 'play now'), and
    # the interlude ends with CallFunction 06 (on to the event in var 0x55, 196, the Lionel battle). Restored in 1.19.0
    # (user's call after testing the trigger): Mod.cs points IC's record 195 at 512 (0x81) and gives 515 IC's hand-off
    # to 196 (next 196, world-map flag 0x80). 515 sets 0x2ED so the scene plays once; saves already past 195 get it from
    # the Zeirchele Falls trigger.
    dict(name='ZeircheleFalls', events=[513, 514, 515], stubs=[512], scenario_key=9512, scion_file_id=2171, text_base=382500,
         # title: no Caption row for PlaceName 18200 "Zeirchele Falls" (map 83's)
         title=1320, captions={1320: 18200},
         # Delita and Ovelia as in IC's event 190 (scenario 790), the same stretch of chapter 2
         speakers={0x05: 1020101, 0x0C: 1030700, 0x81: 1165000},
         new_speakers=[(1165000, 'Northern Sky Scout')],   # WotL's speaker tag; IC has Northern Sky Knight/Captain only
         event_ids={512: (464, {}), 513: (34, {'Unknown4': 513}), 514: (135, {'Unknown4': 513})},
         rules={146: [[(1, 0, 509, 0, [1]), (25, 0, 0, 513, [])],
                      [(1, 0, 0x80, 0, [0]), (6, 0x0C, 0, 0, [0]), (25, 0, 0, 514, [])],
                      [(1, 0, 0x80, 0, [0]), (22, 0, 0, 0, []), (25, 0, 0, 515, [])]]},
         set_flags={515: [0x2ED]},
         # Reached only through 195, as in WotL (no world trigger; 1.19.0-1.22.0 had a fallback for saves past 195)
         triggers=[]),

    # Argath, reborn as a Deathknight, bars the way to the Limberry Castle undercroft as Ramza chases Alma. 537 stub
    # (rules key 154) -> 538 scene and battle start ("Defeat Argath!") -> [539/540 Argath and Ramza trade words on
    # their turns, 541 Argath at low HP, 542 Argath falls: victory scene, back to the world map]. Cast ENTD 519: Argath
    # (unit and job 0xA5, the Deathknight; name, job, CharShape and portrait are this mod's) and five undead (0x81-0x85)
    # against Ramza's party (formation). 542 also sets var 0x3CC (Argath's story stage: IC events 25/58/117 set 1-3,
    # 542 sets 4; nothing in IC's data or exe reads it).
    # WotL's linkage: the Limberry sequence 385-394 (triggered at Limberry Castle, 0x6E == 49) ended at 394 with var
    # 0x55 = 537 + CallFunction 06, so Argath's battle came right after the keep (390-394) and before the undercroft
    # (395); 542 then set 0x55 = 395. IC's 394 goes straight to 395 (record next 395 + 0x80, inside IC's continuous
    # battle sequence). Restored in IC's form (1.22.0, Mod.cs _eventRecords): 394's next is 537 and 542's is 395, and
    # the chain's minimap gets the Inner Court as its third stage (CONTINUOUS_STAGES, tools/continuous_map.py). 537 is
    # a continuous-battle stub like 395 (EventId copied from it: ContinuousSortieConfirm row 18, now the Inner Court's).
    # Reached only through 394, as in WotL (no world trigger; before 1.22.1 a Limberry Castle fallback for saves
    # past 394).
    # Map: WotL's own map 127 (MAP_COPIES). No location title in these scripts.
    dict(name='LimberryArgath', events=[538, 539, 540, 541, 542], stubs=[537], scenario_key=9537, scion_file_id=2172,
         text_base=382600,
         speakers={0xA5: 1100400, 0x03: 1010103, 0x84: 1166000},
         new_speakers=[(1166000, 'Mysterious Voice')],   # WotL's tag for Argath's first, unseen line (unit 0x84)
         chara_control_ids=[0xA5],
         # between the keep (ENTD 456: 5,900) and the undercroft (457: 8,000)
         entry_no={519: '[0,7000,0]'},
         event_ids={537: (395, {}), 538: (34, {'Unknown4': 538}), 539: (35, {'Unknown4': 538}),
                    540: (35, {'Unknown4': 538}), 541: (35, {'Unknown4': 538})},
         # vars 0x7D-0x80 are the battle's scratch flags
         rules={154: [[(1, 0, 509, 0, [1]), (25, 0, 0, 538, [])],
                      [(1, 0, 0x7D, 0, [0]), (1, 0, 0x80, 0, [0]), (4, 0xA5, 0, 0, []), (5, 0xA5, 0, 0, [1]),
                       (4, 0x03, 0, 0, []), (5, 0x03, 0, 0, [1]), (11, 0x03, 0, 0, []), (25, 0, 0, 539, [])],
                      [(1, 0, 0x7D, 0, [1]), (1, 0, 0x7E, 0, [0]), (1, 0, 0x80, 0, [0]), (4, 0xA5, 0, 0, []),
                       (5, 0xA5, 0, 0, [1]), (4, 0x03, 0, 0, []), (5, 0x03, 0, 0, [1]), (11, 0xA5, 0, 0, []),
                       (25, 0, 0, 540, [])],
                      [(1, 0, 0x80, 0, [0]), (1, 0, 0x7F, 0, [0]), (4, 0xA5, 0, 0, []), (8, 0xA5, 0, 0, [20]),
                       (5, 0xA5, 0, 0, [1]), (25, 0, 0, 541, [])],
                      [(1, 0, 0x80, 0, [0]), (4, 0xA5, 0, 0, []), (6, 0xA5, 0, 0, [0]), (25, 0, 0, 542, [])]]},
         # 538 shows objective 37 (DisplayConditions 0x2D = 8 + 37), unnamed in IC ("Defeat Argath!" is row 3)
         objectives={37: 'Defeat Argath!'},
         triggers=[]),

    # Cletienne and Meliadoul at Dorter ("So, the marquis has fallen."): 543 stub (rules key 155) -> 544 scene and
    # battle start (Cletienne's time magick stops Ramza; Meliadoul confronts him; "Defeat Cletienne!", objective 19,
    # named in IC) -> [545 Meliadoul and Cletienne talk on her turn, 546 Meliadoul falls -> game over, 547 Cletienne
    # at 20% HP flees: victory scene, back to the world map]. Map 31 (Dorter, Balthier's battle map), cast ENTD 520:
    # Cletienne, five mages and Meliadoul from the party (level 254 = the roster's); a party formation with Ramza and
    # Meliadoul warped in, the other members revealed later (units 0x78-0x7C). 547 sets 0x2F3 (seen) and 0x3EB = 1
    # (as IC's own event 457 does; IC's scripts only write it).
    dict(name='DorterCletienne', events=[544, 545, 546, 547], stubs=[543], scenario_key=9543, scion_file_id=2173,
         text_base=382700,
         # Meliadoul as an ally (IC's later chapter 4 scenes, with Cletienne's only row)
         speakers={0x27: 1070500, 0x2A: 1070201, 0x03: 1010103},
         sortie=(378, 11),                       # a copy of the Dorter story battle's row (map 31)
         entry_no={520: '[0,7100,0]'},            # as IC event 443's cast (ENTD 460), the same stretch of chapter 4
         event_ids={543: (33, {}), 544: (34, {'Unknown4': 544}), 545: (35, {'Unknown4': 544}),
                    546: (135, {'Unknown4': 544})},
         rules={155: [[(1, 0, 509, 0, [1]), (25, 0, 0, 544, [])],
                      [(1, 0, 0x7D, 0, [0]), (1, 0, 0x80, 0, [0]), (4, 0x2A, 0, 0, []), (5, 0x2A, 0, 0, [1]),
                       (4, 0x27, 0, 0, []), (5, 0x27, 0, 0, [1]), (11, 0x2A, 0, 0, []), (25, 0, 0, 545, [])],
                      [(1, 0, 0x80, 0, [0]), (4, 0x2A, 0, 0, []), (6, 0x2A, 0, 0, [0]), (25, 0, 0, 546, [])],
                      [(1, 0, 0x80, 0, [0]), (4, 0x27, 0, 0, []), (8, 0x27, 0, 0, [20]), (25, 0, 0, 547, [])]]},
         # WotL's trigger: Dorter while story var 0x6E == 51 (IC event 430), not seen (0x2F3), Meliadoul (0x2A) in the
         # party
         triggers=[(9, [(1, [51], 0x6E), (1, [0], 0x2F3), (4, [0x2A], 0), (25, [543, 1], 0)])]),

    # Agrias visits Ovelia at Zeltennia ("My lady."): she tells Ovelia she must go on with Ramza, entrusts her to
    # Delita and gives her a knife. Two versions of one scene (same text block): 550 stub (rules key 157) -> 551, with
    # Lavian and Alicia (units 0x81/0x82; "Lavian, Alicia! With me!"), when both are in the party; otherwise 548 stub
    # (rules key 156) -> 549. Map 45 (Zeltennia Castle - Chapel Ruins, at night; scene only), cast ENTD 521. Both set
    # 0x2F4 (seen), 0x2E9 (WotL's unlock for the rumor Disorder in the Order, renumbered by RUMOR_VARS; not restored
    # yet) and a WotL per-scene flag (0x1B0 / 0x1B1).
    dict(name='ZeltenniaAgrias', events=[549, 551], stubs=[548, 550], scenario_key=9548, scion_file_id=2174,
         text_base=382800,
         # chapter 4 Ovelia and Delita as in the Bervenia scene (IC events 376, 429), Agrias as in the birthday
         speakers={0x0C: 1030701, 0x06: 1020102, 0x34: 1030100},
         # WotL's speaker tags for lines spoken off screen: 1 Agrias ("My lady."), 10 Delita
         message_speakers={1: 5002100, 10: 1167000},
         new_speakers=[(1167000, "Delita's Voice")],   # IC has "Familiar Voice" but no "Delita's Voice"
         event_ids={548: (464, {}), 549: (465, {'Unknown4': 549}), 550: (464, {}), 551: (465, {'Unknown4': 551})},
         rules={156: [[(1, 0, 509, 0, [1]), (25, 0, 0, 549, [])]],
                157: [[(1, 0, 509, 0, [1]), (25, 0, 0, 551, [])]]},
         # WotL's triggers at Zeltennia Castle: chapter 4 (0x6F >= 16), Agrias (0x1E) in the party, not seen (0x2F4);
         # the Lavian (0x78) and Alicia (0x79) version first
         triggers=[(5, [(2, [0x6F, 16], 0), (4, [0x1E], 0), (1, [0], 0x2F4), (4, [0x78], 0), (4, [0x79], 0),
                        (25, [550, 2], 0)]),
                   (5, [(2, [0x6F, 16], 0), (4, [0x1E], 0), (1, [0], 0x2F4), (25, [548, 2], 0)])]),
    # Beowulf and Reis against Celebrant Bremondt (552-569), four stages chained by their records (+0x12 next event,
    # +0x14 0x80 = world map, then play it; 0x81 = play it now), as WotL does (WotL also set var 0x55 and called
    # CallFunction 06, which the converter drops):
    #   552 stub (rules 158) -> 553 Lionel's fields (map 115): Aliste abducts Reis. Sets 0x2F7 (in progress).
    #     Record 553: next 554, 0x80.
    #   554 stub (rules 159) -> 555 Lionel Castle Gate battle (map 12, ENTD 523: Aliste 0xA6, four knights and a mage;
    #     Beowulf from the party; formation) -> [556/557 Aliste and Beowulf talk, 558 Aliste at 20% HP, 559 Beowulf
    #     falls -> game over, 560 Aliste falls: victory]. Record 560 went on to 561 only through 0x55 in WotL, so
    #     Mod.cs _eventRecords adds next 561.
    #   561 stub (rules 160) -> 562 Lionel Castle Oratory battle (map 13, ENTD 524: Bremondt 0xA7, six ninjas and
    #     mystics, his dragon form 0xA8, his body 0xA6) -> [563/564 talk, 565 Bremondt at 20% HP turns into the Dark
    #     Dragon, 566 the dragon falls: victory, record next 568 0x81; 567 game over].
    #   568 stub (rules 161) -> 569 Reis rescued (map 11). Clears the rumor Lionel's New Liege Lord (WotL 0x2EA, i.e.
    #     IC rumor 26), sets character stages 0x3D2 = 1, 0x3D5 = 2, 0x3D6 = 3, 0x3D8 = 3 (IC's 467/483/489 set 0x3D6 and
    #     0x3D8 to 1-2), 0x1B6/0x1B7, 0x2F7 = 0, 0x2F8 = 1 (done).
    # Three groups because unit 0xA6 is Aliste in the fields and at the gate but Bremondt's body in the oratory.
    # Units 0xA6-0xA8 are this mod's (jobs Templar/Celebrant/Dark Dragon 166-168, CharShapes, portraits).
    dict(name='LionelFields', events=[553], stubs=[552], scenario_key=9552, scion_file_id=2175, text_base=382900,
         speakers={0x0F: 1120200, 0x1F: 1120100, 0xA6: 1168000},
         new_speakers=[(1168000, 'Aliste'), (1169000, 'Celebrant Bremondt'), (1170000, 'Ninja')],
         event_ids={552: (464, {}), 553: (465, {'Unknown4': 553})},
         rules={158: [[(1, 0, 509, 0, [1]), (25, 0, 0, 553, [])]]},
         # WotL's trigger at Lionel Castle: chapter 4 (0x6F >= 16), Beowulf's quest done (0xAC), the rumor Lionel's New
         # Liege Lord read (0x2FD), not done yet (0x2F8), Beowulf (0x1F) and Reis (0x0F) in the party
         triggers=[(3, [(2, [0x6F, 16], 0), (1, [1], 0xAC), (1, [1], 0x2FD), (1, [0], 0x2F8), (4, [0x1F], 0),
                        (4, [0x0F], 0), (25, [552, 2], 0)])]),
    dict(name='LionelGate', events=[555, 556, 557, 558, 559, 560], stubs=[554], scenario_key=9554, scion_file_id=2176,
         text_base=383000,
         speakers={0x1F: 1120100, 0xA6: 1168000, 0x03: 1010103},
         chara_control_ids=[0xA6, 0xA7, 0xA8],
         entry_no={523: '[0,8000,0]', 524: '[0,8300,0]'},   # late chapter 4 (IC ENTD 457: 8,000, 459: 8,300)
         # 554 and 561 confirm as IC's Lionel Castle chain does (191 -> 196): its minimap (MapD, Start -> Gate ->
         # Oratory) and continuous confirm rows 1 and 2 ("Battle at Lionel Castle", the gate and oratory names)
         event_ids={554: (191, {}), 555: (34, {'Unknown4': 555}), 556: (35, {'Unknown4': 555}),
                    557: (35, {'Unknown4': 555}), 558: (35, {'Unknown4': 555}), 559: (135, {'Unknown4': 555})},
         rules={159: [[(1, 0, 509, 0, [1]), (25, 0, 0, 555, [])],
                      [(1, 0, 0x7D, 0, [0]), (1, 0, 0x80, 0, [0]), (4, 0xA6, 0, 0, []), (5, 0xA6, 0, 0, [1]),
                       (4, 0x1F, 0, 0, []), (5, 0x1F, 0, 0, [1]), (11, 0x1F, 0, 0, []), (25, 0, 0, 556, [])],
                      [(1, 0, 0x7D, 0, [1]), (1, 0, 0x7E, 0, [0]), (1, 0, 0x80, 0, [0]), (4, 0xA6, 0, 0, []),
                       (5, 0xA6, 0, 0, [1]), (4, 0x1F, 0, 0, []), (5, 0x1F, 0, 0, [1]), (11, 0xA6, 0, 0, []),
                       (25, 0, 0, 557, [])],
                      [(1, 0, 0x7F, 0, [0]), (1, 0, 0x80, 0, [0]), (4, 0xA6, 0, 0, []), (8, 0xA6, 0, 0, [20]),
                       (4, 0x1F, 0, 0, []), (5, 0x1F, 0, 0, [1]), (25, 0, 0, 558, [])],
                      [(1, 0, 0x80, 0, [0]), (4, 0x1F, 0, 0, []), (6, 0x1F, 0, 0, [0]), (25, 0, 0, 559, [])],
                      [(1, 0, 0x7F, 0, [1]), (1, 0, 0x80, 0, [0]), (4, 0xA6, 0, 0, []), (6, 0xA6, 0, 0, [0]),
                       (25, 0, 0, 560, [])]]},
         objectives={38: 'Defeat Aliste!'},      # 555: DisplayConditions 0x2E = 8 + 38
         triggers=[]),
    dict(name='LionelOratory', events=[562, 563, 564, 565, 566, 567, 569], stubs=[561, 568], scenario_key=9561,
         scion_file_id=2177, text_base=383100,
         speakers={0x81: 1170000, 0xA7: 1169000, 0xA8: 1169000, 0xA6: 1169000, 0x1F: 1120100, 0x0F: 1120200,
                   0x03: 1010103},
         event_ids={561: (196, {}), 562: (34, {'Unknown4': 562}), 563: (35, {'Unknown4': 562}),
                    564: (35, {'Unknown4': 562}), 565: (35, {'Unknown4': 562}), 567: (135, {'Unknown4': 562}),
                    568: (464, {}), 569: (465, {'Unknown4': 569})},
         rules={160: [[(1, 0, 509, 0, [1]), (25, 0, 0, 562, [])],
                      [(1, 0, 0x7D, 0, [0]), (1, 0, 0x80, 0, [0]), (4, 0xA7, 0, 0, []), (5, 0xA7, 0, 0, [1]),
                       (4, 0x1F, 0, 0, []), (5, 0x1F, 0, 0, [1]), (11, 0x1F, 0, 0, []), (25, 0, 0, 563, [])],
                      [(1, 0, 0x7D, 0, [1]), (1, 0, 0x7E, 0, [0]), (1, 0, 0x80, 0, [0]), (4, 0xA7, 0, 0, []),
                       (5, 0xA7, 0, 0, [1]), (4, 0x1F, 0, 0, []), (5, 0x1F, 0, 0, [1]), (11, 0xA7, 0, 0, []),
                       (25, 0, 0, 564, [])],
                      [(1, 0, 0x7F, 0, [0]), (1, 0, 0x80, 0, [0]), (4, 0xA7, 0, 0, []), (8, 0xA7, 0, 0, [20]),
                       (25, 0, 0, 565, [])],
                      [(1, 0, 0x7F, 0, [1]), (1, 0, 0x80, 0, [0]), (4, 0xA8, 0, 0, []), (6, 0xA8, 0, 0, [0]),
                       (25, 0, 0, 566, [])]],
                161: [[(1, 0, 509, 0, [1]), (25, 0, 0, 569, [])]]},
         objectives={39: 'Defeat Celebrant Bremondt!'},   # 562: DisplayConditions 0x2F = 8 + 39
         triggers=[]),
    # Agrias and Orlandeau against Northern Sky deserters at the Brigands' Den: 570 stub (rules key 162) -> 571 scene
    # and battle start (the deserters plan to sack a village; "Defeat all enemies!", objective 0) -> [572-575 talk on
    # turns: the deserters recognise the Thunder God, Ramza and Agrias rebuke them, Orlandeau (575 sets 0x81), 576
    # victory with Agrias standing, 577 victory otherwise; both back to the world map]. Map 91 (Brigands' Den), cast
    # ENTD 526: six deserters and Agrias from the party (level 254); a party formation. Both victories set 0x2F6 (done)
    # and clear WotL's unlock of Disorder in the Order (0x2E9, i.e. IC rumor 25's 0x2EA), whose read flag 0x2FC the
    # trigger needs.
    dict(name='BrigandsDen', events=[571, 572, 573, 574, 575, 576, 577], stubs=[570], scenario_key=9570,
         scion_file_id=2178, text_base=383200,
         speakers={0x80: 1171000, 0x81: 1171000, 0x82: 1171000, 0x84: 1171000, 0x03: 1010103, 0x1E: 1030100,
                   0x0D: 1030200},
         new_speakers=[(1171000, 'Northern Sky Deserter')],   # IC has "Southern Sky Deserter" only
         sortie=(381, 16),                        # a copy of vanilla's Brigands' Den row (map 91)
         entry_no={526: '[0,8000,0]'},            # late chapter 4 (IC ENTD 457: 8,000)
         event_ids={570: (33, {}), 571: (34, {'Unknown4': 571}), 572: (35, {'Unknown4': 571}),
                    573: (35, {'Unknown4': 571}), 574: (35, {'Unknown4': 571}), 575: (35, {'Unknown4': 571})},
         # vars 0x7D-0x81 are the battle's scratch flags; units 0x80/0x82 (deserters), 0x0D Orlandeau, 0x1E Agrias
         rules={162: [[(1, 0, 509, 0, [1]), (25, 0, 0, 571, [])],
                      [(1, 0, 0x7D, 0, [0]), (1, 0, 0x80, 0, [0]), (4, 0x80, 0, 0, []), (5, 0x80, 0, 0, [1]),
                       (4, 0x82, 0, 0, []), (5, 0x82, 0, 0, [1]), (4, 0x0D, 0, 0, []), (5, 0x0D, 0, 0, [1]),
                       (11, 0x82, 0, 0, []), (25, 0, 0, 572, [])],
                      [(1, 0, 0x7E, 0, [0]), (1, 0, 0x80, 0, [0]), (4, 0x80, 0, 0, []), (5, 0x80, 0, 0, [1]),
                       (4, 0x03, 0, 0, []), (5, 0x03, 0, 0, [1]), (11, 0x03, 0, 0, []), (25, 0, 0, 573, [])],
                      [(1, 0, 0x7E, 0, [1]), (1, 0, 0x7F, 0, [0]), (1, 0, 0x80, 0, [0]), (4, 0x80, 0, 0, []),
                       (5, 0x80, 0, 0, [1]), (4, 0x1E, 0, 0, []), (11, 0x1E, 0, 0, []), (4, 0x03, 0, 0, []),
                       (5, 0x03, 0, 0, [1]), (25, 0, 0, 574, [])],
                      [(1, 0, 0x7F, 0, [1]), (1, 0, 0x80, 0, [0]), (1, 0, 0x81, 0, [0]), (4, 0x0D, 0, 0, []),
                       (5, 0x0D, 0, 0, [1]), (11, 0x0D, 0, 0, []), (25, 0, 0, 575, [])],
                      [(1, 0, 0x80, 0, [0]), (4, 0x03, 0, 0, []), (4, 0x1E, 0, 0, []), (22, 0, 0, 0, []),
                       (25, 0, 0, 576, [])],
                      [(1, 0, 0x80, 0, [0]), (4, 0x03, 0, 0, []), (22, 0, 0, 0, []), (25, 0, 0, 577, [])]]},
         # WotL's trigger at the Brigands' Den: chapter 4 (0x6F >= 16), Agrias (0x1E) in the party, not done (0x2F6),
         # the rumor Disorder in the Order read (0x2FC)
         triggers=[(17, [(2, [0x6F, 16], 0), (4, [0x1E], 0), (1, [0], 0x2F6), (1, [1], 0x2FC), (25, [570, 1], 0)])]),
    # Gariland tavern gossip (WotL's advert for its PSP multiplayer modes): two patrons puzzle over "Melee" and
    # "Rendezvous" on the menu, and the tavernmaster invites Ramza to try them. 580 stub (rules key 164) -> 581 scene
    # (map 96, the tavern, as Agrias's Birthday; ENTD 529), sets 0x2FE (seen). IC has neither mode, so the scene is
    # built but NOT triggered (user's call, 2026-09-25): WotL's trigger is kept in triggers_disabled, ready for
    # whoever restores those modes (move it to triggers).
    dict(name='GarilandGossip', events=[581], stubs=[580], scenario_key=9580, scion_file_id=2179, text_base=383300,
         speakers={0x86: 2120500, 0x85: 2120600, 0x80: 1900700},   # IC's Tavern Patron rows and Tavernmaster
         event_ids={580: (464, {}), 581: (465, {'Unknown4': 581})},
         rules={164: [[(1, 0, 509, 0, [1]), (25, 0, 0, 581, [])]]},
         triggers=[],
         # WotL's: Gariland (6), not seen (0x2FE), story var 0x6E >= 3 (early chapter 1)
         triggers_disabled=[(6, [(1, [0], 0x2FE), (2, [0x6E, 3], 0), (25, [580, 2], 0)])]),
]
for g in WOTL_SCENES:
    for key in ('new_speakers', 'chara_control_ids'): g.setdefault(key, [])
    for key in ('entry_no', 'objectives', 'captions'): g.setdefault(key, {})
    g.setdefault('sortie', None)
ENTD_ADD_FIRST, ENTD_ADD_COUNT = 512, 80   # WotL casts: fftpack event_btlevt_bin_entrydata_add_ent.bin, 80 x 0x280

# ---- Tavern rumors (Gossip) ----
# IC's Gossip rows 0-21 are WotL's rumors 0-21; IC dropped WotL's 22-25 and used 22 for its own "At Battle's End".
# The table is read as a plain array (use_base_row_id), so restored rumors take the next ids, 23 on. A rumor is listed
# in a tavern when the town's bit (0x4000 >> town) is set in the exe's mask table (RVA 0x7BE620, patched by
# _rumorTowns in Mod.cs) and its unlock var 0x2D1 + id is set (availability check 0x36F53C). WotL's unlock vars are
# 0x2D1 + WotL id, so they are renumbered to IC's ids everywhere they appear (RUMOR_VARS, applied to the converted
# scripts and to the rumors' own actions). Reading a rumor advances sidequest counter Unknown4 to stage Unknown8 (IC
# event opcode E9 sets the same counters; 0 is the main story, the Beowulf line is 2) and, only when that raises it,
# runs its actions. Text and actions come from research/wotl_rumors.json (tools/wotl_rumors.py).
# A rumor with a counter shows a picture above its text (IconId -> icon/base/base_NN, the town art; Town.Unknown1C
# gives each town's), as IC's own quest rumors The Haunted Mine (base_11, Gollund) and The Cursed Isle do: the read
# actions need the counter, so these use their town's art too. (1.4.1 used counter 3, which IC's event 461 sets to 10:
# that silently blocked the rumors on a save that had seen it.)
# Counters: IC's quest counters are 12 dwords (0-11; the setter 0xFF660 writes [obj + 0x18 + 4n], and a byte flag
# bank follows at +0x48), so 1.4.3-1.11.0's counter 12 wrote past them into flag bytes 0-3. IC's scripts use 0-3, its
# rumors 0 and 2, its UserSituation checks 0-3: the restored rumors use 4 (the Rash / Call pair, in order), 5 and 6
# (independent rumors need their own counters: reading one at a higher stage would skip the other's actions).
# Towns are WotL's masks, patched in Mod.cs (_rumorTowns); icon = a town's art (Town.Unknown1C).
RUMORS = [
    dict(ic=23, wotl=22, counter=4, stage=10, icon=11),   # Rash of Thefts (Gollund art): sets 0x2FA, unlocks A Call for Guards
    dict(ic=24, wotl=23, counter=4, stage=20, icon=14),   # A Call for Guards (Dorter): sets 0x2FB (Balthier's trigger)
    dict(ic=25, wotl=24, counter=5, stage=10, icon=10),   # Disorder in the Order (Eagrose): sets 0x2FC (the deserters' trigger)
    dict(ic=26, wotl=25, counter=6, stage=10, icon=9),    # Lionel's New Liege Lord (Lionel): sets 0x2FD (Beowulf and Reis's)
]
RUMOR_UNLOCK_BASE = 0x2D1
RUMOR_VARS = {RUMOR_UNLOCK_BASE + w: RUMOR_UNLOCK_BASE + w + 1 for w in range(22, 26)}   # WotL 22-25 -> IC 23-26

def run(*args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0 or 'Error' in r.stdout or 'Exception' in r.stdout:
        raise SystemExit('command failed: %s\n%s%s' % (' '.join(args), r.stdout, r.stderr))


def build_script():
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'convert_event.py')], check=True)
    dst = os.path.join(OUT, 'script', 'enhanced')
    os.makedirs(dst, exist_ok=True)
    shutil.copyfile(os.path.join(BUILD, 'event%03d.e' % SOURCE_EVENT), os.path.join(dst, 'event%03d.e' % SCENE_EVENT))
    # the stub is the same placeholder every vanilla stub uses
    shutil.copyfile(os.path.join(RES, 'vanilla', 'script', 'event000.e'), os.path.join(dst, 'event%03d.e' % STUB_EVENT))
    for g in WOTL_SCENES:
        for e in g['events']:
            shutil.copyfile(os.path.join(BUILD, 'wotl', 'event%03d.e' % e), os.path.join(dst, 'event%03d.e' % e))
        for e in g['stubs']:
            shutil.copyfile(os.path.join(RES, 'vanilla', 'script', 'event000.e'), os.path.join(dst, 'event%03d.e' % e))


def speakers_by_message():
    """Speaking unit per message: DisplayMessage names it; ChangeDialog reuses its box's last speaker
    (box 1 = the last type-0x91 message, box 2 = the last type-0x92 one)."""
    table = open(os.path.join(RES, 'evlen_enh.bin'), 'rb').read()
    script = open(os.path.join(BUILD, 'event%03d.e' % SOURCE_EVENT), 'rb').read()
    last = {}; out = {}
    for _, op, a in disasm(script, table):
        if op == 0x10:
            msg = struct.unpack_from('<I', a, 2)[0] - TEXT_ID_BASE
            out[msg] = a[6]
            if a[1] in (0x91, 0x92): last[a[1] & 0x0F] = a[6]
        elif op == 0x51:
            msg = struct.unpack_from('<I', a, 1)[0]
            if msg != 0xFFFFFFFF: out[msg - TEXT_ID_BASE] = last[a[0]]
    return out


def yaml_str(s):
    return "'" + s.replace("'", "''") + "'"


def build_text():
    lines = json.load(open(os.path.join(BUILD, 'event%03d_text.json' % SOURCE_EVENT), encoding='utf-8'))
    units = speakers_by_message()
    entries = []
    for l in lines:
        if l['msg'] == max(x['msg'] for x in lines):
            text, speaker = REWARD_LINE, SYSTEM_SPEAKER
        else:
            text = ' '.join(l['text'].replace('{Ramza}', 'Ramza').split())
            speaker = SPEAKERS[units[l['msg']]]
        entries.append((l['id'], text, speaker))
    write_pzd(SCENARIO_KEY, entries)


def write_pzd(scenario_key, entries):
    """entries: (text id, line, speaker code)"""
    yml = os.path.join(BUILD, 'scenario%04d.en.yaml' % scenario_key)
    open(yml, 'w', encoding='utf-8').write(''.join(
        '- Id: %d\n  Line: %s\n  Speaker:\n    Type: 24\n    Value: %d\n'
        "  VoiceSoundPath: ''\n  ShowType: Normal\n  ShortVoiceSoundPath: ''\n  IsShortened: false\n"
        % (tid, yaml_str(text), speaker) for tid, text, speaker in entries))
    run(FF16TOOLS, 'pzd-conv', '-i', yml)
    dst = os.path.join(OUT, 'nxd', 'text', 'scenario', 'scenario%04d.en.pzd' % scenario_key)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(yml[:-5] + '.pzd', dst)


def build_wotl():
    """Converts the WotL groups' scripts (into build/wotl) and writes their text; returns the event sprite sheets
    they load."""
    sheets = set()
    for g in WOTL_SCENES:
        lines, used = convert_wotl(g['events'], g['text_base'], RUMOR_VARS, g.get('map_map'), g.get('tile_map'),
                                   g.get('title'), g.get('set_flags'))
        # speakers by unit, or by WotL message number where a line is not its box unit's (an unseen voice)
        write_pzd(g['scenario_key'], [(l['id'], l['text'], g.get('message_speakers', {}).get(l['msg'], g['speakers'][l['unit']]))
                                      for l in lines])
        sheets |= used
    return sheets


def rumor_actions(pairs):
    """WotL rumor action pairs -> IC Gossip (Unknown14, Unknown1C), with rumor unlock vars renumbered."""
    sets, base = [], 0
    for typ, value in pairs:
        if typ == 102: base = value * 10
        else: sets.append((RUMOR_VARS.get(typ + base, typ + base), value))
    types, values = [], []
    for var, value in sets:
        types += [102, var % 10]; values += [var // 10, value]
    return types, values


def build_nxd():
    db = os.path.join(BUILD, 'nxd.sqlite')
    if os.path.exists(db): os.remove(db)
    # vanilla tables, except CharShape: the mod's own (vanilla + its WotL character rows)
    src = os.path.join(BUILD, 'nxd_in')
    shutil.rmtree(src, ignore_errors=True)
    shutil.copytree(os.path.join(RES, 'vanilla', 'nxd'), src)
    shutil.copyfile(os.path.join(OUT, 'nxd', 'charshape.nxd'), os.path.join(src, 'charshape.nxd'))
    run(FF16TOOLS, 'nxd-to-sqlite', '-i', src, '-o', db, '-g', 'fft')
    c = sqlite3.connect(db)

    c.execute('INSERT INTO ScionFiles (Key, DLCFlags, File) VALUES (?, 0, ?)',
              (SCION_FILE_ID, 'nxd/text/scenario/scenario%04d.pzd' % SCENARIO_KEY))
    c.execute('INSERT INTO ScenarioId (Key, DLCFlags, EventIds, UnknownC) VALUES (?, 0, ?, ?)',
              (SCENARIO_KEY, '[%d]' % SCENE_EVENT, SCION_FILE_ID))

    # Event flags copied from the vanilla map-96 pair: stub 464 (confirm prompt) and scene 465 (Unknown4 = itself)
    cols = [r[1] for r in c.execute('PRAGMA table_info(EventId)') if r[1] != 'Key']
    def copy_event(src, dst, **changes):
        row = dict(zip(cols, c.execute('SELECT %s FROM EventId WHERE Key = ?' % ', '.join('"%s"' % k for k in cols), (src,)).fetchone()))
        row.update(changes)
        c.execute('UPDATE EventId SET %s WHERE Key = ?' % ', '.join('"%s" = ?' % k for k in row), (*row.values(), dst))
    copy_event(464, STUB_EVENT, SortieConfirmUnionId=SORTIE_CONFIRM)
    copy_event(465, SCENE_EVENT, Unknown4=SCENE_EVENT)

    # Stub rule, as vanilla 464's: var 509 == 1 -> start the scene
    ebe_cols = [r[1] for r in c.execute('PRAGMA table_info(EnhancedBattleEvent)')]
    def ebe(key3, typ, **fields):
        row = {k: 0 for k in ebe_cols}; row.update(Key=STUB_RULES_KEY, Key2=0, Key3=key3, UnkType4=typ, Unknown14='[]', Comment=None)
        row.update(fields)
        c.execute('INSERT INTO EnhancedBattleEvent (%s) VALUES (%s)' % (', '.join('"%s"' % k for k in row), ', '.join('?' * len(row))), tuple(row.values()))
    ebe(0, 1, UnknownC=509, Unknown14='[1]')
    ebe(1, 25, Unknown10=SCENE_EVENT)

    # The gift box is WotL sprite set 0xA9 (unit_psp/spr_dst_bchr_sword_m_spr.bin, a PSP-only prop sheet IC ships),
    # but vanilla CharShape (render parameters per sprite set, table 174) stops at 0x9E, and a missing row crashes the
    # scene (v0.3.0, RVA 0x217172). (0x9F-0xA8 are added by this mod.) 0xA9 uses the humanoid frame
    # layout (SHP/SEQ type 0), so it gets vanilla 0x83's row: humanoid, smallest shadow, no special palette.
    shape_cols = [r[1] for r in c.execute('PRAGMA table_info(CharShape)') if r[1] != 'Key']
    shape = c.execute('SELECT %s FROM CharShape WHERE Key = 131' % ', '.join('"%s"' % k for k in shape_cols)).fetchone()
    c.execute('DELETE FROM CharShape WHERE Key = 169')   # the input is the mod's own table, which may have it already
    c.execute('INSERT INTO CharShape (Key, %s) VALUES (169, %s)' % (', '.join('"%s"' % k for k in shape_cols), ', '.join('?' * len(shape_cols))), shape)

    def world_block(town, steps):
        block = c.execute('SELECT MAX(Key2) FROM EnhancedWorldEvent WHERE Key = ?', (town,)).fetchone()[0] + 1
        for step, (typ, values, var) in enumerate(steps):
            c.execute('INSERT INTO EnhancedWorldEvent (Key, Key2, Key3, DLCFlags, Type, Unknown8, Unknown10, '
                      'Unknown14, Unknown18, Unknown1C) VALUES (?, ?, ?, 0, ?, ?, ?, 47, 47, 0)',
                      (town, block, step, typ, json.dumps(values, separators=(',', ':')), var))
    for town in TOWNS:
        world_block(town, TRIGGER)

    # ---- WotL scene groups ----
    sc_cols = ', '.join('"%s"' % r[1] for r in c.execute('PRAGMA table_info(SortieConfirm)') if r[1] != 'Key')
    for g in WOTL_SCENES:
        c.execute('INSERT INTO ScionFiles (Key, DLCFlags, File) VALUES (?, 0, ?)',
                  (g['scion_file_id'], 'nxd/text/scenario/scenario%04d.pzd' % g['scenario_key']))
        c.execute('INSERT INTO ScenarioId (Key, DLCFlags, EventIds, UnknownC) VALUES (?, 0, ?, ?)',
                  (g['scenario_key'], json.dumps(g['events'], separators=(',', ':')), g['scion_file_id']))
        for row in g['new_speakers']:
            c.execute('INSERT INTO "Speaker-en" (Key, DLCFlags, Name) VALUES (?, 0, ?)', row)
        for unit in g['chara_control_ids']:
            c.execute('INSERT INTO CharaControlId (Key, DLCFlags, Comment, Unknown8) VALUES (?, 0, NULL, ?)', (unit, unit))
        for key, place in g['captions'].items():     # Caption (nxd 13) is keyed sparsely: new keys are safe
            c.execute('INSERT INTO Caption (Key, DLCFlags, Comment, UnionId) VALUES (?, 0, NULL, ?)', (key, '113:%d' % place))
        for key, name in g['objectives'].items():   # rows 35-68 exist, unnamed
            assert c.execute('UPDATE "BattleObjective-en" SET Name = ? WHERE Key = ? AND Name IS NULL', (name, key)).rowcount == 1

        if g['sortie']:
            key, src = g['sortie'][:2]
            c.execute('INSERT INTO SortieConfirm (Key, %s) SELECT ?, %s FROM SortieConfirm WHERE Key = ?' % (sc_cols, sc_cols),
                      (key, src))
            for col, value in (g['sortie'][2] if len(g['sortie']) > 2 else {}).items():
                c.execute('UPDATE SortieConfirm SET "%s" = ? WHERE Key = ?' % col, (value, key))
        for dst_event, (src_event, changes) in g['event_ids'].items():
            if dst_event in g['stubs'] and g['sortie']: changes = dict(changes, SortieConfirmUnionId='7:%d' % g['sortie'][0])
            copy_event(src_event, dst_event, **changes)
        for key, blocks in g['rules'].items():
            for block, steps in enumerate(blocks):
                for step, (typ, unit, var, event, values) in enumerate(steps):
                    row = {k: 0 for k in ebe_cols}
                    row.update(Key=key, Key2=block, Key3=step, UnkType4=typ, CharaControlId=unit, UnknownC=var,
                               Unknown10=event, Unknown14=json.dumps(values, separators=(',', ':')), Comment=None)
                    c.execute('INSERT INTO EnhancedBattleEvent (%s) VALUES (%s)' % (', '.join('"%s"' % k for k in row),
                              ', '.join('?' * len(row))), tuple(row.values()))
        for town, steps in g['triggers']:
            world_block(town, steps)

    # EntryNo (per ENTD, nxd table 0x6D) has rows only for vanilla ENTDs 0-511, and a battle whose cast has none
    # crashes while loading (RVA 0xFB6C8). The game reads it as a plain array (row = key - first key, bounded by the
    # row count), so keys must stay contiguous: every WotL cast (512-591) gets a row, a scene row unless a group gives
    # battle values ([] / [130, 130, 130] as vanilla 330, Beowulf's tavern).
    battles = {k: v for g in WOTL_SCENES for k, v in g['entry_no'].items()}
    for entd in range(ENTD_ADD_FIRST, ENTD_ADD_FIRST + ENTD_ADD_COUNT):
        first = battles.get(entd, '[]')
        c.execute('INSERT INTO EntryNo (Key, DLCFlags, Comment, SortieConfirmId, UnknownC, Unknown14) VALUES (?, 0, NULL, 0, ?, ?)',
                  (entd, first, '[130,145,130]' if first != '[]' else '[130,130,130]'))

    # ---- battle surfaces ----
    # The game marks a map's panel object in RefinedBgMeshNode (per map, arrangement Key2, object Key3): IC's panel
    # nodes have Unknown16 = 1 (82 of its 85 panels; with UnknownC = -100, a draw bias). Without the row a generated
    # panel is loaded but never used (1.15.1 test: the cursor stayed at one height). Values: map 76's panel node 13.
    node_cols = [r[1] for r in c.execute('PRAGMA table_info(RefinedBgMeshNode)')]
    template = dict(zip(node_cols, c.execute('SELECT * FROM RefinedBgMeshNode WHERE Key = 76 AND Key2 = 0 AND Key3 = 13').fetchone()))
    assert template['Unknown16'] == 1
    for mapno in PANEL_MAPS:
        panel_node = len(panel_ui.read(os.path.join(panel_ui.GAME, 'bg', 'meshes', 'map_%03d_mesh.bin' % mapno))['names'])
        for (key2,) in c.execute('SELECT DISTINCT Key2 FROM RefinedBgMeshNode WHERE Key = ?', (mapno,)).fetchall():
            assert not c.execute('SELECT 1 FROM RefinedBgMeshNode WHERE Key = ? AND Key2 = ? AND Key3 = ?', (mapno, key2, panel_node)).fetchone()
            row = dict(template, Key=mapno, Key2=key2, Key3=panel_node)
            c.execute('INSERT INTO RefinedBgMeshNode (%s) VALUES (%s)' % (', '.join('"%s"' % k for k in row), ', '.join('?' * len(row))),
                      tuple(row.values()))

    # ---- rumors ----
    wotl_rumors = json.load(open(os.path.join(RES, 'wotl_rumors.json'), encoding='utf-8'))
    for r in RUMORS:
        w = wotl_rumors[r['wotl']]
        types, values = rumor_actions(w['actions'])
        c.execute('INSERT INTO "Gossip-en" (Key, DLCFlags, Unknown4, Unknown8, Title, Text, Unknown14, Unknown1C, '
                  'UserSituationID, IconId, UnkBool2C) VALUES (?, 0, ?, ?, ?, ?, ?, ?, 0, ?, 0)',
                  (r['ic'], r['counter'], r['stage'], w['title'], w['text'], json.dumps(types, separators=(',', ':')),
                   json.dumps(values, separators=(',', ':')), r['icon']))
    # ---- multi-stage battle chains (CONTINUOUS_STAGES) ----
    csc_cols = [r[1] for r in c.execute('PRAGMA table_info(ContinuousSortieConfirm)')]
    templates = {t: c.execute('SELECT * FROM ContinuousSortieConfirm WHERE Key = ?', (t,)).fetchone()   # vanilla rows
                 for t, _, _ in CONTINUOUS_STAGES.values()}
    for key, (template, changes, stubs) in CONTINUOUS_STAGES.items():
        row = dict(zip(csc_cols, templates[template]))
        row.update(changes, Key=key)
        c.execute('DELETE FROM ContinuousSortieConfirm WHERE Key = ?', (key,))
        c.execute('INSERT INTO ContinuousSortieConfirm (%s) VALUES (%s)' % (', '.join('"%s"' % k for k in row), ', '.join('?' * len(row))),
                  tuple(row.values()))
        for event in stubs:
            assert c.execute('UPDATE EventId SET SortieConfirmUnionId = ? WHERE Key = ?', ('289:%d' % key, event)).rowcount == 1

    # ---- WotL maps copied from IC ones (MAP_COPIES) ----
    for mapno, (source, (title_key, title), region, (spot_key, spot)) in MAP_COPIES.items():
        for table in MAP_COPY_TABLES:
            cols = [r[1] for r in c.execute('PRAGMA table_info(%s)' % table)]
            assert not c.execute('SELECT 1 FROM %s WHERE Key = ?' % table, (mapno,)).fetchone(), (table, mapno)
            for row in c.execute('SELECT * FROM %s WHERE Key = ?' % table, (source,)).fetchall():
                row = dict(zip(cols, row), Key=mapno)
                c.execute('INSERT INTO %s (%s) VALUES (%s)' % (table, ', '.join('"%s"' % k for k in row), ', '.join('?' * len(row))),
                          tuple(row.values()))
        src = dict(zip([r[1] for r in c.execute('PRAGMA table_info(Map)')], c.execute('SELECT * FROM Map WHERE Key = ?', (source,)).fetchone()))
        # Map: Unknown8 = the title (battle start, formation), UnknownC + Unknown10 = the save entry (region, spot)
        c.execute('UPDATE Map SET Unknown8 = ?, UnknownC = ?, Unknown10 = ?, Unknown14 = ?, Unknown1C = ? WHERE Key = ?',
                  (title_key, region, spot_key, src['Unknown14'], src['Unknown1C'], mapno))
        for lang in ITEM_LANGUAGES:
            table = '"PlaceName-%s"' % lang
            for key, text in ((title_key, title), (spot_key, spot)):
                assert not c.execute('SELECT 1 FROM %s WHERE Key = ?' % table, (key,)).fetchone(), (table, key)
                c.execute('INSERT INTO %s (Key, DLCFlags, Comment, PlaceNameId, Title, Unknown10) VALUES (?, 0, NULL, 0, ?, NULL)'
                          % table, (key, text))

    # ---- WotL items' text rows ----
    # Item is a base-row-id table (Nex layout use_base_row_id): the game finds a row by its position from the first
    # key, so the rows past vanilla's last (260) must be contiguous. 1.16.0 shipped only row 312 (the Tynar Rouge),
    # which sat at position 261 and was never found (no name, description or icon). Every id from 261 to the last
    # WotL item gets a row: the enabled items their own, the rest a blank one like vanilla's unused 254.
    for lang in ITEM_LANGUAGES:
        table = '"Item-%s"' % lang
        cols = [r[1] for r in c.execute('PRAGMA table_info(%s)' % table)]
        last = c.execute('SELECT MAX(Key) FROM %s' % table).fetchone()[0]
        assert last == 260, 'vanilla %s ends at %d' % (table, last)
        blank = dict(zip(cols, c.execute('SELECT * FROM %s WHERE Key = 254' % table).fetchone()))
        for item_id in range(last + 1, WOTL_LAST_ITEM + 1):
            if item_id in WOTL_ITEMS: continue
            c.execute('INSERT INTO %s (%s) VALUES (%s)' % (table, ', '.join('"%s"' % k for k in blank), ', '.join('?' * len(blank))),
                      tuple(dict(blank, Key=item_id).values()))
    sys.path.insert(0, os.path.join(ROOT, 'tools')); import item_text
    wotl = {it['ic_id']: it for it in item_text.items()}
    assert set(WOTL_ITEMS) == set(wotl), sorted(set(wotl) ^ set(WOTL_ITEMS))
    for lang in ITEM_LANGUAGES:
        # The Fell Sword category: a copy of Knight's Sword's row (UIItemCategory is base-row-id: 35 follows 34)
        table = '"UIItemCategory-%s"' % lang
        cols = [r[1] for r in c.execute('PRAGMA table_info(%s)' % table)]
        assert c.execute('SELECT MAX(Key) FROM %s' % table).fetchone()[0] == FELL_SWORD_CATEGORY - 1
        row = dict(zip(cols, c.execute('SELECT * FROM %s WHERE Key = 4' % table).fetchone()), Key=FELL_SWORD_CATEGORY,
                   Name='Fell Sword', Comment=None)
        c.execute('INSERT INTO %s (%s) VALUES (%s)' % (table, ', '.join('"%s"' % k for k in row), ', '.join('?' * len(row))),
                  tuple(row.values()))

        table = '"Item-%s"' % lang
        cols = [r[1] for r in c.execute('PRAGMA table_info(%s)' % table)]
        sorts = {}
        for item_id in sorted(WOTL_ITEMS):
            name, singular, plural, flavour = WOTL_ITEMS[item_id]
            it = wotl[item_id]
            item_type = bytes.fromhex(it['common'])[5]
            category = FELL_SWORD_CATEGORY if item_type == 0x23 else item_type    # UI categories are item types
            like = 4 if category == FELL_SWORD_CATEGORY else category
            # the category's last plain item: magic guns (Blaze Gun, Blaster) set IsRandomDamage, plain guns do not;
            # axes and flails have only random ones, so theirs is kept
            template = (c.execute('SELECT MAX(Key) FROM %s WHERE UiItemCategoryId = ? AND Key < 256 AND IsRandomDamage = 0'
                                  % table, (like,)).fetchone()[0] or
                        c.execute('SELECT MAX(Key) FROM %s WHERE UiItemCategoryId = ? AND Key < 256' % table, (like,)).fetchone()[0])
            if item_id in WOTL_SORT:
                sort = WOTL_SORT[item_id]
            else:
                last = c.execute('SELECT MAX(SortOrder) FROM %s WHERE UiItemCategoryId = ?' % table, (like,)).fetchone()[0]
                sort = max([last] + [v for k, v in sorts.items() if k == category] + [WOTL_SORT[k] for k in WOTL_SORT
                           if k in wotl and (FELL_SWORD_CATEGORY if bytes.fromhex(wotl[k]['common'])[5] == 0x23 else
                                             bytes.fromhex(wotl[k]['common'])[5]) == category]) + 1
            sorts[category] = sort
            row = dict(zip(cols, c.execute('SELECT * FROM %s WHERE Key = ?' % table, (template,)).fetchone()))
            row.update(Key=item_id, Name=name, NameSingular=singular, NamePlural=plural, Name2=name, Comment=None,
                       Description='\n'.join([flavour] + item_text.effects(it)), UiItemCategoryId=category, SortOrder=sort)
            clash = c.execute('SELECT Key FROM %s WHERE SortOrder = ? AND UiItemCategoryId = ? AND Key != ?' % table,
                              (sort, category, item_id)).fetchone()
            assert clash is None, ('SortOrder %d already used by item %d' % (sort, clash[0]))
            c.execute('DELETE FROM %s WHERE Key = ?' % table, (item_id,))
            c.execute('INSERT INTO %s (%s) VALUES (%s)' % (table, ', '.join('"%s"' % k for k in row), ', '.join('?' * len(row))),
                      tuple(row.values()))

    c.commit(); c.close()

    dst = os.path.join(OUT, 'nxd')
    os.makedirs(dst, exist_ok=True)
    run(FF16TOOLS, 'sqlite-to-nxd', '-i', db, '-o', dst, '-g', 'fft',
        '-t', 'EnhancedWorldEvent', 'EnhancedBattleEvent', 'ScenarioId', 'ScionFiles', 'EventId', 'CharShape',
        'Speaker-en', 'SortieConfirm', 'CharaControlId', 'EntryNo', 'Gossip-en', 'BattleObjective-en', 'Caption', 'RefinedBgMeshNode',
        *('Item-%s' % lang for lang in ITEM_LANGUAGES), *('UIItemCategory-%s' % lang for lang in ITEM_LANGUAGES),
        'Map', *('PlaceName-%s' % lang for lang in ITEM_LANGUAGES), *(t for t in MAP_COPY_TABLES if t != 'RefinedBgMeshNode'),
        'ContinuousSortieConfirm')


def build_art(sheets):
    """Enhanced-mode textures for the WotL event sprite sheets the scenes load: 0x8E (the birthday poses) plus the
    ones the WotL conversions report; see research/art/README.md."""
    dst = os.path.join(OUT, 'system', 'ffto', 'g2d')
    os.makedirs(dst, exist_ok=True)
    for sheet in sorted(({0x8E} | set(sheets)) & set(SHEET_TEXTURES)):   # vanilla sheets have their textures
        name = 'tex_%d.bin' % SHEET_TEXTURES[sheet]
        shutil.copyfile(os.path.join(RES, 'art', name), os.path.join(dst, name))


if __name__ == '__main__':
    os.makedirs(BUILD, exist_ok=True)
    sheets = build_wotl(); build_script(); build_text(); build_nxd(); build_art(sheets)
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'panel_ui.py')] + [str(m) for m in PANEL_MAPS], check=True)
    for mapno, (source, *_) in MAP_COPIES.items():             # HD half of the copied maps (see MAP_COPIES)
        mesh = bytearray(open(os.path.join(panel_ui.GAME, 'bg', 'meshes', 'map_%03d_mesh.bin' % source), 'rb').read())
        assert mesh[:8] == b'FFTOMESH' and struct.unpack_from('<I', mesh, 8)[0] == source
        struct.pack_into('<I', mesh, 8, mapno)
        os.makedirs(os.path.join(OUT, 'bg', 'meshes'), exist_ok=True)
        open(os.path.join(OUT, 'bg', 'meshes', 'map_%03d_mesh.bin' % mapno), 'wb').write(mesh)
        dst = os.path.join(OUT, 'bg', 'textures', '%03d' % mapno)
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(os.path.join(panel_ui.GAME, 'bg', 'textures', '%03d' % source), dst)
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'continuous_map.py')], check=True)   # CONTINUOUS_STAGES' minimaps
    sys.path.insert(0, os.path.join(ROOT, 'tools')); import item_icons
    import item_text
    item_icons.install(OUT, {it['wotl_id']: it['ic_id'] for it in item_text.items() if it['ic_id'] in WOTL_ITEMS})
    print('built', OUT)
