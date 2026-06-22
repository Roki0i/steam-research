# steam-research

Steamゲームが過疎る理由・共通点を、カテゴリ別に分析するための研究用Pythonプロジェクトです。

本プロジェクトでは、Steam上の複数カテゴリのゲームを対象に、カテゴリ別ゲーム候補、現在の同時接続者数、レビュー概要、生レビュー、Steamニュース、SteamCharts月次データを取得し、CSV形式で保存します。取得したデータを継続的に蓄積することで、カテゴリごとのプレイヤー数の変化や、レビュー・ニュースとプレイヤー離脱の関係を分析するための基礎データを作成します。

---

## 1. 研究背景

近年、Steamでは多様なジャンルのゲームが長期的に運営・販売されています。一方で、発売直後や大型アップデート後にプレイヤー数が増加しても、その後プレイヤーが減少していくゲームも多く存在します。

プレイヤー離脱には、ゲームカテゴリ、レビュー評価、プレイ体験、アップデート頻度、ニュースやイベント情報など、複数の要因が関係していると考えられます。

本研究では、Steam上のゲームデータを収集し、カテゴリごとにプレイヤー離脱傾向がどのように異なるかを分析することを目的とします。

---

## 2. 研究目的

本研究の目的は、Steamゲームが過疎る理由・共通点を、カテゴリ別に分析することです。

具体的には、以下のデータを収集します。

* カテゴリ別のゲーム候補
* 現在の同時接続者数
* レビュー概要
* 生レビュー
* Steamニュース
* SteamCharts月次プレイヤー数

これらのデータを継続的に蓄積し、カテゴリごとのプレイヤー数の推移や、レビュー評価・ニュース情報との関係を比較します。

---

## 3. リサーチクエスチョン

本研究では、以下の問いを扱います。

1. Steamゲームのカテゴリによって、プレイヤー数の減少傾向に違いはあるか。
2. レビュー評価やレビュー内容は、プレイヤー離脱傾向と関係しているか。
3. Steamニュースやアップデート情報は、プレイヤー数の維持・回復に関係しているか。
4. 継続的にプレイヤーを維持しやすいカテゴリと、離脱が起きやすいカテゴリにはどのような違いがあるか。

---

## 4. 現在の位置づけ

このリポジトリは、卒業研究のうち **データ収集基盤** にあたります。

現段階では、Steam APIからデータを取得し、分析用CSVとして保存する処理を実装しています。今後は、取得したデータを日次または週次で蓄積し、プレイヤー数の時系列変化やレビュー情報との関係を分析します。

---

## 5. 収集対象データ

| データ       | 内容                  | 保存ファイル                |
| --------- | ------------------- | --------------------- |
| ゲーム候補 | Steam Storeのタグ検索ページから集めたカテゴリ別候補 | `game_candidates.csv` |
| 現在の同時接続者数 | 各ゲームの現在プレイヤー数       | `current_players.csv` |
| SteamCharts月次プレイヤー数 | 過去の月次平均・増減・ピークプレイヤー数 | `steamcharts_monthly.csv` |
| レビュー概要    | レビュー評価、肯定・否定レビュー数など | `review_summary.csv`  |
| 生レビュー     | ユーザーが投稿したレビュー本文や評価  | `reviews_raw.csv`     |
| Steamニュース | ゲームごとのニュース・アップデート情報 | `news.csv`            |

---

## 6. 対象ゲームとカテゴリ

`games.py` に定義している12本の手入力ゲームは、収集処理を確認するための試作用データです。

本分析では、`game_candidates_collect.py` で作成する `data/game_candidates.csv` を使います。候補収集はSteamSpy APIではなく、Steam Storeの公開タグ検索結果を使います。

方針は **10カテゴリ × 各カテゴリ最大100本** で、最大1000本のゲーム候補を自動収集します。現在の初期値は動作確認用に **10カテゴリ × 各カテゴリ最大10本** です。動作確認後、`MAX_GAMES_PER_CATEGORY = 100` に変更します。

採用カテゴリは以下です。

1. FPS / Shooter
2. Action
3. RPG
4. Strategy
5. Simulation
6. Survival / Open World
7. Horror / Mystery
8. Sports / Racing
9. Casual / Puzzle
10. Co-op / Multiplayer

`steamcharts_collect.py` は、`data/game_candidates.csv` が存在する場合はそれを優先して読みます。存在しない場合は、従来通り `games.py` の `GAMES` を読みます。

### 試作用ゲーム

### core：本採用ゲーム

