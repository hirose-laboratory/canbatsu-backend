# -*- coding: utf-8 -*-
"""
Unityの姿勢付きキャプチャ (captures.jsonl + anchor.json) と COLMAP の橋渡し。

座標系の約束:
- Unity: 左手系・Y上。captures.jsonl の head_pos/head_rot は「カメラ→ワールド」(セッション座標)
- COLMAP: 右手系。カメラは x=右, y=下, z=前。images.txt には「ワールド→カメラ」を書く
- 変換は M = diag(1,-1,1) (Y反転) を両側から挟む:  R_colmap = M · R_unity · M,  t_colmap = M · t_unity
  (det=+1 のままなので正しい回転行列になる)
- マップ座標系 (アプリと同一): 基準点を原点、基準方向を+Z、yは基準点からの相対
  map.x = c·rx − s·rz,  map.y = ry,  map.z = s·rx + c·rz   (r = p − anchorPos, c=cos(yaw), s=sin(yaw))
"""
import json
import math
from pathlib import Path

import numpy as np

M_FLIP = np.diag([1.0, -1.0, 1.0])


def quat_to_mat(x, y, z, w):
    """クォータニオン→回転行列 (Unity/一般で同形の標準式。v' = R v)"""
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ], dtype=np.float64)


def mat_to_quat(R):
    """回転行列→クォータニオン (w,x,y,z)。COLMAP images.txt の並び"""
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    return w, x, y, z


class Capture:
    """captures.jsonl の1行 (1枚分)"""

    def __init__(self, d):
        self.file = d["file"]
        self.w = int(d["w"])
        self.h = int(d["h"])
        self.fx, self.fy = float(d["fx"]), float(d["fy"])
        self.cx, self.cy = float(d["cx"]), float(d["cy"])
        hp = d["head_pos"]
        hq = d["head_rot"]
        op = d.get("cam_off_pos", [0, 0, 0])
        oq = d.get("cam_off_rot", [0, 0, 0, 1])
        # カメラ姿勢 = 頭の姿勢 × 頭→RGBカメラのオフセット (MsKeyframe.FromYPlane と同じ合成)
        Rh = quat_to_mat(*hq)
        Ro = quat_to_mat(*oq)
        self.R_unity = Rh @ Ro                      # カメラ→ワールド (セッション座標)
        self.t_unity = np.array(hp, dtype=np.float64) + Rh @ np.array(op, dtype=np.float64)

    def colmap_world_to_cam(self):
        """COLMAP images.txt 用の (qw,qx,qy,qz, tx,ty,tz) を返す"""
        R_cw = M_FLIP @ self.R_unity @ M_FLIP       # カメラ→ワールド (COLMAP系)
        t_cw = M_FLIP @ self.t_unity
        R_wc = R_cw.T                               # ワールド→カメラ
        t_wc = -R_wc @ t_cw
        qw, qx, qy, qz = mat_to_quat(R_wc)
        return (qw, qx, qy, qz, t_wc[0], t_wc[1], t_wc[2])


def load_session(session_dir):
    """セッションディレクトリから (captures, anchor) を読む。anchor.json が無ければ anchor=None"""
    session_dir = Path(session_dir)
    captures = []
    jsonl = session_dir / "captures.jsonl"
    if not jsonl.exists():
        return [], None
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        line = line.strip().lstrip("﻿")
        if not line:
            continue
        try:
            captures.append(Capture(json.loads(line)))
        except Exception as e:
            print(f"  [warn] メタ1行を読み飛ばし: {e}")
    anchor = None
    aj = session_dir / "anchor.json"
    if aj.exists():
        raw = aj.read_text(encoding="utf-8", errors="replace").strip().lstrip("﻿")
        try:
            d = json.loads(raw)
            pos = np.array(d["pos"], dtype=np.float64)
            yaw = float(d["yawRad"])
            if pos.shape != (3,) or not np.all(np.isfinite(pos)) or not math.isfinite(yaw):
                raise ValueError("位置か向きが数値でない (NaN/Infinity)")
            anchor = {"pos": pos, "yaw": yaw}
        except Exception as e:
            # 壊れた基準点は「基準点なし」と同じ扱いにして、この計画の他のセッションは続ける
            print(f"  [warn] anchor.json が読めません ({e}) -> このセッションは対象外")
            print(f"         {aj}")
            print(f"         中身: {raw[:200]!r}")
            anchor = None
    return captures, anchor


def colmap_points_to_unity(points_colmap):
    """COLMAP世界座標の点群 (N,3) → Unityセッション座標"""
    return points_colmap @ M_FLIP  # M は対角なので転置不要


def session_to_map(points_unity, anchor):
    """Unityセッション座標 (N,3) → 計画のマップ座標 (アプリの SessionToMap と同一式)"""
    r = points_unity - anchor["pos"]
    c, s = math.cos(anchor["yaw"]), math.sin(anchor["yaw"])
    out = np.empty_like(r)
    out[:, 0] = c * r[:, 0] - s * r[:, 2]
    out[:, 1] = r[:, 1]
    out[:, 2] = s * r[:, 0] + c * r[:, 2]
    return out
