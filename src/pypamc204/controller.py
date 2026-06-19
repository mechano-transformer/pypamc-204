from __future__ import annotations

import re
import time
from typing import Optional

import serial

from .exceptions import (
    BusyError,
    CommandError,
    ConnectionError,
    TimeoutError,
    ValueRangeError,
)

# 電圧(V) → DAC値の変換テーブル
VOLTAGE_TABLE = {
    150: 4095,
    140: 3750,
    130: 3450,
    120: 3200,
    110: 3000,
    100: 2700,
    90: 2450,
    80: 2200,
    70: 1900,
}

# チャンネル番号 → コマンド文字の変換テーブル
CHANNEL_MAP = {1: "A", 2: "B", 3: "C", 4: "D"}


class PAMC204:
    """PAMC-204 / PAMC-204-RJ ピエゾアシストモーターコントローラのドライバクラス

    Parameters
    ----------
    port : str
        シリアルポート名（例: ``"COM3"``、``"/dev/ttyUSB0"``）
    address : int
        ドライバアドレス（1〜32）。デフォルトは1。
    timeout : float
        シリアル受信タイムアウト（秒）。デフォルトは1.0。
    """

    def __init__(
        self,
        port: str,
        address: int = 1,
        timeout: float = 1.0,
    ) -> None:
        self._validate_address(address)
        self.address = address
        self.timeout = timeout
        self._ser: Optional[serial.Serial] = None
        self._port = port

    # ── 接続管理 ───────────────────────────────────────────────

    def open(self) -> None:
        """シリアル接続を開く"""
        try:
            self._ser = serial.Serial(
                port=self._port,
                baudrate=115200,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
            )
        except serial.SerialException as e:
            raise ConnectionError(f"{self._port} のオープンに失敗: {e}") from e

    def close(self) -> None:
        """シリアル接続を閉じる"""
        if self._ser and self._ser.is_open:
            self._ser.close()

    def __enter__(self) -> "PAMC204":
        self.open()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    @property
    def is_open(self) -> bool:
        """シリアルポートが開いているかどうか"""
        return self._ser is not None and self._ser.is_open

    # ── 低レベル通信 ──────────────────────────────────────────

    def _send(self, command: str) -> None:
        """コマンド文字列を送信する"""
        if not self.is_open:
            raise ConnectionError("シリアルポートが開いていません。先にopen()を呼んでください。")
        self._ser.reset_input_buffer()
        self._ser.write((command + "\r\n").encode("ascii"))

    def _recv(self, timeout: Optional[float] = None) -> Optional[str]:
        """1行受信する。タイムアウト時はNoneを返す。"""
        if not self.is_open:
            raise ConnectionError("シリアルポートが開いていません。先にopen()を呼んでください。")
        old_timeout = self._ser.timeout
        if timeout is not None:
            self._ser.timeout = timeout
        try:
            line = self._ser.readline()
        finally:
            self._ser.timeout = old_timeout
        if not line:
            return None
        return line.decode("ascii", errors="replace").strip()

    def _send_recv(self, command: str, timeout: Optional[float] = None) -> str:
        """コマンドを送信し、レスポンスを受信して返す"""
        self._send(command)
        resp = self._recv(timeout=timeout)
        if resp is None:
            raise TimeoutError(f"コマンドに対するレスポンスなし: {command}")
        self._check_error(resp)
        return resp

    def _check_error(self, response: str) -> None:
        """レスポンスにエラーが含まれていないかチェックする"""
        upper = response.upper()
        if upper == "BUSY":
            raise BusyError("ドライバが駆動中です。先にモーターを停止してください。")
        if upper == "ERROR VALUE RANGE":
            raise ValueRangeError("DAC値が範囲外です。")
        if upper.startswith("ERROR"):
            raise CommandError(f"ドライバエラー: {response}")

    def _addr(self) -> str:
        """現在のアドレスをExx形式の文字列で返す"""
        return f"E{self.address:02d}"

    # ── バリデーション ────────────────────────────────────────

    @staticmethod
    def _validate_address(addr: int) -> None:
        if not 1 <= addr <= 32:
            raise ValueError(f"アドレスは1〜32の範囲で指定してください（入力値: {addr}）")

    @staticmethod
    def _validate_channel(ch: int) -> None:
        if ch not in CHANNEL_MAP:
            raise ValueError(f"チャンネルは1〜4の範囲で指定してください（入力値: {ch}）")

    @staticmethod
    def _validate_frequency(freq: int) -> None:
        if not 1 <= freq <= 1500:
            raise ValueError(f"周波数は1〜1500 Hzの範囲で指定してください（入力値: {freq}）")

    # ── 1. ExxINF – ファームウェアバージョン確認 ─────────────

    def get_firmware_info(self) -> str:
        """ファームウェアバージョンを取得する

        Returns
        -------
        str
            ドライバから返されたファームウェアバージョン文字列
        """
        return self._send_recv(f"{self._addr()}INF")

    # ── 2. Exx – ドライバ存在確認 ────────────────────────────

    def ping(self, address: Optional[int] = None) -> bool:
        """指定アドレスにドライバが存在するか確認する

        Parameters
        ----------
        address : int, optional
            確認するアドレス。省略時はこのインスタンスのアドレスを使用。

        Returns
        -------
        bool
            ドライバが応答した場合True、応答なしの場合False
        """
        addr = address if address is not None else self.address
        self._validate_address(addr)
        self._send(f"E{addr:02d}")
        resp = self._recv()
        if resp is None:
            return False
        return "OK" in resp.upper()

    # ── 3. SETADDRxx – アドレス変更 ─────────────────────────

    def set_address(self, new_address: int) -> str:
        """ドライバのアドレスを変更する

        Parameters
        ----------
        new_address : int
            新しいアドレス（1〜32）

        .. warning::
            単一ドライバ接続時のみ実行してください。
        """
        self._validate_address(new_address)
        resp = self._send_recv(f"SETADDR{new_address:02d}")
        self.address = new_address
        return resp

    # ── 4. ExxDACnnnn – 出力電圧調整 ────────────────────────

    def set_voltage(self, voltage: int) -> str:
        """出力電圧を設定する

        Parameters
        ----------
        voltage : int
            目標電圧（V）。70, 80, 90, 100, 110, 120, 130, 140, 150 のいずれか。
        """
        if voltage not in VOLTAGE_TABLE:
            raise ValueError(
                f"電圧は {sorted(VOLTAGE_TABLE.keys())} のいずれかを指定してください（入力値: {voltage}）"
            )
        dac = VOLTAGE_TABLE[voltage]
        return self._send_recv(f"{self._addr()}DAC{dac}")

    def set_voltage_raw(self, dac_value: int) -> str:
        """DAC値を直接指定して出力電圧を設定する（1900〜4095）"""
        if not 1900 <= dac_value <= 4095:
            raise ValueError(f"DAC値は1900〜4095の範囲で指定してください（入力値: {dac_value}）")
        return self._send_recv(f"{self._addr()}DAC{dac_value}")

    # ── 5. ExxNR – 正回転駆動 ───────────────────────────────

    def rotate_forward(
        self,
        channel: int,
        frequency: int,
        pulses: int = 0,
    ) -> str:
        """モーターを正回転（+）方向に駆動する

        Parameters
        ----------
        channel : int
            駆動チャンネル（1〜4）
        frequency : int
            駆動周波数（1〜1500 Hz）
        pulses : int
            駆動パルス数。0で連続駆動。
            1〜9999は通常モード、1〜999999は拡張モード。
        """
        self._validate_channel(channel)
        self._validate_frequency(frequency)
        ch = CHANNEL_MAP[channel]
        cmd = self._build_drive_cmd("NR", frequency, pulses, ch)
        return self._send_recv(f"{self._addr()}{cmd}")

    # ── 6. ExxRR – 逆回転駆動 ───────────────────────────────

    def rotate_reverse(
        self,
        channel: int,
        frequency: int,
        pulses: int = 0,
    ) -> str:
        """モーターを逆回転（−）方向に駆動する

        パラメータは :meth:`rotate_forward` と同じ。
        """
        self._validate_channel(channel)
        self._validate_frequency(frequency)
        ch = CHANNEL_MAP[channel]
        cmd = self._build_drive_cmd("RR", frequency, pulses, ch)
        return self._send_recv(f"{self._addr()}{cmd}")

    def _build_drive_cmd(
        self, prefix: str, freq: int, pulses: int, ch: str
    ) -> str:
        """駆動コマンド文字列を組み立てる"""
        freq_s = f"{freq:04d}"
        if pulses == 0:
            return f"{prefix}{freq_s}0000{ch}"
        if 1 <= pulses <= 9999:
            return f"{prefix}{freq_s}{pulses:04d}{ch}"
        if 1 <= pulses <= 999999:
            return f"{prefix}{freq_s}X{pulses:06d}{ch}"
        raise ValueError(f"パルス数は0〜999999の範囲で指定してください（入力値: {pulses}）")

    # ── 7. ExxS – 連続駆動停止 ──────────────────────────────

    def stop(self) -> str:
        """連続駆動を停止し、駆動パルス数を含むレスポンスを返す

        Returns
        -------
        str
            ``"E01FIN1456"`` のような駆動パルス数を含む文字列
        """
        return self._send_recv(f"{self._addr()}S")

    def get_stop_pulse_count(self) -> Optional[int]:
        """連続駆動を停止し、実際に駆動したパルス数を返す"""
        resp = self.stop()
        m = re.search(r"FIN(\d+)", resp)
        return int(m.group(1)) if m else None

    # ── 8. ExxAB – モーション停止 ──────────────────────────

    def abort(self) -> None:
        """全チャンネルのモーション即時停止（レスポンスなし）"""
        self._send(f"{self._addr()}AB")

    # ── 9. ExxmDHnnnn – ホームポジション設定 ─────────────────

    def set_home(self, channel: int, position: int) -> None:
        """チャンネルのホームポジション（絶対位置）を設定する

        Parameters
        ----------
        channel : int
            チャンネル（1〜4）
        position : int
            ホームポジション（−2147483648 〜 +2147483647）
        """
        self._validate_channel(channel)
        self._send(f"{self._addr()}{channel}DH{position}")

    # ── 10. ExxmDH? – ホームポジション問い合わせ ─────────────

    def get_home(self, channel: int) -> int:
        """チャンネルのホームポジションを取得する"""
        self._validate_channel(channel)
        resp = self._send_recv(f"{self._addr()}{channel}DH?")
        return int(resp)

    # ── 11. ExxmMD? – 動作完了ステータス問い合わせ ────────────

    def is_motion_done(self, channel: int) -> bool:
        """チャンネルの動作が完了しているか確認する

        Returns
        -------
        bool
            停止中ならTrue、駆動中ならFalse
        """
        self._validate_channel(channel)
        resp = self._send_recv(f"{self._addr()}{channel}MD?")
        return resp.strip() == "1"

    # ── 12. ExxmMVn – 無限移動 ─────────────────────────────

    def move_indefinite(self, channel: int, direction: str) -> None:
        """チャンネルのモーターを無限移動させる

        Parameters
        ----------
        channel : int
            チャンネル（1〜4）
        direction : str
            移動方向。``"+"`` または ``"-"``。
        """
        self._validate_channel(channel)
        if direction not in ("+", "-"):
            raise ValueError(f"方向は '+' または '-' で指定してください（入力値: {direction!r}）")
        self._send(f"{self._addr()}{channel}MV{direction}")

    # ── 13. ExxmMV? – 移動状況問い合わせ ─────────────────────

    def is_moving(self, channel: int) -> bool:
        """チャンネルのモーターが移動中かどうか確認する

        Returns
        -------
        bool
            移動中ならTrue、停止中ならFalse
        """
        self._validate_channel(channel)
        resp = self._send_recv(f"{self._addr()}{channel}MV?")
        return resp.strip() == "0"

    # ── 14. ExxmPAnnnn – 絶対位置移動 ──────────────────────

    def move_absolute(self, channel: int, position: int) -> None:
        """モーターを絶対位置に移動させる

        Parameters
        ----------
        channel : int
            チャンネル（1〜4）
        position : int
            目標絶対位置（−2147483648 〜 +2147483647）
        """
        self._validate_channel(channel)
        self._send(f"{self._addr()}{channel}PA{position}")

    # ── 15. ExxmPA? – 目標位置問い合わせ ─────────────────────

    def get_target_position(self, channel: int) -> int:
        """目標位置を取得する（駆動中: 目標位置、停止中: 実位置）"""
        self._validate_channel(channel)
        resp = self._send_recv(f"{self._addr()}{channel}PA?")
        return int(resp)

    # ── 16. ExxmPRnnnn – 相対位置移動 ──────────────────────

    def move_relative(self, channel: int, steps: int) -> None:
        """現在位置から相対的にモーターを移動させる

        Parameters
        ----------
        channel : int
            チャンネル（1〜4）
        steps : int
            相対ステップ数（−2147483648 〜 +2147483647）
        """
        self._validate_channel(channel)
        self._send(f"{self._addr()}{channel}PR{steps}")

    # ── 17. ExxmPR? – 相対移動の目標位置問い合わせ ────────────

    def get_relative_target(self, channel: int) -> int:
        """相対移動の目標位置を取得する（駆動中: 目標位置、停止中: 実位置）"""
        self._validate_channel(channel)
        resp = self._send_recv(f"{self._addr()}{channel}PR?")
        return int(resp)

    # ── 18. ExxmST – チャンネル動作停止 ─────────────────────

    def stop_channel(self, channel: int) -> None:
        """指定チャンネルのモーション停止（レスポンスなし）"""
        self._validate_channel(channel)
        self._send(f"{self._addr()}{channel}ST")

    # ── 19. ExxmTP? – 実位置問い合わせ ──────────────────────

    def get_position(self, channel: int) -> int:
        """チャンネルの実際の現在位置を取得する"""
        self._validate_channel(channel)
        resp = self._send_recv(f"{self._addr()}{channel}TP?")
        return int(resp)

    # ── 20. ExxmVAnnnn – 速度設定 ──────────────────────────

    def set_velocity(self, channel: int, velocity: int) -> None:
        """チャンネルの速度を設定する

        Parameters
        ----------
        channel : int
            チャンネル（1〜4）
        velocity : int
            速度（1〜1500 steps/sec）
        """
        self._validate_channel(channel)
        if not 1 <= velocity <= 1500:
            raise ValueError(f"速度は1〜1500の範囲で指定してください（入力値: {velocity}）")
        self._send(f"{self._addr()}{channel}VA{velocity}")

    # ── 21. ExxmVA? – 速度問い合わせ ────────────────────────

    def get_velocity(self, channel: int) -> int:
        """チャンネルの現在の速度設定を取得する（steps/sec）"""
        self._validate_channel(channel)
        resp = self._send_recv(f"{self._addr()}{channel}VA?")
        return int(resp)

    # ── 便利メソッド ─────────────────────────────────────────

    def scan_addresses(self) -> list[int]:
        """全アドレス（1〜32）をスキャンし、応答のあるアドレスのリストを返す"""
        found = []
        for addr in range(1, 33):
            if self.ping(addr):
                found.append(addr)
        return found

    def wait_until_done(
        self,
        channel: int,
        poll_interval: float = 0.1,
        timeout: Optional[float] = None,
    ) -> bool:
        """チャンネルの動作が完了するまでブロックする

        Parameters
        ----------
        channel : int
            チャンネル（1〜4）
        poll_interval : float
            ステータス確認の間隔（秒）
        timeout : float, optional
            最大待機時間（秒）。Noneの場合は無制限に待機。

        Returns
        -------
        bool
            動作完了ならTrue、タイムアウトならFalse
        """
        start = time.monotonic()
        while True:
            if self.is_motion_done(channel):
                return True
            if timeout is not None and (time.monotonic() - start) >= timeout:
                return False
            time.sleep(poll_interval)

    def send_raw(self, command: str) -> Optional[str]:
        """生のコマンド文字列を送信し、レスポンスを返す"""
        self._send(command)
        return self._recv()
