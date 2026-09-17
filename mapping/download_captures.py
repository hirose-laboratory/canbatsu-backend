# -*- coding: utf-8 -*-
"""
Firebase Storage から計画の作業画像 (plans/{planId}/captures/...) をローカルへ落とす。

使い方: python download_captures.py --plan <planId> [--out captures_dl] [--key ../forestry/serviceAccountKey.json]
落ちる場所: <out>/<planId>/session_*/ (アプリが端末に置くのと同じ構成)
"""
import argparse
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, storage

BUCKET = "can-batsu.firebasestorage.app"


def init(key_path):
    cred = credentials.Certificate(str(key_path))
    firebase_admin.initialize_app(cred, {"storageBucket": BUCKET})


def download(plan_id, out_dir):
    bucket = storage.bucket()
    prefix = f"plans/{plan_id}/captures/"
    blobs = list(bucket.list_blobs(prefix=prefix))
    if not blobs:
        print(f"[dl] {prefix} にファイルがありません (アップロードがまだ?)")
        return []
    sessions = set()
    for blob in blobs:
        rel = blob.name[len(prefix):]  # session_xxx/cap_000.jpg
        dst = Path(out_dir) / plan_id / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            blob.download_to_filename(str(dst))
        sessions.add(rel.split("/")[0])
    print(f"[dl] {len(blobs)}ファイル / セッション{len(sessions)}件 -> {Path(out_dir) / plan_id}")
    return sorted(Path(out_dir) / plan_id / s for s in sessions)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", default="captures_dl")
    ap.add_argument("--key", default=str(Path(__file__).parent.parent / "forestry" / "serviceAccountKey.json"))
    a = ap.parse_args()
    init(a.key)
    download(a.plan, a.out)
