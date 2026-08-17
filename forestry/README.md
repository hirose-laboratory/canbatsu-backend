# 森林簿データをFirestoreに入れるところ

林野庁の国有林オープンデータ (小班区画シェープファイル) を変換して、
Firestoreの `forest_registry` コレクションに入れる。
アプリは作業計画の範囲選択時にここを検索して、樹種・林齢を取ってくる。

今は**三重県 (24.zip) だけ**。約4,200小班。

## 手順

```bash
pip install pyshp pyproj firebase-admin

# 1. 24.zipを展開して「24三重県」フォルダのパスを渡す
python convert_shinrinbo.py C:\path\to\24三重県

# 2. serviceAccountKey.json を置いてから (README冒頭のコメント参照)
python upload_forest_registry.py
```

## forest_registry のフィールド (1ドキュメント = 1小班)

| フィールド | 型 | 説明 |
|---|---|---|
| name | string | 林小班名称 (例: "78_林班_ほ") |
| city | string | 市町村 |
| planningArea | string | 森林計画区 (伊賀/北伊勢/南伊勢/尾鷲熊野) |
| species1〜3 | string | 樹種 (スギ/ヒノキ/アカマツ/他Ｌ など) |
| age1〜3 | number | 樹立林齢 (年) |
| volumeM3 | number | 材積 (m³) |
| areaHa | number | 面積 (ha) |
| centerLat / centerLng | number | 中心座標 (アプリの範囲検索に使う) |
| areaPolygon | array\<geopoint\> | 小班の外周 (緯度, 経度) |

⚠ DB担当へ: このコレクション定義を `docs/Firebaseフィールド一覧.md` にも足しておいて

## 他県対応するとき

- 平面直角座標系の系番号が県ごとに違う (convert_shinrinbo.py の EPSG を変える。.prjファイルに書いてある)
- 三重県は第6系 = EPSG:2448 (JGD2000)
