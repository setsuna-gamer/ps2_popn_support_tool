# CLAUDE.md

このリポジトリは **pop'n music Lively 用サポートツール** (`pop_lively_support_tool`) です。
**現在の改変目標**: 本ツールを **PS2 専用**に改変し、PS2 版 pop'n music の **7 ～ 14、および best hits!** で使えるようにする
(タイトル / モードを画像で認識し、タイトルごとの画面レイアウトに対応する)。

言語は日本語 (UI・コメント・README)。コミットメッセージも日本語が慣例。

---

## 1. プロジェクト概要 (現状 = Lively 版)

ゲーム画面の映像をキャプチャして読み取り、次を行う Windows 専用デスクトップアプリ (PySide6)。

- 画面状態 (タイトル / 選曲 / オプション / プレー / リザルト 等) の自動検出
- プレー中の判定内訳 (COOL/GREAT/GOOD/BAD) の累計値読み取り → 打鍵数集計
- 曲名・難易度の特定 (バナー特徴量照合 + Windows OCR フォールバック)
- 使用オプションの読み取り
- リザルトのスコア記録 (SQLite)、統計、CSV、スクリーンショット保存
- OBS WebSocket 連動、署名付き自動更新・曲リスト配信

ゲームのメモリ・通信には触れず、**映像のみ**を読む設計 (この方針は維持する)。

### 技術スタック
Python >= 3.11 / PySide6 / NumPy / Pillow / ImageHash / DXcam / obsws-python / winrt-* (Windows.Media.Ocr)。
ビルドは cx_Freeze (`setup.py`, `build.bat`)。依存管理は uv (`uv sync`)。

### コマンド
```bash
uv sync                      # 環境構築
run.bat                      # 起動 (.venv の python で pop_lively_support_tool.pyw)
build.bat                    # exe ビルド (dist\pop_lively_support_tool)
uv run --with pytest python -m pytest tests   # テスト (画面識別・数字・バナー・OCR・記録の流れ・セキュリティ。§7.2)
python tools/sync_agent_md.py                 # CLAUDE.md を AGENT.md にコピーする (§6)
python manage_db.py stats    # DB 管理 CLI (import-music / export-csv / import-csv / stats)
```
バージョンは `pyproject.toml` の `version` (`YYMMDD` / `YYMMDD.N`)。

---

## 2. アーキテクチャ

```
キャプチャ層 → ScreenReader.detect_mode → MainWindow._handle_mode → 各 reader → ScoreManager → DB
```

### 処理の流れ (`pop_lively_support_tool.pyw`)
- `MainWindow._main_loop` を **100ms ごと**に QTimer で実行。
- `obs_manager.read_frame()` でフレーム取得 → `screen_reader.detect_mode(image)` → `_handle_mode`。
- モード遷移時 `_on_mode_changed` → `_enter_mode` / `_leave_mode` と OBS トリガー (`<mode>_start/_end`)。
- `option` 中: `_process_option` (バナーで曲特定 + オプション読み取り、2 回連続一致で反映)。
- `play` 中: `_process_play` (曲名 OCR を 5 フレームごと最大 20 回、判定累計値を毎フレーム)。
- `result` 中: `_process_result` (値が 3 フレーム連続で同じなら確定、50 フレームでタイムアウト) → `_save_result`。

### キャプチャ層
| ファイル | 役割 |
|---|---|
| `src/obs_websocket_manager.py` | 取り込み方式の統括 (`read_frame`)。優先順位リスト + フォールバック。OBS 制御ルール |
| `src/dxcam_window_capture.py` | DXCAM 直接取得 (HDR 有効時は旧方式へ) |
| `src/direct_window_capture.py` | 旧直接取得 (Win32 PrintWindow 系) |
| `src/hdr_monitor.py` | HDR 有効判定 |
| `src/config.py` | `direct_capture_exe` (既定 `popnLively.exe`) / `direct_capture_title` (既定 `pop'n music Lively`) でウィンドウ特定 |
| `src/cpu_affinity.py` | Lively プロセスの CPU 割り当て (任意機能) |

### 認識層 (すべて PIL.Image を受け取る)
| ファイル | 役割 |
|---|---|
| `src/define.py` | **画面識別の座標・average-hash 定数** (`PosTitle`, `PosMusicSelect`, `PosOption`, `PosIsPlay`, `PosResult`, ...)。1920x1080 基準 |
| `src/screen_reader.py` | `detect_mode`。`_matches()` が領域 crop の `imagehash.average_hash` と基準ハッシュの距離 (閾値 10) で判定。判定順は loading → title → status → ticket → character_select → option → exit → play → result → select |
| `src/ps2_numbers.py` / `ps2_layouts.py` / `ps2_readers.py` | プレー・リザルト画面の数字 (§4.13)。Lively の `judge_reader` / `result_reader` / 数字テンプレートは削除済み |
| `src/ps2_marks.py` | リザルトの STAGE FAILED / NEW RECORD (§4.14) |
| `src/ps2_songs.py` + `ps2_banner.py` + `ps2_ocr.py` | 曲の特定 (§4.9)。`src/win_ocr.py` が Windows OCR のラッパー |
| `src/banner_reader.py` | 選曲バナーの 16x4 RGB サムネ特徴量 (`music list` の `banner` 列) と相関照合 |
| `src/option_reader.py` + `option_templates.py` + `option_master.py` | オプション一覧 OCR / アイコンテンプレ照合 |
| `src/diagnostics.py`, `diagnostics_dialog.py` | 読み取り失敗画面の保存・正解入力 |

`tools/build_option_templates.py` (Lively のオプション用。作り直し予定) と、PS2 版の `tools/build_screen_profiles.py` / `build_ps2_digit_templates.py` / `build_ps2_marks.py` は、
正解値付きスクリーンショットから生成物を**自動生成**する。生成物 (`option_templates.py`、`src/*.json`) は手で編集しない。

### データ層
- `src/db.py` (SQLite `popn.db`): `musics` / `scores` / `option_masters` / `song_aliases`。スコアは `music_id` (UUID) で曲に紐づく。
- `src/score_manager.py`: 現在曲・オプションの保持、`identify_song` (OCR あいまい照合) / `identify_banner` / `add_record`。
- `popn_music_list.json`: 曲マスター (ver, genre, title, artist, bpm, easy/normal/hyper/ex レベル, pack, music_id, banner)。
  `generate_music_list.py` が Wiki 由来 HTML から生成、`tools/sign_release.py` が Ed25519 署名 (`.sig`)。
