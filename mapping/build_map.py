# -*- coding: utf-8 -*-
"""
1セッションの姿勢付き画像から COLMAP で3D点群を作る (姿勢は固定して三角測量だけさせる)。

流れ:
  1. captures.jsonl の姿勢を COLMAP のモデル形式 (cameras/images/points3D.txt) に書き出す
  2. colmap feature_extractor  → 特徴点
  3. colmap sequential_matcher → 撮った順番どうしのマッチング (現地の「順番」がここで効く)
  4. colmap point_triangulator → 姿勢固定で三角測量
  5. points3D を読み、トラック長・再投影誤差でふるいにかけ、
     Unityセッション座標→(anchor.json)→計画のマップ座標に変換して points_map.json に保存

使い方:
  python build_map.py --session <session_dir> [--colmap colmap] [--flip-v]

--flip-v: 三角測量の点数が異常に少ない場合の縦反転試行 (JPEGの上下と姿勢の規約が
          端末側で反転していた場合の保険。まず無しで実行し、点が出なければ付けて再実行)
"""
import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import numpy as np

from unity_colmap import load_session, colmap_points_to_unity, session_to_map

MIN_TRACK_LEN = 3     # この枚数以上の画像から見えた点だけ使う
MAX_REPROJ_ERR = 2.0  # 再投影誤差 [px]


