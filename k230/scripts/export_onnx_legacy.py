"""Export the YOLOv5 classifier to ONNX with the legacy exporter (opset 12, ir_version < 10).

torch >= 2.9 defaults to the dynamo exporter, which forces opset 18 / ir_version 10;
nncase 2.9 (K230) expects an older graph, so export through `dynamo=False` instead.
"""
import argparse
import os
import sys

import onnx
import torch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "yolov5"))

from models.experimental import attempt_load  # noqa: E402

WEIGHTS = os.path.join(ROOT, "runs", "fist_palm_crop", "weights", "best.pt")
OUT = os.path.join(ROOT, "runs", "fist_palm_crop", "weights", "best_op12.onnx")


def main():
    global WEIGHTS, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=WEIGHTS)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    WEIGHTS, OUT = a.weights, a.out
    model = attempt_load(WEIGHTS, device="cpu", fuse=True).eval()
    dummy = torch.zeros(1, 3, 224, 224)
    with torch.no_grad():
        logits = model(dummy)
    print("torch output:", tuple(logits.shape), logits[0].tolist())

    torch.onnx.export(
        model, dummy, OUT,
        opset_version=12,
        input_names=["images"],
        output_names=["output0"],
        dynamo=False,
        do_constant_folding=True,
    )

    m = onnx.load(OUT)
    onnx.checker.check_model(OUT)
    print("saved:", OUT)
    print("ir_version:", m.ir_version, "opset:", [(o.domain or "ai.onnx", o.version) for o in m.opset_import])
    print("inputs:", [i.name for i in m.graph.input], "outputs:", [o.name for o in m.graph.output])
    print("external_data files:", any(i.data_location == onnx.TensorProto.EXTERNAL for i in m.graph.initializer))


if __name__ == "__main__":
    main()