| ゲーム名                |   appid | ジャンル          |
| ------------------- | ------: | ------------- |
| Counter-Strike 2    |     730 | FPS           |
| Team Fortress 2     |     440 | FPS           |
| Apex Legends        | 1172470 | Battle Royale |
| PUBG: BATTLEGROUNDS |  578080 | Battle Royale |
| Dota 2              |     570 | MOBA          |
| SMITE               |  386360 | MOBA          |
| Path of Exile       |  238960 | RPG           |
| ELDEN RING          | 1245620 | RPG           |
| Rust                |  252490 | Survival      |
| Palworld            | 1623730 | Survival      |
| Dead by Daylight    |  381210 | Horror        |
| Lethal Company      | 1966720 | Horror        |

### reserve：予備ゲーム

| ゲーム名            |   appid | ジャンル       |
| --------------- | ------: | ---------- |
| Stardew Valley  |  413150 | Simulation |
| Factorio        |  427520 | Simulation |
| TEKKEN 8        | 1778820 | Fighting   |
| Forza Horizon 5 | 1551360 | Racing     |

---

## 7. ファイル構成

```text
steam-research/
├── games.py
├── game_candidates_collect.py
├── steam_collect.py
├── steamcharts_collect.py
├── requirements.txt
├── README.md
├── .gitignore
└── data/
```

| ファイル               | 内容                             |
| ------------------ | ------------------------------ |
| `games.py`         | 試作用の手入力ゲーム一覧を定義                  |
| `game_candidates_collect.py` | Steam Storeのタグ検索結果からカテゴリ別ゲーム候補を収集するプログラム |
| `steam_collect.py` | Steam APIからデータを取得しCSV保存するプログラム |
| `steamcharts_collect.py` | SteamChartsから過去の月次プレイヤー数を取得しCSV保存するプログラム。`game_candidates.csv` があれば優先して読む |
| `requirements.txt` | 使用するPythonライブラリ                |
| `README.md`        | 研究目的・実行方法・構成説明                 |
| `.gitignore`       | GitHubに含めないファイルの設定             |
| `data/`            | CSV保存先。GitHubには含めない            |

---

## 8. 使用技術

* Python
* requests
* pandas
* BeautifulSoup
* GitHub
* Google Colab
* Google Drive

---

## 9. 実行環境

開発はMacBookで行い、最終的なデータ収集はGoogle Colab上で実行します。

Google Driveがマウントされている場合、CSVは以下に保存されます。

```text
/content/drive/MyDrive/卒業研究/steam_research/data
```

Google Driveがない環境では、ローカルの以下に保存されます。

```text
./data
```

---

## 10. Google Colabでの実行手順

Google Colabで以下を順番に実行します。

### Google Driveをマウント

```python
from google.colab import drive
drive.mount('/content/drive')
```

### GitHubからclone

```python
%cd /content
!rm -rf steam-research
!git clone https://github.com/Roki0i/steam-research.git
%cd /content/steam-research
```

### 必要ライブラリをインストール

```python
!pip install -r requirements.txt
```

### 本分析用のゲーム候補を収集

```python
!python game_candidates_collect.py
```

### SteamCharts月次データを収集

```python
!python steamcharts_collect.py
```

`game_candidates.csv` が存在する場合、`steamcharts_collect.py` はその候補一覧を優先して読みます。存在しない場合は、試作用の `games.py` を読みます。

### 既存のSteam APIデータ収集を実行する場合

```python
!python steam_collect.py
```

### 保存結果を確認

```python
!ls -la "/content/drive/MyDrive/卒業研究/steam_research/data"
```

---

## 11. MacBookでの実行手順

```bash
cd ~/projects/steam-research
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python game_candidates_collect.py
python steam_collect.py
python steamcharts_collect.py
```

---

## 12. 設定項目

`game_candidates_collect.py` の上部で、本分析用の候補収集カテゴリとカテゴリごとの最大本数を変更できます。`CATEGORY_TAGS` は分析カテゴリと対応Steamタグの定義です。検索時はSteam Storeタグ検索用のタグIDを使い、SteamSpy APIは使いません。

```python
TARGET_CATEGORIES = list(CATEGORY_TAGS.keys())
MAX_GAMES_PER_CATEGORY = 10
```

動作確認後、本番収集では以下のように変更します。

```python
MAX_GAMES_PER_CATEGORY = 100
```

一部カテゴリだけ集める場合：

```python
TARGET_CATEGORIES = ["RPG", "Strategy"]
```

`steam_collect.py` の上部で、試作用ゲームの収集対象やレビュー取得量を変更できます。

```python
TARGET_TYPES = ["core"]
MAX_REVIEW_PAGES = 1
```

### TARGET_TYPES

本採用ゲームのみ収集する場合：

