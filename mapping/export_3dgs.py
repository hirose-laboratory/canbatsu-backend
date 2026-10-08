# -*- coding: utf-8 -*-
"""
build_map.py の COLMAP 出力 (姿勢固定の三角測量モデル) を、3D Gaussian Splatting の学習用データに並べ直す。

本体アプリは 3DGS を使わない (方針: 自前COLMAPバッチ)。これはデモ・発表用の見える化で、
同じ COLMAP 出力を流用するだけなので現地の撮影や Firestore のデータには影響しない。

出力 (gaussian-splatting 公式リポジトリの train.py がそのまま読める形):
  <session>/gs_dataset/
    images/        cap_000.jpg ...  (colmap_work/images のコピー)
    sparse/0/      cameras.txt / images.txt / points3D.txt  (colmap_work/sparse_out のコピー)

使い方:
  python export_3dgs.py --session captures_dl/<planId>/session_xxx
  → 続けて学習:  python train.py -s <session>/gs_dataset -m <出力先>   (gaussian-splatting リポジトリ内で)
"""
import argparse
import shutil
import sys
from pathlib import Path

REQUIRED = ("cameras.txt", "images.txt", "points3D.txt")


def count_points3d(path):
    n = 0
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if line and not line.startswith("#"):
            n += 1
    return n


def export_session(session_dir):
    session_dir = Path(session_dir)
    work = session_dir / "colmap_work"
    sparse_out = work / "sparse_out"
    img_dir = work / "images"
    if not sparse_out.exists() or not img_dir.exists():
        print(f"[3dgs] {session_dir.name}: colmap_work がありません。先に build_map.py を実行してください")
        return None
    missing = [f for f in REQUIRED if not (sparse_out / f).exists()]
    if missing:
        print(f"[3dgs] {session_dir.name}: sparse_out に {missing} がありません (model_converter の TXT 出力が必要)")
        return None

    out = session_dir / "gs_dataset"
    if out.exists():
        shutil.rmtree(out)
    (out / "sparse" / "0").mkdir(parents=True)
    out_images = out / "images"
    out_images.mkdir()

    for f in REQUIRED:
        shutil.copy2(sparse_out / f, out / "sparse" / "0" / f)
    jpgs = sorted(img_dir.glob("*.jpg"))
    for p in jpgs:
        shutil.copy2(p, out_images / p.name)

    n_pts = count_points3d(sparse_out / "points3D.txt")
    print(f"[3dgs] {session_dir.name}: 画像{len(jpgs)}枚 / 初期点{n_pts}点 -> {out}")
    if n_pts < 1000:
        print("  [warn] 初期点が少ないので学習結果が粗くなりやすい (撮影枚数を増やす・重なりを大きくする)")
    print(f"  学習: python train.py -s \"{out}\" -m \"{session_dir / 'gs_model'}\"")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, nargs="+", help="session_* ディレクトリ (複数可)")
    a = ap.parse_args()
    ok = 0
    for s in a.session:
        if export_session(s) is not None:
            ok += 1
    sys.exit(0 if ok > 0 else 1)
