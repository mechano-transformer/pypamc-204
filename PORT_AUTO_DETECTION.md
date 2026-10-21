# ポート自動検出

## 概要

`PAMC204(port=None)` でポート名を省略すると、`open()` 時に `find_port()` が
接続中のUSBシリアルポートからコントローラを自動検出する。
`COM3` や `/dev/ttyUSB0` のようなポート名を環境ごとに調べて指定する必要がなくなる。

## 仕組み

1. pyserial の `serial.tools.list_ports.comports()` で全シリアルポートを列挙する
   （Windows は SetupAPI、Linux は sysfs 経由。外部コマンドへの依存なし）
2. 各ポートのUSB VID/PID を既定値 `0x0403:0x6015`（FTDI FT230X = PAMC-204 / PAMC-204A 搭載チップ）と照合する
3. 結果に応じて以下のように動作する

| 一致件数 | 動作 |
| --- | --- |
| 1件 | そのポートを採用 |
| 0件 | `ConnectionError`（接続確認またはポート明示指定を促す） |
| 複数件 | `ConnectionError`（候補一覧を提示。誤接続防止のため自動選択しない） |

VID/PID が異なる個体には `find_port(vid=..., pid=...)` で対応できる。

## 制約

- `0403:6015` は FT230X チップの汎用IDのため、**同じチップを使う他社製USBシリアル機器と区別できない**
- 同一VID/PIDの機器が複数接続されている場合は特定できない（エラーにして明示指定を促す）

## 恒久対応（安定してポートを特定するために）

確実性の高い順。

1. **カスタムPIDの書き込み（推奨）**
   FT230X の EEPROM に FTDI 提供ツール（FT_PROG）で PAMC-204 / PAMC-204A 専用の PID を書き込む。
   汎用IDとの衝突が根本的になくなる。ライブラリ側は `USB_PID` 定数の変更のみで対応可能。
2. **接続後の機種確認（プローブ方式）**
   候補ポートを open して `INF` コマンドを送り、レスポンスに `PAMC` が含まれるか検証する。
   複数候補があっても順に試すことで特定できる。将来 `find_port(probe=True)` として拡張可能。
3. **シリアル番号による個体識別**
   `list_ports` の `serial_number` 属性（FTDIチップの iSerial）と照合する。
   同型機を複数接続する構成で有効。
4. **OS側でポートを固定する**
   - Linux: udev ルールで固定名を割り当てる
     `SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6015", SYMLINK+="pamc204"`
   - Windows: デバイスマネージャーで COM ポート番号を固定する
