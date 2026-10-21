class PAMC204Error(Exception):
    """PAMC-204 / PAMC-204A 通信エラーの基底クラス"""


class ConnectionError(PAMC204Error):
    """ドライバへの接続に失敗"""


class CommandError(PAMC204Error):
    """ドライバがエラーレスポンスを返した"""


class TimeoutError(PAMC204Error):
    """タイムアウト時間内にレスポンスを受信できなかった"""


class BusyError(PAMC204Error):
    """ドライバが駆動中（モーター動作中）"""


class ValueRangeError(PAMC204Error):
    """パラメータ値が許容範囲外"""
