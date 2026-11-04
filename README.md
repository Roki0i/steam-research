# Steamゲームのプレイヤー推移分析

2027年 安形ゼミの卒業研究。Steamゲームの月間平均同時接続数の変化と、同時期のニュース・レビューを照合する。

## Webアプリ

**[Steam Player Observatory を開く](https://steam-player-observatory-roki.roki3i.chatgpt.site)**

収集済み実データを使い、ゲーム検索、期間切り替え、月次グラフ、最大減少月への移動、前後のニュース表示、月次データ表、CSV保存ができる。選択中のゲーム・期間・月・ニュース範囲はURLに反映する。

対象はCyberpunk 2077、Dragon's Dogma 2、Black Myth: Wukong、PAYDAY 3、Tiny Glade、The Crew 2の6タイトル。公開用に選んだ一部であり、Steam全体を代表する標本ではない。

### ローカル起動

Python 3で、リポジトリのルートから実行する。Webアプリ自体に外部パッケージやAPIキーは不要。

```bash
python -m http.server 8000 --directory web
```

ブラウザで `http://localhost:8000` を開く。`index.html` の直接オープンではJSONを読み込めないため、HTTPサーバーを使う。

### 検証

Node.js 24で実行する。外部依存なし。

```bash
node --test web/tests/model.test.mjs
node --check web/app.mjs
```

### データと計算

- プレイヤー数の出典は [SteamCharts](https://steamcharts.com/)。2026-08-25に収集したCSVから6タイトル・276か月分を抽出。観測期間はゲームごとに異なる。
- ニュースは研究用に保存したSteamニュースの一部から、公開記事のタイトル・日付・URLの589件を抽出。本文、投稿者、レビュー、ユーザーIDは含めない。記事タイトルは原文のまま表示する。
- `web/snapshot.json` は公開用の抜粋。元CSVは引き続きGit管理外。公開ファイルには入力ファイル名とSHA-256を記録する。
- 前月比は `(当月平均 / 前月平均 - 1) × 100`。連続する暦月があり、前月の平均が0より大きいときのみ計算。表示期間の先頭月も、元データに直前月があれば比較する。
- 最大減少月は表示期間内の負の前月比の最小値。研究スクリプトの「ピーク後3〜12か月」の条件とは別の、画面探索用の指標。
- ニュース範囲は選択月の前後0〜2暦月。ニュース未表示は、出来事がなかったことを意味しない。
- 平均同時接続数は月間利用者数・個人の離脱率ではない。時間的一致だけから因果関係を断定しない。
- 保存済みスナップショットであり、自動更新は行わない。

元CSVから公開用データを再生成する場合：

```bash
python web/scripts/prepare_data.py /path/to/steamcharts_monthly_clean.csv /path/to/factor_news_12m.csv
node --test web/tests/model.test.mjs
```

タイトルの追加は `web/scripts/prepare_data.py` の `APPIDS` と画面のタイトル数表記・テストを更新する。

### 構成・公開

`web/` のHTML・CSS・JavaScriptとJSONだけで動く静的サイト。描画はSVG、計算は `model.mjs`、操作と表示は `app.mjs` に分けている。ニュースは文字列をHTMLとして解釈せず表示する。

GitHub Pagesなどへ公開する場合も、`web/` 内の6ファイル（`index.html`、`style.css`、`app.mjs`、`model.mjs`、`snapshot.json`、`favicon.svg`）を同じ階層に配置すれば動作する。公開先の更新は自動連携していないため、コード変更後は別途再デプロイする。

## 研究スクリプト

研究データは `data/`（ColabではGoogle Drive上のデータディレクトリ）で扱う。CSVはGit管理しない。

```bash
python -m pip install -r requirements.txt
```

- `game_candidates_collect.py`：ゲーム候補の収集
- `steamcharts_collect.py`：月次同時接続数の収集
- `steam_collect.py`：プレイヤー数・レビュー・ニュースの収集
- `decline_analysis.py`：減少傾向の集計
- `factor_data_collect.py` / `factor_news_collect_3to12.py`：要因調査用データの収集
- `factor_analysis.py` / `04_statistical_analysis.py`：要因・統計分析
- `jev_*.py`：ニュース分類・人手評価用処理

各スクリプトの入力ファイル名・収集条件はコード内の定数を確認する。既存研究の統計分析はWebアプリのテスト対象には含まない。
