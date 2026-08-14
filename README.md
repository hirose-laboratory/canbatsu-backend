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


**自分の担当フォルダだけを触る**のが基本で、`ml/pipeline/` は共通なので変更前に相談してね

ルールは [CONTRIBUTING.md](CONTRIBUTING.md)。
