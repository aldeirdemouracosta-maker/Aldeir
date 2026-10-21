#!/usr/bin/env python3
"""Protótipo de comparação (PC): troca de rosto por MALHA (a mesma do app Android) x inswapper (IA), no SEU clipe e SUA foto.

Gera, em --out: mesh.mp4, inswapper.mp4 (se informado o modelo), tiras de comparação (compare_XX.png) e report.txt com o tempo por quadro.
Todos os vídeos saem com o selo "CONTEÚDO ALTERADO • IA" (igual ao app; não há opção para desligar).

Uso uso pessoal/avaliação. Exige --i-have-consent: a pessoa da foto é você ou autorizou, e você pode usar o vídeo.
O modelo inswapper_128.onnx tem licença de PESQUISA NÃO COMERCIAL (InsightFace): você baixa por sua conta; este script não o baixa nem o redistribui.

Instalação (Python 3.10+):  pip install mediapipe opencv-python numpy      (e, para o inswapper: pip install insightface onnxruntime)
Biblioteca da malha:        cmake -S tools/pc_prototype -B build_pc && cmake --build build_pc --config Release
Modelo de pontos:           sh tools/fetch_face_model.sh      (gera app/src/main/assets/face_landmarker.task)
"""
import argparse
import ctypes
import glob
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BADGE = "CONTEUDO ALTERADO - IA"   # cv2.putText não desenha acentos


def load_lib(path):
    cands = [path] if path else []
    for pat in ("build_pc", "build", "."):
        for ext in ("so", "dll", "dylib"):
            cands += glob.glob(os.path.join(ROOT, pat, "**", f"*vmfaceswap*.{ext}"), recursive=True)
            cands += glob.glob(os.path.join(HERE, pat, "**", f"*vmfaceswap*.{ext}"), recursive=True)
    for c in cands:
        if c and os.path.isfile(c):
            lib = ctypes.CDLL(c)
            lib.vm_fs_new.restype = ctypes.c_void_p
            lib.vm_fs_new.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
            lib.vm_fs_apply.restype = ctypes.c_int
            lib.vm_fs_apply.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_float, ctypes.c_float]
            lib.vm_fs_free.argtypes = [ctypes.c_void_p]
            lib.vm_sm_new.restype = ctypes.c_void_p
            lib.vm_sm_filter.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_double]
            lib.vm_sm_reset.argtypes = [ctypes.c_void_p]
            lib.vm_sm_free.argtypes = [ctypes.c_void_p]
            return lib
    sys.exit("Biblioteca vmfaceswap não encontrada. Compile com cmake (veja o topo deste arquivo) ou use --lib.")


class Landmarks:
    """MediaPipe Face Landmarker (modo vídeo): 478 pontos (x,y em pixels)."""

    def __init__(self, model):
        import mediapipe as mp
        from mediapipe.tasks import python as mpt
        from mediapipe.tasks.python import vision
        self.mp = mp
        self.lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=mpt.BaseOptions(model_asset_path=model), running_mode=vision.RunningMode.VIDEO, num_faces=1))
        self.img = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=mpt.BaseOptions(model_asset_path=model), running_mode=vision.RunningMode.IMAGE, num_faces=1))

    def close(self):
        self.lm.close()
        self.img.close()

    def detect(self, rgb, ts_ms=None):
        mpimg = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        r = self.lm.detect_for_video(mpimg, int(ts_ms)) if ts_ms is not None else self.img.detect(mpimg)
        if not r.face_landmarks:
            return None
        h, w = rgb.shape[:2]
        return np.array([[p.x * w, p.y * h] for p in r.face_landmarks[0]], dtype=np.float32)


def badge(bgr):
    h, w = bgr.shape[:2]
    scale = w / 900.0
    (tw, th), base = cv2.getTextSize(BADGE, cv2.FONT_HERSHEY_DUPLEX, scale, max(1, int(scale * 2)))
    x, y = int(w * 0.04), int(h * 0.065)
    pad = int(th * 0.5)
    ov = bgr.copy()
    cv2.rectangle(ov, (x, y), (x + tw + 2 * pad, y + th + base + 2 * pad), (0, 0, 0), -1)
    cv2.addWeighted(ov, 0.7, bgr, 0.3, 0, bgr)
    cv2.putText(bgr, BADGE, (x + pad, y + pad + th), cv2.FONT_HERSHEY_DUPLEX, scale, (255, 255, 255), max(1, int(scale * 2)), cv2.LINE_AA)
    return bgr


def cover_crop(bgr, w, h):
    sh, sw = bgr.shape[:2]
    k = max(w / sw, h / sh)
    nw, nh = int(round(sw * k)), int(round(sh * k))
    r = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC)
    x, y = (nw - w) // 2, (nh - h) // 2
    return r[y:y + h, x:x + w].copy()


def read_frames(path, fps, max_s, w, h):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        sys.exit("Não consegui abrir o vídeo.")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(min(cap.get(cv2.CAP_PROP_FRAME_COUNT) / src_fps, max_s) * fps)
    frames = []
    for i in range(max(1, total)):
        cap.set(cv2.CAP_PROP_POS_MSEC, i * 1000.0 / fps)
        ok, f = cap.read()
        if not ok:
            break
        frames.append(cover_crop(f, w, h))
    cap.release()
    return frames


