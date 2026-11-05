# Steamゲームのプレイヤー推移分析

2027年 安形ゼミの研究。Steamゲームの月間平均同時接続数の変化を扱う。

## Webアプリ

**[Steam Player Observatoryを開く](https://roki0i.github.io/steam-research/)**

取得済み1,000タイトルの月次人数データを表示する。ゲーム名／App ID検索、ジャンル絞り込み、名前順・保存最終月の人数順、月次グラフ、期間変更、月選択、前後ボタン、キーボード対応スライダー、月次表、CSV保存、共有リンクに対応する。

画面はゲームと人数に絞り、ニュース表示・ニュースCSV読込は含めない。初期選択は一覧先頭ゲームの保存最終月。「例で試してみる」や「使い方」で操作を確認できる。

ライト／ダーク表示はブラウザ・OSの既定設定（`prefers-color-scheme`）に自動追従する。ページを開いたまま設定が変わっても切り替わり、選択状態は維持する。フォーム・表・グラフ・ダイアログも同じ配色に対応。

GitHub Pages（Settings → Pages → Build and deployment → Source: GitHub Actions）で公開する。初回公開には管理者によるPagesの有効化とデプロイ成功の確認が必要。公開URLは上記。\n\n### ローカル起動・検証

Webアプリは外部パッケージ・APIキー不要。Python 3とNode.js 24を使う。

```bash
python -m http.server 8000 --directory web
```

`http://localhost:8000` を開く。ファイルの直接オープンではJSONを取得できないためHTTPサーバーを使用する。

```bash
node --test web/tests/*.test.mjs
node --check web/app.mjs
node --check web/csv.mjs
```

### データの意味

- 出典：[SteamCharts](https://steamcharts.com/)。初期データは2026-08-25収集。以後の取得状況は画面に表示する。研究で取得した1,000タイトルを掲載しており、Steam全体を網羅するデータではない。
- 平均同時接続数は、月間利用者数・ゲーム所有者数・個人の離脱率ではない。表示の人数だけで変化の原因は判断できない。
- 一覧の人数・並び順は、各ゲームの保存最終月の平均同時接続数に基づく。各行に対象年月を表示する。観測期間はゲームごとに異なる。
- 前月比＝（当月平均÷前月平均−1）×100。連続した月があり、前月平均が正の場合のみ計算。表示期間の直前月も元データにあれば比較する。
- GitHub Actionsで毎月2日、日本時間9:23頃に完了済みの暦月を更新する。スケジュールは混雑時に遅延する場合がある。

### 公開用データの管理

`web/snapshot.json` は全タイトルの目録・保存最終月の値・分割先。`web/data/players-*.json` は全1,000タイトルの月次人数。選択したゲームの分割ファイルだけを読み込み、キャッシュする。一覧は50件ずつ追加表示する。元CSVはGit管理外。

公開するのはゲーム名・App ID・ジャンル・観測年月・平均／最大同時接続数・出典・収集日の情報。レビュー・ニュース・投稿者情報は含めない。入力CSVのSHA-256を目録に記録する。

```bash
python web/scripts/prepare_data.py /path/to/steamcharts_monthly_clean.csv
node --test web/tests/*.test.mjs
```

取得済みタイトルをすべて抽出する。公開用タイトルの固定リストは使わない。

### 自分のCSV

「CSVを読み込む」からUTF-8・カンマ区切り、20MB以下・20万行以内のプレイヤー数CSVを選ぶ。

| 必須列 | 任意列・互換形式 |
| --- | --- |
| `appid, name, month, avg_players` | `category, peak_players, collected_at`。`month_date`も可。年月はYYYY-MM・YYYY-MM-DD・英語月名に対応 |

ブラウザのメモリー内だけで処理し、サーバーへ送信・永続保存しない。再読み込みで取得済みデータに戻る。CSV内容は共有リンクに含まれない。

不正な値・列不足・異なる値の重複はエラーを表示して現在のデータを維持する。同値の重複は統合。最大同時接続数が未入力なら「—」を表示。保存するCSVはApp ID・ゲーム名を含み、そのまま再読込できる。「試せるサンプルCSV」は取得済みゲーム1本の実データを保存する。

### 構成・公開

- `app.mjs`：一覧・遅延読込・画面操作・SVG描画
- `model.mjs`：期間・前月比・減少月・CSV出力
- `csv.mjs`：プレイヤー数CSVの解析・検証
- `scripts/prepare_data.py`：公開用データの生成

静的ホスティングには `index.html`、`style.css`、`app.mjs`、`model.mjs`、`csv.mjs`、`dataset.mjs`、`snapshot.json`、`favicon.svg` と **`data/` 全体**を配置する。画面のコード変更は再デプロイが必要。月次データはGitHubの公開JSONを直接読み込むため、データだけの更新では再デプロイ不要。通信失敗時は同梱データへ戻り、その旨を表示する。

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

### 月次データの自動更新

`.github/workflows/monthly-player-update.yml` が公開JSONを更新する。PCの起動やAPIキーは不要。Actionsの「Monthly player update」から手動実行でき、`limit=0` は全1,000タイトル、正の数は動作確認用の件数。収集コード変更時のpushでは3件のみ確認し、全件更新とは区別して表示する。

```bash
python -m unittest discover -s web/tests -p 'test_*.py'
python web/scripts/update_players.py --limit 3 --dry-run
```

SteamChartsの月次表から完了済みの暦月だけを統合する。「Last 30 Days」や当月は除外し、欠損月を0で補完しない。研究用CSVは書き換えない。既存の月次値は収集元の訂正があれば更新する。

アクセス間隔は最低3秒。robots.txtで禁止された場合、403/429や人間確認を検出した場合は停止する。通常の失敗が5件連続した場合も停止。失敗したゲームは元データを保持する。取得結果をActionsのレポートと目録に記録し、失敗・一部成功のジョブは失敗として表示する。全件は約50分以上かかる。

目録の`refresh`に成功件数・対象件数・最終試行日・最終全件成功日、ゲームごとの`lastCheckedAt`に取得確認日を記録する。分割JSONは内容のハッシュを名前に含め、現在と直前世代を保持する。初期データの分割ファイルも残す。入力CSVのハッシュは`baselineInputSha256`として保持する。
