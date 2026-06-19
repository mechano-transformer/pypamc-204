# pypamc_204

[![PyPI](https://img.shields.io/pypi/v/pypamc-204)](https://pypi.org/project/pypamc-204/)
[![Python](https://img.shields.io/pypi/pyversions/pypamc-204)](https://pypi.org/project/pypamc-204/)
[![テスト](https://github.com/mechano-transformer/PAMC-204/actions/workflows/test.yml/badge.svg)](https://github.com/mechano-transformer/PAMC-204/actions/workflows/test.yml)

PAMC-204 / PAMC-204-RJ ピエゾアシストモーターコントローラ用 Python ライブラリ

- **PyPI:** https://pypi.org/project/pypamc-204/
- **GitHub:** https://github.com/mechano-transformer/PAMC-204

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
git clone https://github.com/mechano-transformer/PAMC-204.git
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

# コントローラに接続（アドレス1がデフォルト）
with PAMC204("COM3") as ctrl:
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

```python
from pypamc204 import PAMC204

# context manager（推奨）
with PAMC204("COM3", address=1) as ctrl:
    ...

# 手動で接続管理
ctrl = PAMC204("COM3")
ctrl.open()
# ... 操作 ...
ctrl.close()
```

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

### 生コマンド送信

```python
with PAMC204("COM3") as ctrl:
    response = ctrl.send_raw("E01INF")
    print(response)
```

## コマンド一覧

| メソッド | コマンド | 説明 |
|---|---|---|
| `get_firmware_info()` | `ExxINF` | ファームウェアバージョン確認 |
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
