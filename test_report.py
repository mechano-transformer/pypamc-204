"""PAMC-204 / PAMC-204A 設計検証報告書用テストスクリプト

READMEに記載の公開メソッド37項目を実機で順に試験し、結果を標準出力と
TSVファイル（Excel貼り付け用、「YYYYMMDD pypamc-204試験結果表.tsv」）に出力する。

使い方:
    python test_report.py          # ポート自動検出（FTDI FT230X）
    python test_report.py COM4     # ポート明示指定

注意:
    - CH1にモーターを接続した単一ドライバ（E01）構成を想定。
    - モーターが実際に動作する（±200ステップ程度・短時間の連続駆動）。
      試験終了後、CH1は初期位置へ復帰する。
"""
import io
import sys
import time
from datetime import date
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from pypamc204 import PAMC204

PORT = sys.argv[1] if len(sys.argv) > 1 else None  # None = 自動検出
CH = 1  # モーター接続チャンネル
RESULTS = []  # (num, name, result, judge)
STATE = {}  # 試験間で受け渡す値


def test(num, name, func):
    try:
        result = func()
        RESULTS.append((num, name, str(result), "OK"))
        print(f"  [{num:2d}] {name} => {result}  ... OK")
    except Exception as e:
        RESULTS.append((num, name, f"{type(e).__name__}: {e}", "NG"))
        print(f"  [{num:2d}] {name} => {type(e).__name__}: {e}  ... NG")


def drain(ctrl, timeout=0.3):
    """受信バッファに残った非同期レスポンス（FIN等）を読み捨てる"""
    lines = []
    while True:
        line = ctrl._recv(timeout=timeout)
        if line is None:
            break
        lines.append(line)
    return lines


