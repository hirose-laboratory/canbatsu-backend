# mapping — 作業画像から3Dマップ (幹マップ) を作るサーバーバッチ

アプリが作業中に撮り溜めた**姿勢付き画像** (Firebase Storageの `plans/{planId}/captures/`) から、
訪問の合間にPCで点群→幹マップを作り、Firestoreの `work_plans/{planId}/armap/state` に保存する。
アプリは次の作業開始時にこのマップを読み、**圏外の現地では基準点+幹マップ照合だけ**で
前回の選木マーカーを復元する (重い処理は全部こちら、現地は軽い照合のみ、という分担)。

```
現地(圏外): 画像+順番+姿勢+基準点を蓄積 ──Wi-Fi──> Storage
このバッチ: DL → COLMAP三角測量(姿勢固定) → 点群 → 幹マップ → Firestore(armap)
再訪(圏外): アプリがキャッシュ済みマップを読む → 基準点+照合で復元
```

3DGS (見た目の3D表示) を作りたくなったら、このバッチの中間出力
(`colmap_work/sparse_out` と `points_map.ply`) がそのまま学習の入力になる。

## セットアップ (1回だけ)

1. **COLMAP** を入れる: https://github.com/colmap/colmap/releases から
   Windows版 (colmap-x.x-windows-cuda.zip か no-cuda) を展開し、`colmap.bat` のあるフォルダにパスを通す
   (通さない場合は `--colmap "C:\path\to\colmap.bat"` で指定)
2. Python依存: `pip install -r requirements.txt`
3. `../forestry/serviceAccountKey.json` があること (Firestore/Storageへの管理者アクセス)

## 使い方

作業した日の後、Wi-Fiでアプリのアップロードが済んだら:

```
python run_pipeline.py --plan <計画ID>
```

計画IDは Firebaseコンソール → Firestore → work_plans のドキュメントID。
結果を書き込む前に確認したいときは `--skip-upload` (結果は `captures_dl/<planId>/trees_map.json`)。

## 各スクリプト

| ファイル | 役割 |
|---|---|
| `run_pipeline.py` | 上記の一括実行 |
| `download_captures.py` | Storageから画像+メタをDL |
| `build_map.py` | 1セッションをCOLMAPで3D化 (姿勢固定の三角測量) → マップ座標の点群 `points_map.json` + 確認用 `points_map.ply` |
| `tree_extract.py` | 点群→幹マップ (アプリ内 TreeDetectorMS の忠実な移植。斜面対応・直線除去の保護入り) |
| `upload_map.py` | armap/state へ保存。**既存の選木フラグは0.6m以内の木へ引き継ぎ、対応が無い選木も消さない** |
| `unity_colmap.py` | Unity(左手系)↔COLMAP(右手系) の座標変換と captures.jsonl の読込 |

## 注意・トラブル

- **anchor.json が無いセッションはスキップされる**: 基準点 (音声「きじゅん」/基準点ボタン) を
  セットした作業だけがサーバー3D化の対象。現地で必ず基準点をセットする運用にすること
- **三角測量の点が異常に少ない** (数十点未満): `--flip-v` を付けて再実行。
  それでも少ない場合は歩きながらの撮影でブレている可能性 (静止気味の区間が必要)
- 点群の目視確認は `points_map.ply` をMeshLab等で開く (基準点が原点、+Zが基準方向)
- 処理時間の目安: 1セッション100枚で数分 (CPUのみ)。GPU版COLMAPなら
  `--SiftExtraction.use_gpu 1` に書き換えると速い (build_map.py内)
- Firestoreの1ドキュメント上限は1MB ≒ 木5,000本相当。実用域では届かない
