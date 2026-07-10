from __future__ import annotations

import re
import time
from typing import Optional

import serial
from serial.tools import list_ports

from .exceptions import (
    BusyError,
    CommandError,
    ConnectionError,
    TimeoutError,
    ValueRangeError,
)

# USBシリアル変換チップのVID/PID（FTDI FT230X）
USB_VID = 0x0403
USB_PID = 0x6015

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

# チャンネル番号 → 軸コマンド文字の変換テーブル
CHANNEL_MAP = {1: "A", 2: "B", 3: "C", 4: "D"}

# 軸コマンド文字 → チャンネル番号の逆引きテーブル
AXIS_MAP = {"A": 1, "B": 2, "C": 3, "D": 4}


def _strip_prompt(text: str) -> str:
    """レスポンス先頭の '>' プレフィックスを除去する"""
    if text.startswith(">"):
        return text[1:]
    return text


def find_port(vid: int = USB_VID, pid: int = USB_PID) -> str:
    """接続されているコントローラのシリアルポートを自動検出する

    USBシリアルポートを列挙し、VID/PIDが一致するポートを返す。
    WindowsでもLinuxでも動作する（例: ``"COM3"``、``"/dev/ttyUSB0"``）。

    Parameters
    ----------
    vid : int
        USBベンダーID。デフォルトは0x0403（FTDI）。
    pid : int
        USBプロダクトID。デフォルトは0x6015（FT230X）。

    Returns
    -------
    str
        検出されたポート名

    Raises
    ------
    ConnectionError
        デバイスが見つからない場合、または複数見つかり特定できない場合
    """
    candidates = sorted(
        p.device for p in list_ports.comports() if p.vid == vid and p.pid == pid
    )
    if not candidates:
        raise ConnectionError(
            f"コントローラが見つかりません（VID=0x{vid:04X}, PID=0x{pid:04X}）。"
            "USB接続を確認するか、port引数でポート名を指定してください。"
        )
    if len(candidates) > 1:
        raise ConnectionError(
            f"候補ポートが複数見つかりました: {', '.join(candidates)}。"
            "port引数でポート名を指定してください。"
        )
    return candidates[0]