def write_video(path, frames, fps):
    if not frames:
        return
    h, w = frames[0].shape[:2]
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for f in frames:
        vw.write(f)
    vw.release()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", required=True)
    ap.add_argument("--photo", required=True)
    ap.add_argument("--out", default="saida_comparacao")
    ap.add_argument("--landmarker", default=os.path.join(ROOT, "app/src/main/assets/face_landmarker.task"))
    ap.add_argument("--inswapper", help="caminho do inswapper_128.onnx (opcional; licença não comercial)")
    ap.add_argument("--lib", help="caminho da biblioteca vmfaceswap (.so/.dll)")
    ap.add_argument("--fps", type=int, default=12)
    ap.add_argument("--max-seconds", type=float, default=8.0)
    ap.add_argument("--height", type=int, default=960, help="altura do quadro de trabalho (largura = 9/16)")
    ap.add_argument("--i-have-consent", action="store_true", help="confirmo: a foto é minha ou autorizada e posso usar o vídeo")
    a = ap.parse_args()
    if not a.i_have_consent:
        sys.exit("Use --i-have-consent para confirmar que a pessoa da foto é você ou autorizou, e que você pode usar o vídeo.")
    os.makedirs(a.out, exist_ok=True)
    W, H = int(a.height * 9 / 16) // 2 * 2, a.height

    lib = load_lib(a.lib)
    lm = Landmarks(a.landmarker)
    photo = cv2.imread(a.photo)
    if photo is None:
        sys.exit("Não consegui abrir a foto.")
    scale = min(1.0, 1280 / max(photo.shape[:2]))
    if scale < 1:
        photo = cv2.resize(photo, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    p_rgb = cv2.cvtColor(photo, cv2.COLOR_BGR2RGB)
    p_pts = lm.detect(p_rgb)
    if p_pts is None:
        sys.exit("Não encontrei rosto na foto (use foto frontal, nítida e bem iluminada).")
    p_rgba = np.ascontiguousarray(np.dstack([p_rgb, np.full(p_rgb.shape[:2], 255, np.uint8)]))
    swapper = lib.vm_fs_new(p_rgba.ctypes.data, p_rgba.shape[1], p_rgba.shape[0], p_pts.ctypes.data, 956)
    if not swapper:
        sys.exit("Rosto da foto pequeno ou cortado demais.")
    smoother = lib.vm_sm_new()

    frames = read_frames(a.video, a.fps, a.max_seconds, W, H)
    print(f"{len(frames)} quadros de {W}x{H} a {a.fps} fps")

    # --- inswapper (opcional)
    ins = None
    if a.inswapper:
        import insightface
        from insightface.app import FaceAnalysis
        fa = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        fa.prepare(ctx_id=-1, det_size=(640, 640))
        ins = (fa, insightface.model_zoo.get_model(a.inswapper, providers=["CPUExecutionProvider"]))
        src_faces = ins[0].get(photo)
        if not src_faces:
            sys.exit("inswapper: não achei rosto na foto.")
        src_face = max(src_faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))

    out_mesh, out_ins, t_mesh, t_ins = [], [], [], []
    found_mesh = found_ins = 0
    for i, f in enumerate(frames):
        rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
        t0 = time.perf_counter()
        pts = lm.detect(rgb, i * 1000.0 / a.fps)
        m = f.copy()
        if pts is not None:
            lib.vm_sm_filter(smoother, pts.ctypes.data, 956, i / a.fps)
            rgba = np.ascontiguousarray(np.dstack([cv2.cvtColor(m, cv2.COLOR_BGR2RGB), np.full(m.shape[:2], 255, np.uint8)]))
            if lib.vm_fs_apply(swapper, rgba.ctypes.data, W, H, pts.ctypes.data, 956, 0.85, 0.06):
                m = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_RGB2BGR)
                found_mesh += 1
        else:
            lib.vm_sm_reset(smoother)
        t_mesh.append((time.perf_counter() - t0) * 1000)
        out_mesh.append(badge(m))

        if ins:
            t0 = time.perf_counter()
            r = f.copy()
            faces = ins[0].get(f)
            if faces:
                tgt = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
                r = ins[1].get(r, tgt, src_face, paste_back=True)
                found_ins += 1
            t_ins.append((time.perf_counter() - t0) * 1000)
            out_ins.append(badge(r))

        if i % max(1, len(frames) // 6) == 0:
            cols = [badge(f.copy()), out_mesh[-1]] + ([out_ins[-1]] if ins else [])
            cv2.imwrite(os.path.join(a.out, f"compare_{i:03d}.png"), np.hstack(cols))

    write_video(os.path.join(a.out, "mesh.mp4"), out_mesh, a.fps)
    if ins:
        write_video(os.path.join(a.out, "inswapper.mp4"), out_ins, a.fps)
    rep = [f"quadros: {len(frames)} ({W}x{H}, {a.fps} fps)",
           f"malha (app): rosto trocado em {found_mesh}/{len(frames)}; tempo médio {np.mean(t_mesh):.0f} ms/quadro (inclui detecção MediaPipe)"]
    if ins:
        rep.append(f"inswapper (CPU): rosto trocado em {found_ins}/{len(frames)}; tempo médio {np.mean(t_ins):.0f} ms/quadro")
    else:
        rep.append("inswapper: não executado (passe --inswapper caminho/inswapper_128.onnx)")
    rep.append("Veja compare_XX.png (original | malha | inswapper) e os .mp4. Todos têm o selo CONTEÚDO ALTERADO • IA.")
    open(os.path.join(a.out, "report.txt"), "w", encoding="utf-8").write("\n".join(rep) + "\n")
    print("\n".join(rep))
    lib.vm_fs_free(swapper)
    lib.vm_sm_free(smoother)
    lm.close()


if __name__ == "__main__":
    main()
