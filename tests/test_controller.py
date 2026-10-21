"""PAMC204コントローラのユニットテスト"""

import unittest
from unittest.mock import MagicMock, patch, PropertyMock

import serial

from pypamc204 import PAMC204, find_port
from pypamc204.controller import _strip_prompt
from pypamc204.exceptions import (
    BusyError,
    CommandError,
    ConnectionError,
    TimeoutError,
    ValueRangeError,
)


def make_controller(address=1):
    """モック済みのコントローラインスタンスを生成する"""
    with patch("pypamc204.controller.serial.Serial"):
        ctrl = PAMC204("COM3", address=address)
        ctrl.open()
        return ctrl


def set_response(ctrl, response_text):
    """モックのレスポンスを設定する（単一行）"""
    ctrl._ser.readline.return_value = (response_text + "\r\n").encode("ascii")


def set_multi_response(ctrl, lines):
    """モックの複数行レスポンスを設定する"""
    encoded = [(line + "\r\n").encode("ascii") for line in lines] + [b""]
    ctrl._ser.readline.side_effect = encoded


def set_no_response(ctrl):
    """レスポンスなし（タイムアウト）を設定する"""
    ctrl._ser.readline.return_value = b""


class TestStripPrompt(unittest.TestCase):
    """レスポンスの '>' プレフィックス除去"""

    def test_strip_leading_bracket(self):
        self.assertEqual(_strip_prompt(">E01OK"), "E01OK")

    def test_strip_leading_bracket_number(self):
        self.assertEqual(_strip_prompt(">1000"), "1000")

    def test_no_bracket(self):
        self.assertEqual(_strip_prompt("E01OK"), "E01OK")

    def test_empty_after_bracket(self):
        self.assertEqual(_strip_prompt(">"), "")

    def test_empty_string(self):
        self.assertEqual(_strip_prompt(""), "")

    def test_multiple_brackets(self):
        self.assertEqual(_strip_prompt(">>test"), ">test")


class TestConnection(unittest.TestCase):
    """接続管理のテスト"""

    @patch("pypamc204.controller.serial.Serial")
    def test_open_close(self, mock_serial_cls):
        ctrl = PAMC204("COM3")
        ctrl.open()
        mock_serial_cls.assert_called_once_with(
            port="COM3",
            baudrate=115200,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=1.0,
        )
        ctrl.close()
        ctrl._ser.close.assert_called_once()

    @patch("pypamc204.controller.serial.Serial")
    def test_context_manager(self, mock_serial_cls):
        with PAMC204("COM3") as ctrl:
            self.assertTrue(ctrl.is_open)
        ctrl._ser.close.assert_called_once()

    @patch("pypamc204.controller.serial.Serial", side_effect=serial.SerialException("port error"))
    def test_open_failure(self, mock_serial_cls):
        ctrl = PAMC204("COM99")
        with self.assertRaises(ConnectionError):
            ctrl.open()

    def test_send_without_open(self):
        ctrl = PAMC204("COM3")
        with self.assertRaises(ConnectionError):
            ctrl._send("E01INF")

    def test_recv_without_open(self):
        ctrl = PAMC204("COM3")
        with self.assertRaises(ConnectionError):
            ctrl._recv()


