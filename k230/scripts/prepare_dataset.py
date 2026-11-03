"""Build a YOLOv5 classification dataset (train/val split) from a HaGRID-style zip.

The zip is expected to hold per-class image folders (any nesting depth); entries
whose path contains the class name as a path segment are used. Images are copied
byte-for-byte (no re-encode) and split deterministically by filename hash.
"""
import argparse
import hashlib
import os
import shutil
import zipfile


def pick_entries(zf, classes, limit_per_class):
    """Return {class: [(zip_entry_name, original_name)]} limited per class."""
    found = {c: [] for c in classes}
    for name in zf.namelist():
        if name.endswith("/"):
            continue
        parts = name.split("/")
        dirs = [p.lower() for p in parts[:-1]]
        for c in classes:
            # accept "fist", "train_val_fist", "fist-1", "some_fist_dir"
            if any(d == c or d.endswith("_" + c) or d.endswith("-" + c) for d in dirs):
                found[c].append(name)
                break
    for c in classes:
        found[c].sort()
        if limit_per_class and len(found[c]) > limit_per_class:
            step = len(found[c]) / limit_per_class
            found[c] = [found[c][int(i * step)] for i in range(limit_per_class)]
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--classes", default="fist,palm")
    ap.add_argument("--limit-per-class", type=int, default=0)
    ap.add_argument("--val-ratio", type=float, default=0.15)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    classes = [c.strip().lower() for c in a.classes.split(",") if c.strip()]
    zf = zipfile.ZipFile(a.zip)
    found = pick_entries(zf, classes, a.limit_per_class)

    for c in classes:
        names = found[c]
        print(f"{c}: {len(names)} images in zip")
        if len(names) < 50:
            print(f"  WARNING: only {len(names)} images for class '{c}'")
    if a.dry_run:
        for c in classes:
            print(f"  sample {c}: {found[c][:3]}")
        return 0

    counts = {"train": {}, "val": {}}
    for c in classes:
        for split in ("train", "val"):
            os.makedirs(os.path.join(a.out, split, c), exist_ok=True)
        for name in found[c]:
            base = os.path.basename(name)
            h = int(hashlib.md5(base.encode()).hexdigest(), 16) % 1000 / 1000
            split = "val" if h < a.val_ratio else "train"
            dst = os.path.join(a.out, split, c, base)
            if os.path.exists(dst):
                continue
            with zf.open(name) as src, open(dst, "wb") as out:
                shutil.copyfileobj(src, out, 1 << 20)
            counts[split][c] = counts[split].get(c, 0) + 1

    print("\nwritten:")
    for split in ("train", "val"):
        for c in classes:
            n = len(os.listdir(os.path.join(a.out, split, c)))
            print(f"  {split}/{c}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
