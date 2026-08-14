# チームのルール

AIは使っていいけど自分の書いたコードは理解しよう　ちゃんとコミュニケーション取ってやろう

## ブランチ

- `main` に直接pushしない癖をつけよう
`feature/<担当>-<内容>` のブランチを切ろう
  - 例: `feature/tree-detect-dataset`, `feature/rules-update`
  作業はじめるときは
  git fetch
  git pull
  作業終わったら　
  git add .
  git commit -m "作業内容"
  git push origin main

## 触っていい場所

- 基本は**自分の担当フォルダのみ** 触りたい時は他のメンバーと相談しながら

## 置いてはいけないもの

- **秘密鍵・サービスアカウントのJSON**  は絶対にコミットしない　セキュリティとかをちゃんと考えよう
- 学習データセットと学習済みモデルの実体 (数GB) はコミットしない (.gitignoreで設定済み)。研究室のgoogledriveを活用して