class TestRecvStripsPrompt(unittest.TestCase):
    """_recv() が '>' プレフィックスを除去するテスト"""

    def test_recv_strips_prompt(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        result = ctrl._recv()
        self.assertEqual(result, "E01OK")

    def test_recv_strips_prompt_number(self):
        ctrl = make_controller()
        set_response(ctrl, ">1000")
        result = ctrl._recv()
        self.assertEqual(result, "1000")

    def test_recv_no_prompt(self):
        ctrl = make_controller()
        set_response(ctrl, "E01OK")
        result = ctrl._recv()
        self.assertEqual(result, "E01OK")


class TestValidation(unittest.TestCase):
    """バリデーションのテスト"""

    def test_address_range(self):
        with self.assertRaises(ValueError):
            PAMC204("COM3", address=0)
        with self.assertRaises(ValueError):
            PAMC204("COM3", address=33)
        PAMC204("COM3", address=1)
        PAMC204("COM3", address=32)

    def test_channel_validation(self):
        ctrl = make_controller()
        with self.assertRaises(ValueError):
            ctrl.rotate_forward(channel=0, frequency=100)
        with self.assertRaises(ValueError):
            ctrl.rotate_forward(channel=5, frequency=100)

    def test_channel_strict_validation(self):
        """1,2,3,4 または A,B,C,D 以外は厳密に拒否する"""
        ctrl = make_controller()
        for bad in ("1", "E", "AA", "", 1.0, True, None):
            with self.assertRaises(ValueError):
                ctrl.move_absolute(channel=bad, position=0)

    def test_frequency_validation(self):
        ctrl = make_controller()
        with self.assertRaises(ValueError):
            ctrl.rotate_forward(channel=1, frequency=0)
        with self.assertRaises(ValueError):
            ctrl.rotate_forward(channel=1, frequency=1501)

    def test_pulse_validation(self):
        ctrl = make_controller()
        with self.assertRaises(ValueError):
            ctrl.rotate_forward(channel=1, frequency=100, pulses=1000000)

    def test_voltage_validation(self):
        ctrl = make_controller()
        with self.assertRaises(ValueError):
            ctrl.set_voltage(75)

    def test_voltage_raw_validation(self):
        ctrl = make_controller()
        with self.assertRaises(ValueError):
            ctrl.set_voltage_raw(1899)
        with self.assertRaises(ValueError):
            ctrl.set_voltage_raw(4096)

    def test_velocity_validation(self):
        ctrl = make_controller()
        with self.assertRaises(ValueError):
            ctrl.set_velocity(channel=1, velocity=0)
        with self.assertRaises(ValueError):
            ctrl.set_velocity(channel=1, velocity=1501)

    def test_direction_validation(self):
        ctrl = make_controller()
        with self.assertRaises(ValueError):
            ctrl.move_indefinite(channel=1, direction="x")


class TestErrorHandling(unittest.TestCase):
    """エラーレスポンスのテスト"""

    def test_busy_error(self):
        ctrl = make_controller()
        set_response(ctrl, "BUSY")
        with self.assertRaises(BusyError):
            ctrl.set_voltage(100)

    def test_value_range_error(self):
        ctrl = make_controller()
        set_response(ctrl, "Error Value Range")
        with self.assertRaises(ValueRangeError):
            ctrl.set_voltage(100)

    def test_command_error(self):
        ctrl = make_controller()
        set_response(ctrl, "ERROR")
        with self.assertRaises(CommandError):
            ctrl.set_voltage(100)

    def test_error1(self):
        ctrl = make_controller()
        set_response(ctrl, "ERROR1")
        with self.assertRaises(CommandError):
            ctrl.set_voltage(100)

    def test_error4(self):
        ctrl = make_controller()
        set_response(ctrl, "ERROR4")
        with self.assertRaises(CommandError):
            ctrl.set_voltage(100)

    def test_error5(self):
        ctrl = make_controller()
        set_response(ctrl, "ERROR5")
        with self.assertRaises(CommandError):
            ctrl.set_voltage(100)

    def test_timeout_error(self):
        ctrl = make_controller()
        set_no_response(ctrl)
        with self.assertRaises(TimeoutError):
            ctrl.set_voltage(100)


class TestFirmwareInfo(unittest.TestCase):
    """INF – ファームウェアバージョン確認（マニュアル例: アドレスなしの INF）"""

    def test_get_firmware_info_single_line(self):
        """単一行レスポンス"""
        ctrl = make_controller()
        set_multi_response(ctrl, [">PAMC-NEWTYPE Ver:0.1.8(115200bps)"])
        result = ctrl.get_firmware_info()
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"INF\r\n")
        self.assertIn("0.1.8", result)

    def test_get_firmware_info_multi_line(self):
        """マニュアル通りの複数行レスポンス"""
        ctrl = make_controller()
        set_multi_response(ctrl, [">PAMC-NEWTYPE", "Ver:0.1.4(115200bps)"])
        result = ctrl.get_firmware_info()
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"INF\r\n")
        self.assertIn("PAMC-NEWTYPE", result)
        self.assertIn("Ver:0.1.4", result)

    def test_get_firmware_info_timeout(self):
        """レスポンスなしの場合"""
        ctrl = make_controller()
        set_no_response(ctrl)
        with self.assertRaises(TimeoutError):
            ctrl.get_firmware_info()

    def test_get_firmware_info_sends_inf_not_exxinf(self):
        """マニュアル例に従い、'INF' を送信する（'E01INF' ではない）"""
        ctrl = make_controller(address=5)
        set_multi_response(ctrl, [">PAMC-NEWTYPE Ver:0.1.8(115200bps)"])
        ctrl.get_firmware_info()
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"INF\r\n")


