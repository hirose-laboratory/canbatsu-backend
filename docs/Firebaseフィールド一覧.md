# CAN伐 Firebase(Firestore) コレクション構成・フィールド一覧

作成: DB設計担当 / 2026-08-13 (Firebase版に改訂)
DB: Cloud Firestore + Firebase Authentication(ログイン)

## 全体構成(3コレクション)

```
users(ユーザー情報)   work_plans(作業計画) ──< work_records(作業記録)
 ※ログイン自体はFirebase Authenticationが担当。       ※記録のplanIdで計画と紐づけ(任意)
   usersはユーザー名などの追加情報だけ持つ
```

- ドキュメントIDはFirestoreの**自動生成**を使う(「適当なid」はこれで解決。連番は使わない)
- フィールド名はFirestoreの慣習に合わせて**camelCase**(小文字始まり・単語の頭を大文字)

---

## 0. ログインについて(重要)

パスワードは**Firestoreに保存しない**。ログインは **Firebase Authentication(メール/パスワード方式)** を使う。

- パスワードの保管・照合はFirebaseが安全にやってくれる(自前実装より安全で、実装も楽)
- Authに登録すると各ユーザーに **UID**(ユーザー固有ID)が発行される
- ユーザー名などアプリで使う追加情報は、UIDをドキュメントIDにして`users`コレクションに保存する

## 1. users(ユーザー情報)

ドキュメントID = **Firebase AuthのUID**(自動生成IDは使わない。Authと1対1で繋げるため)

| フィールド | 型 | 必須 | 説明 | 例 |
|---|---|---|---|---|
| username | string | ○ | 表示用のユーザー名 | "hirose" |
| createdAt | timestamp | ○ | 登録日時 | 2026-08-13 14:30 |

## 2. work_plans(作業計画)

ドキュメントID = 自動生成

| フィールド | 型 | 必須 | 説明 | 例 |
|---|---|---|---|---|
| scheduledDate | timestamp | — | 作業予定日 | 2026-09-01 |
| species | string | — | 樹種(任意。無ければ省略可) | "スギ" |
| thinningRate | number | — | 間伐率(0.3 = 30%) | 0.3 |
| areaHa | number | — | 面積(ha) | 1.5 |
| spacingThresholdM | number | — | 伐採間隔のしきい値(m) | 2.5 |
| diameterThresholdCm | number | — | 伐採基準: この直径(cm)未満の木を伐る | 18.0 |
| areaPolygon | array\<geopoint\> | — | 選択した範囲。GeoPoint(緯度,経度)の配列、**3点以上**で多角形 | [GeoPoint(36.10,137.25), GeoPoint(36.11,137.25), GeoPoint(36.11,137.26)] |
| createdBy | string | — | 作成したユーザーのUID(提案項目) | "xK9f…" |
| createdAt | timestamp | ○ | 作成日時 | 2026-08-13 14:30 |

## 3. work_records(作業記録)

ドキュメントID = 自動生成

| フィールド | 型 | 必須 | 説明 | 例 |
|---|---|---|---|---|
| planId | string | — | 対応する作業計画のドキュメントID(**提案項目**・省略可。入れると計画vs実績の比較が可能) | "8fKz3…" |
| workDate | timestamp | — | 作業日 | 2026-09-01 |
| felledCount | number | — | 伐採本数(実装できたら。省略可) | 43 |
| actualThinningRate | number | — | 実施した間伐率 | 0.28 |
| areaHa | number | — | 作業面積(ha) | 0.8 |
| areaPolygon | array\<geopoint\> | — | 作業した範囲(work_plansと同形式) | [GeoPoint(…), …] |
| createdBy | string | — | 記録したユーザーのUID(提案項目) | "xK9f…" |
| createdAt | timestamp | ○ | 記録日時 | 2026-09-01 16:45 |

---

## ドキュメントの実例(こう保存される)

```
work_plans/8fKz3aBcDeF   ← コレクション名/自動生成されたドキュメントID
{
  scheduledDate: 2026年9月1日 00:00 (timestamp),
  species: "スギ",
  thinningRate: 0.3,
  areaHa: 1.5,
  spacingThresholdM: 2.5,
  diameterThresholdCm: 18.0,
  areaPolygon: [ [36.10° N, 137.25° E], [36.11° N, 137.25° E], [36.11° N, 137.26° E] ],
  createdBy: "xK9fQ2rT...",
  createdAt: 2026年8月13日 14:30 (timestamp)
}
```

## アプリ担当への申し送り

1. **Firestoreは事前のテーブル定義が不要** — この一覧の名前・型のとおりに保存してくれれば、コレクションは自動でできます(逆に言うと**タイプミスがそのまま別フィールドになる**ので、フィールド名はこの一覧からコピペ推奨)
2. ログインは**Firebase Authentication(メール/パスワード)** を使用。パスワードをFirestoreに書かないこと
3. Unity用のFirebase SDKが公式にあります(FirebaseAuth + FirebaseFirestore)
4. **オフライン対策**: Firestoreの「オフラインキャッシュ(persistence)」を必ず有効化。山では圏外の可能性が高く、事前に(圏内で)ログイン+データ取得しておき、現地ではキャッシュで動作→帰宅後に自動同期、という運用になります
5. **セキュリティルール設定が必須** — 初期設定のままだと誰でも読み書きできる/一定期間後に全拒否になる。最低限「ログイン済みユーザーのみ読み書き可」に設定(DB担当と一緒に設定しましょう)

## 未決事項(チームに確認したい)

- [ ] ログインはFirebase Authentication利用でよいか?(パスワード自前保存は非推奨)
- [ ] Authのログイン方式: メールアドレス+パスワードでよいか?(ユーザー名だけの運用なら「ユーザー名@can-batsu.local」のような形式で内部的にメール化する手もある)
- [ ] planId(計画との紐づけ)・createdBy(誰が作ったか)の提案項目を採用するか?
- [ ] 完全オフライン動作(予選資料の売り)とFirebaseの相性 — 圏外運用の検証をいつやるか
