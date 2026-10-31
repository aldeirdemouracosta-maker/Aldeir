"""Gera o retrato de selecao do Kojiro a partir do retrato do Ginzu (sem a katana, paleta vermelha)
e a plaquinha de nome/vida.  Uso: python3 build_portrait.py"""
import os, numpy as np
from PIL import Image
from collections import deque
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'portrait'); os.makedirs(OUT, exist_ok=True)
gs = Image.open(os.path.join(HERE,'ginzu_sheet.png')).convert('RGB')
ks = Image.open(os.path.join(HERE,'kojiro_sheet.png')).convert('RGB')

BG_NEW = (0, 56, 152)            # fundo azul-escuro: o Kojiro e vermelho, o fundo vermelho do Ginzu sumiria
MAP = {
 (8,8,8):(64,0,0),(44,62,96):(96,0,0),(96,113,153):(136,0,0),(153,170,201):(200,80,0),(185,201,233):(232,112,0),
 (233,233,248):(248,168,0),(248,248,248):(248,232,0),(217,137,0):(232,136,0),(233,185,0):(248,168,0),
 (137,62,44):(136,64,48),(170,96,0):(200,80,0),(248,248,113):(248,232,0),(201,137,79):(184,96,64),
 (248,185,113):(232,152,0),(248,217,169):(248,168,0),(137,79,62):(136,64,48),(233,185,44):(248,168,0),(137,0,0):(136,0,0),
}
BLUE = {(44,62,96),(96,113,153),(153,170,201),(185,201,233),(233,233,248),(248,248,248)}

p = np.array(gs.crop((507,9,603,105)))
H, W, _ = p.shape
# 1) remove a katana (faixa diagonal do canto esquerdo ate o punho) e a ponta no canto inferior direito
for y in range(H):
    for x in range(W):
        c = tuple(int(v) for v in p[y,x])
        if c in BLUE:
            if 0 <= x <= 49 and 66 <= y <= 90 and abs(y - (72 + (x-2)*11/46)) <= 3.5: p[y,x] = (8,8,8)
            if x >= 86 and y >= 89: p[y,x] = (170,0,0)
# 2) fundo (flood fill a partir da borda interna) -> azul
bgmask = np.zeros((H,W), bool); q = deque()
for x in range(W):
    for y in (1,H-2): q.append((y,x))
for y in range(H):
    for x in (1,W-2): q.append((y,x))
while q:
    y,x = q.popleft()
    if 0<=y<H and 0<=x<W and not bgmask[y,x] and tuple(p[y,x])==(170,0,0):
        bgmask[y,x]=True; q.extend([(y+1,x),(y-1,x),(y,x+1),(y,x-1)])
out = p.copy()
for y in range(H):
    for x in range(W):
        c = tuple(int(v) for v in p[y,x])
        if bgmask[y,x] or c==(170,0,0): out[y,x] = BG_NEW
        else: out[y,x] = MAP.get(c, c)
for y in range(86,H-1):
    for x in range(84,W-1):
        if tuple(out[y,x]) in {(64,0,0),(8,8,8)} and x>=86: out[y,x]=BG_NEW
# moldura preta de 1px
out[0,:]=out[-1,:]=0; out[:,0]=out[:,-1]=0
img = Image.fromarray(out); img.save(os.path.join(OUT,'kojiro_portrait_96x96.png'))
img.resize((384,384), Image.NEAREST).save(os.path.join(OUT,'kojiro_portrait_x4.png'))

# 3) plaquinha: troca o icone e o nome GINZU por KOJIRO
plate = gs.crop((506,114,595,149)).convert('RGBA'); a = np.array(plate)
a[np.all(a[:,:,:3]==(0,0,248),axis=2),3] = 0
cyan = None
from collections import Counter
cnt = Counter(tuple(int(v) for v in a[y,x,:3]) for y in range(19,27) for x in range(24,70) if a[y,x,3])
print('cores na area do nome:', cnt.most_common(4))
plate = Image.fromarray(a)
# apaga icone (0..16, 19..35) e texto do nome
for y in range(19,35):
    for x in range(0,89):
        if x < 17 or (19 <= y <= 27 and 17 <= x < 80):
            a[y,x,3] = 0
plate = Image.fromarray(a)
icon = ks.crop((195,13,211,29)).convert('RGBA'); plate.paste(icon,(0,19))
label = ks.crop((219,13,267,21)).convert('RGBA'); la = np.array(label); la[np.all(la[:,:,:3]==(0,248,248),axis=2),3]=0
# texto do nome em ciano (como o do Ginzu)
CY = cnt.most_common(1)[0][0] if cnt else (0,168,248)
for y in range(la.shape[0]):
    for x in range(la.shape[1]):
        if la[y,x,3] and tuple(la[y,x,:3]) in {(248,168,0),(248,232,0),(232,136,0),(248,152,0),(232,152,0)}: pass
label = Image.fromarray(la); plate.paste(label,(28,19),label)
plate.save(os.path.join(OUT,'kojiro_nameplate.png'))
plate.resize((plate.width*5,plate.height*5), Image.NEAREST).save(os.path.join(OUT,'kojiro_nameplate_x5.png'))