class TestPing(unittest.TestCase):
    """Exx – ドライバ存在確認"""

    def test_ping_success(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        self.assertTrue(ctrl.ping())

    def test_ping_no_response(self):
        ctrl = make_controller()
        set_no_response(ctrl)
        self.assertFalse(ctrl.ping())

    def test_ping_other_address(self):
        ctrl = make_controller()
        set_response(ctrl, ">E05OK")
        self.assertTrue(ctrl.ping(address=5))
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E05\r\n")

    def test_ping_invalid_address(self):
        ctrl = make_controller()
        with self.assertRaises(ValueError):
            ctrl.ping(address=0)


class TestSetAddress(unittest.TestCase):
    """SETADDRxx – アドレス変更"""

    def test_set_address(self):
        ctrl = make_controller()
        set_response(ctrl, ">SETADDR05")
        ctrl.set_address(5)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"SETADDR05\r\n")
        self.assertEqual(ctrl.address, 5)

    def test_set_address_invalid(self):
        ctrl = make_controller()
        with self.assertRaises(ValueError):
            ctrl.set_address(0)
        with self.assertRaises(ValueError):
            ctrl.set_address(33)


class TestVoltage(unittest.TestCase):
    """ExxDACnnnn – 出力電圧調整"""

    def test_set_voltage_150(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        ctrl.set_voltage(150)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01DAC4095\r\n")

    def test_set_voltage_100(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        ctrl.set_voltage(100)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01DAC2700\r\n")

    def test_set_voltage_70(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        ctrl.set_voltage(70)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01DAC1900\r\n")

    def test_set_voltage_all_values(self):
        ctrl = make_controller()
        expected = {
            70: 1900, 80: 2200, 90: 2450, 100: 2700,
            110: 3000, 120: 3200, 130: 3450, 140: 3750, 150: 4095,
        }
        for voltage, dac in expected.items():
            set_response(ctrl, ">E01OK")
            ctrl.set_voltage(voltage)
            sent = ctrl._ser.write.call_args[0][0]
            self.assertEqual(sent, f"E01DAC{dac}\r\n".encode("ascii"))

    def test_set_voltage_raw(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        ctrl.set_voltage_raw(3000)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01DAC3000\r\n")


class TestRotation(unittest.TestCase):
    """ExxNR / ExxRR – 正回転・逆回転駆動"""

    def test_forward_with_pulses(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        ctrl.rotate_forward(channel=1, frequency=1500, pulses=1500)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01NR15001500A\r\n")

    def test_forward_continuous(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        ctrl.rotate_forward(channel=1, frequency=1500, pulses=0)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01NR15000000A\r\n")

    def test_forward_extended_pulses(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        ctrl.rotate_forward(channel=1, frequency=1500, pulses=100000)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01NR1500X100000A\r\n")

    def test_forward_channel_mapping(self):
        ctrl = make_controller()
        channels = {1: "A", 2: "B", 3: "C", 4: "D"}
        for ch_num, ch_letter in channels.items():
            set_response(ctrl, ">E01OK")
            ctrl.rotate_forward(channel=ch_num, frequency=500, pulses=100)
            sent = ctrl._ser.write.call_args[0][0]
            expected = f"E01NR05000100{ch_letter}\r\n".encode("ascii")
            self.assertEqual(sent, expected)

    def test_forward_channel_by_axis_letter(self):
        """軸文字 'A'〜'D'（大文字・小文字）でも指定できる"""
        ctrl = make_controller()
        for ch_letter in ("A", "B", "C", "D", "a", "b", "c", "d"):
            set_response(ctrl, ">E01OK")
            ctrl.rotate_forward(channel=ch_letter, frequency=500, pulses=100)
            sent = ctrl._ser.write.call_args[0][0]
            expected = f"E01NR05000100{ch_letter.upper()}\r\n".encode("ascii")
            self.assertEqual(sent, expected)

    def test_move_absolute_by_axis_letter(self):
        """位置系コマンドでも軸文字で CH 番号に変換される（B → m=2）"""
        ctrl = make_controller()
        ctrl.move_absolute(channel="B", position=5000)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E012PA5000\r\n")

    def test_reverse_with_pulses(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        ctrl.rotate_reverse(channel=2, frequency=800, pulses=2000)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01RR08002000B\r\n")

    def test_reverse_continuous(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        ctrl.rotate_reverse(channel=3, frequency=1000)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01RR10000000C\r\n")

    def test_reverse_extended_pulses(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        ctrl.rotate_reverse(channel=1, frequency=1500, pulses=100000)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01RR1500X100000A\r\n")

    def test_forward_min_frequency(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        ctrl.rotate_forward(channel=1, frequency=1, pulses=1)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01NR00010001A\r\n")

    def test_forward_max_pulses_standard(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        ctrl.rotate_forward(channel=1, frequency=100, pulses=9999)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01NR01009999A\r\n")

    def test_forward_max_pulses_extended(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        ctrl.rotate_forward(channel=1, frequency=100, pulses=999999)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01NR0100X999999A\r\n")


class TestStop(unittest.TestCase):
    """ExxS – 連続駆動停止"""

    def test_stop(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01FIN1456")
        result = ctrl.stop()
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01S\r\n")
        self.assertIn("FIN", result)

    def test_get_stop_pulse_count(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01FIN1456")
        count = ctrl.get_stop_pulse_count()
        self.assertEqual(count, 1456)

    def test_get_stop_pulse_count_zero(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01FIN0")
        count = ctrl.get_stop_pulse_count()
        self.assertEqual(count, 0)

    def test_get_stop_pulse_count_no_match(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        count = ctrl.get_stop_pulse_count()
        self.assertIsNone(count)


class TestAbort(unittest.TestCase):
    """ExxAB – モーション停止"""

    def test_abort(self):
        ctrl = make_controller()
        ctrl.abort()
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01AB\r\n")


class TestHome(unittest.TestCase):
    """ExxmDH / ExxmDH? – ホームポジション"""

    def test_set_home(self):
        ctrl = make_controller()
        ctrl.set_home(channel=1, position=1000)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E011DH1000\r\n")

    def test_set_home_negative(self):
        ctrl = make_controller()
        ctrl.set_home(channel=2, position=-500)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E012DH-500\r\n")

    def test_get_home(self):
        ctrl = make_controller()
        set_response(ctrl, ">1000")
        result = ctrl.get_home(channel=1)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E011DH?\r\n")
        self.assertEqual(result, 1000)

    def test_get_home_with_prompt_prefix(self):
        """マニュアル例: E011DH? → >1000（'>'除去後に数値パース）"""
        ctrl = make_controller()
        set_response(ctrl, ">1000")
        result = ctrl.get_home(channel=1)
        self.assertEqual(result, 1000)


class TestMotionDone(unittest.TestCase):
    """ExxmMD? – 動作完了ステータス（0:駆動中, 1:停止）"""

    def test_motion_done_stopped(self):
        ctrl = make_controller()
        set_response(ctrl, ">1")
        self.assertTrue(ctrl.is_motion_done(channel=1))

    def test_motion_done_moving(self):
        ctrl = make_controller()
        set_response(ctrl, ">0")
        self.assertFalse(ctrl.is_motion_done(channel=1))

    def test_motion_done_without_prompt(self):
        ctrl = make_controller()
        set_response(ctrl, "1")
        self.assertTrue(ctrl.is_motion_done(channel=1))


class TestMoveIndefinite(unittest.TestCase):
    """ExxmMVn – 無限移動"""

    def test_move_positive(self):
        ctrl = make_controller()
        ctrl.move_indefinite(channel=1, direction="+")
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E011MV+\r\n")

    def test_move_negative(self):
        ctrl = make_controller()
        ctrl.move_indefinite(channel=3, direction="-")
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E013MV-\r\n")


class TestIsMoving(unittest.TestCase):
    """ExxmMV? – 移動状況問い合わせ（0:駆動中, 1:停止）"""

    def test_is_moving_true(self):
        ctrl = make_controller()
        set_response(ctrl, ">0")
        self.assertTrue(ctrl.is_moving(channel=1))

    def test_is_moving_false(self):
        ctrl = make_controller()
        set_response(ctrl, ">1")
        self.assertFalse(ctrl.is_moving(channel=1))


class TestMoveAbsolute(unittest.TestCase):
    """ExxmPAnnnn / ExxmPA? – 絶対位置移動"""

    def test_move_absolute(self):
        ctrl = make_controller()
        ctrl.move_absolute(channel=1, position=5000)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E011PA5000\r\n")

    def test_move_absolute_negative(self):
        ctrl = make_controller()
        ctrl.move_absolute(channel=2, position=-3000)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E012PA-3000\r\n")

    def test_get_target_position(self):
        ctrl = make_controller()
        set_response(ctrl, ">15400")
        result = ctrl.get_target_position(channel=1)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E011PA?\r\n")
        self.assertEqual(result, 15400)


class TestMoveRelative(unittest.TestCase):
    """ExxmPRnnnn / ExxmPR? – 相対位置移動"""

    def test_move_relative(self):
        ctrl = make_controller()
        ctrl.move_relative(channel=1, steps=1000)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E011PR1000\r\n")

    def test_move_relative_negative(self):
        ctrl = make_controller()
        ctrl.move_relative(channel=1, steps=-500)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E011PR-500\r\n")

    def test_get_relative_target(self):
        ctrl = make_controller()
        set_response(ctrl, ">1123")
        result = ctrl.get_relative_target(channel=1)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E011PR?\r\n")
        self.assertEqual(result, 1123)


class TestStopChannel(unittest.TestCase):
    """ExxmST – チャンネル動作停止"""

    def test_stop_channel(self):
        ctrl = make_controller()
        ctrl.stop_channel(channel=1)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E011ST\r\n")

    def test_stop_channel_4(self):
        ctrl = make_controller()
        ctrl.stop_channel(channel=4)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E014ST\r\n")


class TestGetPosition(unittest.TestCase):
    """ExxmTP? – 実位置問い合わせ"""

    def test_get_position(self):
        ctrl = make_controller()
        set_response(ctrl, ">15400")
        result = ctrl.get_position(channel=1)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E011TP?\r\n")
        self.assertEqual(result, 15400)

    def test_get_position_negative(self):
        ctrl = make_controller()
        set_response(ctrl, ">-200")
        result = ctrl.get_position(channel=2)
        self.assertEqual(result, -200)


class TestVelocity(unittest.TestCase):
    """ExxmVAnnnn / ExxmVA? – 速度設定・問い合わせ"""

    def test_set_velocity(self):
        ctrl = make_controller()
        ctrl.set_velocity(channel=1, velocity=500)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E011VA500\r\n")

    def test_set_velocity_min(self):
        ctrl = make_controller()
        ctrl.set_velocity(channel=1, velocity=1)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E011VA1\r\n")

    def test_set_velocity_max(self):
        ctrl = make_controller()
        ctrl.set_velocity(channel=1, velocity=1500)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E011VA1500\r\n")

    def test_get_velocity(self):
        ctrl = make_controller()
        set_response(ctrl, ">1")
        result = ctrl.get_velocity(channel=1)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E011VA?\r\n")
        self.assertEqual(result, 1)


class TestAcceleration(unittest.TestCase):
    """ExxmACnnnn / ExxmAC? – 加速度設定・問い合わせ（F/W Ver.0.2.1以降）"""

    def test_set_acceleration(self):
        ctrl = make_controller()
        ctrl.set_acceleration(channel=1, acceleration=10000)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E011AC10000\r\n")

    def test_set_acceleration_by_axis_letter(self):
        ctrl = make_controller()
        ctrl.set_acceleration(channel="C", acceleration=500)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E013AC500\r\n")

    def test_set_acceleration_min(self):
        ctrl = make_controller()
        ctrl.set_acceleration(channel=1, acceleration=1)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E011AC1\r\n")

    def test_set_acceleration_max(self):
        ctrl = make_controller()
        ctrl.set_acceleration(channel=4, acceleration=150000)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E014AC150000\r\n")

    def test_set_acceleration_no_response(self):
        """設定コマンドは応答を待たない（TimeoutError にならない）"""
        ctrl = make_controller()
        set_no_response(ctrl)
        ctrl.set_acceleration(channel=1, acceleration=10000)  # 例外が出なければOK

    def test_set_acceleration_validation(self):
        ctrl = make_controller()
        for bad in (0, -1, 150001, 1.0, True):
            with self.assertRaises(ValueError):
                ctrl.set_acceleration(channel=1, acceleration=bad)

    def test_get_acceleration(self):
        ctrl = make_controller()
        set_response(ctrl, ">10000")
        result = ctrl.get_acceleration(channel=1)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E011AC?\r\n")
        self.assertEqual(result, 10000)


class TestScanAddresses(unittest.TestCase):
    """アドレススキャン"""

    def test_scan_addresses(self):
        ctrl = make_controller()
        responses = []
        for addr in range(1, 33):
            if addr in (1, 3, 5):
                responses.append(f">E{addr:02d}OK\r\n".encode("ascii"))
            else:
                responses.append(b"")
        ctrl._ser.readline.side_effect = responses
        found = ctrl.scan_addresses()
        self.assertEqual(found, [1, 3, 5])


class TestWaitUntilDone(unittest.TestCase):
    """動作完了待ち"""

    def test_wait_already_done(self):
        ctrl = make_controller()
        set_response(ctrl, ">1")
        result = ctrl.wait_until_done(channel=1, timeout=1.0)
        self.assertTrue(result)

    def test_wait_timeout(self):
        ctrl = make_controller()
        set_response(ctrl, ">0")
        result = ctrl.wait_until_done(channel=1, poll_interval=0.01, timeout=0.05)
        self.assertFalse(result)

    def test_wait_becomes_done(self):
        ctrl = make_controller()
        ctrl._ser.readline.side_effect = [
            b">0\r\n",
            b">0\r\n",
            b">1\r\n",
        ]
        result = ctrl.wait_until_done(channel=1, poll_interval=0.01, timeout=1.0)
        self.assertTrue(result)


class TestSendRaw(unittest.TestCase):
    """生コマンド送信"""

    def test_send_raw(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        result = ctrl.send_raw("E01INF")
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01INF\r\n")
        self.assertEqual(result, "E01OK")

    def test_send_raw_no_response(self):
        ctrl = make_controller()
        set_no_response(ctrl)
        result = ctrl.send_raw("E01AB")
        self.assertIsNone(result)


class TestDriveStatus(unittest.TestCase):
    """ExxST? – 動作状態問い合わせ（F/W Ver.0.1.7以降）"""

    def test_get_drive_status_stopped(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01S")
        result = ctrl.get_drive_status()
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01ST?\r\n")
        self.assertEqual(result, "S")

    def test_get_drive_status_driving(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01NR1500A")
        self.assertEqual(ctrl.get_drive_status(), "NR1500A")

    def test_is_driving_false(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01S")
        self.assertFalse(ctrl.is_driving())

    def test_is_driving_true(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01RR1000B")
        self.assertTrue(ctrl.is_driving())


class TestTxfin(unittest.TestCase):
    """ExxTXFINn – 停止時パルス数送信ON/OFF（F/W Ver.0.1.8以降）"""

    def test_set_txfin_on(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        ctrl.set_txfin(True)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01TXFIN1\r\n")

    def test_set_txfin_off(self):
        ctrl = make_controller()
        set_response(ctrl, ">E01OK")
        ctrl.set_txfin(False)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01TXFIN0\r\n")


class TestSerialNumber(unittest.TestCase):
    """ExxSNO? – シリアルナンバー問い合わせ"""

    def test_get_serial_number(self):
        ctrl = make_controller()
        set_response(ctrl, ">E0110001")
        result = ctrl.get_serial_number()
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E01SNO?\r\n")
        self.assertEqual(result, "10001")


class TestAllChannels(unittest.TestCase):
    """4チャンネル一括操作（libpamc-204 / libpamc-204A *_all_channels 相当）"""

    def _sent_list(self, ctrl):
        return [c[0][0] for c in ctrl._ser.write.call_args_list]

    def test_move_relative_all(self):
        ctrl = make_controller()
        ctrl.move_relative_all(1000)
        self.assertEqual(
            self._sent_list(ctrl),
            [b"E011PR1000\r\n", b"E012PR1000\r\n", b"E013PR1000\r\n", b"E014PR1000\r\n"],
        )

    def test_move_indefinite_all(self):
        ctrl = make_controller()
        ctrl.move_indefinite_all("+")
        self.assertEqual(
            self._sent_list(ctrl),
            [b"E011MV+\r\n", b"E012MV+\r\n", b"E013MV+\r\n", b"E014MV+\r\n"],
        )

    def test_stop_all(self):
        ctrl = make_controller()
        ctrl.stop_all()
        self.assertEqual(
            self._sent_list(ctrl),
            [b"E011ST\r\n", b"E012ST\r\n", b"E013ST\r\n", b"E014ST\r\n"],
        )

    def test_get_position_all(self):
        ctrl = make_controller()
        ctrl._ser.readline.side_effect = [b">100\r\n", b">200\r\n", b">300\r\n", b">400\r\n"]
        self.assertEqual(ctrl.get_position_all(), [100, 200, 300, 400])

    def test_get_motion_done_all(self):
        ctrl = make_controller()
        ctrl._ser.readline.side_effect = [b">1\r\n", b">0\r\n", b">1\r\n", b">1\r\n"]
        self.assertEqual(ctrl.get_motion_done_all(), [True, False, True, True])


class TestMultipleAddresses(unittest.TestCase):
    """複数アドレスのテスト"""

    def test_address_32(self):
        ctrl = make_controller(address=32)
        set_response(ctrl, ">E32OK")
        ctrl.set_voltage(100)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E32DAC2700\r\n")

    def test_address_format_padding(self):
        ctrl = make_controller(address=5)
        set_response(ctrl, ">E05OK")
        ctrl.set_voltage(100)
        sent = ctrl._ser.write.call_args[0][0]
        self.assertEqual(sent, b"E05DAC2700\r\n")


class TestFindPort(unittest.TestCase):
    """ポート自動検出（find_port）"""

    @staticmethod
    def _mock_port(device, vid, pid):
        p = MagicMock()
        p.device = device
        p.vid = vid
        p.pid = pid
        return p

    def test_single_match(self):
        ports = [
            self._mock_port("/dev/ttyS0", None, None),
            self._mock_port("/dev/ttyUSB0", 0x0403, 0x6015),
        ]
        with patch("pypamc204.controller.list_ports.comports", return_value=ports):
            self.assertEqual(find_port(), "/dev/ttyUSB0")

    def test_no_match_raises(self):
        with patch("pypamc204.controller.list_ports.comports", return_value=[]):
            with self.assertRaises(ConnectionError):
                find_port()

    def test_multiple_matches_raises(self):
        ports = [
            self._mock_port("COM3", 0x0403, 0x6015),
            self._mock_port("COM4", 0x0403, 0x6015),
        ]
        with patch("pypamc204.controller.list_ports.comports", return_value=ports):
            with self.assertRaises(ConnectionError):
                find_port()

    def test_custom_vid_pid(self):
        ports = [self._mock_port("COM5", 0x1234, 0x5678)]
        with patch("pypamc204.controller.list_ports.comports", return_value=ports):
            self.assertEqual(find_port(vid=0x1234, pid=0x5678), "COM5")


class TestAutoDetectOpen(unittest.TestCase):
    """port省略時の自動検出オープン"""

    def test_open_without_port_uses_find_port(self):
        with patch("pypamc204.controller.find_port", return_value="COM7") as mock_find, \
                patch("pypamc204.controller.serial.Serial") as mock_serial:
            ctrl = PAMC204()
            ctrl.open()
            mock_find.assert_called_once()
            self.assertEqual(mock_serial.call_args.kwargs["port"], "COM7")

    def test_open_with_explicit_port_skips_detection(self):
        with patch("pypamc204.controller.find_port") as mock_find, \
                patch("pypamc204.controller.serial.Serial") as mock_serial:
            ctrl = PAMC204("COM3")
            ctrl.open()
            mock_find.assert_not_called()
            self.assertEqual(mock_serial.call_args.kwargs["port"], "COM3")

    def test_open_propagates_detection_error(self):
        with patch(
            "pypamc204.controller.find_port",
            side_effect=ConnectionError("not found"),
        ):
            ctrl = PAMC204()
            with self.assertRaises(ConnectionError):
                ctrl.open()


if __name__ == "__main__":
    unittest.main()
