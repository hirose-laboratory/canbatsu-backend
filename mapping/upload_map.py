# -*- coding: utf-8 -*-
"""
幹マップ (trees_map.json) を Firestore の work_plans/{planId}/armap/state へ保存する。

アプリが読む形式 ({trees:[{x,y,z,widthCm,selected}]}) に合わせる。
既存の選木フラグは消さない:
  - 既存の selected=true の木は、新マップの0.6m以内の木に selected を引き継ぐ
  - 近くに新しい木が無ければ、その選木はそのまま残す (伐る予定の木を勝手に消さない)

使い方: python upload_map.py --plan <planId> --trees trees_map.json [--key ...]
"""
import argparse
import json
import math
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore

SAME_TREE = 0.6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--trees", default="trees_map.json")
    ap.add_argument("--key", default=str(Path(__file__).parent.parent / "forestry" / "serviceAccountKey.json"))
    a = ap.parse_args()

    firebase_admin.initialize_app(credentials.Certificate(a.key))
    db = firestore.client()
    doc_ref = db.collection("work_plans").document(a.plan).collection("armap").document("state")

    new_trees = json.loads(Path(a.trees).read_text(encoding="utf-8"))["trees"]
    entries = [{"x": t["x"], "y": t["y"], "z": t["z"],
                "widthCm": int(t.get("widthCm", 0)), "selected": False}
               for t in new_trees]

    snap = doc_ref.get()
    carried = 0
    anchor_geo = None
    if snap.exists:
        # 基準点の地理情報 (アプリが書く。選木結果の地図表示に使う) は消さずに引き継ぐ
        anchor_geo = snap.to_dict().get("anchorGeo")
        for old in snap.to_dict().get("trees", []):
            if not old.get("selected"):
                continue
            near = None
            for e in entries:
                if math.hypot(e["x"] - old["x"], e["z"] - old["z"]) < SAME_TREE:
                    near = e
                    break
            if near is not None:
                near["selected"] = True
                if near["widthCm"] == 0:
                    near["widthCm"] = int(old.get("widthCm", 0))
            else:
                entries.append(old)  # 対応する木が無くても選木は消さない
            carried += 1

    data = {
        "trees": entries,
        "updatedAt": firestore.SERVER_TIMESTAMP,
        "source": "server",  # サーバーバッチ由来であることの目印 (アプリは読み飛ばすだけ)
    }
    if anchor_geo is not None:
        data["anchorGeo"] = anchor_geo
    doc_ref.set(data)
    print(f"[upload] {len(entries)}本 (選木引き継ぎ{carried}件) -> work_plans/{a.plan}/armap/state")


if __name__ == "__main__":
    main()
