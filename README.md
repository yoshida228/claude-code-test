# claude-code-test

Muse と Claude Code の連携テスト用リポジトリです。

## TimeTree → Googleカレンダー同期

TimeTree の予定を、専用の Google カレンダーへ自動同期する仕組みが
入っています。同期された予定は Muse（Google カレンダー経由）からも
読めるようになります。

- `sync.py` — ICS ファイルを Google カレンダーへ同期するプログラム
- `.github/workflows/sync.yml` — 6時間ごとに自動実行する GitHub Actions
- `SETUP.md` — 鍵（Secrets）の登録手順

流れ:

```
TimeTree
  ↓ timetree-exporter で ICS を取得（GitHub Actions 内）
Google カレンダー（TimeTree同期用）
  ↓
Muse が予定を読める
```

セットアップは [SETUP.md](SETUP.md) を見てください。

注意: これは TimeTree 公式の連携ではありません。非公式ツールを利用する
ため、TimeTree 側の仕様変更で動かなくなることがあります。パスワード等の
鍵は GitHub Secrets にのみ登録し、コードには含めていません。