with PAMC204(PORT) as ctrl:
    print(f"接続: {ctrl.port} (E{ctrl.address:02d})")

    # 準備: 停止時FIN応答を有効化（OFFだと stop() がタイムアウトする）
    ctrl.set_txfin(True)

    # ── 接続・情報系 ──────────────────────────────────────
    test(1, "get_firmware_info()", lambda: ctrl.get_firmware_info())
    test(2, "ping()", lambda: ctrl.ping())

    def scan():
        # 応答なしアドレスの待ち時間を短縮してスキャン
        old = ctrl._ser.timeout
        ctrl._ser.timeout = 0.3
        try:
            return ctrl.scan_addresses()
        finally:
            ctrl._ser.timeout = old
    test(3, "scan_addresses()", scan)

    # 現アドレスと同じ値を設定（実質無変更で動作のみ確認）
    test(4, "set_address()", lambda: ctrl.set_address(ctrl.address))

    # ── 出力電圧 ─────────────────────────────────────────
    test(5, "set_voltage()", lambda: ctrl.set_voltage(100))
    test(6, "set_voltage_raw()", lambda: ctrl.set_voltage_raw(2700))  # 100V相当

    # ── 回転駆動 ─────────────────────────────────────────
    def rotate(func):
        resp = func(channel=CH, frequency=500, pulses=100)
        time.sleep(0.5)
        fin = drain(ctrl)
        return resp + (f" / 完了通知: {' '.join(fin)}" if fin else "")
    test(7, "rotate_forward()", lambda: rotate(ctrl.rotate_forward))
    test(8, "rotate_reverse()", lambda: rotate(ctrl.rotate_reverse))

    def stop_test():
        ctrl.rotate_forward(channel=CH, frequency=300, pulses=0)
        time.sleep(0.5)
        return f"{ctrl.stop()}（連続駆動0.5秒→停止。※要TXFIN=ON）"
    test(9, "stop()", stop_test)

    def pulse_count_test():
        ctrl.rotate_reverse(channel=CH, frequency=300, pulses=0)
        time.sleep(0.5)
        return f"{ctrl.get_stop_pulse_count()}（連続駆動0.5秒→停止しパルス数取得）"
    test(10, "get_stop_pulse_count()", pulse_count_test)

    # 準備: 位置制御系のため全CHに速度・加速度を設定し、初期位置を記録
    for ch in (1, 2, 3, 4):
        ctrl.set_velocity(ch, 500)
        ctrl.set_acceleration(ch, 10000)
    init_pos = ctrl.get_position(CH)
    print(f"  (準備: 全CH 速度500/加速度10000, CH1初期位置={init_pos})")

    # ── モーション停止 ────────────────────────────────────
    def abort_test():
        ctrl.move_indefinite(CH, "+")
        time.sleep(0.3)
        ctrl.abort()
        time.sleep(0.3)
        done = ctrl.is_motion_done(CH)
        return f"駆動中に送信(応答なし) → 停止確認 MD?={'1(停止)' if done else '0(駆動中)'}"
    test(11, "abort()", abort_test)

    def stop_channel_test():
        ctrl.move_indefinite(CH, "+")
        time.sleep(0.3)
        ctrl.stop_channel(CH)
        time.sleep(0.5)
        done = ctrl.is_motion_done(CH)
        return f"駆動中に送信(応答なし) → 停止確認 MD?={'1(停止)' if done else '0(駆動中)'}"
    test(12, "stop_channel()", stop_channel_test)

    # ── ホームポジション ──────────────────────────────────
    def set_home_test():
        home0 = ctrl.get_home(CH)
        ctrl.set_home(CH, 1000)
        v = ctrl.get_home(CH)
        ctrl.set_home(CH, home0)  # 元に戻す
        return f"DH1000設定 → DH?={v}" + ("（一致）" if v == 1000 else "（不一致!）")
    test(13, "set_home()", set_home_test)
    test(14, "get_home()", lambda: ctrl.get_home(CH))

    # ── 速度・位置制御 ────────────────────────────────────
    def set_velocity_test():
        ctrl.set_velocity(CH, 500)
        v = ctrl.get_velocity(CH)
        return f"VA500設定 → VA?={v}" + ("（一致）" if v == 500 else "（不一致!）")
    test(15, "set_velocity()", set_velocity_test)
    test(16, "get_velocity()", lambda: ctrl.get_velocity(CH))

    def move_absolute_test():
        cur = ctrl.get_position(CH)
        ctrl.move_absolute(CH, cur + 200)
        ok = ctrl.wait_until_done(CH, timeout=15)
        pos = ctrl.get_position(CH)
        return f"{cur} → 目標{cur + 200} → 実位置{pos}" + ("" if ok else "（タイムアウト）")
    test(17, "move_absolute()", move_absolute_test)
    test(18, "get_target_position()", lambda: ctrl.get_target_position(CH))

    def move_relative_test():
        cur = ctrl.get_position(CH)
        ctrl.move_relative(CH, -200)
        ok = ctrl.wait_until_done(CH, timeout=15)
        pos = ctrl.get_position(CH)
        return f"{cur} → -200 → 実位置{pos}" + ("" if ok else "（タイムアウト）")
    test(19, "move_relative()", move_relative_test)
    test(20, "get_relative_target()", lambda: ctrl.get_relative_target(CH))

    def move_indefinite_test():
        ctrl.move_indefinite(CH, "+")
        time.sleep(0.2)
        STATE["moving"] = ctrl.is_moving(CH)
        return f"MV+送信(応答なし) → 移動中確認 MV?={'移動中' if STATE['moving'] else '停止'}"
    test(21, "move_indefinite()", move_indefinite_test)
    test(22, "is_moving()", lambda: f"{STATE['moving']}（無限移動中に取得）")
    ctrl.stop_channel(CH)
    time.sleep(0.5)

    test(23, "is_motion_done()", lambda: ctrl.is_motion_done(CH))

    def wait_until_done_test():
        ctrl.move_relative(CH, 100)
        t0 = time.monotonic()
        ok = ctrl.wait_until_done(CH, timeout=15)
        return f"{ok}（{time.monotonic() - t0:.2f}秒で完了）"
    test(24, "wait_until_done()", wait_until_done_test)
    test(25, "get_position()", lambda: ctrl.get_position(CH))

    # ── 加速度（F/W Ver.0.2.1以降） ───────────────────────
    def set_acceleration_test():
        ctrl.set_acceleration(CH, 10000)
        v = ctrl.get_acceleration(CH)
        return f"AC10000設定 → AC?={v}" + ("（一致）" if v == 10000 else "（不一致!）")
    test(26, "set_acceleration()", set_acceleration_test)
    test(27, "get_acceleration()", lambda: ctrl.get_acceleration(CH))

    # ── 動作状態・FIN送信設定・シリアルNo. ─────────────────
    def drive_status_test():
        s_idle = ctrl.get_drive_status()
        ctrl.rotate_forward(channel=CH, frequency=300, pulses=0)
        time.sleep(0.3)
        s_drive = ctrl.get_drive_status()
        STATE["driving"] = ctrl.is_driving()
        ctrl.stop()
        drain(ctrl)
        return f"停止時={s_idle} / 駆動中={s_drive}"
    test(28, "get_drive_status()", drive_status_test)
    test(29, "is_driving()", lambda: f"{STATE['driving']}（連続駆動中に取得）")
    test(30, "set_txfin()", lambda: ctrl.set_txfin(True))
    test(31, "get_serial_number()", lambda: ctrl.get_serial_number())

    # ── 4チャンネル一括操作 ───────────────────────────────
    def move_relative_all_test():
        before = ctrl.get_position_all()
        ctrl.move_relative_all(100)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 20:
            if all(ctrl.get_motion_done_all()):
                break
            time.sleep(0.2)
        after = ctrl.get_position_all()
        return f"{before} → +100 → {after}"
    test(32, "move_relative_all()", move_relative_all_test)

    def move_indefinite_all_test():
        ctrl.move_indefinite_all("+")
        time.sleep(0.3)
        return "全CHにMV+送信(応答なし) → 0.3秒駆動"
    test(33, "move_indefinite_all()", move_indefinite_all_test)

    def stop_all_test():
        ctrl.stop_all()
        time.sleep(0.5)
        return f"全CHにST送信(応答なし) → 停止確認 MD?={ctrl.get_motion_done_all()}"
    test(34, "stop_all()", stop_all_test)

    test(35, "get_position_all()", lambda: ctrl.get_position_all())
    test(36, "get_motion_done_all()", lambda: ctrl.get_motion_done_all())

    # ── 生コマンド送信 ────────────────────────────────────
    test(37, "send_raw()", lambda: ctrl.send_raw(f"{ctrl._addr()}SNO?"))

    # 後始末: CH1を初期位置へ復帰
    ctrl.move_absolute(CH, init_pos)
    ctrl.wait_until_done(CH, timeout=20)
    print(f"  (後始末: CH1を初期位置{init_pos}へ復帰 → {ctrl.get_position(CH)})")

# ── 結果出力 ─────────────────────────────────────────────
print("\n=== 試験結果まとめ ===")
print(f"{'#':<4} {'コマンド':<25} {'結果':<50} {'判定'}")
print("-" * 90)
for num, name, result, judge in RESULTS:
    print(f"{num:<4} {name:<25} {result:<50} {judge}")

tsv_path = Path(__file__).parent / f"{date.today():%Y%m%d} pypamc-204試験結果表.tsv"
with open(tsv_path, "w", encoding="utf-8-sig", newline="") as f:
    f.write("#\tコマンド\t結果\t判定\n")
    for num, name, result, judge in RESULTS:
        f.write(f"{num}\t{name}\t{result}\t{'○' if judge == 'OK' else '×'}\n")

ng = sum(1 for r in RESULTS if r[3] == "NG")
print(f"\n{len(RESULTS)}項目中 OK={len(RESULTS) - ng}, NG={ng}")
print(f"TSV出力: {tsv_path}")
