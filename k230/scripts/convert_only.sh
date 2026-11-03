#!/usr/bin/env bash
# 只做转换（依赖已装好时用）：onnx -> kmodel -> 拷回工作区。
# 用法：
#   bash convert_only.sh                                  # 默认 runs/fist_palm/weights/best_op12.onnx
#   bash convert_only.sh <onnx路径> [输出kmodel路径]
set -uo pipefail

# 项目根目录 = 本脚本所在目录的上一级（工程目录或发布包根目录都能用）
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD=/root/km-build

# 自动找 onnx：优先工程目录，其次发布包 models/ 布局
DEFAULT_ONNX=""
for c in "$ROOT/runs/fist_palm_crop/weights/best_op12.onnx" \
         "$ROOT/runs/fist_palm/weights/best_op12.onnx" \
         "$ROOT/models/fist_palm_crop/best_op12.onnx"; do
    if [ -f "$c" ]; then DEFAULT_ONNX="$c"; break; fi
done

ONNX_SRC="${1:-${DEFAULT_ONNX:-$ROOT/runs/fist_palm_crop/weights/best_op12.onnx}}"
CALIB_SRC="${3:-$ROOT/datasets/fist_palm_crop/calib}"
KMODEL_DST="${2:-$ROOT/k230/best.kmodel}"
VENV=/root/km-venv

step() { echo; echo "===== $* ====="; }
die()  { echo "!! $*"; exit 1; }

step "0. 检查"
[ -f "$ONNX_SRC" ] || die "找不到 $ONNX_SRC"
[ -x "$VENV/bin/python" ] || die "$VENV 不存在，先跑 setup_and_convert.sh"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -c "import nncase, onnx, onnxsim; print('nncase ok | onnx', onnx.__version__)" || die "venv 里 nncase 导入失败"

step "1. 准备构建目录"
rm -rf $BUILD && mkdir -p $BUILD/calib
cp -r "$ROOT/tools/test_yolov5/classify/." $BUILD/
cp "$ONNX_SRC" $BUILD/model.onnx
cp "$CALIB_SRC"/*.jpg $BUILD/calib/ 2>/dev/null || true
echo "onnx : $(du -h $BUILD/model.onnx | cut -f1)"
echo "calib: $(ls $BUILD/calib | wc -l) 张"

step "2. 修正 ir_version（onnxsim 0.4.x 的 checker 只认 <= 9）"
python - <<'PY'
import onnx
p = '/root/km-build/model.onnx'
m = onnx.load(p)
print('before: ir_version', m.ir_version, '| opset', [o.version for o in m.opset_import])
if m.ir_version > 9:
    m.ir_version = 9
    onnx.save(m, p, save_as_external_data=False)
    m = onnx.load(p)
print('after : ir_version', m.ir_version, '| opset', [o.version for o in m.opset_import])
PY

step "3. onnx -> kmodel（PTQ uint8）"
cd $BUILD || die "进入 $BUILD 失败"
python to_kmodel.py --target k230 \
    --model model.onnx \
    --dataset calib \
    --input_width 224 --input_height 224 \
    --ptq_option 0 2>&1 | tail -30
rc=${PIPESTATUS[0]}
[ $rc -eq 0 ] || die "to_kmodel.py 退出码 $rc"

step "4. 拷回工作区"
[ -f model.kmodel ] || die "没有生成 model.kmodel"
mkdir -p "$(dirname "$KMODEL_DST")"
cp model.kmodel "$KMODEL_DST"
ls -lh "$KMODEL_DST"

echo
echo "===== 完成 ====="
echo "产物: $KMODEL_DST"
echo "下一步: 复制到 K230 的 /data/fist_palm.kmodel，运行 k230/deploy_cls.py"
