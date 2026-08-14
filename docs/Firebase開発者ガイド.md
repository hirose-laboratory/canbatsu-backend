# CAN伐 Firebase 開発者ガイド(機能担当者向け)

作成: DB設計担当 / 2026-08-13
対象: ログイン・作業計画・作業記録・AR/AIの各機能を実装する人
前提: Unity + Firebase Unity SDK(FirebaseAuth / FirebaseFirestore)
フィールドの正式な定義は `フィールド一覧.md` を参照(フィールド名はそこからコピペすること)

---

## 0. 全体像

使うFirebaseサービスは2つ:

- **Firebase Authentication** … ログイン係(登録・照合・ログイン状態の保持)
- **Cloud Firestore** … データ保管係(users / work_plans / work_records の3コレクション)

```
[ログイン機能] ──> Authentication(+usersに表示名を保存)
[作業計画機能] ──> work_plans に書く
[自動選木/AI]  ──> work_plans を読む(しきい値を判定に使う)※AI判定結果はDBに保存しない
[作業記録機能] ──> work_records に書く / 読む
```

## 1. 最初のセットアップ(全員共通・1回だけ)

1. Firebaseコンソールでプロジェクト作成 → Unityアプリを登録 → `google-services.json`(Android)を取得してUnityプロジェクトに配置
2. Firebase Unity SDK を導入(FirebaseAuth.unitypackage, FirebaseFirestore.unitypackage)
3. コンソールで **Authentication > ログイン方法 > メール/パスワード を有効化**
4. コンソールで **Firestore Database を作成**(本番モード) → セキュリティルールは下記§6を設定
5. オフラインキャッシュはモバイルでは**初期状態で有効**。無効化しないこと

```csharp
using Firebase.Auth;
using Firebase.Firestore;

FirebaseAuth auth = FirebaseAuth.DefaultInstance;
FirebaseFirestore db = FirebaseFirestore.DefaultInstance;
```

## 2. ログイン機能の人

### 新規登録(圏内でのみ可能)

```csharp
// 1. Authに登録(パスワードはFirebaseが預かる。Firestoreには絶対保存しない)
var result = await auth.CreateUserWithEmailAndPasswordAsync(email, password);
string uid = result.User.UserId;

// 2. 表示用ユーザー名を users コレクションに保存(ドキュメントID = UID)
await db.Collection("users").Document(uid).SetAsync(new Dictionary<string, object> {
    { "username", username },
    { "createdAt", FieldValue.ServerTimestamp }
});
```

### ログイン(圏内でのみ可能。ログイン状態は端末に残る)

```csharp
await auth.SignInWithEmailAndPasswordAsync(email, password);
// 以降どこからでも: auth.CurrentUser.UserId で「今誰か」が取れる
// アプリ再起動後も auth.CurrentUser は残っている(＝山で再ログイン不要)
```

⚠ **山へ行く前日に必ず一度ログインしておく運用**をユーザーに案内すること。

## 3. 作業計画機能の人

### 計画を保存する(計画作成画面の「保存」ボタン)

```csharp
DocumentReference doc = await db.Collection("work_plans").AddAsync(new Dictionary<string, object> {
    { "scheduledDate", Timestamp.FromDateTime(scheduledDate.ToUniversalTime()) },
    { "species", "スギ" },                    // 任意。無ければ入れなくてよい
    { "thinningRate", 0.3 },                  // 30%は0.3で保存(パーセントの30ではない)
    { "areaHa", 1.5 },
    { "spacingThresholdM", 2.5 },
    { "diameterThresholdCm", 18.0 },
    { "areaPolygon", new List<object> {       // 3点以上。頂点を結んだ多角形が範囲
        new GeoPoint(36.10, 137.25),
        new GeoPoint(36.11, 137.25),
        new GeoPoint(36.11, 137.26)
    }},
    { "createdBy", auth.CurrentUser.UserId },
    { "createdAt", FieldValue.ServerTimestamp }
});
string planId = doc.Id;  // 自動生成ID。作業記録との紐づけに使う
```

### 計画一覧を読む(一覧画面・AR側への受け渡し)

