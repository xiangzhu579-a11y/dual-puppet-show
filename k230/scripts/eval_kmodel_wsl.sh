#!/usr/bin/env bash
# 用 nncase 模拟器在 PC 上验证 kmodel 的量化后精度（不需要板子）。
# 用法：bash eval_kmodel_wsl.sh [图片数] [验证集目录] [kmodel路径]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV=/root/km-venv
LIMIT="${1:-200}"
VAL_DIR="${2:-$ROOT/datasets/fist_palm_crop/val}"
KMODEL="${3:-$ROOT/k230/best.kmodel}"

[ -x "$VENV/bin/python" ] || { echo "先跑 setup_and_convert.sh 建好 venv"; exit 1; }
[ -f "$KMODEL" ] || { echo "找不到 $KMODEL"; exit 1; }
[ -d "$VAL_DIR" ] || { echo "找不到验证集目录 $VAL_DIR（发布包内不含数据集，需指定）"; exit 1; }

# shellcheck disable=SC1091
source "$VENV/bin/activate"

python - "$KMODEL" "$VAL_DIR" "$LIMIT" <<'PY'
import os, sys, time
import numpy as np
from PIL import Image
import nncase

kmodel, valdir, limit = sys.argv[1], sys.argv[2], int(sys.argv[3])
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

with open(kmodel, "rb") as f:
    sim = nncase.Simulator()
    sim.load_model(f.read())

try:  # nncase 2.9 的 TensorDesc 只暴露部分属性，取不到就退回默认值
    inp = sim.get_input_desc(0)
    print("kmodel 输入:", getattr(inp, "shape", "[1,3,224,224]"), getattr(inp, "dtype", "uint8"))
except Exception:
    print("kmodel 输入: [1, 3, 224, 224] uint8 (由编译参数确定)")

classes = sorted(d for d in os.listdir(valdir) if os.path.isdir(os.path.join(valdir, d)))
print("类别:", classes)

def prep(path, size=224):
    img = Image.open(path).convert("RGB")
    w, h = img.size
    m = min(w, h)
    img = img.crop(((w - m) // 2, (h - m) // 2, (w + m) // 2, (h + m) // 2)).resize((size, size), Image.BILINEAR)
    a = np.asarray(img, dtype=np.uint8)              # HWC RGB uint8
    return np.transpose(a, (2, 0, 1))[None, ...]     # NCHW

total = correct = 0
per = {c: [0, 0] for c in classes}
t0 = time.time()
for idx, cls in enumerate(classes):
    d = os.path.join(valdir, cls)
    for name in sorted(os.listdir(d))[: max(1, limit // len(classes))]:
        if not name.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        x = prep(os.path.join(d, name))
        sim.set_input_tensor(0, nncase.RuntimeTensor.from_numpy(x))
        sim.run()
        t = sim.get_output_tensor(0)
        arr = t.to_numpy() if hasattr(t, "to_numpy") else np.array(t, copy=True)
        out = np.asarray(arr).reshape(-1)
        pred = int(np.argmax(out))
        ok = pred == idx
        correct += ok
        total += 1
        per[cls][0] += ok
        per[cls][1] += 1

print(f"\nkmodel 量化后精度: {correct}/{total} = {correct / max(total,1) * 100:.2f}%")
for c in classes:
    a, b = per[c]
    print(f"  {c:<6} {a}/{b} = {a / max(b,1) * 100:.2f}%")
print(f"平均耗时: {(time.time()-t0)/max(total,1)*1000:.1f} ms/张（PC 模拟器，非板端性能）")
PY
