# CAN伐 バックエンド (2026プロコン)

ARグラスで使う **AIモデルの学習・変換** と **Firebaseの設定管理** をまとめるリポジトリ。

---

## システムの全体像

サーバーは立てない　AIは端末内 (エッジ処理)、データはFirebaseに直接読み書きする

```
[XREAL Eye カメラ] → [XREAL Beam Pro: Unityアプリ + Sentis(AI推論)]
                            │  ONNXモデルを同梱 ←━━ このリポジトリで学習・変換
                            │
                            └→ Firebase Auth / Firestore に直接読み書き
                               (work_plans / work_records) ←━ ルール等を firebase/ で管理
```

- モデルの配布は**ONNXファイルをUnityプロジェクトに同梱**する方式でやりたい
- `forestry/` = 森林簿 (国有林オープンデータ) をFirestoreに入れる変換スクリプト。
  アプリはここで入れた `forest_registry` から樹種・林齢を取って間伐の目安値を自動算出する (今は三重県のみ)


**自分の担当フォルダだけを触る**のが基本で、`ml/pipeline/` は共通なので変更前に相談してね

ルールは [CONTRIBUTING.md](CONTRIBUTING.md)。