class PAMC204:
    """PAMC-204 / PAMC-204-RJ ピエゾアシストモーターコントローラのドライバクラス

    Parameters
    ----------
    port : str, optional
        シリアルポート名（例: ``"COM3"``、``"/dev/ttyUSB0"``）。
        省略時は :func:`find_port` によりUSB VID/PIDから自動検出する。
    address : int
        ドライバアドレス（E01〜E32）。デフォルトはE01。
    timeout : float
        シリアル受信タイムアウト（秒）。デフォルトは1.0。
    """

    def __init__(
        self,
        port: Optional[str] = None,
        address: int = 1,
        timeout: float = 1.0,
    ) -> None:
        self._validate_address(address)
        self.address = address
        self.timeout = timeout
        self._ser: Optional[serial.Serial] = None
        self._port = port

    # ── 接続管理 ───────────────────────────────────────────────

    @property
    def port(self) -> Optional[str]:
        """使用中のポート名（port未指定かつ未接続の場合はNone）"""
        if self._ser is not None:
            return self._ser.port
        return self._port

    def open(self) -> None:
        """シリアル接続を開く（port未指定の場合は自動検出する）"""
        port = self._port if self._port is not None else find_port()
        try:
            self._ser = serial.Serial(
                port=port,
                baudrate=115200,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
            )
        except serial.SerialException as e:
            raise ConnectionError(f"{port} のオープンに失敗: {e}") from e

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
        """1行受信し、先頭の '>' を除去して返す。タイムアウト時はNoneを返す。"""
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
        text = line.decode("ascii", errors="replace").strip()
        return _strip_prompt(text)

    def _recv_lines(self, max_lines: int = 10, timeout: Optional[float] = None) -> list[str]:
        """複数行レスポンスを受信する。空行またはタイムアウトで終了。"""
        lines = []
        for _ in range(max_lines):
            line = self._recv(timeout=timeout)
            if line is None:
                break
            lines.append(line)
        return lines

    def _send_recv(self, command: str, timeout: Optional[float] = None) -> str:
        """コマンドを送信し、レスポンスを1行受信して返す"""
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

    def _strip_address(self, text: str) -> str:
        """レスポンス先頭のアドレス（Exx）プレフィックスを除去する"""
        prefix = self._addr()
        if text.startswith(prefix):
            return text[len(prefix):]
        return text

    # ── バリデーション ────────────────────────────────────────

    @staticmethod
    def _validate_address(addr: int) -> None:
        if not 1 <= addr <= 32:
            raise ValueError(f"アドレスはE01〜E32の範囲で指定してください（入力値: {addr}）")

    @staticmethod
    def _normalize_channel(ch: "int | str") -> int:
        """チャンネル指定を 1〜4 の整数に正規化する。

        整数の 1〜4、または軸文字 ``"A"``〜``"D"``（大文字・小文字どちらも可）を
        受け付ける。``"A"``=CH1, ``"B"``=CH2, ``"C"``=CH3, ``"D"``=CH4。
        """
        # 軸文字 'A'〜'D'（大文字・小文字のみ許可）
        if isinstance(ch, str):
            if ch.upper() in AXIS_MAP:
                return AXIS_MAP[ch.upper()]
            raise ValueError(
                f"チャンネルは 1, 2, 3, 4 または 'A', 'B', 'C', 'D' のいずれかで"
                f"指定してください（入力値: {ch!r}）"
            )
        # 整数 1〜4 のみ許可（bool は不可）
        if isinstance(ch, int) and not isinstance(ch, bool) and ch in CHANNEL_MAP:
            return ch
        raise ValueError(
            f"チャンネルは 1, 2, 3, 4 または 'A', 'B', 'C', 'D' のいずれかで"
            f"指定してください（入力値: {ch!r}）"
        )

    @staticmethod
    def _validate_frequency(freq: int) -> None:
        if not 1 <= freq <= 1500:
            raise ValueError(f"周波数は1〜1500 Hzの範囲で指定してください（入力値: {freq}）")

    @staticmethod
    def _validate_acceleration(acceleration: int) -> None:
        if not (isinstance(acceleration, int) and not isinstance(acceleration, bool)):
            raise ValueError(
                f"加速度は整数で指定してください（入力値: {acceleration!r}）"
            )
        if not 1 <= acceleration <= 150000:
            raise ValueError(
                f"加速度は1〜150000 steps/sec²の範囲で指定してください（入力値: {acceleration}）"
            )

    # ── 1. ExxINF – ファームウェアバージョン確認 ─────────────
    # 構文: ExxINF
    # 例:   INF → >PAMC-NEWTYPE\r\nVer:0.1.4(115200bps)
    # 例ではアドレスなしの "INF" で送信。レスポンスは複数行の場合あり。

    def get_firmware_info(self) -> str:
        """ファームウェアバージョンを取得する

        アドレスなしの ``INF`` コマンドを送信する。
        レスポンスが複数行の場合は結合して返す。

        Returns
        -------
        str
            ドライバから返されたファームウェアバージョン文字列
        """
        self._send("INF")
        lines = self._recv_lines(max_lines=5)
        if not lines:
            raise TimeoutError("コマンドに対するレスポンスなし: INF")
        result = " ".join(lines)
        self._check_error(result)
        return result

    # ── 2. Exx – ドライバ存在確認 ────────────────────────────
    # 構文: Exx  (Exx: E01~E32)
    # 例:   E01 → >E01OK  /  E02 → (返事なし)

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
    # 構文: SETADDRxx  (Exx: E01~E32)
    # 例:   SETADDR02 → >SETADDR02

    def set_address(self, new_address: int) -> str:
        """ドライバのアドレスを変更する

        Parameters
        ----------
        new_address : int
            新しいアドレス（E01〜E32）

        .. warning::
            単一ドライバ接続時のみ実行してください。
        """
        self._validate_address(new_address)
        resp = self._send_recv(f"SETADDR{new_address:02d}")
        self.address = new_address
        return resp

    # ── 4. ExxDACnnnn – 出力電圧調整 ────────────────────────
    # 構文: ExxDACnnnn  (Exx: E01~E32, nnnn: 1900~4095)
    # 例:   E01DAC4095 → >E01OK

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
    # 構文: ExxNRnnnnyyyyz / ExxNRnnnnXyyyyyyz
    #   Exx: E01~E32, nnnn: 0001~1500, yyyy: 0000~9999, yyyyyy: 000001~999999
    #   z: A~D (A:CH1, B:CH2, C:CH3, D:CH4)
    #   yyyy=0000 で連続駆動
    # 例:   E01NR15001500A → >E01OK

    def rotate_forward(
        self,
        channel: int | str,
        frequency: int,
        pulses: int = 0,
    ) -> str:
        """モーターを正回転（+）方向に駆動する

        Parameters
        ----------
        channel : int | str
            駆動チャンネル。1〜4 または軸文字 'A'〜'D'。
        frequency : int
            駆動周波数（1〜1500 Hz）
        pulses : int
            駆動パルス数。0で連続駆動。
            1〜9999は通常モード、1〜999999は拡張モード。
        """
        channel = self._normalize_channel(channel)
        self._validate_frequency(frequency)
        ch = CHANNEL_MAP[channel]
        cmd = self._build_drive_cmd("NR", frequency, pulses, ch)
        return self._send_recv(f"{self._addr()}{cmd}")

    # ── 6. ExxRR – 逆回転駆動 ───────────────────────────────
    # 構文: ExxRRnnnnyyyyz / ExxRRnnnnXyyyyyyz（NRと同一形式）
    # 例:   E01RR15001500A → >E01OK

    def rotate_reverse(
        self,
        channel: int | str,
        frequency: int,
        pulses: int = 0,
    ) -> str:
        """モーターを逆回転（−）方向に駆動する

        パラメータは :meth:`rotate_forward` と同じ。
        """
        channel = self._normalize_channel(channel)
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
    # 構文: ExxS  (Exx: E01~E32)
    # 例:   E01S → >E01FIN1456

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
    # 構文: ExxAB  (Exx: E01~E32)
    # 例:   E01AB → レスポンスなし

    def abort(self) -> None:
        """全チャンネルのモーション即時停止（レスポンスなし）"""
        self._send(f"{self._addr()}AB")

    # ── 9. ExxmDHnnnn – ホームポジション設定 ─────────────────
    # 構文: ExxmDHnnnn  (Exx: E01~E32, m: 1~4, nnnn: -2147483648~+2147483647)
    # 例:   E011DH1000 → レスポンスなし

    def set_home(self, channel: int | str, position: int) -> None:
        """チャンネルのホームポジション（絶対位置）を設定する

        Parameters
        ----------
        channel : int | str
            チャンネル。1〜4 または軸文字 'A'〜'D'。
        position : int
            ホームポジション（−2147483648 〜 +2147483647）
        """
        channel = self._normalize_channel(channel)
        self._send(f"{self._addr()}{channel}DH{position}")

    # ── 10. ExxmDH? – ホームポジション問い合わせ ─────────────
    # 構文: ExxmDH?  (Exx: E01~E32, m: 1~4)
    # 例:   E011DH? → >1000

    def get_home(self, channel: int | str) -> int:
        """チャンネルのホームポジションを取得する"""
        channel = self._normalize_channel(channel)
        resp = self._send_recv(f"{self._addr()}{channel}DH?")
        return int(resp)

    # ── 11. ExxmMD? – 動作完了ステータス問い合わせ ────────────
    # 構文: ExxmMD?  (Exx: E01~E32, m: 1~4)
    # 例:   E011MD? → >1（0:駆動中, 1:停止）

    def is_motion_done(self, channel: int | str) -> bool:
        """チャンネルの動作が完了しているか確認する

        Returns
        -------
        bool
            停止中ならTrue、駆動中ならFalse
        """
        channel = self._normalize_channel(channel)
        resp = self._send_recv(f"{self._addr()}{channel}MD?")
        return resp.strip() == "1"

    # ── 12. ExxmMVn – 無限移動 ─────────────────────────────
    # 構文: ExxmMVn  (Exx: E01~E32, m: 1~4, n: +/-)
    # 例:   E011MV+ → レスポンスなし

    def move_indefinite(self, channel: int | str, direction: str) -> None:
        """チャンネルのモーターを無限移動させる

        Parameters
        ----------
        channel : int | str
            チャンネル。1〜4 または軸文字 'A'〜'D'。
        direction : str
            移動方向。``"+"`` または ``"-"``。
        """
        channel = self._normalize_channel(channel)
        if direction not in ("+", "-"):
            raise ValueError(f"方向は '+' または '-' で指定してください（入力値: {direction!r}）")
        self._send(f"{self._addr()}{channel}MV{direction}")

    # ── 13. ExxmMV? – 移動状況問い合わせ ─────────────────────
    # 構文: ExxmMV?  (Exx: E01~E32, m: 1~4)
    # 例:   E011MV? → >1（0:駆動中, 1:停止）

    def is_moving(self, channel: int | str) -> bool:
        """チャンネルのモーターが移動中かどうか確認する

        Returns
        -------
        bool
            移動中ならTrue、停止中ならFalse
        """
        channel = self._normalize_channel(channel)
        resp = self._send_recv(f"{self._addr()}{channel}MV?")
        return resp.strip() == "0"

    # ── 14. ExxmPAnnnn – 絶対位置移動 ──────────────────────
    # 構文: ExxmPAnnnn  (Exx: E01~E32, m: 1~4, nnnn: -2147483648~+2147483647)
    # 例:   E011PA1000 → レスポンスなし

    def move_absolute(self, channel: int | str, position: int) -> None:
        """モーターを絶対位置に移動させる

        Parameters
        ----------
        channel : int | str
            チャンネル。1〜4 または軸文字 'A'〜'D'。
        position : int
            目標絶対位置（−2147483648 〜 +2147483647）
        """
        channel = self._normalize_channel(channel)
        self._send(f"{self._addr()}{channel}PA{position}")

    # ── 15. ExxmPA? – 目標位置問い合わせ ─────────────────────
    # 構文: ExxmPA?  (Exx: E01~E32, m: 1~4)
    # 例:   E011PA? → >15400
    # 駆動中: 目標位置、停止中: 実位置

    def get_target_position(self, channel: int | str) -> int:
        """目標位置を取得する（駆動中: 目標位置、停止中: 実位置）"""
        channel = self._normalize_channel(channel)
        resp = self._send_recv(f"{self._addr()}{channel}PA?")
        return int(resp)

    # ── 16. ExxmPRnnnn – 相対位置移動 ──────────────────────
    # 構文: ExxmPRnnnn  (Exx: E01~E32, m: 1~4, nnnn: -2147483648~+2147483647)
    # 例:   E011PR1000 → レスポンスなし

    def move_relative(self, channel: int | str, steps: int) -> None:
        """現在位置から相対的にモーターを移動させる

        Parameters
        ----------
        channel : int | str
            チャンネル。1〜4 または軸文字 'A'〜'D'。
        steps : int
            相対ステップ数（−2147483648 〜 +2147483647）
        """
        channel = self._normalize_channel(channel)
        self._send(f"{self._addr()}{channel}PR{steps}")

    # ── 17. ExxmPR? – 相対移動の目標位置問い合わせ ────────────
    # 構文: ExxmPR?  (Exx: E01~E32, m: 1~4)
    # 例:   E011PR? → >15400
    # 駆動中: 目標位置、停止中: 実位置

    def get_relative_target(self, channel: int | str) -> int:
        """相対移動の目標位置を取得する（駆動中: 目標位置、停止中: 実位置）"""
        channel = self._normalize_channel(channel)
        resp = self._send_recv(f"{self._addr()}{channel}PR?")
        return int(resp)

    # ── 18. ExxmST – チャンネル動作停止 ─────────────────────
    # 構文: ExxmST  (Exx: E01~E32, m: 1~4)
    # 例:   E011ST → レスポンスなし

    def stop_channel(self, channel: int | str) -> None:
        """指定チャンネルのモーション停止（レスポンスなし）"""
        channel = self._normalize_channel(channel)
        self._send(f"{self._addr()}{channel}ST")

    # ── 19. ExxmTP? – 実位置問い合わせ ──────────────────────
    # 構文: ExxmTP?  (Exx: E01~E32, m: 1~4)
    # 例:   E011TP? → >15400

    def get_position(self, channel: int | str) -> int:
        """チャンネルの実際の現在位置を取得する"""
        channel = self._normalize_channel(channel)
        resp = self._send_recv(f"{self._addr()}{channel}TP?")
        return int(resp)

    # ── 20. ExxmVAnnnn – 速度設定 ──────────────────────────
    # 構文: ExxmVAnnnn  (Exx: E01~E32, m: 1~4, nnnn: 1~1500)
    # 例:   E011VA1 → レスポンスなし

    def set_velocity(self, channel: int | str, velocity: int) -> None:
        """チャンネルの速度を設定する

        Parameters
        ----------
        channel : int | str
            チャンネル。1〜4 または軸文字 'A'〜'D'。
        velocity : int
            速度（1〜1500 steps/sec）
        """
        channel = self._normalize_channel(channel)
        if not 1 <= velocity <= 1500:
            raise ValueError(f"速度は1〜1500の範囲で指定してください（入力値: {velocity}）")
        self._send(f"{self._addr()}{channel}VA{velocity}")

    # ── 21. ExxmVA? – 速度問い合わせ ────────────────────────
    # 構文: ExxmVA?  (Exx: E01~E32, m: 1~4)
    # 例:   E011VA? → >1

    def get_velocity(self, channel: int | str) -> int:
        """チャンネルの現在の速度設定を取得する（steps/sec）"""
        channel = self._normalize_channel(channel)
        resp = self._send_recv(f"{self._addr()}{channel}VA?")
        return int(resp)

    # ── 22. ExxmACnnnn – 加速度設定（F/W Ver.0.2.1以降） ──────
    # 構文: ExxmACnnnn  (Exx: E01~E32, m: 1~4, nnnn: 1~150000)
    # 例:   E011AC10000 → レスポンスなし
    # 加速度設定は MV / PA / PR / ST コマンドに対して有効
    #（NR / RR / S は加速度設定に非対応）。

    def set_acceleration(self, channel: int | str, acceleration: int) -> None:
        """チャンネルの加速度を設定する（F/W Ver.0.2.1以降）

        Parameters
        ----------
        channel : int | str
            チャンネル。1〜4 または軸文字 'A'〜'D'。
        acceleration : int
            加速度（1〜150000 steps/sec²）

        Notes
        -----
        加速度は無限移動（``move_indefinite``）・絶対位置移動（``move_absolute``）・
        相対移動（``move_relative``）・動作停止（``stop_channel``）に作用します。
        パルス駆動（``rotate_forward`` / ``rotate_reverse``）および ``stop`` は
        加速度設定に対応していません。
        """
        channel = self._normalize_channel(channel)
        self._validate_acceleration(acceleration)
        self._send(f"{self._addr()}{channel}AC{acceleration}")

    # ── 23. ExxmAC? – 加速度問い合わせ（F/W Ver.0.2.1以降） ───
    # 構文: ExxmAC?  (Exx: E01~E32, m: 1~4)
    # 例:   E011AC? → >10000

    def get_acceleration(self, channel: int | str) -> int:
        """チャンネルの現在の加速度設定を取得する（steps/sec²、F/W Ver.0.2.1以降）"""
        channel = self._normalize_channel(channel)
        resp = self._send_recv(f"{self._addr()}{channel}AC?")
        return int(resp)

    # ── 24. ExxST? – 動作状態問い合わせ（F/W Ver.0.1.7以降） ──
    # 構文: ExxST?  (Exx: E01~E32)
    # 例:   E01ST? → >E01S（停止）/ >E01NR1500A（正回転中）/ >E01RR1500A（逆回転中）

    def get_drive_status(self) -> str:
        """ドライバの動作状態を取得する（F/W Ver.0.1.7以降）

        Returns
        -------
        str
            ``"S"``（停止中）、``"NRnnnnz"``（正回転駆動中）、
            ``"RRnnnnz"``（逆回転駆動中）。先頭のアドレス（``Exx``）は除去して返す。
            （``nnnn``: 駆動周波数、``z``: 駆動軸 A〜D）
        """
        resp = self._send_recv(f"{self._addr()}ST?")
        return self._strip_address(resp)

    def is_driving(self) -> bool:
        """ドライバがいずれかの軸を駆動中かどうかを返す（F/W Ver.0.1.7以降）

        Returns
        -------
        bool
            駆動中なら True、停止中（``"S"``）なら False。
        """
        return self.get_drive_status().upper() != "S"

    # ── 25. ExxTXFINn – 停止時パルス数送信ON/OFF（F/W Ver.0.1.8以降） ──
    # 構文: ExxTXFINn  (Exx: E01~E32, n: 0=OFF, ≠0=ON)
    # 例:   E01TXFIN1 → >E01OK

    def set_txfin(self, enabled: bool) -> str:
        """連続駆動停止時（``stop()`` / ``ExxS``）のパルス数送信ON/OFFを設定する
        （F/W Ver.0.1.8以降）

        Parameters
        ----------
        enabled : bool
            ``True``: 停止時に ``FIN<パルス数>`` を送信する（既定動作）。
            ``False``: 送信しない。

        .. warning::
            ``False`` に設定すると ``stop()`` がレスポンスを返さなくなるため、
            ``stop()`` / ``get_stop_pulse_count()`` は ``TimeoutError`` になります。
        """
        n = 1 if enabled else 0
        return self._send_recv(f"{self._addr()}TXFIN{n}")

    # ── 26. ExxSNO? – シリアルナンバー問い合わせ ──
    # 構文: ExxSNO?  (Exx: E01~E32)
    # 例:   E01SNO? → >E0110001

    def get_serial_number(self) -> str:
        """ドライバのシリアルナンバーを取得する

        Returns
        -------
        str
            シリアルナンバー文字列。先頭のアドレス（``Exx``）は除去して返す。
        """
        resp = self._send_recv(f"{self._addr()}SNO?")
        return self._strip_address(resp)

    # ── 便利メソッド ─────────────────────────────────────────

    def scan_addresses(self) -> list[int]:
        """全アドレス（E01〜E32）をスキャンし、応答のあるアドレスのリストを返す"""
        found = []
        for addr in range(1, 33):
            if self.ping(addr):
                found.append(addr)
        return found

    def wait_until_done(
        self,
        channel: int | str,
        poll_interval: float = 0.1,
        timeout: Optional[float] = None,
    ) -> bool:
        """チャンネルの動作が完了するまでブロックする

        Parameters
        ----------
        channel : int | str
            チャンネル。1〜4 または軸文字 'A'〜'D'。
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
        """生のコマンド文字列を送信し、レスポンスを返す（'>'プレフィックスは除去済み）"""
        self._send(command)
        return self._recv()

    # ── 4チャンネル一括操作 ───────────────────────────────────
    # libpamc-204 の *_all_channels API 相当。CH1〜CH4 へ順次コマンドを送信する。

    def move_relative_all(self, steps: int) -> None:
        """全チャンネル（CH1〜CH4）を同じ相対量だけ移動させる（応答なし）"""
        for ch in (1, 2, 3, 4):
            self.move_relative(ch, steps)

    def move_indefinite_all(self, direction: str) -> None:
        """全チャンネル（CH1〜CH4）を同じ方向に無限移動させる（応答なし）"""
        for ch in (1, 2, 3, 4):
            self.move_indefinite(ch, direction)

    def stop_all(self) -> None:
        """全チャンネル（CH1〜CH4）を個別に動作停止させる（ExxmST、応答なし）

        全軸即時停止には :meth:`abort`（ExxAB）を使用してください。
        """
        for ch in (1, 2, 3, 4):
            self.stop_channel(ch)

    def get_position_all(self) -> list[int]:
        """全チャンネルの実位置を取得する（``[CH1, CH2, CH3, CH4]``）"""
        return [self.get_position(ch) for ch in (1, 2, 3, 4)]

    def get_motion_done_all(self) -> list[bool]:
        """全チャンネルの動作完了ステータスを取得する

        Returns
        -------
        list[bool]
            ``[CH1, CH2, CH3, CH4]``。各要素は停止中なら True、駆動中なら False。
        """
        return [self.is_motion_done(ch) for ch in (1, 2, 3, 4)]
