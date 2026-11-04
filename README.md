# Steamゲームのプレイヤー推移分析

2027年 安形ゼミの卒業研究。Steamゲームの月間平均同時接続数の変化と、同時期のニュース・レビューを照合する。

## Webアプリ

**[Steam Player Observatory を開く](https://steam-player-observatory-roki.roki3i.chatgpt.site)**

収集済み実データを使い、ゲーム名・App ID検索、ジャンル絞り込み、期間切り替え、月次グラフ、最大減少月への移動、前後のニュース表示、月次データ表、CSV保存ができる。月の選択欄・前後ボタン・キーボード対応スライダーから同じ月を操作できる。選択中のゲーム・期間・月・ニュース範囲はURLに反映し、共有ボタンでコピーできる。

「例で試してみる」でDragon's Dogma 2の2024年5月を開ける。「使い方」に操作手順・指標の意味・レポートでの扱い方をまとめた。記事がない期間には、記事と人数の期間が重なる月へ移動するボタンを表示する。

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
node --test web/tests/*.test.mjs
node --check web/app.mjs
node --check web/csv.mjs
```

### 自分のCSVを読み込む

画面右上の「CSVを読み込む」で、プレイヤー数CSVと任意のニュースCSVを選ぶ。UTF-8・カンマ区切り、各20MB以下・20万行以内。入力はブラウザのメモリー内だけで処理し、サーバーへの送信や永続保存は行わない。再読み込みすると研究サンプルに戻る。CSVの内容は共有URLに含まれない。

| 種類 | 必須列 | 任意列・互換形式 |
| --- | --- | --- |
| プレイヤー数 | `appid, name, month, avg_players` | `category, peak_players, collected_at`。`month_date`も可。年月はYYYY-MM・YYYY-MM-DD・英語月名に対応 |
| ニュース | `appid, title, url` と `news_date` または `date` | 日付はYYYY-MM-DDまたはUnix秒。URLはHTTP(S)のみ |

数値が不正・必要な列がない・値が異なる重複などはエラーを表示し、現在表示中のデータを維持する。同値の重複は統合する。ニュースはappidで照合し、対象外の件数を通知する。最大同時接続数が未入力なら「—」を表示する。月次CSVを先に読んだ後、ニュースだけ追加することもできる。入力した文字列はHTMLとして解釈しない。

画面から保存したCSVはゲーム名・App ID・ジャンルを含み、再読込できる。読込画面の「試せるサンプルCSV」は公開用6タイトルの実データを保存する。

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
node --test web/tests/*.test.mjs
```

タイトルの追加は `web/scripts/prepare_data.py` の `APPIDS` と画面のタイトル数表記・テストを更新する。

### 構成・公開

`web/` のHTML・CSS・JavaScriptとJSONだけで動く静的サイト。描画はSVG、計算は `model.mjs`、CSV解析・検証は `csv.mjs`、操作と表示は `app.mjs` に分けている。ニュースは文字列をHTMLとして解釈せず表示する。

GitHub Pagesなどへ公開する場合も、`web/` 内の7ファイル（`index.html`、`style.css`、`app.mjs`、`model.mjs`、`csv.mjs`、`snapshot.json`、`favicon.svg`）を同じ階層に配置すれば動作する。公開先の更新は自動連携していないため、コード変更後は別途再デプロイする。

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
