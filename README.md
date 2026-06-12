# steam-research

Steamゲームにおけるジャンル別プレイヤー離脱傾向を分析するためのPythonプロジェクトです。現在の同時接続者数、レビュー概要、生レビュー、Steamニュースを取得し、CSVとして保存します。

## 1. 研究目的

本研究では、Steamゲームのジャンルごとにプレイヤー離脱の傾向がどのように異なるかを分析します。プレイヤー数、レビュー内容、レビュー評価、ニュース情報を集め、離脱に関係しそうな要因を比較できるデータを作成します。

## 2. ファイル構成

- `games.py`: 収集対象ゲームの一覧
- `steam_collect.py`: Steam APIからデータを取得してCSV保存するプログラム
- `requirements.txt`: 必要なPythonライブラリ
- `.gitignore`: GitHubに入れないファイルの設定
- `data/`: 取得したCSVの保存先。GitHubには入れません

保存されるCSVは以下です。

- `data/current_players.csv`
- `data/review_summary.csv`
- `data/reviews_raw.csv`
- `data/news.csv`

## 3. MacBookでの準備

```bash
cd ~/projects/steam-research
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 4. GitHubへのpush手順

```bash
git status
git add games.py steam_collect.py requirements.txt README.md .gitignore
git commit -m "Create Steam research data collector"
git branch -M main
git remote add origin https://github.com/Rokioi/steam-research.git
git push -u origin main
```

すでにremoteを設定済みの場合、`git remote add origin ...` は不要です。

## 5. Google Colabでの実行手順

Google Colabでは、以下をノートブックのセルで実行します。

```python
from google.colab import drive
drive.mount('/content/drive')
```

```python
!git clone https://github.com/Rokioi/steam-research.git
%cd steam-research
!pip install -r requirements.txt
!python steam_collect.py
```

## 6. Google Drive保存先

Google Driveがマウントされている場合、CSVは以下に保存されます。

```text
/content/drive/MyDrive/卒業研究/steam_research/data
```

Google Driveがない環境では、プロジェクト内の以下に保存されます。

```text
./data
```

CSVは `utf-8-sig` で保存するため、Excelでも文字化けしにくくなります。既存CSVがある場合は追記し、追記後に重複行を削除します。

## 7. MAX_REVIEW_PAGES と TARGET_TYPES

`steam_collect.py` の上部で設定できます。

```python
TARGET_TYPES = ["core"]
MAX_REVIEW_PAGES = 1
```

`TARGET_TYPES = ["core"]` の場合、本採用ゲームだけを収集します。

予備ゲームも収集したい場合は、以下のように変更します。

```python
TARGET_TYPES = ["core", "reserve"]
```

`MAX_REVIEW_PAGES` は生レビューを何ページ取得するかを指定します。1ページあたり最大100件です。大きくすると取得件数は増えますが、実行時間も長くなります。

## 8. CSVはGitHubに入れない方針

取得したCSVデータは研究用の生データであり、ファイルサイズが大きくなる可能性があります。そのため、`data/` は `.gitignore` に追加し、GitHubには入れません。

## 9. 実行コマンド

MacBookで実行する場合:

```bash
python steam_collect.py
```

仮想環境を使う場合:

```bash
source .venv/bin/activate
python steam_collect.py
```
