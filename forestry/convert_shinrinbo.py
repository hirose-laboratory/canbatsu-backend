# -*- coding: utf-8 -*-
"""森林簿シェープファイル → forest_registry JSON 変換

林野庁の国有林オープンデータ (小班区画シェープファイル) を、
Firestoreにアップロードできる形のJSONに変換する。

出力: output/forest_registry_24.json
"""
import json
import sys
from pathlib import Path

import shapefile
from pyproj import Transformer

# JGD2000 平面直角座標系 第6系 (三重県など) → 緯度経度
# 他県のデータを使うときはその県の系番号のEPSGに変えること (.prjファイルで確認)
TRANSFORMER = Transformer.from_crs("EPSG:2448", "EPSG:4326", always_xy=True)


def to_int(value):
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return 0


def convert_area(shp_path, patches):
    sf = shapefile.Reader(str(shp_path), encoding="cp932")
    fields = [f[0] for f in sf.fields[1:]]

    for sr in sf.iterShapeRecords():
        rec = dict(zip(fields, sr.record))
        points = sr.shape.points
        parts = list(sr.shape.parts) + [len(points)]
        ring = points[parts[0]:parts[1]]  # 外周リングのみ (穴は無視)

        polygon = []
        for x, y in ring:
            lon, lat = TRANSFORMER.transform(x, y)
            polygon.append([round(lat, 6), round(lon, 6)])
        if len(polygon) < 3:
            continue

        center_lat = sum(p[0] for p in polygon) / len(polygon)
        center_lng = sum(p[1] for p in polygon) / len(polygon)

        patches.append({
            "id": rec["ID"],
            "name": rec["林小班名称"],
            "city": rec["県市町村"],
            "planningArea": rec["計画区"],
            "species1": rec["樹種１"], "age1": to_int(rec["樹立林齢１"]),
            "species2": rec["樹種２"], "age2": to_int(rec["樹立林齢２"]),
            "species3": rec["樹種３"], "age3": to_int(rec["樹立林齢３"]),
            "volumeM3": to_int(rec["材積"]),
            "areaHa": float(rec["面積"] or 0),
            "centerLat": round(center_lat, 6),
            "centerLng": round(center_lng, 6),
            "polygon": polygon,  # [[lat, lng], ...]
        })


def main():
    if len(sys.argv) < 2:
        print("使い方: python convert_shinrinbo.py <24三重県フォルダのパス>")
        sys.exit(1)

    root = Path(sys.argv[1])
    patches = []
    for shp in sorted(root.glob("*森林計画区/第6系/小班区画.shp")):
        before = len(patches)
        convert_area(shp, patches)
        print(f"{shp.parent.parent.name}: {len(patches) - before}件")

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "forest_registry_24.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"prefecture": "三重県", "patches": patches}, f, ensure_ascii=False)

    print(f"合計 {len(patches)}件 → {out_path}")


if __name__ == "__main__":
    main()