- `src/classes.py`: `DetectMode` (enum), `PopnJudge`, `PopnOptions`, `PopnScoreRecord`。難易度コードは L/N/H/EX。

### UI / その他
`src/ui_jp.py` (文字列)、`config_dialog.py`、`score_dialog.py`、`stats_dialog.py`、`chart_widgets.py`、`obs_dialog.py`、`session_image.py`。
更新・セキュリティ: `updater.py`, `update_dialog.py`, `signing.py`, `ed25519.py`, `secure_http.py`, `trusted_keys.py`, `music_list_fetch.py`, `startup_check.py`。
`.github/workflows/update-music-list.yml` が毎週曲リストを自動更新 (PR 作成・署名)。**`popn_music_list.json` 手編集は署名が壊れるので不可** (`.gitattributes` で改行変換も禁止)。

---

## 3. 画面モード (DetectMode) 一覧

`unknown / select / play / result / option / title / character_select / exit / loading / mode_select / freetraining`
(PS2 版。Lively 固有だった ticket / status は削除し、mode_select / freetraining を追加した。画面識別のモード名との対応は `src/screen_tracker.py` の `MODE_TO_DETECT`)。

---

## 4. PS2 版 (7 ～ 14, best hits!) への改変方針

### 4.1 確定事項 (ユーザー回答)
- **PS2 専用に置き換える** (Lively 版との併用はしない)。Lively 固有の処理は削除・置換してよい。
- 対象タイトル: pop'n music **7, 8, 9, 10, 11, 12 いろは, 13 カーニバル, 14 FEVER!, best hits!**。
- 各タイトルの **タイトル画面 / モード選択画面 / 曲選択画面 / オプション画面 / プレー画面 / リザルト画面** の画像を読み込ませ、**タイトルとモード(画面)を認識**する。
- **スコア記録まで行う** (リザルト読み取り・DB 保存・統計は残す)。
- **映像入力**: キャプチャボード利用を想定して **OBS WebSocket 連携は残す**。PCSX2 (エミュレータ) の場合は **DXcam によるウィンドウ取得**を使う。旧直接取得 (`direct_window_capture.py`) は不要なら整理可。
- **キャラクターセレクト画面は作品によって存在する**ため `DetectMode.character_select` は残す (作品ごとにあり/なしをプロファイルで持つ)。ticket / status は Lively 固有なので削除対象。
- **判定値 (COOL/GREAT/GOOD/BAD) はプレー中に表示される**。`judge_reader.py` / `judge_templates.py` は**作品ごとに作り直す** (表示位置・フォント・桁数が作品で異なる)。累計値の読み取り・誤読排除ロジック (`ScreenReader.detect_judge`) の方針は流用する。
- **曲リストは更新されない静的リスト** (出典は §4.7)。タイトル別ファイルにはしない (収録曲が重複するため)。1 曲 1 レコードとし、**収録タイトルを DB の値として持つ** (例: `musics` に `titles` 列、または `music_titles(music_id, title_id)` 多対多テーブル)。自動更新・署名配信・GitHub Actions の曲リスト更新・バナー取得は不要になる。

