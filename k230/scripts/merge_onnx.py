"""Merge an ONNX model that uses external data into a single self-contained file.

torch's newer ONNX exporter may write `model.onnx.data` next to the graph; nncase and
the K230 toolchain expect one file.
"""
import argparse
import os

import onnx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    a = ap.parse_args()

    model = onnx.load(a.src)  # resolves external data automatically
    onnx.save_model(model, a.dst, save_as_external_data=False)

    n = len(model.graph.input)
    print(f"saved {a.dst} ({os.path.getsize(a.dst) / 2**20:.2f} MiB)")
    print("inputs :", [(i.name, [d.dim_value or d.dim_param for d in i.type.tensor_type.shape.dim]) for i in model.graph.input])
    print("outputs:", [(o.name, [d.dim_value or d.dim_param for d in o.type.tensor_type.shape.dim]) for o in model.graph.output])


if __name__ == "__main__":
    main()
