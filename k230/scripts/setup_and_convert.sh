#!/usr/bin/env bash
# 在 WSL Ubuntu 22.04 里一次性完成：装依赖 -> onnx 转 kmodel -> 拷回工作区。
# 用法（Ubuntu 终端里）：bash scripts/setup_and_convert.sh
set -uo pipefail

# 项目根目录 = 本脚本所在目录的上一级（工程目录或发布包根目录都能用）
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD=/root/km-build

DEFAULT_ONNX=""
for c in "$ROOT/runs/fist_palm_crop/weights/best_op12.onnx" \
         "$ROOT/models/fist_palm_crop/best_op12.onnx"; do
    if [ -f "$c" ]; then DEFAULT_ONNX="$c"; break; fi
done
ONNX_SRC="${DEFAULT_ONNX:-$ROOT/runs/fist_palm_crop/weights/best_op12.onnx}"   # ir_version 7 / opset 12
CALIB_SRC="$ROOT/datasets/fist_palm_crop/calib"
KMODEL_DST="$ROOT/k230/best.kmodel"
MIRROR=https://mirrors.aliyun.com/pypi/simple/

step() { echo; echo "===== $* ====="; }
die()  { echo "!! $*"; exit 1; }

step "0. 检查输入"
[ -f "$ONNX_SRC" ] || die "找不到 $ONNX_SRC"
[ -d "$CALIB_SRC" ] || die "找不到校准图目录 $CALIB_SRC"
echo "onnx : $(du -h "$ONNX_SRC" | cut -f1)"
echo "calib: $(ls "$CALIB_SRC" | wc -l) 张"

step "1. 换阿里云 apt 源（官方源在国外，会很慢）"
if ! grep -q "mirrors.aliyun.com" /etc/apt/sources.list 2>/dev/null; then
    cp /etc/apt/sources.list /etc/apt/sources.list.bak 2>/dev/null || true
    cat > /etc/apt/sources.list <<'EOF'
deb https://mirrors.aliyun.com/ubuntu/ jammy main restricted universe multiverse
deb https://mirrors.aliyun.com/ubuntu/ jammy-updates main restricted universe multiverse
deb https://mirrors.aliyun.com/ubuntu/ jammy-backports main restricted universe multiverse
deb https://mirrors.aliyun.com/ubuntu/ jammy-security main restricted universe multiverse
EOF
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq || die "apt-get update 失败"

step "2. 安装 python3.10-venv 与 dotnet（nncase-kpu 需要 .NET 运行时）"
apt-get install -y -qq python3.10-venv python3-pip unzip >/dev/null || die "安装 python venv 失败"
if apt-get install -y -qq dotnet-sdk-7.0 >/dev/null 2>&1; then
    echo "dotnet-sdk-7.0 已安装"
elif apt-get install -y -qq dotnet-sdk-8.0 >/dev/null 2>&1; then
    echo "dotnet-sdk-8.0 已安装（7.0 源里没有）"
else
    echo "警告：dotnet 没装上，nncase-kpu 可能报 libhostfxr 错误"
fi
command -v dotnet >/dev/null && dotnet --list-runtimes | head -3

step "3. 建 venv 并安装 nncase 2.9.0（放在 /root，避免 /mnt/d 慢）"
rm -rf /root/km-venv
python3.10 -m venv /root/km-venv || die "创建 venv 失败"
# shellcheck disable=SC1091
source /root/km-venv/bin/activate
pip install -q --upgrade pip -i $MIRROR
# 版本刻意钉住：onnx 1.14 才有 to_kmodel.py 用到的 onnx.mapping；numpy<2 兼容 nncase 2.9
pip install -q -i $MIRROR \
    nncase==2.9.0 nncase-kpu==2.9.0 \
    "onnx==1.14.1" "onnxsim==0.4.33" "onnxruntime==1.16.3" "numpy<2" pillow \
    || die "pip 安装失败"
python -c "import nncase, onnx, numpy; print('nncase', nncase.__version__, '| onnx', onnx.__version__, '| numpy', numpy.__version__)"

step "4. 准备构建目录"
rm -rf $BUILD && mkdir -p $BUILD
cp -r "$ROOT/tools/test_yolov5/classify/." $BUILD/
cp "$ONNX_SRC" $BUILD/best_single.onnx
mkdir -p $BUILD/calib && cp "$CALIB_SRC"/*.jpg $BUILD/calib/ 2>/dev/null
cd $BUILD || die "进入 $BUILD 失败"
ls -1

step "5. onnx -> kmodel（PTQ uint8，calib 20 张）"
python to_kmodel.py --target k230 \
    --model best_single.onnx \
    --dataset calib \
    --input_width 224 --input_height 224 \
    --ptq_option 0 2>&1 | tail -40
rc=${PIPESTATUS[0]}
[ $rc -eq 0 ] || die "to_kmodel.py 退出码 $rc"

step "6. 拷回工作区并检查"
[ -f best_single.kmodel ] || die "没有生成 best_single.kmodel"
mkdir -p "$(dirname "$KMODEL_DST")"
cp best_single.kmodel "$KMODEL_DST"
ls -lh "$KMODEL_DST"

echo
echo "===== 完成 ====="
echo "产物: $KMODEL_DST"
echo "下一步: 复制到 K230 的 /data/fist_palm.kmodel，运行 k230/deploy_cls.py"
