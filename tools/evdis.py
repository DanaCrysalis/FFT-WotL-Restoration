"""Disassemble an FFT event script.

  python tools/evdis.py <file.e> [enh|classic|remixed]      IC .e script
  python tools/evdis.py TEST.EVT:<n> remixed                PSX TEST.EVT event n
  python tools/evdis.py TEST_wotl.EVT:<n> wotl              War of the Lions TEST.EVT event n (0x2800 records)

Length tables live in research/: evlen_enh.bin (IC enhanced), evlen_ic.bin (IC exe table,
classic scripts), evlen_clean.bin (vanilla PSX), evlen_remixed.bin (ReMixed).
"""
import os, struct, sys
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'research')
TABLES = {'enh': 'evlen_enh.bin', 'classic': 'evlen_ic.bin', 'psx': 'evlen_clean.bin', 'remixed': 'evlen_remixed.bin',
          'wotl': 'evlen_ic.bin'}
NAMES={0x10:'DisplayMessage',0x11:'UnitAnim',0x13:'ChangeMapBeta',0x16:'Pause',0x18:'Effect',0x19:'Camera',0x1A:'MapDarkness',0x1B:'MapLight',0x1C:'EventSpeed',0x1D:'CameraFusionStart',0x1E:'CameraFusionEnd',0x1F:'Focus',0x21:'SoundEffect',0x22:'SwitchTrack',0x27:'ReloadMapState',0x28:'WalkTo',0x29:'WaitWalk',0x2A:'BlockStart',0x2B:'BlockEnd',0x2C:'FaceUnit2',0x2D:'RotateUnit',0x2E:'Background',0x31:'ColorBGBeta',0x32:'ColorUnit',0x33:'ColorField',0x38:'FocusSpeed',0x3B:'SpriteMove',0x3C:'Weather',0x3D:'RemoveUnit',0x3E:'ColorScreen',0x41:'EarthquakeStart',0x42:'EarthquakeEnd',0x43:'CallFunction',0x44:'Draw',0x45:'AddUnit',0x46:'Erase',0x47:'AddGhostUnit',0x48:'WaitAddUnit',0x49:'AddUnitStart',0x4A:'AddUnitEnd',0x4B:'WaitAddUnitEnd',0x4C:'ChangeMap',0x4D:'Reveal',0x4E:'UnitShadow',0x50:'PortraitCol',0x51:'ChangeDialog',0x53:'FaceUnit',0x54:'Use3DObject',0x55:'UseFieldObject',0x56:'Wait3DObject',0x57:'WaitFieldObject',0x58:'LoadEVTCHR',0x59:'SaveEVTCHR',0x5A:'SaveEVTCHRClear',0x5B:'LoadEVTCHRClear',0x5F:'WarpUnit',0x60:'FadeSound',0x63:'CameraSpeedCurve',0x64:'WaitRotateUnit',0x65:'WaitRotateAll',0x68:'MirrorSprite',0x69:'FaceTile',0x6A:'EditBGSound',0x6B:'BGSound',0x6E:'SpriteMoveBeta',0x6F:'WaitSpriteMove',0x70:'Jump',0x76:'DarkScreen',0x77:'RemoveDarkScreen',0x78:'DisplayConditions',0x79:'WalkToAnim',0x7A:'DismissUnit',0x7D:'ShowGraphic',0x7E:'WaitValue',0x7F:'EVTCHRPalette',0x80:'March',0x83:'ChangeStats',0x84:'PlayTune',0x85:'UnlockDate',0x86:'TempWeapon',0x87:'Arrow',0x88:'MapUnfreeze',0x89:'MapFreeze',0x8A:'EffectStart',0x8B:'EffectEnd',0x8C:'UnitAnimRotate',0x8E:'WaitGraphicPrint',0x91:'ShowMapTitle',0x92:'InflictStatus',0x94:'TeleportOut',0x96:'AppendMapState',0x97:'ResetPalette',0x98:'TeleportIn',0x99:'BlueRemoveUnit',0xB0:'ADD',0xB1:'ADDVar',0xB2:'SUB',0xB3:'SUBVar',0xB4:'MULT',0xB5:'MULTVar',0xB6:'DIV',0xB7:'DIVVar',0xB8:'MOD',0xB9:'MODVar',0xBA:'AND',0xBB:'ANDVar',0xBC:'OR',0xBD:'ORVar',0xBE:'ZERO',0xD0:'JumpForwardIfZero',0xD1:'JumpForward',0xD2:'ForwardTarget',0xD3:'JumpBack',0xD5:'BackTarget',0xDB:'EventEnd',0xE3:'EventEnd2',0xE5:'WaitForInstruction',0xF1:'Wait',0xF2:'Pad'}

def disasm(sc, table):
    out, i = [], 0
    while i < len(sc):
        op = sc[i]; n = table[op]
        out.append((i, op, sc[i + 1:i + 1 + n])); i += 1 + n
        if op == 0xDB: break
    return out

if __name__ == '__main__':
    src, kind = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else 'enh')
    table = open(os.path.join(RES, TABLES[kind]), 'rb').read()
    if ':' in os.path.basename(src):
        path, n = src.rsplit(':', 1); n = int(n, 0)
        size = 0x2800 if kind == 'wotl' else 0x2000
        ev = open(path, 'rb').read()[n * size:(n + 1) * size]
        data = ev[4:struct.unpack_from('<I', ev, 0)[0]]
    else:
        data = open(src, 'rb').read()
    for off, op, a in disasm(data, table):
        print('%04x  %02X %-20s %s' % (off, op, NAMES.get(op, '?'), a.hex(' ')))
