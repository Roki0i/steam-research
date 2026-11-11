# Steam Player Observatory

Steamの**1,000タイトルの月次平均同時接続数**を検索・比較できるデータ分析Webアプリです。大学の研究で収集したデータを使い、変化の傾向を探索します。

**[Webアプリを開く](https://roki0i.github.io/steam-research/)** · [Web CI](https://github.com/Roki0i/steam-research/actions/workflows/web-checks.yml)

## できること

- ゲーム名・App ID・ジャンルで検索し、月次グラフ・前月比・表を表示
- 期間変更、CSV保存、共有リンク、独自CSV（最大20MB・20万行）のブラウザ内読込
- 更新日・取得失敗・観測月の違いを明示。ライト/ダーク表示に対応
- Pythonで**前年同月比とジャンル別の探索的集計**を実行

**技術**：JavaScript ES Modules / SVG / Python / GitHub Pages・Actions。表示データは必要な分割JSONだけを読み込みます。

## ローカルで見る

Python 3、テストにはNode.js 24を使用します。

```bash
python -m http.server 8000 --directory web
node --test web/tests/*.test.mjs
python -m unittest discover -s web/tests -p 'test_*.py'
```

`http://localhost:8000`へアクセスしてください。CSVは `appid,name,month,avg_players` が必須で、`category,peak_players,collected_at` は任意です。読み込んだCSVはブラウザのメモリ内だけで処理し、サーバーへ送信・永続保存しません。

## データから探索する

公開JSONを読むだけで、前年同月比の増減・中央値・カテゴリー別の比較可能数を確認できます。**ネットワークアクセスやデータ更新はしません。**

```bash
python web/scripts/explore_players.py
python web/scripts/explore_players.py --end-month 2026-10 --json
```

基準月の平均が10未満、または比較する月が欠損するゲームは除外します。元CSVはGit管理外。研究側の収集・分析スクリプトはリポジトリ直下にあります。

## データの準備・更新

公開データの目録は `web/snapshot.json`、月次データは `web/data/players-*.json` です。

```bash
python web/scripts/prepare_data.py /path/to/steamcharts_monthly_clean.csv
python web/scripts/update_players.py --diagnostics
python web/scripts/update_players.py --limit 3 --dry-run
```

[Monthly player update](https://github.com/Roki0i/steam-research/actions/workflows/monthly-player-update.yml)は原則毎月2日に実行。push時の3件試験は全件更新ではありません。失敗した取得は旧値を保持し、未処理・失敗の状況を画面と診断に記録します。手動の失敗対象再試行はActionsで `retry_failed=true` を指定します。

**SteamChartsのrobots.txt・アクセス間隔（最低3秒）・403/429・人間確認による停止条件を守り、失敗時に連続して再試行しないでください。**

## 解釈上の制約

- 出典は[SteamCharts](https://steamcharts.com/)。月間**平均同時接続数**は月間の固有人数や個人の離脱率ではなく、変化の原因も示しません。
- 1,000タイトルはSteam全体の無作為標本ではなく、各ゲームの観測期間・取得月が異なります。
- 前月比は連続した月と正の前月平均がある場合だけ計算し、欠損を0として扱いません。
- 公開データはゲーム・人数・出典等の情報で、レビュー本文・投稿者情報は含めません。
