"""Evaluate an exported ONNX classifier on a folder-per-class validation set.

Preprocessing mirrors YOLOv5 classification (center-crop square + resize + ImageNet
normalization), which is also what the K230 board demo does.
"""
import argparse
import os
import time

import cv2
import numpy as np
import onnxruntime as ort

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def preprocess(path, size=224):
    img = cv2.imread(path)
    if img is None:
        return None
    h, w = img.shape[:2]
    m = min(h, w)
    top, left = (h - m) // 2, (w - m) // 2
    img = cv2.resize(img[top:top + m, left:left + m], (size, size), interpolation=cv2.INTER_LINEAR)
    img = img[:, :, ::-1].astype(np.float32) / 255.0
    img = (img - MEAN) / STD
    return np.transpose(img, (2, 0, 1))[None, ...].copy()


def softmax(x):
    e = np.exp(x - x.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--onnx", required=True)
    ap.add_argument("--val", required=True, help="folder with one subfolder per class")
    ap.add_argument("--imgsz", type=int, default=224)
    a = ap.parse_args()

    sess = ort.InferenceSession(a.onnx, providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name
    classes = sorted(d for d in os.listdir(a.val) if os.path.isdir(os.path.join(a.val, d)))
    print(f"onnx={a.onnx}\nclasses={classes}")

    total, correct = 0, 0
    per_class = {c: [0, 0] for c in classes}  # [correct, total]
    t0 = time.time()
    for label, cls in enumerate(classes):
        d = os.path.join(a.val, cls)
        for name in sorted(os.listdir(d)):
            if not name.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                continue
            x = preprocess(os.path.join(d, name), a.imgsz)
            if x is None:
                continue
            pred = int(np.argmax(sess.run(None, {in_name: x})[0]))
            ok = pred == label
            correct += ok
            total += 1
            per_class[cls][0] += ok
            per_class[cls][1] += 1

    dt = time.time() - t0
    print(f"\naccuracy: {correct}/{total} = {correct / max(total, 1) * 100:.2f}%")
    for cls in classes:
        c, n = per_class[cls]
        print(f"  {cls:<8} {c}/{n} = {c / max(n, 1) * 100:.2f}%")
    print(f"latency: {dt / max(total, 1) * 1000:.1f} ms/image (CPU, single thread)")


if __name__ == "__main__":
    main()
