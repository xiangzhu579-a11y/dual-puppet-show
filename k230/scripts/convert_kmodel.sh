#!/usr/bin/env bash
# 在 Linux（WSL2 Ubuntu 22.04 或独立 Ubuntu）里把 best.onnx 转成 K230 的 kmodel。
#
# 前置：
#   1. 已在本机 Windows 训练并导出 best.onnx（见 README 的「导出 ONNX」一节）
#   2. 把 best.onnx 和 calibration 图片放到工作区（Windows 的 D:\... 在 WSL 里是 /mnt/d/...）
#   3. 系统有 python3.10（nncase 2.9.0 的 manylinux wheel 覆盖 cp37–cp310）和 dotnet-sdk-7.0
#
#   用法：bash convert_kmodel.sh [项目根目录]
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ONNX="$ROOT/runs/fist_palm/weights/best_single.onnx"
CALIB="$ROOT/datasets/fist_palm/calib"
OUT_DIR="$ROOT/k230"
VENV="$ROOT/.venv_kmodel"

echo "==> 检查输入"
[ -f "$ONNX" ] || { echo "缺少 $ONNX，请先运行 export.py 导出 onnx"; exit 1; }
[ -d "$CALIB" ] || { echo "缺少校准图片目录 $CALIB"; exit 1; }

echo "==> 安装 nncase 2.9.0（需要 python3.10）"
python3.10 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/
pip install nncase==2.9.0 nncase-kpu==2.9.0 onnx onnxruntime onnxsim \
    -i https://mirrors.aliyun.com/pypi/simple/

# nncase-kpu 依赖 dotnet 运行时（Ubuntu 下需先装 dotnet-sdk-7.0）
if ! command -v dotnet >/dev/null 2>&1; then
    echo "警告：未找到 dotnet。按 PDF 安装：sudo apt-get install -y dotnet-sdk-7.0"
fi

echo "==> 转换 onnx -> kmodel"
cd "$(dirname "$0")/../tools/test_yolov5/classify" 2>/dev/null || cd "$ROOT/tools/test_yolov5/classify"
python to_kmodel.py --target k230 \
    --model "$ONNX" \
    --dataset "$CALIB" \
    --input_width 224 --input_height 224 \
    --ptq_option 0

KMOEL="${ONNX%.onnx}.kmodel"
mkdir -p "$OUT_DIR"
cp -v "$KMOEL" "$OUT_DIR/best.kmodel"
echo "==> 完成：$OUT_DIR/best.kmodel，复制到 K230 的 /data 后运行 k230/deploy_cls.py"
