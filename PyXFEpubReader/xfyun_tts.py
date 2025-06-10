
import websocket
import datetime
import hashlib
import base64
import hmac
import json
from urllib.parse import urlencode
import ssl
from wsgiref.handlers import format_date_time
from datetime import datetime
from time import mktime
import _thread as thread
import threading


class XFYunTTS:
    def __init__(self, APPID, APIKey, APISecret):
        """初始化TTS引擎，设置API凭证"""
        self.APPID = APPID
        self.APIKey = APIKey
        self.APISecret = APISecret
        self.ws = None
        self.audio_data = bytearray()
        self.is_finished = False
        self.error_message = None
        self.lock = threading.Lock()
        self.connection_timeout = 10
        self.sid = None
        self._close_event = threading.Event()

    def create_url(self):
        """生成带鉴权的WebSocket连接URL"""
        url = 'wss://tts-api.xfyun.cn/v2/tts'
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))

        signature_origin = "host: " + "ws-api.xfyun.cn" + "\n"
        signature_origin += "date: " + date + "\n"
        signature_origin += "GET " + "/v2/tts " + "HTTP/1.1"

        signature_sha = hmac.new(self.APISecret.encode('utf-8'),
                                 signature_origin.encode('utf-8'),
                                 digestmod=hashlib.sha256).digest()
        signature_sha = base64.b64encode(signature_sha).decode(encoding='utf-8')

        authorization_origin = f'api_key="{self.APIKey}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha}"'
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')

        v = {
            "authorization": authorization,
            "date": date,
            "host": "ws-api.xfyun.cn"
        }
        return url + '?' + urlencode(v)

    def on_message(self, ws, message):
        """处理WebSocket接收到的消息（音频数据/状态）"""
        try:
            message = json.loads(message)
            code = message["code"]
            self.sid = message["sid"]

            if code != 0:
                self.error_message = f"Error {code}: {message.get('message', 'Unknown error')}"
                ws.close()
                return

            audio = message["data"]["audio"]
            status = message["data"]["status"]

            with self.lock:
                self.audio_data.extend(base64.b64decode(audio))
                if status == 2:  # 最后一帧
                    self.is_finished = True
                    ws.close()

        except Exception as e:
            self.error_message = f"Parse message exception: {str(e)}"
            ws.close()

    def on_error(self, ws, error):
        """处理WebSocket错误"""
        self.error_message = str(error)

    def on_close(self, ws, close_status_code, close_msg):
        """WebSocket关闭时触发事件"""
        self._close_event.set()

    def on_open(self, ws):
        """WebSocket连接建立后发送TTS请求参数"""
        def run(*args):
            common_args = {"app_id": self.APPID}
            business_args = {
                "aue": "raw",
                "auf": "audio/L16;rate=16000",
                "vcn": "x4_yezi",
                "tte": "utf8"
            }
            data = {
                "status": 2,
                "text": str(base64.b64encode(self.current_text.encode('utf-8')), "UTF8")
            }

            d = {
                "common": common_args,
                "business": business_args,
                "data": data
            }
            ws.send(json.dumps(d))

        thread.start_new_thread(run, ())

    def text_to_speech(self, text):
        """主接口：将文本转换为语音并返回音频数据"""
        self.current_text = text
        self.audio_data = bytearray()
        self.is_finished = False
        self.error_message = None
        self.sid = None
        self._close_event.clear()

        ws_url = self.create_url()

        try:
            websocket.setdefaulttimeout(self.connection_timeout)
            self.ws = websocket.WebSocketApp(
                ws_url,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )
            self.ws.on_open = self.on_open

            self.ws.run_forever(
                sslopt={"cert_reqs": ssl.CERT_NONE},
                ping_interval=10,
                ping_timeout=5
            )

            if not self._close_event.wait(timeout=30):
                raise Exception("TTS操作超时")

            if self.error_message:
                raise Exception(f"TTS Error (SID: {self.sid}): {self.error_message}")

            if not self.is_finished:
                raise Exception("TTS未完成")

            return bytes(self.audio_data)

        except Exception as e:
            if self.ws:
                self.ws.close()
            raise
        finally:
            self.ws = None