# pypamc_204

[![PyPI](https://img.shields.io/pypi/v/pypamc-204)](https://pypi.org/project/pypamc-204/)
[![Python](https://img.shields.io/pypi/pyversions/pypamc-204)](https://pypi.org/project/pypamc-204/)
[![テスト](https://github.com/mechano-transformer/pypamc-204/actions/workflows/test.yml/badge.svg)](https://github.com/mechano-transformer/pypamc-204/actions/workflows/test.yml)

PAMC-204 / PAMC-204A / PAMC-204-RJ ピエゾアシストモーターコントローラ用 Python ライブラリ

- **PyPI:** https://pypi.org/project/pypamc-204/
- **GitHub:** https://github.com/mechano-transformer/pypamc-204

## インストール

```bash
pip install pypamc_204
```

開発版（ローカルインストール）：

```bash
cd pypamc-204
pip install -e .
```

## 必要環境

- Python 3.9+
- pyserial

## 開発環境のセットアップ

### 1. リポジトリをクローン

```bash
git clone https://github.com/mechano-transformer/pypamc-204.git
cd pypamc-204
```

### 2. 仮想環境（venv）を作成・有効化

**Windows:**

```bash
python -m venv .venv
.venv\Scripts\activate
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 開発用依存パッケージと共にインストール

```bash
pip install -e ".[dev]"
```

これで `pypamc204` 本体 + `pytest` がインストールされます。

### 4. ユニットテストの実行

```bash
pytest
```

詳細出力で実行する場合：

```bash
pytest -v
```

特定のテストクラスだけ実行する場合：

```bash
pytest tests/test_controller.py::TestRotation -v
```

### 5. 仮想環境の終了

```bash
deactivate
```

## クイックスタート

```python
from pypamc204 import PAMC204

# コントローラに接続（ポートは自動検出、アドレス1がデフォルト）
with PAMC204() as ctrl:
    # ファームウェアバージョン確認
    print(ctrl.get_firmware_info())

    # 出力電圧を100Vに設定
    ctrl.set_voltage(100)

    # CH1を正回転（500Hz, 1000パルス）
    ctrl.rotate_forward(channel=1, frequency=500, pulses=1000)

    # CH2を逆回転（連続駆動）
    ctrl.rotate_reverse(channel=2, frequency=300)

    # 停止
    ctrl.stop()
```

## 使い方

### 接続

ポート名を省略すると、USBのVID/PID（FTDI FT230X: `0403:6015`）が一致する
シリアルポートを自動検出します。ポート名の明示指定も可能です。

```python
from pypamc204 import PAMC204, find_port

# context manager（推奨）。ポート自動検出
with PAMC204(address=1) as ctrl:
    ...

# ポート名を明示指定（自動検出をスキップ）
with PAMC204("COM3", address=1) as ctrl:
    ...

# 手動で接続管理
ctrl = PAMC204()
ctrl.open()
print(ctrl.port)  # 実際に使用中のポート（例: "COM3", "/dev/ttyUSB0"）
# ... 操作 ...
ctrl.close()

# 検出だけ行うことも可能（見つからない/複数候補の場合は ConnectionError）
port = find_port()
```

### アドレス（E01〜E32）の指定方法

PAMC-204 / PAMC-204A は RS-485 で複数台をデイジーチェーン接続できるため、各ドライバは
**E01〜E32 の固有アドレス**を持ちます。コマンドはすべてこのアドレス（`Exx`）を
先頭に付けて送信されます（例: `E01DAC2700`、`E05NR...`）。

このライブラリでは **アドレスを整数 `address` で指定**します。内部で
`E{address:02d}` 形式（2桁ゼロ埋め）の文字列に変換され、コマンド先頭に付加されます。

| `address` 引数 | 送信される先頭文字列 |
|---|---|
| `1`（デフォルト） | `E01` |
| `5` | `E05` |
| `32` | `E32` |

```python
# 接続時にアドレスを固定（最も一般的な使い方）
with PAMC204("COM3", address=1) as ctrl:   # → 以後すべて "E01..." で送信
    ctrl.set_voltage(100)                  # 送信: E01DAC2700

with PAMC204("COM3", address=5) as ctrl:   # → 以後すべて "E05..." で送信
    ctrl.set_voltage(100)                  # 送信: E05DAC2700
```

- 指定できる範囲は **1〜32**。範囲外は `ValueError` になります（`E01`〜`E32` に対応）。
- 既定値は `1`（`E01`）です。

#### 同一ポート上の複数ドライバを扱う

1本のシリアルポートに複数台がぶら下がっている場合は、アドレスごとに
インスタンスを分けるか、`address` 属性を切り替えて使います。

```python
ctrl = PAMC204("COM3")
ctrl.open()

ctrl.address = 1        # 以後 E01 宛て
ctrl.set_voltage(100)

ctrl.address = 2        # 以後 E02 宛て
ctrl.set_voltage(120)

ctrl.close()
```

`ping()` は呼び出し時だけ別アドレスを確認できます（インスタンスの `address` は変わりません）。

```python
with PAMC204("COM3", address=1) as ctrl:
    ctrl.ping(5)        # E05 が応答するか一時的に確認（送信: E05）
```

### チャンネル / 軸（CH1〜CH4 = A〜D）の指定方法

1台のドライバは最大4軸を制御できます。各メソッドの **`channel`** 引数には、
**数字 `1`〜`4`** でも **軸文字 `"A"`〜`"D"`**（大文字・小文字どちらも可）でも指定できます。
両者は次のように対応します。

| 数字 | 軸文字 | 軸 |
|---|---|---|
| `1` | `"A"` | CH1 |
| `2` | `"B"` | CH2 |
| `3` | `"C"` | CH3 |
| `4` | `"D"` | CH4 |

コマンド文字列上の軸表記はコマンド系統で異なりますが、ライブラリが自動変換します。
利用者はどちらの書き方をしても同じ結果になります。

| コマンド系統 | 軸表記 | 例（CH1 / CH2） |
|---|---|---|
| 回転駆動（`NR`/`RR`） | 末尾に `A`〜`D` | `E01NR05000100`**`A`** / …**`B`** |
| 位置・速度・状態系（`PA`/`PR`/`VA`/`DH`/`MD?`/`TP?` ほか） | アドレス直後に `1`〜`4` | `E01`**`1`**`PA5000` / `E01`**`2`**`PA5000` |

```python
with PAMC204("COM3", address=1) as ctrl:
    # 数字でも軸文字でも、どちらでも同じコマンドが送られる
    ctrl.rotate_forward(channel=1,   frequency=500, pulses=100)  # 送信: E01NR05000100A
    ctrl.rotate_forward(channel="A", frequency=500, pulses=100)  # 送信: E01NR05000100A

    ctrl.move_absolute(channel=2,   position=5000)               # 送信: E012PA5000
    ctrl.move_absolute(channel="B", position=5000)               # 送信: E012PA5000
```

`channel` は **`1`/`2`/`3`/`4`、または `"A"`/`"B"`/`"C"`/`"D"`（小文字可）のいずれか**のみを
受け付けます。それ以外（`0`、`5`、`"1"`、`"E"`、`True` など）は `ValueError` になります。

### コマンドの応答有無について

PAMC-204 / PAMC-204A には**応答を返すコマンドと返さないコマンド**があり、本ライブラリは
これをメソッド単位で正しく区別しています（実機マニュアル準拠）。

- **応答あり**: `ping()` / `set_address()` / `set_voltage()` / `rotate_forward()` /
  `rotate_reverse()` / `stop()`、および末尾が `?` の問い合わせ系すべて。
  → メソッドは応答（`OK` 確認値・`FIN`パルス数・問い合わせ値）を返します。
  応答が無い場合は `TimeoutError`。
- **応答なし**: `abort()` / `stop_channel()` / `set_home()` / `move_absolute()` /
  `move_relative()` / `move_indefinite()` / `set_velocity()`。
  → 送信のみで戻り値はありません（`timeout` 待ちは発生しません）。

### ドライバの検出

```python
with PAMC204("COM3") as ctrl:
    # 特定アドレスにドライバが存在するか確認
    if ctrl.ping(1):
        print("E01 is connected")

    # 全アドレス (1–32) をスキャン
    found = ctrl.scan_addresses()
    print(f"Found drivers: {found}")
```

### アドレス変更

```python
# ※単一ドライバ接続時のみ実行すること
with PAMC204("COM3") as ctrl:
    ctrl.set_address(5)  # アドレスを E05 に変更
```

### 出力電圧の調整

```python
with PAMC204("COM3") as ctrl:
    # 70, 80, 90, 100, 110, 120, 130, 140, 150V から選択
    ctrl.set_voltage(120)

    # DAC値を直接指定（1900–4095）
    ctrl.set_voltage_raw(3000)
```

### モーター駆動（正回転 / 逆回転）

```python
with PAMC204("COM3") as ctrl:
    # 正回転: CH1, 1000Hz, 5000パルス
    ctrl.rotate_forward(channel=1, frequency=1000, pulses=5000)

    # 逆回転: CH2, 500Hz, 連続駆動（pulses=0）
    ctrl.rotate_reverse(channel=2, frequency=500)

    # 拡張パルス（最大999999パルス）
    ctrl.rotate_forward(channel=1, frequency=800, pulses=100000)

    # 連続駆動を停止（駆動パルス数が返る）
    result = ctrl.stop()
    print(result)  # e.g. "E01FIN1456"

    # パルス数だけ取得
    count = ctrl.get_stop_pulse_count()
```

### モーション停止

```python
with PAMC204("COM3") as ctrl:
    # 連続駆動を停止（パルス数レスポンスあり）
    ctrl.stop()

    # 全チャンネル即時停止（レスポンスなし）
    ctrl.abort()

    # 特定チャンネルの停止（レスポンスなし）
    ctrl.stop_channel(channel=1)
```

### ホームポジション

```python
with PAMC204("COM3") as ctrl:
    # ホームポジション設定
    ctrl.set_home(channel=1, position=1000)

    # ホームポジション取得
    home = ctrl.get_home(channel=1)
    print(f"Home position: {home}")
```

### 位置制御

```python
with PAMC204("COM3") as ctrl:
    # 速度設定（1–1500 steps/sec）
    ctrl.set_velocity(channel=1, velocity=500)

    # 絶対位置へ移動
    ctrl.move_absolute(channel=1, position=5000)

    # 相対移動（現在位置から+1000ステップ）
    ctrl.move_relative(channel=1, steps=1000)

    # 無限移動
    ctrl.move_indefinite(channel=1, direction="+")

    # 動作完了を待つ
    ctrl.wait_until_done(channel=1, timeout=10.0)
```

### 加速度設定（F/W Ver.0.2.1以降）

`ExxmACnnnn` / `ExxmAC?` に対応します。加速度は **1〜150000 steps/sec²** の範囲で指定します。

```python
with PAMC204("COM3") as ctrl:
    # 加速度設定（軸文字でも指定可）
    ctrl.set_acceleration(channel=1, acceleration=10000)   # 送信: E011AC10000
    ctrl.set_acceleration(channel="A", acceleration=10000) # 同上

    # 加速度の問い合わせ
    acc = ctrl.get_acceleration(channel=1)                 # 送信: E011AC?
    print(f"Acceleration: {acc} steps/sec^2")
```

**加速度が作用するコマンド:** 無限移動（`move_indefinite`）/ 絶対位置移動（`move_absolute`）/
相対移動（`move_relative`）/ 動作停止（`stop_channel`）。
**非対応:** パルス駆動（`rotate_forward` / `rotate_reverse`）と連続駆動停止（`stop`）。

> **注意:** 本コマンドは PAMC-204 / PAMC-204A ファームウェア **Ver.0.2.1 以降**でのみ利用できます。
> 範囲外（0 や 150001、小数など）や非整数を指定すると `ValueError` になります。

### ステータス問い合わせ

```python
with PAMC204("COM3") as ctrl:
    # 実位置
    pos = ctrl.get_position(channel=1)

    # 目標位置（駆動中: 目標位置 / 停止中: 実位置）
    target = ctrl.get_target_position(channel=1)

    # 相対移動の目標位置
    rel_target = ctrl.get_relative_target(channel=1)

    # 速度
    vel = ctrl.get_velocity(channel=1)

    # 動作完了チェック（True=停止, False=駆動中）
    done = ctrl.is_motion_done(channel=1)

    # 移動チェック（True=移動中, False=停止）
    moving = ctrl.is_moving(channel=1)
```

### 動作状態・シリアル番号・FIN送信設定

```python
with PAMC204("COM3") as ctrl:
    # 動作状態の問い合わせ（F/W Ver.0.1.7以降）
    status = ctrl.get_drive_status()   # "S"（停止）/ "NR1500A"（正回転中）/ "RR1500A"（逆回転中）
    if ctrl.is_driving():
        print(f"駆動中: {status}")

    # 連続駆動停止時のパルス数送信ON/OFF（F/W Ver.0.1.8以降）
    ctrl.set_txfin(True)               # stop() が "FIN<パルス数>" を返すようにする（既定）
    # ctrl.set_txfin(False)            # ※OFFにすると stop() は応答を返さず TimeoutError になる

    # シリアルナンバーの取得
    sn = ctrl.get_serial_number()      # e.g. "10001"
```

### 4チャンネル一括操作

CH1〜CH4 へ順次コマンドを送信するユーティリティです（libpamc-204 / libpamc-204A の
`*_all_channels` API 相当）。PAMC-204 / PAMC-204A は同時に1軸ずつ駆動するため、内部でも順次実行されます。

```python
with PAMC204("COM3") as ctrl:
    # 全CHを同じ相対量だけ移動
    ctrl.move_relative_all(1000)

    # 全CHを同じ方向に無限移動
    ctrl.move_indefinite_all("+")

    # 全CHを個別に停止（ExxmST）。即時全停止は abort() を使用。
    ctrl.stop_all()

    # 全CHの実位置 / 動作完了ステータスをまとめて取得
    positions = ctrl.get_position_all()      # [CH1, CH2, CH3, CH4]
    done = ctrl.get_motion_done_all()        # [True/False, ...]
```

### 生コマンド送信

```python
with PAMC204("COM3") as ctrl:
    response = ctrl.send_raw("E01INF")
    print(response)
```

## コマンド一覧

| メソッド | コマンド | 説明 |
|---|---|---|
| `get_firmware_info()` | `INF` [^inf] | ファームウェアバージョン確認 |
| `ping()` | `Exx` | ドライバ存在確認 |
| `set_address()` | `SETADDRxx` | アドレス変更 |
| `set_voltage()` | `ExxDACnnnn` | 出力電圧調整 |
| `rotate_forward()` | `ExxNRnnnnyyyyz` | 正回転駆動 |
| `rotate_reverse()` | `ExxRRnnnnyyyyz` | 逆回転駆動 |
| `stop()` | `ExxS` | 連続駆動停止 |
| `abort()` | `ExxAB` | モーション停止 |
| `set_home()` | `ExxmDHnnnn` | ホームポジション設定 |
| `get_home()` | `ExxmDH?` | ホームポジション問い合わせ |
| `is_motion_done()` | `ExxmMD?` | 動作完了ステータス |
| `move_indefinite()` | `ExxmMVn` | 無限移動 |
| `is_moving()` | `ExxmMV?` | 移動方向問い合わせ |
| `move_absolute()` | `ExxmPAnnnn` | 絶対位置移動 |
| `get_target_position()` | `ExxmPA?` | 目標位置問い合わせ |
| `move_relative()` | `ExxmPRnnnn` | 相対移動 |
| `get_relative_target()` | `ExxmPR?` | 相対目標位置問い合わせ |
| `stop_channel()` | `ExxmST` | チャンネル動作停止 |
| `get_position()` | `ExxmTP?` | 実位置問い合わせ |
| `set_velocity()` | `ExxmVAnnnn` | 速度設定 |
| `get_velocity()` | `ExxmVA?` | 速度問い合わせ |
| `set_acceleration()` | `ExxmACnnnn` | 加速度設定（F/W Ver.0.2.1以降） |
| `get_acceleration()` | `ExxmAC?` | 加速度問い合わせ（F/W Ver.0.2.1以降） |
| `get_drive_status()` / `is_driving()` | `ExxST?` | 動作状態問い合わせ（F/W Ver.0.1.7以降） |
| `set_txfin()` | `ExxTXFINn` | 停止時パルス数送信ON/OFF（F/W Ver.0.1.8以降） |
| `get_serial_number()` | `ExxSNO?` | シリアルナンバー問い合わせ |
| `move_relative_all()` | `ExxmPRnnnn` ×4 | 全CH一括相対移動 |
| `move_indefinite_all()` | `ExxmMVn` ×4 | 全CH一括無限移動 |
| `stop_all()` | `ExxmST` ×4 | 全CH一括停止 |
| `get_position_all()` | `ExxmTP?` ×4 | 全CH実位置取得 |
| `get_motion_done_all()` | `ExxmMD?` ×4 | 全CH動作完了ステータス取得 |

[^inf]: マニュアル上の構文は `ExxINF` ですが、ファームウェアバージョン確認はアドレスなしの `INF` を送信します（`get_firmware_info()` の実装に準拠）。

## 通信仕様

| 項目 | 値 |
|---|---|
| ボーレート | 115200 bps |
| データビット | 8 bit |
| パリティ | None |
| ストップビット | 1 bit |
| フロー制御 | None |
| デリミタ | CR + LF |

## ライセンス

MIT
