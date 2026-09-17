# -*- coding: utf-8 -*-
"""
マップ座標の点群 (points_map.json ×セッション数) から幹マップを作る。

アルゴリズムはアプリ内の Assets/MotionStereo/TreeDetectorMS.cs (アプリ側改修2点入り) の忠実な移植:
  1. 地面レベル: 高さヒストグラム最頻値 (点が少なければ8%分位)
  2. 局所地面: 2mグリッド (孤立高セル破棄 + 隣接+0.6mの包絡平滑化) — 斜面対応
  3. 幹帯: 局所地面+0.5〜3.0m
  4. 建物面除去: RANSAC直線 (幹帯200点以上のときだけ発動 = 直線に並んだ木を守る)
  5. XZグリッド連結 → 密度ピーク分割 → コンパクト(≤0.45m)×縦長(≥0.6m)条件
サーバー版の違い: 範囲フィルタの基準は基準点 (マップ原点)、半径30m (サーバーは広く拾ってよい)。

使い方: python tree_extract.py --sessions <points_map.jsonのパス...> --out trees_map.json
"""
import argparse
import json
import math
import random
from pathlib import Path

MIN_H, MAX_H = 0.5, 3.0
CELL = 0.25
MIN_PTS = 5
MAX_XZ_RADIUS = 0.45
MIN_Y_EXTENT = 0.6
PEAK_SEP = 0.7
MAX_RANGE = 30.0
LINE_REMOVAL_MIN_POINTS = 200
MERGE_ACROSS_SESSIONS = 0.6  # セッション間で同じ木とみなす距離


def estimate_ground(points, cam_y):
    low = sorted(p[1] for p in points if p[1] < cam_y - 0.5)
    if len(low) > 20:
        lo, hi = low[0], low[-1]
        nbins = max(1, int((hi - lo) / 0.15) + 1)
        hist = [0] * nbins
        for y in low:
            hist[min(nbins - 1, int((y - lo) / 0.15))] += 1
        bi = max(range(nbins), key=lambda i: hist[i])
        return lo + bi * 0.15 + 0.075
    if points:
        ys = sorted(p[1] for p in points)
        return ys[int((len(ys) - 1) * 0.08)]
    return cam_y - 1.4


def local_ground_table(points, global_ground):
    """2mグリッドの局所地面 (孤立高セル破棄 + 包絡平滑化)"""
    GCELL = 2.0
    cell_ys = {}
    for p in points:
        key = (math.floor(p[0] / GCELL), math.floor(p[2] / GCELL))
        cell_ys.setdefault(key, []).append(p[1])
    ground = {}
    for key, ys in cell_ys.items():
        if len(ys) < 5:
            continue
        ys.sort()
        lo = ys[0]
        nb = int(1.5 / 0.15) + 1
        hist = [0] * nb
        for y in ys:
            if y > lo + 1.5:
                break
            hist[min(nb - 1, int((y - lo) / 0.15))] += 1
        bi = max(range(nb), key=lambda i: hist[i])
        ground[key] = lo + bi * 0.15 + 0.075
    # 幹しか写っていない孤立セルの偽地面を捨てる
    isolated = []
    for key, g in ground.items():
        has_neighbor = any(
            (key[0] + dx, key[1] + dz) in ground
            for dx in (-1, 0, 1) for dz in (-1, 0, 1) if (dx, dz) != (0, 0))
        if not has_neighbor and g > global_ground + 0.8:
            isolated.append(key)
    for key in isolated:
        del ground[key]
    # 隣より0.6m以上高くなれない包絡平滑化 ×2
    for _ in range(2):
        updated = {}
        for key, g in ground.items():
            best = g
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    nb = ground.get((key[0] + dx, key[1] + dz))
                    if nb is not None:
                        best = min(best, nb + 0.6)
            updated[key] = best
        ground = updated

    def lookup(x, z):
        key = (math.floor(x / 2.0), math.floor(z / 2.0))
        if key in ground:
            return ground[key]
        vals = [ground[(key[0] + dx, key[1] + dz)]
                for dx in (-1, 0, 1) for dz in (-1, 0, 1)
                if (key[0] + dx, key[1] + dz) in ground]
        return sum(vals) / len(vals) if vals else global_ground

    return lookup


def remove_lines(trunk):
    """建物面・塀のRANSAC直線除去 (点数が多いときだけ。直線に並んだ木を守る)"""
    keep = [True] * len(trunk)
    rng = random.Random(0)
    for _ in range(2):
        alive = [i for i in range(len(trunk)) if keep[i]]
        if len(alive) < LINE_REMOVAL_MIN_POINTS:
            break
        best = None
        for _try in range(200):
            i1, i2 = rng.choice(alive), rng.choice(alive)
            if i1 == i2:
                continue
            dx = trunk[i2][0] - trunk[i1][0]
            dz = trunk[i2][2] - trunk[i1][2]
            L = math.hypot(dx, dz)
            if L < 2.0:
                continue
            nx, nz = -dz / L, dx / L
            inl = [i for i in alive
                   if abs((trunk[i][0] - trunk[i1][0]) * nx + (trunk[i][2] - trunk[i1][2]) * nz) < 0.25]
            if best is None or len(inl) > len(best):
                best = inl
        if best is not None and len(best) > max(40.0, 0.3 * len(alive)):
            for i in best:
                keep[i] = False
        else:
            break
    return [trunk[i] for i in range(len(trunk)) if keep[i]]