### 4.2 オプション仕様 (作品別)
HID-SUD 列は HIDDEN / SUDDEN / HID-SUD (ほか OFF)。RANDOM 列は RANDOM / MIRROR (9 以降は S-RANDOM も) (ほか OFF)。
[モダナイズパッチ](https://github.com/setsuna-gamer/popn_modernize_patcher) 適用時はハイスピードの選択肢が増えるため、**パッチ適用の有無も設定 (または認識) で扱う**。

| タイトル | ハイスピード (モダナイズ適用時) | ハイスピード (通常) | ポップ君 | HID-SUD | RANDOM |
| --- | --- | --- | --- | --- | --- |
| 7, 8, best hits | OFF, x1.5 ～ x8 (0.5 刻み) | OFF, x2, x3, x4 | BEAT | HIDDEN, SUDDEN, HID-SUD | RANDOM, MIRROR |
| 9 | OFF, x1.5 ～ x8 (0.5 刻み) | OFF, x2, x3, x4, x6, x8 | BEAT, STAGE, CHARA | 同上 | RANDOM, MIRROR, S-RANDOM |
| 10 | OFF, x1.5 ～ x8 (0.5 刻み), LOW | OFF, x2, x3, x4, x6, LOW | BEAT, STAGE, CHARA | 同上 | 同上 |
| 11 | OFF, x1.5 ～ x10 (0.5 刻み) | OFF, x2, x3, x4, x5, x6 | BEAT, STAGE, CHARA | 同上 | 同上 |
| 12, 13 | OFF, x1.5 ～ x10 (0.5 刻み) | OFF, x2, x3, x4, x5, x6 | BEAT, CHARA | 同上 | 同上 |
| 14 | OFF, x1.5 ～ x8 (0.5 刻み) | OFF, x1.5 ～ x6 (0.5 刻み) | BEAT, CHARA | 同上 | 同上 |

> 元の回答表で 9 のモダナイズ欄に「10 は LOW-Speed あり」とあったが、10 の行に LOW が明記されているため 10 の行に集約した (要確認)。

実装への影響:
- `src/option_master.py` の `OPTION_MASTER` を **タイトル別の選択肢テーブル** (`OPTION_MASTER[title_id][key]`) に再設計。項目は ハイスピード / ポップ君 / HID-SUD / RANDOM の 4 つ (Lively の GAUGE TYPE, GUIDE SE, JUDGE+, OJAMA*, AUTO は廃止)。
- `PopnOptions` と `scores` テーブルの列、CSV 列 (`db.py` の `CSV_HEADERS`) も同様に整理。**既存 DB / CSV のマイグレーションは不要** (専用化のため新規スキーマでよい。ただしユーザーに破棄可否を確認すること)。
- `option_reader.py` (一覧 OCR・アイコンテンプレ照合) は PS2 画面向けに作り直し。作品別テンプレートを `tools/build_option_templates.py` で生成。
- `scores` に **title_id (どの作品でプレーしたか)** 列を追加。曲の収録タイトルとは別に、プレーしたタイトルを記録する。

### 4.3 Lively 版からの主な差異・影響範囲
| 項目 | Lively 版 | PS2 版 |
|---|---|---|
| 映像入力 | `popnLively.exe` ウィンドウ直接取得 / OBS | PCSX2 = DXcam / キャプチャボード = OBS WebSocket。`direct_capture_exe/title` の既定値を PCSX2 向けに。入力は 480 系 (4:3 または 16:9) なので `define.py` の 1920x1080 前提座標は使えない → 正規化座標 |
| 画面識別 | 固定座標 + average hash (単一タイトル) | **タイトル別 × 画面別**のプロファイル (§4.4) |
| 画面種 | title / status / ticket / character_select / select / option / play / result / exit / loading | title / **mode_select (新規)** / character_select (作品による) / select / option / play / result (+ 必要なら loading, exit) |
| 判定表示 | 画面下部 4 桁累計 | プレー中に表示あり。**作品別にテンプレ・領域を作り直し** |
| 曲特定 | バナー特徴量 + 曲名バー OCR | **オプション画面のバナー**で特定する (§4.9)。プレー / リザルトの曲名は画像フォントで OCR 不可なので、オプション画面で決めた曲を保持して使う |
| 難易度 | EASY/NORMAL/HYPER/EX | 作品ごとの難易度体系 (EASY/NORMAL/HYPER/EX、5 ボタン/9 ボタン)。`DIFFICULTY_LEVEL_COLUMNS` 見直し |
| 曲リスト | Wiki/公式から自動生成・署名・週次更新 | 静的。収録タイトルを DB 値で保持 |
| 自動更新 | GitHub リリースの署名付き自動更新 | 当面維持 (リポジトリ名・公開鍵・配布先は PS2 版に合わせて要見直し) |

### 4.4 推奨する設計 (タイトル × 画面 の 2 段認識)
1. **プロファイル化**: `define.py` の `Pos*` を作品ごとのプロファイル (`src/profiles/popn07.py` … `popn14.py`, `besthits.py`) に分離し、`PROFILES[title_id][screen]` で引く。
   各画面の目印は `(area, [average_hash...], threshold)`。座標は **正規化 (0..1)** で持ち、入力画像サイズに合わせて crop する (レターボックス・タイトルバー有無の差は §4.5 参照)。
2. **タイトル判定 → 画面判定**: まずタイトル画面・ロゴ等で `title_id` を決定 (全プロファイルと照合し最良一致)、確定後はそのタイトルのプロファイルだけで `detect_mode` を実行。複数フレームの投票で安定させ、タイトル画面に戻ったら再判定する。
3. **基準画像の取り込み**: `assets/ps2/<title_id>/<screen>.png` に各作品 6 画面 (+ キャラセレクト等) を置き、`tools/build_screen_profiles.py` (新規) で **average hash と領域を自動生成**する (既存 `tools/build_*_templates.py` と同じ方式。ハッシュの手書きは禁止)。
4. 類似画面 (作品間のロゴ違い・選曲/モード選択) を区別できるよう閾値を調整し、混同する画面は複数領域の AND/OR 条件にする。
5. `DetectMode` に `mode_select` を追加、ticket / status を削除し、`ui_jp.py` の `status.*`、`_MODE_COLORS`、`_TRIGGER_MODES`、OBS ルール画面一覧 (`obs_dialog.py`)、README を同期する。メイン画面に「現在のタイトル」表示を追加。
6. 画像は容量・権利の面から、リポジトリに入れるのはプロファイル生成に必要な最小限のクロップに留める (原本の扱いはユーザーに確認)。

### 4.5 作業ステップ案
1. 各タイトルのサンプル画像 (6 画面) を収集・配置 (入力解像度とアスペクトを記録)。
2. `build_screen_profiles.py` とプロファイル構造を実装。
3. `ScreenReader.detect_mode` をプロファイル駆動にし、タイトル認識を追加。画像でのテスト (`tests/`) を作成。
4. 判定値 (プレー中)・リザルト・曲名・オプションの各 reader を作品別に作り直し。
5. 静的曲リスト + 収録タイトルの DB 設計、スコア保存 (title_id 付き)、統計・CSV を調整。
6. キャプチャ既定値 (PCSX2 / OBS)、Lively 固有機能 (CPU 割り当て、ticket/status 等) の削除、README 更新。

### 4.6 未確定事項
- (解決済み) サンプル画像は `screenshots/<title_id>/<mode>/` に分類して置く (例: `screenshots/popn7/play/`)。`screenshots/` は .gitignore 済みでコミットしない。リポジトリには画像が**まだ無い**。
- (解決済み) 入力は **4:3** を想定。PCSX2 のウィンドウ枠・タイトルバーの有無、キャプチャボードの余白は画像を見て正規化方法を決める。
- (解決済み) 静的曲リストの出典は §4.7 の pmdream.net。
- モダナイズパッチ適用有無の扱い (設定で選ばせるか、画面から自動認識するか)。
- (解決済み) 既存 DB は popn 15 以降の曲を削除し、`music_id` と `banner` 特徴量は流用する (§4.7)。
- (解決済み) N / H / EX すべて現行と基準が違うため `*_old` / `*_current` に分ける (§4.7)。
- リポジトリ名・自動更新の配布先を PS2 版として分けるか。

### 4.7 曲リスト (静的) の作り方

**実装済みのツール** (動作確認済み):
- `tools/fetch_ps2_songlist.py`: 9 ページを `tmp_ps2_songlist/` に取得 (CP932 のまま保存、2 秒間隔、取得済みはスキップ、`--force` で再取得)。`TITLES` が title_id と ページ名の対応表。
- `generate_ps2_music_list.py`: HTML を解析し、タイトルをまたいで曲を統合、既存の `popn_music_list.json` と照合して `music_id` / `banner` / `*_current` を引き継ぎ、`ps2_music_list.json` を出力。照合できなかった曲・あいまいな曲はレポートに表示する (近い既存曲のヒント付き)。
- 表記ゆれで自動照合できない同一曲は `tools/ps2_manual_matches.json` に目視確認済みのものだけ書く (釈迦 / 大釈迦のような別曲は書かない)。表記ゆれで別々に読まれた PS2 曲が同じ既存曲に当たった場合は 1 レコードに統合する。
- 出力は 695 曲 (既存と一致 500 曲 / 新規採番 195 曲)。ヒントの目視確認は完了済み。最終版 (`ps2_music_list.json`) の置き場所とコミットは未実施。

**出典** (pmdream.net の家庭用 PS2 版曲リスト。文字コードは **Shift_JIS**):

| title_id | タイトル | URL |
|---|---|---|
| popn7 | pop'n music 7 | http://pmdream.net/popn/cs7/music.html |
| popn8 | pop'n music 8 | http://pmdream.net/popn/cs8/music.html |
| popn9 | pop'n music 9 | http://pmdream.net/popn/cs9/music.html |
| popn10 | pop'n music 10 | http://pmdream.net/popn/cs10/music.html |
| popn11 | pop'n music 11 | http://pmdream.net/popn/cs11/music.html |
| popn12 | pop'n music 12 いろは | http://pmdream.net/popn/cs12/music.html |
| popn13 | pop'n music 13 カーニバル | http://pmdream.net/popn/cs13/music.html |
| popn14 | pop'n music 14 FEVER! | http://pmdream.net/popn/cs14/music.html |
| besthits | pop'n music best hits! | http://pmdream.net/popn/csbest/music.html |

**ページ構造** (cs14 で確認): `<TABLE class="mlist">`、列は ジャンル / 曲名 / アーティスト / キャラクター / N / H / EX / 5 (5 ボタン譜面) / BPM / Point。
`class="mc"` の見出し行 (例「PS2版 pop'n music 14 FEVER! / 新曲 (10曲)」) で、その曲の区分 (新曲・過去作からの移植・隠し曲など) が分かる。セルのクラスは `mw`(通常) `mn` `mh` `mex` `m5`。
取得は `tools/fetch_ps2_songlist.py` (新規。`fetch_wiki.py` / `generate_music_list.py` を参考に) で一度だけ実行し、結果を静的 JSON にコミットする。サイトへの負荷を避けるためリクエスト間隔を空け、取得した HTML はリポジトリに入れない。

**既存データの流用** (`popn_music_list.json`、現在 2160 曲):
- **popn 15 以降の曲は削除**してよい (ver が `pop'n music 15 ADVENTURE` 以降・Sunny Park・ラピストリア・High☆Cheers!! など)。
- PS2 リストの曲と既存曲を **ジャンル・曲名・アーティストで照合**し (`generate_music_list.py` の照合ロジックを流用)、一致した曲は既存の **`music_id` (UUID) と `banner` 特徴量を引き継ぐ**。`banner` は PS2 画面の曲表示と見た目が違う可能性があるため、使えるかは画像確認後に判断 (使えなければ列だけ残す)。
- 一致しなかった PS2 曲は新しい UUID を採番。一致しなかった既存曲 (15 以降以外でも PS2 収録外のもの) は削除候補としてユーザーに一覧を見せてから消す。
- 同一曲が複数タイトルに収録されるので **1 曲 1 レコード + 収録タイトル (多対多)**。例: `music_titles(music_id, title_id)`。曲リスト JSON では `titles: ["popn7", "besthits"]` のような配列で持つ。

**難易度の持ち方** (現行と基準が違うため、全難易度で old / current を分ける):
- PS2 版の値 (pmdream の N/H/EX/5) は **当時の基準 (`*_old`)**。現行 (Lively) の基準で設定されている曲は、既存 JSON の値を **`*_current`** に移す。現行に無い曲の `*_current` は NULL。
- カラム案 (例。より良い案があれば採用可):

| カラム | 内容 | 出典 |
|---|---|---|
| `normal_old` / `normal_current` | NORMAL | pmdream の N / 既存 JSON の `normal` |
| `hyper_old` / `hyper_current` | HYPER | pmdream の H / 既存 JSON の `hyper` |
| `ex_old` / `ex_current` | EX | pmdream の EX / 既存 JSON の `ex` |
| `five` | 5 ボタン譜面 | pmdream の 5 (現行に対応値なし) |

- EASY は現行のみの難易度のため **`easy` 列は削除**する (既存 JSON の `easy` は捨てる)。
- `difficulty_code` (`src/classes.py`) の L/N/H/EX と `DIFFICULTY_LEVEL_COLUMNS` は、PS2 の難易度体系 (N/H/EX と 5 ボタン) に合わせて見直す。スコア画面・統計に表示するレベルは **PS2 基準 (`*_old`) を既定**とし、現行基準の併記は任意。
- `musics` テーブル (`src/db.py`)、`generate_music_list.py` の出力、CSV の「レベル」列、`tests/` の該当箇所を同時に更新する。

### 4.8 画面識別の実装 (popn7 で動作確認済み)

- `src/screen_profile.py`: 4:3 の画面をぼかして 32x24 のセルに分け、セルの平均色をテンプレートと比べる。一致したセルの割合 (`MIN_SCORE` 0.5 以上) と、別の (タイトル, モード) との差 (`MIN_MARGIN` 0.2 以上) で `(title, mode)` を決める (`ScreenProfiles.identify`)。1 回の判定でタイトルとモードの両方が分かる。座標はセル番号で、4:3 であれば解像度に依存しない。4:3 以外の入力は呼び出し側で切り出す。
- `tools/build_screen_profiles.py`: `screenshots/<title_id>/<フォルダ>/**/*.png` から `src/screen_profiles.json` を生成する。フォルダ名 → モード名は `MODE_FOLDERS` (tilte→title, modeselect→mode_select, musicselect→music_select, option, play, result, load→loading, charaselect→character_select)。`popnbesthits` は `besthits`。階層が深いときは一番深い既知のフォルダ名を採用し、`freetraining` (または `free`) 以下の画像は階層によらず **`freetraining` モード (独立モード)** とする。そのほか既知でないフォルダはその名前のままモード名になる。
  - 同じ画面でも見た目の違うもの (別レイアウト) は自動で別テンプレートに分ける。
  - 各テンプレートは「同じ画面の画像・拡縮/ずれ/ぼかし/明るさを変えた派生画像の間で変わらず、他の画面の画像と違うセル」を最大 96 個選ぶ。
  - `--eval` は画像を 1 枚ずつ除いて作り直し、その画像を識別できるかを確かめる (同じレイアウトの画像が他にあるものだけが対象)。
- `tests/test_screen_profile.py`: 学習画像の識別・解像度違い・黒/ノイズ画面の不採用を確認する。`uv run --with pytest python -m pytest tests/test_screen_profile.py`。
- 結果 (popn7, 21 枚): 学習画像 21/21、除外検証 16/16 (別レイアウトとみなす基準 `SAME_LAYOUT_RATIO` = 0.6)。同じレイアウトの画像が 1 枚しか無い画面 (result など 5 枚) は除外検証できないので、各画面の画像を増やす。
- `src/screen_profiles.json` は生成物なので手で編集しない。配布 exe には含める (`setup.py` の include_files に追加が必要。未対応)。

popn7 の画像から分かった画面の種類 (`screenshots/popn7/`):
- `tilte/` (綴りは tilte のまま): PRESS START と、OPTION / GAME / RECORDS のメニューの 2 状態。
- `load/`: 黒地の「Now LOADING」と、メモリーカードチェックの 2 種。
- `modeselect/`: GAME SELECT (Side-A / Side-B) と MODE SELECT (フリートレーニング等) の 2 レイアウト。
- `musicselect/`: チャレンジモードの MUSIC SELECT。`freetraining/` 以下に別レイアウトの選曲 (サムネイル一覧) と、STYLE SELECT / SELECT メニューがある。
- `option/`: OPTIONS ポップアップ (Hi-SPEED / HIDDEN / RANDOM / MIRROR。ON!/OFF 表示) と、その直前の「Next Music」表示。
- `play/`: 左上のプレーヤー名、上部に曲名 (画像フォントなので OCR 不可) とオプション帯、下部に `BAD GOOD GREAT COOL` の累計値 (4 桁)、左に SCORE と MAX COMBO。
- `result/`: COOL / GREAT / GOOD / BAD / COMBO (4 桁)、STAGE SCORE、TOTAL SCORE。曲名は画像フォント。
- 画像サイズは 1325x994 (4:3)。ウィンドウ枠は含まれていない。

**確定**: フリートレーニング (STYLE SELECT / SELECT メニュー / その選曲) は独立モード `freetraining`。`DetectMode` にも `freetraining` を追加する (組み込み時)。
**要確認**: `load` を `loading` モードとして扱ってよいか。

### 4.9 曲の特定 (オプション画面のバナー, `src/ps2_banner.py`)

**確定**: 曲はオプション画面のバナーで特定する。
- オプション画面の左上「Next Music」にバナーが出る。画像は曲リストの `banner` 列の元 (Lively 版のバナー) と同じなので、`banner_reader.banner_feature` の 16x4 特徴量と相関で照合できる (popn7 マシュマロ・マーチ: 相関 0.997、2 位との差 0.2)。
- 状態が 2 つある: (1) Next Music だけ = バナー全体が見える、(2) OPTIONS ポップアップが開く = 暗くなり下半分が隠れる。(1) は 4 行全部、(2) は上 2 行だけで照合する (相関 0.996)。(2) の基準は厳しめ (`PARTIAL_MIN_SCORE` 0.95 / `PARTIAL_MIN_MARGIN` 0.08)。(1) も Lively 用の 0.80 は緩すぎる (best hits で、バナー未登録の MELO CORE が「魔法の扉」に 0.802 で誤一致した) ので `FULL_MIN_SCORE` 0.92 にした。正しい一致は 0.98 以上 (ポップアップ中の上半分でも)。
- バナーの位置は作品ごとに `BANNER_BOXES` (4:3 の画面に対する比率)。**popn7 のみ登録済み**。他作品は画像を見て追加する。
- `Ps2BannerIndex.match(feature, title)` は曲リストの `titles` で作品に収録された曲に絞る。
- 既存の `banner_reader.locate_banner` / `read_banner` (1920x1080 の黒縁検出) は削除した。`banner_reader.py` は特徴量 (`banner_feature` ほか) と `BannerIndex` だけを持つ。
- `banner` を持つ曲は各作品で 36～93 曲 (popn7 は 97 曲中 70)。残りは Lively に無い曲なので、**PS2 の画面から登録する** (`tools/register_ps2_banners.py`):
  - `scan`: `screenshots/<title>/**/option/` を調べ、特定できないバナーを一覧にして `tmp_ps2_banners/` に切り出し画像を保存する。
  - `add <画像> <曲名>`: 曲名 (その作品の収録曲から部分一致。複数当たれば絞り込みを求める) の曲に登録する。ポップアップが開いた画像 (popn7)・別の曲のバナーと一致する画像は拒否する。
  - 登録内容は `tools/ps2_banners.json` (music_id → 特徴量) と `ps2_music_list.json` に書く。`generate_ps2_music_list.py` は前回の出力から新規曲の music_id を引き継ぎ、`ps2_banners.json` を取り込むので、再生成しても消えない。
- バナー位置の登録状況: popn7 と best hits (どちらも、ポップアップがバナーの下半分に重なる)、popn8 (ポップアップは画面下で、バナーは暗くなるだけ。範囲はアーティスト名の帯を含めない)、popn9 (バナーは左上でポップアップは重ならない。アーティスト名はバナー下の吹き出しの平文字で OCR で読める)、popn10 (左上。曲名がバナー下の板に平文字で出る = `TITLE_BOXES`)、popn11 (左上。アーティスト名はバナー下の平文字)、popn12 (右上。アーティスト名は暗い帯の白文字で、OCR は一部しか読めない)、popn13 (右上)、popn14 (**傾いて表示される**ので、4 隅を長方形に補正して切り出す = `BANNER_QUADS`。矩形のままだと相関は 0.8 止まりで、補正すると 0.998)。全作品を登録済み。登録済みのバナーは popn12 の 10 枚すべて、popn10 / 11 もクリアな画面はすべて特定できる (スライド入場中のフレームだけは特定できないが、複数フレームで確定するので問題ない)。**注意**: 曲リストの Lively 由来のバナーが PS2 の画像と別物の曲がある (popn10 の Xmas の曲は相関 0.56)。そのときは `register_ps2_banners.py add` で PS2 の画像から上書きする。同じバナーを共有する曲 (「Knock Out Regrets」と「脱皮 ～Knock Out Regrets～」など) は、画面のバナーからは区別できない (ジャンル名などで推定して登録した)。
- **OCR による補助** (`src/ps2_ocr.py`): バナー照合で決まらないとき (バナーに特徴量が無い曲など) に使う。`identify_option_song` がバナー → OCR の順で試す。
  - バナー部分 (曲名) とアーティスト帯 (`ARTIST_BOXES`、作品ごと) を Windows OCR で読み、曲リストの「曲名 + アーティスト名」と 2 文字ずつの並び (バイグラム) の一致率で照合する。`titles` で作品の収録曲に絞る。
  - 採用条件: 一致率 0.70 以上 + 一致 5 個以上 + 2 位との差 0.15 以上。または、アーティスト名が 90% 以上読めて (4 バイグラム以上) 2 位との差が 0.15 以上 (同じアーティストの曲が複数あれば採用されない)。
  - アーティスト帯は白文字を二値化した画像でも読む (popn8 のカタカナ「ササラユキエ」がこれで読めた)。
  - **精度の限界**: 英字の曲名・アーティスト名は読めるが、日本語の装飾フォントは読めないことが多い。popn8 は実画像 9/9 (Can't Stop My Love 8 枚は曲名 + アーティスト、silent green は白文字二値化のアーティスト名) で、他の画面に誤認識なし。popn7 の「マシュマロ・マーチ」は丸文字で全く読めず 0/7。**OCR は補助であり、バナー特徴量の登録 (`register_ps2_banners.py`) が本筋**。
  - 要 `winrt-*` (`uv run` の環境)。システムの Python には入っていない。
- フリートレーニングのオプション画面で確認した。通常プレーのオプション画面でも同じ位置かは要確認。

### 4.10 スコア記録のプレー作品 (`title_id`)

**確定**: スコアには、どの作品 (バージョン) でプレーしたかを記録する。曲の収録タイトル (`musics` の `titles`) とは別の値。
- 値は `src/titles.py` の title_id (`popn7` … `popn14`, `besthits`)。表示名は `title_name()` / `title_short_name()`。画面識別・曲リスト・バナー位置と共通。
- `PopnScoreRecord.title_id` → `scores.title_id` 列 (`_SCORES_ADDED_COLUMNS` で既存 DB に ALTER。既存の記録は空 = 作品不明)。保存・修正・読み込み・CSV (列名「作品」、値は title_id・インポート可)・DB 復元で保持される。
- `ScoreManager.current_title_id` (`set_current_title_id()`) を `add_record` が記録に付ける (記録側で明示していればそちらを優先)。曲ごとには初期化せず、作品が変わるまで保持する。
- 履歴一覧に「作品」列 (略称、ツールチップと検索は正式名)。修正ダイアログは作品を変えず引き継ぐ。
- **未接続**: メイン側 (`pop_lively_support_tool.pyw`) はまだ画面識別 (`src/screen_profile.py`) を組み込んでおらず、`set_current_title_id()` を呼んでいない。組み込み時に、識別したタイトルを渡す (タイトル確定後は固定し、タイトル画面に戻ったら再判定)。

### 4.11 画面識別の組み込み (`src/screen_tracker.py`)

**実装済み**: `ScreenReader.detect_mode` は `ScreenTracker` (`src/screen_profile.py` の識別 + 作品の追跡) で (作品, モード) を決める。Lively の `is_*` (average hash + 1920x1080 座標) は削除した。
- 入力は `to_4x3` で 4:3 に中央で切り出す。`is_valid_game_screen` (黒画面・未取得の判定) は残す。
- **作品の確定**: 同じ作品の識別が `CONFIRM_FRAMES` (3) 回続いたら確定する (確定前でもモードは返す)。
- **確定後は、その作品のテンプレートだけでモードを決める**。黒一色のロード画面のように、作品をまたいで同じに見える画面もこれで決まる。
- **作品の切り替え**: 全作品で識別して別の作品が明確に勝つ判定が `SWITCH_FRAMES` (5) 回続いたら切り替える。1 フレームだけの別作品の判定では切り替えない。
- `ScreenReader.current_title` / `reset_title()`。メイン (`_sync_title`) が確定した作品を `ScoreManager.set_current_title_id()` に渡し、メイン画面に「作品」を表示する (§4.10 の記録に付く)。
- UI: 状態表示 (`ui_jp.status`)・色・OBS トリガー (`obs_dialog`) を mode_select / freetraining に合わせた。`setup.py` に `screen_profiles.json` と新モジュールを追加した (凍結時は exe の隣の `src/` から読む)。
- 画面識別テンプレート (`src/screen_profiles.json`): popn7 ～ 14 / besthits の 9 作品を生成済み (339 枚。学習画像のモード識別 339/339、作品の判別 305/305、除外検証 モード 302/315・作品 274/284)。除外検証は十数分かかる (`--out` で別の場所に出せる)。評価は実行時と同じく「モードは作品内、作品は全体」で行い、黒一色のロード画面は作品の判別から除く。テンプレートのセルは、同じ作品の別の画面との違いを優先して選ぶ (popn10 のキャラセレクトとボタン選択のように背景が共通の画面を区別するため)。**タイトルに寄せる**: タイトル画面のメニュー選択中の状態 (ARCADE / FREE を選んでいる画面) は、モード選択・ロードのフォルダに紛れ込みやすい。生成ツールは、mode_select / loading として置かれた画像が同じ作品のタイトル画面と 70% 以上一致すれば title に付け替え (`relabel_title_like`)、実行時も title と mode_select で迷ったら title を採る (`ScreenProfiles.decide`)。**弱いところ**: play 画面は曲ごとの背景が違い、共通して使えるセルが少ない (popn12 で 15 個、besthits で 36 個)。play の画像を増やすと安定する。
- **未対応**: プレー・リザルト・オプション・曲名の各 reader は Lively のまま (1920x1080 前提) なので、PS2 の画面ではスコアを正しく読めない。作品別に作り直すこと (§4.5 の 4)。

### 4.12 プレー環境・モダナイズパッチの記録 (`src/play_env.py`)

**確定**: スコアには、プレー環境 (実機 / PCSX2 / その他) と、モダナイズパッチ (COOL 25ms) が有効かも記録する (パッチ有りは判定が違い、スコアを比べるときに区別が要る)。
- `PopnScoreRecord.platform` (`real` / `pcsx2` / `other`、不明は空) と `modernize_patch` (True / False、不明は None) → `scores.platform` / `scores.modernize_patch` (INTEGER、不明は NULL)。既存の記録は不明になる。保存・修正・読み込み・CSV (列名「環境」「モダナイズ」)・DB 復元で保持される。CSV の環境は表示名 (実機 など) でも読める。
- 値は**設定で選ぶ** (設定 → 記録・保存 →「プレー環境」。`Config.play_platform` 既定 `pcsx2`、`Config.modernize_patch` 既定 False)。画面からの自動認識はしていない (PCSX2 かどうかは映像入力の方式から推測できるが、実機のキャプチャボード経由かどうかは分からないため、明示的な設定にした)。
- `ScoreManager.set_play_environment()` が設定を保持し、`add_record` が記録に付ける (記録側で明示していればそちらを優先)。メイン画面に「環境」を表示し、設定変更時に反映する。履歴一覧に「環境」「モダナイズ」列、修正ダイアログは値を引き継ぐ。
- **未対応**: モダナイズパッチ有無によるハイスピードの選択肢の違い (§4.2) は、オプション reader を作り直すときに `Config.modernize_patch` を使って切り替える。プレー中にパッチの有無・環境が変わったときの記録の振り分けは、設定を変えた時点以降の記録に効く。

### 4.13 リザルト・プレー画面の数字の読み取り (`src/ps2_numbers.py` ほか)

**実装済み** (Lively 版の `judge_reader` / `result_reader` / 数字テンプレートは使わない。1920x1080 前提のため):
- `src/ps2_layouts.py`: 作品 × 画面 (`result` / `play`) × 項目 (cool / great / good / bad / combo / stage_score / total_score) の枠。1325x994 のピクセル座標で書き、読み取り時に比率に直す (4:3 なら解像度に依らない)。`SPLIT_RATIOS` は文字が詰まる画面だけの例外。
- `src/ps2_numbers.py`: 枠の背景色 (外周の中央値) から離れた画素を文字として 1 文字ずつ切り出し (色・明暗に依らない)、16x24 の形と縦横比をテンプレートと照合する。繋がった文字は列のインクの谷で分け、割れた細い文字は繋ぐ。枠の端の細い欠片は捨てる。形の距離 0.18 超は「読めない」(None)。
- `tools/build_ps2_digit_templates.py` が、正解値付きの画像 (`tools/ps2_number_samples.json`) から `src/ps2_digit_templates.json` を生成する (手で編集しない)。`--eval` で 1 枚除外検証。枠を決める・確認する道具: `tools/ps2_numbers_sheet.py` (全画像の枠を並べる)、`tools/preview_ps2_numbers.py`。
- `src/ps2_readers.py`: `read_result()` (7 項目。コンボ ≦ 総ノーツ、累計スコア ≧ 今回のスコアで検算) と `read_play()` (判定の累計 4 つ。score / combo の枠は未登録)。**テンプレートに 0～9 が揃っていない作品・画面は読まない** (見本に無い数字を別の数字に取り違えないため。`supported()` / `missing_digits()`)。
- `ScreenReader.read_result_values()` / `detect_judge()` が、確定した作品 (`current_title`) でこれを使う。作品が未確定・未対応なら None で、呼び出し側が従来どおりプレー中の集計値で補う。

**現状 (数字が揃って読めるもの)**:
- リザルト: popn10 / 11 / 12 / 13 / 14。popn7 (足りない 6,9) / popn8 (8,9) / popn9 (9) / best hits (4,7,8) は、リザルト画像が 1～3 枚しかなく数字が揃わないので未対応。**リザルト画像を増やし、正解値を `ps2_number_samples.json` に足して再生成する**。
- プレー (判定の累計): popn9 / popn11 / popn13。popn7 / 8 / 10 / 12 / 14 / best hits は画像・見本が足りない。best hits は文字が縁取りで繋がり、5 文字に割れる画像がある (その項目は None になるだけで誤読はしない)。
- 除外検証 (見本が少ないうちは目安): 224～243/349 項目。誤読ではなく None が大半。

**未対応**: プレー画面の score / combo の枠。popn10 のプレー画面は枠を調整して 4 桁に切り出せるようになったが (等幅の 0 埋めなので桁数で等分する = `FIXED_DIGITS` / `segment_fixed`)、見本に 4 と 8 が無く未対応 (見本を足す)。

### 4.14 リザルトの検出・曲の特定・記録のつなぎ (`src/ps2_marks.py` / `src/ps2_songs.py`)

**クリア失敗 (`failed`) の記録**: `PopnScoreRecord.failed` (True = STAGE FAILED / False = クリア / None = 判定できない) → `scores.failed` 列 (INTEGER、不明は NULL。既存 DB は ALTER で追加し、既存の記録は不明)。CSV は「クリア失敗」列 (1 / 0 / 空欄)。履歴一覧に「クリア」列 (失敗 / クリア / 空)。修正ダイアログは値を引き継ぐ。リザルトの STAGE FAILED の表示は、一度でも検出したら覚えておく (演出で動いて見えなくなるため)。判定に対応していない作品 (popn7 / 8 / 9 / best hits) は None。FULL COMBO のスクリーンショット条件は、失敗した記録を除く。

**実装済み**:
- **STAGE FAILED / NEW RECORD** (`src/ps2_marks.py`): 作品ごとの枠 (`MARK_BOXES`) を 32x16 の RGB サムネイルにして、正解付きの見本から作った参照 (`src/ps2_mark_templates.json`) との相関で判定する。参照は `tools/build_ps2_marks.py` が `tools/ps2_mark_samples.json` から生成する (`--eval` で 1 枚除外検証)。**見本に「ある」画像が 1 枚も無い目印は検出しない** (None。有ると誤認しないため)。
  - `ScreenReader.read_result_values()` が、STAGE FAILED を `failed`、NEW RECORD を `new_record` に入れる。**STAGE FAILED は「クリア失敗」であり、Lively の Retire には相当しない。PS2 版に retire (途中でやめる) に相当するものは無い**。`retire` の概念・設定「retire 時は保存しない」・「リタイアのため保存しなかった」の通知はすべて削除した (失敗したステージも通常どおり記録する)。
  - 対応: STAGE FAILED = popn10 ～ 14 (popn9 は回転する演出で写真の上に出るため対象外。popn7 / 8 / best hits のフリートレーニングのリザルトには出ない)。NEW RECORD = popn10 / 11 / 12。除外検証は 21/22。**STAGE FAILED が「ない」見本 (クリアしたリザルト) がまだ無い** ので、クリア時に誤検出しないかは未確認 (クリアしたリザルトの画像を足して、`failed: false` で登録する)。
- **曲の特定** (`src/ps2_songs.py` の `Ps2SongIdentifier`、`ScoreManager.identify_screen_song()`): オプション画面はバナー (決まらなければ 5 回に 1 回 OCR)、リザルト画面はバナーが出る作品 (popn13 / popn14。`RESULT_BANNER_BOXES`) だけバナーで特定する (相関 0.998)。そのほかのリザルトは曲名が画像フォントの文字だけなので、オプション画面で決めた曲を使う。曲リストの `titles` で、その作品の収録曲に絞る。
- **曲リスト**: `ScoreManager` の既定は `ps2_music_list.json` (あれば)。`musics` に `titles` 列 (カンマ区切りの title_id) を追加し、レベルは PS2 当時の基準 (`*_old`) を `normal` / `hyper` / `ex` に入れる (`*_current` / `five` の列は未実装)。
- メインの `_read_banner_id` が `identify_screen_song` を使い、プレー画面の曲名 OCR (`read_play_song`) は PS2 では空を返す (曲名は画像フォント。難易度の読み取りも未対応)。
- 通し確認 (ヘッドレスのメイン画面 + popn11 の実画像): オプションで「Space Dog」を特定 → プレーで判定の累計を読む → リザルトで 21623 点 / STAGE FAILED / NEW RECORD を読み、`popn11 / Space Dog / 21623` を記録。`tests/test_ps2_result_flow.py` が同じ流れを確認する。

**Lively 用 reader の整理 (完了)**: `judge_reader` / `judge_templates` / `result_reader` / `digit_templates` / `song_reader` と、それらの生成ツール、`banner_reader` の黒縁検出、`define.py` の画面識別定数を削除した。残したのは、Windows OCR のラッパー (`src/win_ocr.py`)、`PlaySongInfo` (`src/song_info.py`)、`ResultValues` (`src/classes.py`)、オプション読み取り (`option_reader` / `option_templates` / `define.py` の `PosOption*`。作り直し予定)。

**未対応 (次)**: 難易度 (N / H / EX / 5) の読み取り、`*_current` / `five` の列、オプション reader の作り直し、`direct_window_capture` の整理、README の更新。

---

## 5. 開発上の注意
- 画面識別は座標・ハッシュ依存で、**ゲーム側のレイアウト変更に弱い**。ハッシュ定数を直書きで増やさず、生成ツール経由にする。
- OCR は Windows 標準 (`Windows.Media.Ocr`) 依存。日本語言語パック必須。PS2 のボトムレゾ画像では拡大前処理 (`_OCR_SCALE`) の再調整が必要になる。
- `config.json` / `popn.db` / `log/` / `out/` / `diagnostics/` / `result_screenshots/` は実行時生成物。コミットしない。
- セキュリティ機構 (署名検証・https のみ・zip 展開検査) は壊さない。`tests/test_security.py` を通すこと。
- 変更はブランチ → PR で行う (`main` は保護されている)。

---

## 6. 共有ファイルとローカルファイル (CLAUDE.md / AGENT.md)

- **`CLAUDE.md` と `AGENT.md` は同一内容にする** (Claude Code 以外のエージェントが読むのが `AGENT.md`)。**編集するのは `CLAUDE.md` だけ**で、直したら `python tools/sync_agent_md.py` で `AGENT.md` に反映する。`tests/test_agent_md.py` が一致を確認する (ずれるとテストが落ちる)。
- 個人情報・機密情報・自分の環境のパス・アカウント名などは **`CLAUDE.local.md` / `AGENT.local.md`** に書く (`.gitignore` 済みでコミットしない)。この 2 つも同一内容にし、同じスクリプトが同期する。
- 共有ファイルには、メールアドレス・個人のパス・トークン・鍵・スクリーンショットの原本を書かない。

## 7. 開発の進め方・環境の注意 (これまでの作業で分かったこと)

### 7.1 作業の進め方
- ユーザーはサンプル画像を `screenshots/<title_id>/<モード>/` に足してから「後続の作業を行ってください」のように依頼する。画像を足す・フォルダを組み替える (popn9 ～ 13 で実際にあった) たびに、**先に画像の分類を再確認**してから、生成物 (`screen_profiles.json`、数字・目印・バナーの参照) を作り直す。
- 方針が分かれる点 (記録に何を持つか、判定を設定にするか自動にするか等) は、案と推奨を示して確認してから実装する。確定した内容は §4 に書き残す。
- 作業は小さな単位で、日本語のコミットメッセージ (何を・なぜ) で区切る。生成物と生成ツールの変更は同じコミットに入れる。
- 画像から読む処理は、**読めないときは None を返し、誤読しない**ことを優先する (数字の見本が無い作品を読まない、「ある」見本が無い目印は検出しない、など)。

### 7.2 実行環境 (Windows)
- テストは `uv run --with pytest python -m pytest tests` (全 94 件、約 3 分)。実行すると `uv.lock` が書き換わることがあるので、終わったら `git checkout -- uv.lock`。システムの Python には `winrt-*` が無く、OCR の処理は `uv run` でしか動かない。
- 長い処理 (`tools/build_screen_profiles.py --eval` は十数分、全テストは約 3 分) は 2 分のタイムアウトを超える。バックグラウンドで走らせて完了を待つ。
- コンソールに日本語を出すスクリプトは先頭で `sys.stdout.reconfigure(encoding="utf-8")`。
- シェルの複数行クォートは壊れやすい。長い一時スクリプトはファイルに書いて実行する。ファイルの編集は Edit / Write ツールが確実。
- `screenshots/`・`tmp_ps2_*`・実行時生成物はコミットしない。

### 7.3 設計上の判断 (理由)
- **STAGE FAILED は「クリア失敗」であり retire ではない**。PS2 版に途中でやめる操作は無いので、retire の概念・設定は全部削除した。失敗したステージも通常どおり記録する。
- **クリアの分類**は `PopnScoreRecord.clear_type` (PERFECT / FULLCOMBO / CLEAR / FAILED)。DB には `failed` だけ保存し、分類は判定値から計算する。FAILED = STAGE FAILED、PERFECT = BAD も GOOD も無い、FULLCOMBO = BAD が無い、CLEAR = 失敗でないと分かったもの。失敗が不明で BAD がある記録は空。履歴一覧の「クリア」列とスクリーンショット条件 (fullcombo / perfect) が使う。
- **プレー環境・モダナイズパッチは設定で選ぶ**。画面から自動認識しない (実機のキャプチャボード経由かは映像から分からないため)。
- **曲名は画像フォントなので OCR を本筋にしない**。バナー特徴量の登録が本筋で、OCR は補助 (§4.9)。
- **画面識別は「作品を確定してから、その作品内でモードを決める」**。作品をまたいで同じに見える画面 (黒一色のロードなど) を、作品内の判定で解決するため。
- 生成物 (`src/*.json`) は手で編集しない。編集したくなったら、サンプル JSON か生成ツールを直す。

### 7.4 未対応・次の作業 (優先度は高い順の目安)
1. **画像の追加と再生成**: クリアしたリザルト (`failed: false` の見本。STAGE FAILED の誤検出確認)、popn7 / 8 / 9 / best hits のリザルト、popn7 / 8 / 10 / 12 / 14 / best hits のプレー、popn10 プレーの数字 4 と 8。足したら `tools/build_ps2_digit_templates.py` / `build_ps2_marks.py` / `build_screen_profiles.py` を再実行する。
2. **オプション reader の作り直し** (§4.2 の作品別テーブル、`Config.modernize_patch` でハイスピードの選択肢を切り替える)。
3. **難易度 (N / H / EX / 5) の読み取り**と、曲リストの `*_current` / `five` 列。
4. プレー画面の score / combo の枠の登録。
5. `direct_window_capture` の整理、README の更新 (retire の記述や Lively の説明がまだ残っている)、リポジトリ名・自動更新の配布先の決定。
