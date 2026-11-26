# セットアップ手順（TimeTree → Googleカレンダー同期）

プログラムは完成しています。あとは「鍵」を4つ、GitHub の Secrets に
登録するだけです。鍵をコードやチャットに書くことは絶対にしないでください。

所要時間の目安: 15〜20分

---

## 手順1: 同期専用の Google カレンダーを作る

1. Google カレンダー（calendar.google.com）を開く
2. 左側「他のカレンダー」の「＋」→「新しいカレンダーを作成」
3. 名前は「TimeTree同期用」など。作成する
4. そのカレンダーの「設定」→「カレンダーの統合」にある
   **カレンダー ID** をメモする（〜@group.calendar.google.com の形）
   → あとで Secret 名 `GOOGLE_CALENDAR_ID` に登録します

※ このカレンダーは同期専用にしてください。同期プログラムは
「TimeTree から消えた予定」をこのカレンダーから削除します。

## 手順2: Google のサービスアカウントを作る

プログラムが Google カレンダーへ書き込むための専用アカウントです。

1. Google Cloud Console（console.cloud.google.com）で新しいプロジェクトを作成
2. 「APIとサービス」→「ライブラリ」で **Google Calendar API** を有効化
3. 「IAMと管理」→「サービス アカウント」→「サービス アカウントを作成」
   （名前は timetree-sync など）
4. 作成したサービスアカウントの「キー」→「鍵を追加」→「新しい鍵を作成」
   → JSON を選ぶとファイルがダウンロードされます
   - この JSON の中身全体が Secret 名 `GOOGLE_SERVICE_ACCOUNT_JSON` です
   - サービスアカウントのメールアドレス（〜@〜.iam.gserviceaccount.com）もメモ
5. 手順1のカレンダーの「設定」→「特定のユーザーまたはグループと共有する」で、
   そのメールアドレスを追加し、権限を「予定の変更」にする

## 手順3: TimeTree のカレンダーコードを調べる

1. パソコンのブラウザで TimeTree Web版（timetreeapp.com）にログイン
2. 同期したいカレンダーを開く
3. カレンダーの共有リンク／設定に表示される英数字のコードが
   カレンダーコードです
   → Secret 名 `TIMETREE_CALENDAR_CODE` に登録します

※ 見つからない場合は、無理に探さず Muse に相談してください。
初回だけコードなしで実行し、ログで確認する方法もあります。

## 手順4: GitHub に Secrets を登録する

このリポジトリの Settings → Secrets and variables → Actions →
「New repository secret」から、次の4つを1つずつ登録します。

| Secret 名 | 中身 |
|---|---|
| `TIMETREE_EMAIL` | TimeTree にログインするメールアドレス |
| `TIMETREE_PASSWORD` | TimeTree のパスワード |
| `TIMETREE_CALENDAR_CODE` | 手順3のカレンダーコード |
| `GOOGLE_CALENDAR_ID` | 手順1のカレンダー ID |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | 手順2でダウンロードした JSON の中身全体 |

## 手順5: 動かしてみる

1. このリポジトリの Actions タブを開く
2. 「TimeTree to Google Calendar sync」→「Run workflow」
3. 緑のチェックが付けば成功です。Google カレンダーを開いて
   予定が入っているか確認してください
4. 以後は6時間ごとに自動で同期されます

---

## 注意

- この仕組みは TimeTree 公式の連携ではありません。TimeTree の Web 版を
  使う非公式ツール（timetree-exporter）を利用しているため、TimeTree 側の
  仕様変更で突然動かなくなることがあります。
- パスワードなどの鍵は Secrets のみに登録し、コード、Issue、チャットには
  書かないでください。
- うまくいかないときは、Actions の実行ログの内容を Muse に見せてください
  （鍵そのものはログに表示されません）。