def run(cmd, cwd=None):
    print("  $ " + " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], cwd=cwd,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:])
        raise RuntimeError(f"コマンド失敗 ({cmd[0]})")


def prepare_images(session_dir, work, flip_v):
    """画像を作業フォルダへ集める (--flip-v のときは縦反転コピー)"""
    img_dir = work / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    jpgs = sorted(session_dir.glob("cap_*.jpg"))
    if flip_v:
        from PIL import Image  # --flip-v のときだけ必要 (pip install pillow)
        for p in jpgs:
            Image.open(p).transpose(Image.FLIP_TOP_BOTTOM).save(img_dir / p.name, quality=92)
    else:
        for p in jpgs:
            shutil.copy2(p, img_dir / p.name)
    return img_dir, jpgs


def write_pose_model(captures, db_path, model_dir):
    """COLMAPのDBに登録された image_id と名前を突き合わせ、姿勢固定モデル (txt) を書く"""
    con = sqlite3.connect(db_path)
    rows = con.execute("SELECT image_id, name FROM images").fetchall()
    con.close()
    id_by_name = {name: iid for iid, name in rows}

    by_name = {c.file: c for c in captures}
    c0 = captures[0]
    model_dir.mkdir(parents=True, exist_ok=True)
    # カメラは1台 (セッション内で内部パラメータは共通)
    (model_dir / "cameras.txt").write_text(
        f"1 PINHOLE {c0.w} {c0.h} {c0.fx} {c0.fy} {c0.cx} {c0.cy}\n", encoding="utf-8")
    lines = []
    used = 0
    for name, iid in sorted(id_by_name.items()):
        c = by_name.get(name)
        if c is None:
            continue
        qw, qx, qy, qz, tx, ty, tz = c.colmap_world_to_cam()
        lines.append(f"{iid} {qw:.9f} {qx:.9f} {qy:.9f} {qz:.9f} {tx:.6f} {ty:.6f} {tz:.6f} 1 {name}")
        lines.append("")  # 2行目 (2D点リスト) は空で良い
        used += 1
    (model_dir / "images.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (model_dir / "points3D.txt").write_text("", encoding="utf-8")
    return used


def parse_points3d(txt_path):
    """points3D.txt → (N,3) と品質でのふるい"""
    pts = []
    for line in Path(txt_path).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith("#"):
            continue
        f = line.split()
        # POINT3D_ID X Y Z R G B ERROR TRACK(image_id, point2d_idx)...
        err = float(f[7])
        track_len = (len(f) - 8) // 2
        if track_len < MIN_TRACK_LEN or err > MAX_REPROJ_ERR:
            continue
        pts.append([float(f[1]), float(f[2]), float(f[3])])
    return np.array(pts, dtype=np.float64) if pts else np.zeros((0, 3))


def write_ply(path, pts):
    """確認用 (MeshLab等で開ける。将来の3DGSの種にもなる)"""
    with open(path, "w", encoding="ascii") as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {len(pts)}\n")
        f.write("property float x\nproperty float y\nproperty float z\nend_header\n")
        for p in pts:
            f.write(f"{p[0]:.4f} {p[1]:.4f} {p[2]:.4f}\n")


def build_session(session_dir, colmap="colmap", flip_v=False):
    session_dir = Path(session_dir)
    captures, anchor = load_session(session_dir)
    print(f"[build] {session_dir.name}: 画像{len(captures)}枚 anchor={'あり' if anchor else '無し'}")
    if len(captures) < 5:
        print("  [skip] 画像が少なすぎます (5枚未満)")
        return None
    if anchor is None:
        print("  [skip] anchor.json がありません (基準点をセットしたセッションだけが対象)")
        return None

    work = session_dir / "colmap_work"
    if work.exists():
        shutil.rmtree(work)
    img_dir, _ = prepare_images(session_dir, work, flip_v)
    db = work / "database.db"
    c0 = captures[0]

    # 1. 特徴抽出 (カメラは既知の1台として固定)
    run([colmap, "feature_extractor",
         "--database_path", db, "--image_path", img_dir,
         "--ImageReader.camera_model", "PINHOLE",
         "--ImageReader.single_camera", "1",
         "--ImageReader.camera_params", f"{c0.fx},{c0.fy},{c0.cx},{c0.cy}",
         "--SiftExtraction.use_gpu", "0"])
    # 2. 撮影順のマッチング (前後10枚と照合)
    run([colmap, "sequential_matcher",
         "--database_path", db,
         "--SequentialMatching.overlap", "10",
         "--SiftMatching.use_gpu", "0"])
    # 3. 姿勢固定モデルを書いて三角測量
    model_in = work / "sparse_in"
    used = write_pose_model(captures, db, model_in)
    print(f"  姿勢を書き込んだ画像: {used}枚")
    model_out = work / "sparse_out"
    model_out.mkdir(exist_ok=True)
    run([colmap, "point_triangulator",
         "--database_path", db, "--image_path", img_dir,
         "--input_path", model_in, "--output_path", model_out])
    run([colmap, "model_converter",
         "--input_path", model_out, "--output_path", model_out, "--output_type", "TXT"])

    pts_colmap = parse_points3d(model_out / "points3D.txt")
    print(f"  三角測量点 (品質ふるい後): {len(pts_colmap)}点")
    if len(pts_colmap) < 50:
        print("  [warn] 点が少なすぎます。--flip-v を付けて再実行してみてください")

    # 4. COLMAP座標→Unityセッション座標→マップ座標
    pts_unity = colmap_points_to_unity(pts_colmap)
    pts_map = session_to_map(pts_unity, anchor)
    cam_ys = [c.t_unity[1] for c in captures]
    cam_y_map = float(np.mean(cam_ys)) - float(anchor["pos"][1])  # マップ座標でのカメラ高さ

    out = {
        "session": session_dir.name,
        "camY": cam_y_map,
        "points": [[round(float(v), 4) for v in p] for p in pts_map],
    }
    out_path = session_dir / "points_map.json"
    out_path.write_text(json.dumps(out), encoding="utf-8")
    write_ply(session_dir / "points_map.ply", pts_map)
    print(f"  -> {out_path.name} / points_map.ply (確認用)")
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, help="session_* ディレクトリ")
    ap.add_argument("--colmap", default="colmap", help="colmap実行ファイルのパス")
    ap.add_argument("--flip-v", action="store_true")
    a = ap.parse_args()
    if build_session(a.session, a.colmap, a.flip_v) is None:
        sys.exit(1)
