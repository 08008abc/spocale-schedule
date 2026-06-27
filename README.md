# 今日・明日のスポーツ予定 Webページ

このフォルダは、スポカレ対象URLの予定を表示するWebページ一式です。

## ファイル

- `index.html`：表示ページ本体
- `data/schedule.json`：表示する予定データ
- `scripts/update_from_spocale.py`：毎日更新用の取得スクリプト雛形
- `.github/workflows/update.yml`：GitHub Actionsで毎日0時台に更新する設定例

## 使い方

1. このフォルダをGitHubリポジトリに入れる
2. GitHub Pagesを有効化する
3. `scripts/update_from_spocale.py` の取得ロジックを必要に応じて調整する
4. GitHub Actionsを有効化する

## 注意

スポカレのHTML構造が変わると取得スクリプトは調整が必要です。
このテンプレートでは、Webページ側は `data/schedule.json` を読み込んで「今日・明日」だけを自動表示します。
