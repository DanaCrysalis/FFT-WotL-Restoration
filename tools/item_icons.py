"""War of the Lions item icons for IC, from Spikedrose's Mobile set (used with permission).

  python tools/item_icons.py          converts H:/FFT/WotL Sprites/Items/Mobile/WOTL_<id>.png into research/art/items

IC's enhanced item icons are one texture per item, numbered by item id:
  ui/ffto/icon/equip_item/texture/ei_NNN_uitx.tex       large, 100x100 (IC's are painted HD art)
  ui/ffto/icon/equip_item_s/texture/ei_s_NNN_uitx.tex   small, 48x48 pixel art, like the Mobile set
each with a textureparts/*.utexpt naming the texture's path. Both are BC7 (DXGI 98), single mip.
The Mobile icons are 48x48: the small texture uses them as they are, the large one scales them 2x (nearest
neighbour, pixel art stays sharp) and centres them on 100x100.

The icons are staged by WotL id (research/art/items/{large,small}/wotl_<id>.tex, names in items.json) and
install() writes them under the item's IC id (ItemExpansion.cs): its WotL id, except the five Fell Swords
(WotL 0x100-0x104, which IC's bonus items hold), which move to 0x116-0x11A. tools/build_data.py installs the
enabled items' icons (WOTL_ITEMS).
Conversion: tools/png2bc7 (BCnEncoder, the library fftivc.utility.modloader ships) -> BC7 DDS, then
FF16Tools img-conv -> .tex.
"""
import json, os, shutil, subprocess, sys
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
SRC = r'H:/FFT/WotL Sprites/Items'
ART = os.path.join(ROOT, 'research', 'art', 'items')
TEMPLATES = os.path.join(ROOT, 'research', 'vanilla', 'ui')
FF16TOOLS = r'H:\FFT\win-x64\FF16Tools.CLI.exe'
PNG2BC7 = os.path.join(HERE, 'png2bc7', 'bin', 'png2bc7.exe')
LARGE, SMALL = 100, 48

def run(*args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0 or '[Error]' in r.stdout:
        raise SystemExit('command failed: %s\n%s%s' % (' '.join(args), r.stdout, r.stderr))

def to_tex(png, tex):
    """PNG -> BC7 .tex at tex."""
    dds = tex[:-4] + '.dds'
    run(PNG2BC7, png, dds)
    run(FF16TOOLS, 'img-conv', '-i', dds)
    os.remove(dds)

def convert():
    if not os.path.exists(PNG2BC7):
        run('dotnet', 'build', os.path.join(HERE, 'png2bc7', 'png2bc7.csproj'), '-c', 'Release', '-o', os.path.dirname(PNG2BC7))
    names = {}
    for line in open(os.path.join(SRC, 'WOTL Items.txt'), encoding='utf-8'):
        if line.strip():
            hid, name = line.strip().split(' ', 1); names[int(hid, 16)] = name
    for size in ('large', 'small'): os.makedirs(os.path.join(ART, size), exist_ok=True)
    tmp = os.path.join(ROOT, 'build', 'item_icons'); os.makedirs(tmp, exist_ok=True)
    for item, name in sorted(names.items()):
        icon = Image.open(os.path.join(SRC, 'Mobile', 'WOTL_%X.png' % item)).convert('RGBA')
        assert icon.size == (SMALL, SMALL), (item, icon.size)
        big = Image.new('RGBA', (LARGE, LARGE), (0, 0, 0, 0))
        big.alpha_composite(icon.resize((SMALL * 2, SMALL * 2), Image.NEAREST), ((LARGE - SMALL * 2) // 2,) * 2)
        for size, im in (('small', icon), ('large', big)):
            png = os.path.join(tmp, '%s_%x.png' % (size, item)); im.save(png)
            tex = os.path.join(ART, size, 'wotl_%x.tex' % item)
            shutil.copyfile(png, tex[:-4] + '.png')
            to_tex(tex[:-4] + '.png', tex)
            os.remove(tex[:-4] + '.png')
        print('%X %s' % (item, name))
    json.dump({'%X' % k: v for k, v in sorted(names.items())}, open(os.path.join(ART, 'items.json'), 'w', encoding='utf-8'), indent=1)

def texture_parts(template, old, new):
    """A .utexpt naming a different texture: the template's path string, renamed (same length: 3-digit ids)."""
    data = open(template, 'rb').read()
    assert len(old) == len(new) and data.count(old.encode()) == 1
    return data.replace(old.encode(), new.encode())

def install(out, icons):
    """icons: {WotL item id: IC icon number}. Writes both sizes (+ parts) under out (FFTIVC/data/enhanced)."""
    for item, n in icons.items():
        for size, folder, stem in (('large', 'equip_item', 'ei_%03d_uitx'), ('small', 'equip_item_s', 'ei_s_%03d_uitx')):
            base = os.path.join(out, 'ui', 'ffto', 'icon', folder)
            os.makedirs(os.path.join(base, 'texture'), exist_ok=True); os.makedirs(os.path.join(base, 'textureparts'), exist_ok=True)
            shutil.copyfile(os.path.join(ART, size, 'wotl_%x.tex' % item), os.path.join(base, 'texture', stem % n + '.tex'))
            open(os.path.join(base, 'textureparts', stem % n + '.utexpt'), 'wb').write(
                texture_parts(os.path.join(TEMPLATES, stem % 0 + '.utexpt'), stem % 0, stem % n))

if __name__ == '__main__':
    convert()
