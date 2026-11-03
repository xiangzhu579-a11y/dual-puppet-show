"""Build a hand-cropped fist/palm dataset from HaGRID annotations.

The board sees a hand filling a large part of the 640x480 frame, while the raw
HaGRID images show a whole person in a room; training on full frames then collapses
to one class on the board. This crops around the annotated hand with a random margin
(and keeps ~20% full frames) so the classifier sees both framings.
"""
import argparse
import hashlib
import json
import os
import random
import zipfile

from PIL import Image

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP = os.path.join(_ROOT, "_downloads", "hagrid-sample-30k-384p.zip")
SRC = os.path.join(_ROOT, "datasets", "fist_palm")
OUT = os.path.join(_ROOT, "datasets", "fist_palm_crop")
CLASSES = ("fist", "palm")
SIZE = 288


def load_ann(zf):
    ann = {}
    for cls in CLASSES:
        name = [n for n in zf.namelist() if n.endswith(f"ann_train_val/{cls}.json")][0]
        for stem, item in json.loads(zf.read(name)).items():
            boxes = item.get("bboxes") or []
            labels = item.get("labels") or []
            picked = [b for b, l in zip(boxes, labels) if l == cls]
            if picked:
                ann[stem] = picked[0]
    print(f"annotations: {len(ann)}")
    return ann


def crop_square(img, bbox, margin, full_frame_prob, rng):
    w, h = img.size
    if rng.random() < full_frame_prob:
        x0, y0, x1, y1 = 0, 0, w, h
    else:
        bx, by, bw, bh = bbox
        cx, cy = (bx + bw / 2) * w, (by + bh / 2) * h
        side = max(bw * w, bh * h) * margin
        side = min(max(side, 48), max(w, h))
        x0, y0 = cx - side / 2, cy - side / 2
        x1, y1 = x0 + side, y0 + side
    # make the region square and inside the image
    side = min(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    side = min(side, w, h)
    x0 = min(max(cx - side / 2, 0), w - side)
    y0 = min(max(cy - side / 2, 0), h - side)
    return img.crop((int(x0), int(y0), int(x0 + side), int(y0 + side))).resize((SIZE, SIZE), Image.BILINEAR)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full-frame-prob", type=float, default=0.2)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    zf = zipfile.ZipFile(ZIP)
    ann = load_ann(zf)

    total = 0
    for split in ("train", "val"):
        for cls in CLASSES:
            src_dir = os.path.join(SRC, split, cls)
            dst_dir = os.path.join(a.out, split, cls)
            os.makedirs(dst_dir, exist_ok=True)
            n = 0
            for name in sorted(os.listdir(src_dir)):
                stem = os.path.splitext(name)[0]
                bbox = ann.get(stem)
                if bbox is None:
                    continue
                seed = int(hashlib.md5(name.encode()).hexdigest()[:8], 16)
                rng = random.Random(seed)
                margin = rng.uniform(1.3, 2.6)
                img = Image.open(os.path.join(src_dir, name)).convert("RGB")
                out = crop_square(img, bbox, margin, a.full_frame_prob, rng)
                out.save(os.path.join(dst_dir, name), quality=92)
                n += 1
            total += n
            print(f"  {split}/{cls}: {n}")
    print("total:", total)


if __name__ == "__main__":
    main()