```python
TARGET_TYPES = ["core"]
```

予備ゲームも含める場合：

```python
TARGET_TYPES = ["core", "reserve"]
```

### MAX_REVIEW_PAGES

`MAX_REVIEW_PAGES` は、生レビューを何ページ取得するかを指定します。
1ページあたり最大100件です。

値を大きくすると取得件数は増えますが、実行時間も長くなります。

### SteamCharts月次データの設定

`steamcharts_collect.py` は、`data/game_candidates.csv` がある場合は `appid`, `name`, `category` を読み、カテゴリ別のSteamCharts月次データを保存します。

候補CSVがない場合は、従来通り `games.py` を読みます。この場合は `steamcharts_collect.py` の上部で、収集対象を変更できます。

```python
TARGET_TYPES = ["core"]
REQUEST_INTERVAL_SEC = 3.0
```

本採用ゲームのみ収集する場合：

```python
TARGET_TYPES = ["core"]
```

予備ゲームも含める場合：

```python
TARGET_TYPES = ["core", "reserve"]
```

`REQUEST_INTERVAL_SEC` はSteamChartsへのアクセス間隔です。過度なアクセスを避けるため、初期値は3.0秒にしています。

---

## 13. SteamCharts月次データ

Steam公式APIでは、過去の同時接続者数の月次推移を取得できません。そのため、過去プレイヤー数の月次データとしてSteamChartsの各ゲームページを参照します。

SteamChartsはValve公式サービスではありません。研究で利用する場合は出典としてSteamChartsを明記し、短時間に大量アクセスしないように注意してください。

取得元の例：

```text
https://steamcharts.com/app/730
https://steamcharts.com/app/440
https://steamcharts.com/app/1172470
```

実行コマンド：

```bash
python steamcharts_collect.py
```

Google Colabでの実行例：

```python
from google.colab import drive
drive.mount('/content/drive')

%cd /content
!rm -rf steam-research
!git clone https://github.com/Roki0i/steam-research.git
%cd /content/steam-research

!pip install -r requirements.txt
!python game_candidates_collect.py
!python steamcharts_collect.py
```

保存先は、Google Driveがマウントされている場合は以下です。

```text
/content/drive/MyDrive/卒業研究/steam_research/data/steamcharts_monthly.csv
```

Google Driveがない環境では以下です。

```text
./data/steamcharts_monthly.csv
```

保存カラム：

| カラム | 内容 |
| --- | --- |
| `appid` | Steam App ID |
| `name` | ゲーム名 |
| `category` | 分析カテゴリ |
| `genre` | 後方互換用のジャンルまたはカテゴリ |
| `type` | `candidate`, `core`, `reserve` など |
| `month` | 対象月 |
| `avg_players` | 平均プレイヤー数 |
| `gain` | 前月からの増減 |
| `gain_percent` | 前月からの増減率 |
| `peak_players` | 月間ピークプレイヤー数 |
| `source_url` | 取得元URL |
| `collected_at` | 収集日時 |

---

## 14. CSVをGitHubに含めない理由

本研究で取得するCSVデータは、実行するたびに増加します。また、生データはファイルサイズが大きくなる可能性があります。

そのため、本リポジトリではコードのみをGitHubで管理し、CSVデータはGoogle Driveに保存します。

`.gitignore` には以下を設定しています。

```text
data/
*.csv
```

---

## 15. データ保存形式

CSVは `utf-8-sig` 形式で保存します。

これにより、Excelで開いた場合でも日本語が文字化けしにくくなります。

また、既存CSVが存在する場合は新規データを追記し、指定列に基づいて重複を削除します。

---

## 16. 今後の分析予定

今後は、継続的に収集したデータを用いて以下を分析します。

* カテゴリ別のプレイヤー数推移
* プレイヤー数の減少率
* レビュー評価とプレイヤー数変化の関係
* 否定的レビューの増加とプレイヤー離脱の関係
* Steamニュースやアップデート後のプレイヤー数変化
* カテゴリごとの維持率・離脱傾向の比較

---

## 17. 注意点・限界

本プロジェクトで取得する現在プレイヤー数は、実行時点のスナップショットです。そのため、1回の取得だけではプレイヤー離脱を直接分析することはできません。

離脱傾向を分析するためには、同じ条件で定期的にデータを取得し、時系列データとして蓄積する必要があります。

また、Steam APIから取得できるデータには制約があり、ゲーム内の詳細な行動ログや個人単位の継続率は取得できません。そのため、本研究では公開データを用いた間接的な離脱傾向の分析を行います。

---

## 18. GitHubリポジトリ

```text
https://github.com/Roki0i/steam-research
```
