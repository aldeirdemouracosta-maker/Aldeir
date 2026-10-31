"""Fatia os sheets do Ginzu/Kojiro e recolore os quadros de movimento do Ginzu com a paleta do Kojiro.
Uso: python3 build_frames.py   (precisa de Pillow e numpy)"""
import json, os
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
KOJIRO_BG, GINZU_BG = (0, 248, 248), (0, 0, 248)

# Paleta de 15 cores do Kojiro (+1 transparente = 16 cores, o limite de um palette de sprite CPS-1)
PALETTE = [(32,32,32),(64,0,0),(96,0,0),(136,0,0),(168,0,0),(200,80,0),(232,112,0),(136,64,48),
           (184,96,64),(232,136,0),(232,152,0),(248,152,0),(248,168,0),(248,232,0),(248,248,248)]

# Mapa Ginzu -> Kojiro (cores quase iguais, +-1, sao tratadas como a mesma)
MAP = {
 (44,62,96):(64,0,0),(79,96,137):(96,0,0),(113,137,169):(136,0,0),(153,170,201):(168,0,0),
 (185,201,233):(200,80,0),(217,233,248):(232,112,0),(48,64,96):(64,0,0),(80,96,136):(96,0,0),
 (112,136,168):(136,0,0),(152,168,200):(168,0,0),(184,200,232):(200,80,0),(216,232,248):(232,112,0),
 (96,113,153):(96,0,0),(137,62,44):(136,64,48),
 (248,248,248):(248,248,248),(248,248,79):(248,232,0),(248,248,80):(248,232,0),(248,216,16):(248,232,0),
 (26,26,26):(32,32,32),(32,32,32):(32,32,32),(8,8,8):(32,32,32),(0,0,0):(32,32,32),
 (248,185,0):(248,168,0),(248,184,0):(248,168,0),(233,185,0):(248,168,0),
 (233,137,0):(232,136,0),(232,136,0):(232,136,0),(217,137,0):(232,136,0),
 (200,96,0):(200,80,0),(170,96,0):(200,80,0),
 (201,79,44):(184,96,64),(200,80,48):(184,96,64),(153,44,26):(136,64,48),(152,48,32):(136,64,48),
 (170,0,0):(168,0,0),(248,153,96):(232,152,0),(248,152,96):(232,152,0),(248,201,153):(248,168,0),(248,200,152):(248,168,0),
}
def recolor(img):
    a = np.array(img.convert('RGBA')); out = a.copy()
    pal = np.array(PALETTE)
    for y in range(a.shape[0]):
        for x in range(a.shape[1]):
            r,g,b,al = a[y,x]
            if al == 0: continue
            c = (int(r),int(g),int(b))
            if c in MAP: n = MAP[c]
            else: n = tuple(pal[((pal-np.array(c))**2).sum(1).argmin()])
            out[y,x,:3] = n
    return Image.fromarray(out)

def crop(sheet, box, bg):
    c = sheet.crop(tuple(box)).convert('RGBA'); a = np.array(c)
    a[np.all(a[:,:,:3]==bg,axis=2),3] = 0
    return Image.fromarray(a)

if __name__ == '__main__':
    S = HERE
    kb = json.load(open(os.path.join(S,'kojiro_boxes.json'))); gb = json.load(open(os.path.join(S,'ginzu_boxes.json')))
    ks = Image.open(os.path.join(HERE,'kojiro_sheet.png')).convert('RGB'); gs = Image.open(os.path.join(HERE,'ginzu_sheet.png')).convert('RGB')
    # --- Kojiro original ---
    K = {'idle':[0,1,2],'run_original_walk':[7,8,9,10,11,12],'jump_flip':[13,14,5,6,15,16],
         'hurt':[17,18,19,20],'knockdown_getup':[21,22,23,24,25,26,27,28,30,31],
         'punch_jab':[32,33],'punch_cross':[34,35],'punch_hook':[36,37],'kick_low':[38,39],'kick_mid':[40,41],'kick_high':[42,43],
         'grabbed':[29],'dead_lying':[49,50,51,52,53]}
    d = os.path.join(HERE,'frames','kojiro_original'); os.makedirs(d,exist_ok=True)
    for cat,ids in K.items():
        for n,i in enumerate(ids): crop(ks,kb[i],KOJIRO_BG).save(os.path.join(d,f'{cat}_{n:02d}.png'))
    # --- Ginzu recolorido (movimentacao, sem katana) ---
    G = {'idle':[0,1,2],'walk':list(range(5,16)),'run':list(range(17,23)),
         'jump':[38,39,40,41,42,43,44],'jump_roll':[27,28,29,30],
         'jump_attack':[93,94,95,96,97,98],'flip_kick':[99,101,102,103,104],
         'grab_punch':[107,108,109,110,111]}
    d = os.path.join(HERE,'frames','kojiro_movimento_ginzu'); os.makedirs(d,exist_ok=True)
    gb[98][2] = 416  # o quadro 98 vem colado no rotulo 'Jumping attacks'
    for cat,ids in G.items():
        for n,i in enumerate(ids): recolor(crop(gs,gb[i],GINZU_BG)).save(os.path.join(d,f'{cat}_{n:02d}.png'))
