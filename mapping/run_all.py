# -*- coding: utf-8 -*-
"""
Storage に画像がある計画を全部まとめて run_pipeline.py にかける。

使い方:
  python run_all.py --skip-upload --export-3dgs     # まず書き込みなしで全部通して結果を見る
  python run_all.py --skip-download                 # 問題なければ DL 済みの画像で本番 (Firestore へ書く)
  python run_all.py --only <planId> <planId> ...    # 一部だけ

run_pipeline.py に渡せるオプション (--colmap, --flip-v, --skip-download, --skip-upload, --export-3dgs, --out, --key)
はそのまま渡る。1つの計画が失敗しても止めず、最後に成否の一覧を出す。
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent


def list_plans_with_captures(key_path):
    """Storage の plans/<planId>/captures/ を持つ計画IDを集める"""
    import download_captures
    from firebase_admin import storage
    download_captures.init(key_path)
    bucket = storage.bucket()
    plans = set()
    for blob in bucket.list_blobs(prefix="plans/"):
        parts = blob.name.split("/")  # plans/<planId>/captures/session_x/cap_000.jpg
        if len(parts) >= 4 and parts[2] == "captures":
            plans.add(parts[1])
    return sorted(plans)


def list_local_plans(out_dir):
    """--skip-download のときは DL 済みフォルダから集める (Storage に問い合わせない)"""
    root = Path(out_dir)
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and any(p.glob("session_*")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None, help="この計画IDだけ")
    ap.add_argument("--out", default="captures_dl")
    ap.add_argument("--key", default=str(HERE.parent / "forestry" / "serviceAccountKey.json"))
    ap.add_argument("--skip-download", action="store_true")
    a, passthrough = ap.parse_known_args()

    if a.only:
        plans = a.only
    elif a.skip_download:
        plans = list_local_plans(a.out)
    else:
        plans = list_plans_with_captures(a.key)
    if not plans:
        print("対象の計画がありません (Storage の plans/*/captures/ が空、または DL 済みフォルダが無い)")
        sys.exit(1)
    print(f"[all] 対象 {len(plans)} 計画: {' '.join(plans)}")

    results = []
    for i, plan in enumerate(plans, 1):
        print(f"\n===== [{i}/{len(plans)}] {plan} =====")
        t0 = time.time()
        cmd = [sys.executable, str(HERE / "run_pipeline.py"), "--plan", plan,
               "--out", a.out, "--key", a.key, *passthrough]
        if a.skip_download:
            cmd.append("--skip-download")
        r = subprocess.run(cmd)
        results.append((plan, r.returncode == 0, time.time() - t0))

    print("\n===== 結果 =====")
    ok = 0
    for plan, success, sec in results:
        print(f"  {'OK ' if success else 'NG '} {plan}  ({sec / 60:.1f}分)")
        ok += success
    print(f"成功 {ok} / {len(results)}  (NG は上のログで理由を確認。anchor.json 無し・画像不足は仕様どおりのスキップ)")
    sys.exit(0 if ok == len(results) else 2)


if __name__ == "__main__":
    main()
