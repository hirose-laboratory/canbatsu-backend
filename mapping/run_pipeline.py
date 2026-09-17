# -*- coding: utf-8 -*-
"""
一括実行: 画像DL → セッションごとに3D化 → 幹マップ抽出 → Firestoreへ保存。

使い方:
  python run_pipeline.py --plan <planId> [--colmap colmap] [--flip-v] [--skip-download] [--skip-upload]

前提: COLMAPがインストール済み (README.md 参照)、../forestry/serviceAccountKey.json がある。
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", default="captures_dl")
    ap.add_argument("--colmap", default="colmap")
    ap.add_argument("--flip-v", action="store_true")
    ap.add_argument("--skip-download", action="store_true", help="DL済みのローカル画像で回す")
    ap.add_argument("--skip-upload", action="store_true", help="Firestoreに書かず結果だけ見る")
    ap.add_argument("--key", default=str(HERE.parent / "forestry" / "serviceAccountKey.json"))
    a = ap.parse_args()

    plan_dir = Path(a.out) / a.plan

    # 1. ダウンロード
    if not a.skip_download:
        import download_captures
        download_captures.init(a.key)
        download_captures.download(a.plan, a.out)
    sessions = sorted(p for p in plan_dir.glob("session_*") if p.is_dir())
    if not sessions:
        print(f"セッションがありません: {plan_dir}")
        sys.exit(1)

    # 2. セッションごとに3D化 (anchor.jsonが無いものは中でスキップされる)
    import build_map
    point_files = []
    for s in sessions:
        out = build_map.build_session(s, a.colmap, a.flip_v)
        if out is not None:
            point_files.append(str(out))
    if not point_files:
        print("3D化できたセッションがありません (基準点をセットしたセッションが必要)")
        sys.exit(1)

    # 3. 幹マップ抽出
    trees_out = plan_dir / "trees_map.json"
    r = subprocess.run([sys.executable, str(HERE / "tree_extract.py"),
                        "--sessions", *point_files, "--out", str(trees_out)])
    if r.returncode != 0:
        sys.exit(1)

    # 4. アップロード
    if a.skip_upload:
        print(f"[done] --skip-upload のためここまで。結果: {trees_out}")
        return
    r = subprocess.run([sys.executable, str(HERE / "upload_map.py"),
                        "--plan", a.plan, "--trees", str(trees_out), "--key", a.key])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
