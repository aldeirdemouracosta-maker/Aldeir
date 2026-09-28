#!/usr/bin/env python3
"""IA Stop-Motion Studio OS — local AI image tools (ONNX Runtime, CPU).

  ia-sms-ia.py remove-bg --model isnet-general-use.onnx [--background bg.png] IN OUT [IN OUT ...]
  ia-sms-ia.py inpaint   --model lama_fp32.onnx --mask mask.png           IN OUT [IN OUT ...]

remove-bg  salient-object segmentation (IS-Net / U²-Net, as used by rembg):
           writes RGBA, or the photo composited over --background.
inpaint    LaMa: fills the painted area of the mask from its surroundings.
           Only a region around the mask is processed, at the model's 512 px.

The model is loaded once for all pairs. Progress goes to stdout as
"PROGRESS <done> <total>"; errors to stderr with exit code 1.
"""
import argparse
import sys

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageFilter, ImageOps


def session(path):
    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(path, opts, providers=["CPUExecutionProvider"])


def load_rgb(path):
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


# ── background removal ──────────────────────────────────────────────────

def segment(sess, img):
    """Alpha matte (PIL 'L', image size) for the main subject."""
    inp = sess.get_inputs()[0]
    size = inp.shape[2] if isinstance(inp.shape[2], int) else 320
    # IS-Net was trained with mean 0.5 / std 1; U²-Net with ImageNet stats.
    if size >= 1024:
        mean, std = (0.5, 0.5, 0.5), (1.0, 1.0, 1.0)
    else:
        mean, std = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)
    x = np.asarray(img.resize((size, size), Image.LANCZOS), dtype=np.float32)
    x = x / max(float(x.max()), 1e-6)
    x = (x - np.array(mean, np.float32)) / np.array(std, np.float32)
    x = x.transpose(2, 0, 1)[None].astype(np.float32)
    pred = sess.run(None, {inp.name: x})[0][:, 0, :, :]
    lo, hi = float(pred.min()), float(pred.max())
    pred = (pred - lo) / max(hi - lo, 1e-6)
    mask = Image.fromarray((pred[0] * 255).clip(0, 255).astype(np.uint8), "L")
    return mask.resize(img.size, Image.LANCZOS)


def remove_bg(args, pairs):
    sess = session(args.model)
    bg = load_rgb(args.background) if args.background else None
    for k, (src, dst) in enumerate(pairs):
        img = load_rgb(src)
        alpha = segment(sess, img)
        if bg is None:
            out = img.copy()
            out.putalpha(alpha)
        else:
            cover = ImageOps.fit(bg, img.size, Image.LANCZOS)
            out = Image.composite(img, cover, alpha)
        out.save(dst, "PNG")
        print(f"PROGRESS {k + 1} {len(pairs)}", flush=True)


# ── inpainting ──────────────────────────────────────────────────────────

def mask_for(path, size):
    """Binary hole mask (PIL 'L', 0/255) from a painted mask image."""
    m = Image.open(path)
    if m.mode in ("RGBA", "LA") or "transparency" in m.info:
        m = m.convert("RGBA").getchannel("A")
    else:
        m = m.convert("L")
    m = m.resize(size, Image.NEAREST).point(lambda v: 255 if v > 16 else 0)
    return m.filter(ImageFilter.MaxFilter(5))  # cover the painted edge


def lama(sess, crop, hole):
    """Runs LaMa on a 512×512 crop; returns the filled RGB crop."""
    inputs = sess.get_inputs()
    names = [i.name for i in inputs]
    img_name = next((n for n in names if "image" in n.lower()), names[0])
    mask_name = next((n for n in names if "mask" in n.lower()), names[1])
    side = inputs[0].shape[2] if isinstance(inputs[0].shape[2], int) else 512
    x = np.asarray(crop.resize((side, side), Image.BICUBIC), np.float32).transpose(2, 0, 1)[None] / 255.0
    m = (np.asarray(hole.resize((side, side), Image.NEAREST), np.float32) > 127).astype(np.float32)[None, None]
    out = sess.run(None, {img_name: x, mask_name: m})[0][0].transpose(1, 2, 0)
    if out.max() <= 1.5:  # some exports return 0..1
        out = out * 255.0
    return Image.fromarray(out.clip(0, 255).astype(np.uint8), "RGB").resize(crop.size, Image.BICUBIC)


def inpaint(args, pairs):
    sess = session(args.model)
    for k, (src, dst) in enumerate(pairs):
        img = load_rgb(src)
        hole = mask_for(args.mask, img.size)
        box = hole.getbbox()
        if box is None:
            img.save(dst, "PNG")
        else:
            # Square context around the hole: 3× its size, at least 512 px.
            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            side = int(min(max(512, 3 * max(box[2] - box[0], box[3] - box[1])), max(img.size)))
            x0 = int(min(max(0, cx - side / 2), max(0, img.width - side)))
            y0 = int(min(max(0, cy - side / 2), max(0, img.height - side)))
            region = (x0, y0, min(img.width, x0 + side), min(img.height, y0 + side))
            crop, crop_hole = img.crop(region), hole.crop(region)
            filled = lama(sess, crop, crop_hole)
            soft = crop_hole.filter(ImageFilter.GaussianBlur(2))
            img.paste(Image.composite(filled, crop, soft), region[:2])
            img.save(dst, "PNG")
        print(f"PROGRESS {k + 1} {len(pairs)}", flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    rb = sub.add_parser("remove-bg")
    rb.add_argument("--model", required=True)
    rb.add_argument("--background")
    rb.add_argument("files", nargs="+")
    ip = sub.add_parser("inpaint")
    ip.add_argument("--model", required=True)
    ip.add_argument("--mask", required=True)
    ip.add_argument("files", nargs="+")
    args = p.parse_args()
    if len(args.files) % 2:
        p.error("os arquivos vêm em pares: ENTRADA SAÍDA")
    pairs = list(zip(args.files[0::2], args.files[1::2]))
    try:
        (remove_bg if args.cmd == "remove-bg" else inpaint)(args, pairs)
    except Exception as exc:  # reported to the app
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