```csharp
QuerySnapshot snap = await db.Collection("work_plans")
                             .OrderByDescending("scheduledDate")
                             .GetSnapshotAsync();
foreach (DocumentSnapshot d in snap.Documents) {
    string planId = d.Id;
    double rate    = d.GetValue<double>("thinningRate");
    double diamCm  = d.GetValue<double>("diameterThresholdCm");
    var polygon    = d.GetValue<List<GeoPoint>>("areaPolygon");
}
```

⚠ **この読み込みを圏内で一度実行するとキャッシュに写しが残り、山(圏外)でも同じコードがそのまま動く**。「出発前に計画一覧を開いてもらう」のが事前同期になる。

## 4. 自動選木・AI危険予知の人

- **読むだけ**: 選択された計画の `thinningRate` / `spacingThresholdM` / `diameterThresholdCm` を判定の入力に使う
- **書かない**: 1本ごとの判定結果(伐る/残す、かかり木など)はDBに保存しない(その場のAR表示のみ)
- 伐採本数のカウントを実装する場合は、カウント値を作業記録機能に渡す(直接DBに書かず、記録の保存に含めてもらう)

```csharp
DocumentSnapshot plan = await db.Collection("work_plans").Document(planId).GetSnapshotAsync();
double diameterThreshold = plan.GetValue<double>("diameterThresholdCm");  // これ未満の木が伐採対象
```

## 5. 作業記録機能の人

### 記録を保存する(作業終了時。圏外でもこのまま動く)

```csharp
db.Collection("work_records").AddAsync(new Dictionary<string, object> {
    { "planId", planId },                     // どの計画の作業か(取れない場合は省略可)
    { "workDate", Timestamp.FromDateTime(DateTime.UtcNow) },
    { "felledCount", 43 },                    // 実装できたら。無ければ省略可
    { "actualThinningRate", 0.28 },
    { "areaHa", 0.8 },
    { "areaPolygon", polygonPoints },         // List<object>のGeoPoint、3点以上
    { "createdBy", auth.CurrentUser.UserId },
    { "createdAt", FieldValue.ServerTimestamp }
});
// ⚠ 圏外では await しない(完了通知は電波が戻るまで来ない)。
// 保存はローカルに即反映され、圏内復帰後に自動でクラウドへ送信される。
```

### 記録を読む(記録一覧・AR表示・「前回どこまでやったか」)

```csharp
// 全記録を新しい順に
QuerySnapshot snap = await db.Collection("work_records")
                             .OrderByDescending("workDate")
                             .GetSnapshotAsync();

// 特定の計画の記録だけ(計画vs実績の比較画面)
QuerySnapshot snap2 = await db.Collection("work_records")
                              .WhereEqualTo("planId", planId)
                              .GetSnapshotAsync();
```

## 6. セキュリティルール(DB担当がコンソールに設定)

Firestore > ルール に以下を設定(「ログイン済みユーザーのみ読み書き可」):

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if request.auth != null;
    }
  }
}
```

⚠ テストモードのまま放置すると**30日後に全アクセス拒否になりアプリが突然動かなくなる**。早めに上記を設定する。

## 7. オフライン運用の約束(全員)

1. **前日までに圏内で**: ログイン + 計画を作成 + 計画一覧を一度開く(=キャッシュ作成)
2. **山では**: そのまま使う。読み書きともキャッシュで動く。特別な処理は不要
3. **書き込みは await で完了を待たない**(圏外では完了しないため)。エラー表示も「送信待ち」扱いにする
4. **日時は FieldValue.ServerTimestamp** を使う(workDateなど「ユーザーが選ぶ日付」はTimestamp型でOK)
5. 帰宅後にアプリを一度起動すれば自動同期される(ユーザー操作不要)

## 8. よくあるハマりどころ

- **フィールド名のタイプミス** … Firestoreは事前定義がないので、`thiningRate`と打っても普通に保存されてしまい、読む側で見つからない。フィールド名は必ず`フィールド一覧.md`からコピペ
- **間伐率の単位** … 0.3(=30%)で統一。30と入れる人が混ざると集計が壊れる
- **GeoPointの引数順** … (緯度, 経度)の順。逆にすると日本の山が海になる
- **Timestampのタイムゾーン** … `ToUniversalTime()`してから`Timestamp.FromDateTime()`に渡す