def detect_trees(points, cam_y):
    """1セッション分の点群→木リスト (アルゴリズムはTreeDetectorMS準拠)"""
    trees = []
    if len(points) < MIN_PTS:
        return trees
    ground = estimate_ground(points, cam_y)
    lg = local_ground_table(points, ground)

    trunk = [p for p in points if lg(p[0], p[2]) + MIN_H < p[1] < lg(p[0], p[2]) + MAX_H]
    if len(trunk) < MIN_PTS:
        return trees
    tp = remove_lines(trunk)
    if len(tp) < MIN_PTS:
        return trees

    # XZグリッド連結成分
    cell_map = {}
    for i, p in enumerate(tp):
        cell_map.setdefault((math.floor(p[0] / CELL), math.floor(p[2] / CELL)), []).append(i)
    visited = set()
    components = []
    for start in cell_map:
        if start in visited:
            continue
        stack = [start]
        visited.add(start)
        ids = []
        while stack:
            c = stack.pop()
            ids.extend(cell_map[c])
            for da in (-1, 0, 1):
                for db in (-1, 0, 1):
                    nb = (c[0] + da, c[1] + db)
                    if nb in cell_map and nb not in visited:
                        visited.add(nb)
                        stack.append(nb)
        if len(ids) >= MIN_PTS:
            components.append(ids)

    for ids in components:
        counts = {}
        for i in ids:
            key = (math.floor(tp[i][0] / CELL), math.floor(tp[i][2] / CELL))
            counts[key] = counts.get(key, 0) + 1
        peaks = []
        for key, n in counts.items():
            if n < 2:
                continue
            # 8近傍に自分より大きいセルがあれば極大でない
            is_max = not any(
                counts.get((key[0] + da, key[1] + db), -1) > n
                for da in (-1, 0, 1) for db in (-1, 0, 1) if (da, db) != (0, 0))
            if is_max:
                peaks.append(((key[0] + 0.5) * CELL, (key[1] + 0.5) * CELL, n))
        peaks.sort(key=lambda p: (-p[2], p[0], p[1]))
        seeds = []
        for px, pz, n in peaks:
            if all(math.hypot(px - sx, pz - sz) >= PEAK_SEP for sx, sz in seeds):
                seeds.append((px, pz))
        if not seeds:
            continue
        groups = [[] for _ in seeds]
        for i in ids:
            best = min(range(len(seeds)),
                       key=lambda s: (tp[i][0] - seeds[s][0]) ** 2 + (tp[i][2] - seeds[s][1]) ** 2)
            groups[best].append(i)
        for g in groups:
            if len(g) < MIN_PTS:
                continue
            mx = sum(tp[i][0] for i in g) / len(g)
            mz = sum(tp[i][2] for i in g) / len(g)
            r_max = max(math.hypot(tp[i][0] - mx, tp[i][2] - mz) for i in g)
            ys = [tp[i][1] for i in g]
            y_ext = max(ys) - min(ys)
            if r_max > MAX_XZ_RADIUS or y_ext < MIN_Y_EXTENT:
                continue
            vx = sum((tp[i][0] - mx) ** 2 for i in g) / len(g)
            vz = sum((tp[i][2] - mz) ** 2 for i in g) / len(g)
            trees.append({
                "x": round(mx, 3), "z": round(mz, 3),
                "y": round(lg(mx, mz), 3),           # 足元の高さ (マップ座標)
                "widthCm": int(round(2 * math.sqrt(vx + vz) * 100)),
                "n": len(g),
            })
    return trees


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", nargs="+", required=True, help="points_map.json のパス (複数可)")
    ap.add_argument("--out", default="trees_map.json")
    a = ap.parse_args()

    merged = []
    for path in a.sessions:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        pts = d["points"]
        trees = detect_trees(pts, d["camY"])
        print(f"[extract] {d.get('session', path)}: 点{len(pts)} → 木{len(trees)}本")
        # セッション間の重複統合 (0.6m以内は同じ木。点数の多い方を採用)
        for t in trees:
            dup = None
            for m in merged:
                if math.hypot(m["x"] - t["x"], m["z"] - t["z"]) < MERGE_ACROSS_SESSIONS:
                    dup = m
                    break
            if dup is None:
                merged.append(t)
            elif t["n"] > dup["n"]:
                dup.update(t)

    merged = [t for t in merged if math.hypot(t["x"], t["z"]) <= MAX_RANGE]
    Path(a.out).write_text(json.dumps({"trees": merged}, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    print(f"[extract] 合計 {len(merged)}本 -> {a.out}")


if __name__ == "__main__":
    main()
