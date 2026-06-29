# スポカレ 毎日更新Webページ

この一式をGitHub Pagesに置くと、毎日0時に「その日＋翌日」の2日分へ更新されるスポーツ中継予定ページになります。

## ファイル構成

- `index.html`
  - 前回と同じ2カラムのスポカレ風レイアウトです。
  - `data/schedule.json` を読み込み、日本時間の当日＋翌日だけを表示します。
  - 各予定に「Googleカレンダー追加」「タスク用コピー」ボタンがあります。

- `index_html_for_copy.txt`
  - GitHub上で `index.html` を差し替えるときにコピーしやすいテキスト版です。
  - 中身は `index.html` と同じです。

- `data/schedule.json`
  - 予定データです。
  - 初期データとして、2026年6月29日・6月30日分を入れています。

- `scripts/update_from_spocale.py`
  - スポカレ対象URLを確認して、実行日当日＋翌日の予定へ更新します。
  - 取得結果が0件の場合、空データで上書きしない安全装置つきです。

- `.github/workflows/update.yml`
  - GitHub Actionsで毎日0時（日本時間）に更新する設定です。

## GitHubへの反映方法

既存の `spocale-schedule` リポジトリに、ZIP内のファイルを上書きしてください。

特に差し替えるもの:

- `index.html`
- `data/schedule.json`
- `scripts/update_from_spocale.py`
- `.github/workflows/update.yml`
- `requirements.txt`

GitHubで直接編集する場合、`index.html` は `index_html_for_copy.txt` の中身をコピーして貼り付けると簡単です。

## 更新タイミング

毎日、日本時間0:00にGitHub Actionsが実行されます。

例:

- 6月29日 0:00 → 6月29日・6月30日
- 6月30日 0:00 → 6月30日・7月1日
- 7月1日 0:00 → 7月1日・7月2日

## 注意

スポカレ側のHTML構造が変わった場合、取得スクリプトの調整が必要になることがあります。
