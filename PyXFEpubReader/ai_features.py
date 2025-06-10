import json
import os
import ssl
import websocket
import hmac
import hashlib
from PyQt6.QtWidgets import QScrollArea
from urllib.parse import urlparse, urlencode
from wsgiref.handlers import format_date_time
from datetime import datetime
from time import mktime
from typing import Dict, Any
from PyQt6.QtWidgets import (QWidget,QGridLayout,QComboBox, QVBoxLayout,
                             QTextEdit, QPushButton, QLabel, QHBoxLayout,
                             QGroupBox)

import base64
from PyQt6.QtCore import pyqtSignal, QThread
from enum import Enum
from bs4 import BeautifulSoup
from PyQt6.QtWidgets import QInputDialog
from PyQt6.QtWidgets import QApplication
import logging

# 设置日志记录
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class AIModelType(Enum):
    """AI模型类型枚举"""
    XUNFEI = "讯飞星火"


class Ws_Param(object):
    """WebSocket参数类"""

    def __init__(self, APPID, APIKey, APISecret, gpt_url):
        """初始化WebSocket参数"""
        self.APPID = APPID
        self.APIKey = APIKey
        self.APISecret = APISecret
        self.host = urlparse(gpt_url).netloc
        self.path = urlparse(gpt_url).path
        self.gpt_url = gpt_url

    def create_url(self):
        """生成WebSocket连接URL"""
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))

        signature_origin = "host: " + self.host + "\n"
        signature_origin += "date: " + date + "\n"
        signature_origin += "GET " + self.path + " HTTP/1.1"

        signature_sha = hmac.new(self.APISecret.encode('utf-8'),
                               signature_origin.encode('utf-8'),
                               digestmod=hashlib.sha256).digest()

        signature_sha_base64 = base64.b64encode(signature_sha).decode(encoding='utf-8')

        authorization_origin = f'api_key="{self.APIKey}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha_base64}"'

        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')

        v = {
            "authorization": authorization,
            "date": date,
            "host": self.host
        }
        url = self.gpt_url + '?' + urlencode(v)
        logger.debug(f"Generated URL: {url}")
        return url


class AIWorker(QThread):
    """AI工作线程"""

    response_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, model_type: AIModelType, prompt: str, config: dict):
        """初始化工作线程"""
        super().__init__()
        self.model_type = model_type
        self.prompt = prompt
        self.config = {
            "app_id": config.get("app_id", "").strip(),
            "api_key": config.get("api_key", "").strip(),
            "api_secret": config.get("api_secret", "").strip(),
            "api_url": config.get("api_url", "wss://spark-api.xf-yun.com/v1.1/chat").strip()
        }

    def run(self):
        """执行API调用"""
        try:
            if self.model_type == AIModelType.XUNFEI:
                result = self.call_xunfei()
                self.response_signal.emit(result)
        except Exception as e:
            self.error_signal.emit(str(e))

    def call_xunfei(self) -> str:
        """调用讯飞星火API"""
        wsParam = Ws_Param(
            APPID=self.config["app_id"],
            APIKey=self.config["api_key"],
            APISecret=self.config["api_secret"],
            gpt_url=self.config["api_url"]
        )
        response_content = []

        def on_message(ws, message):
            """处理WebSocket消息"""
            data = json.loads(message)
            code = data['header']['code']
            if code != 0:
                raise ValueError(f'请求错误: {code}, {data}')

            choices = data["payload"]["choices"]
            status = choices["status"]
            content = choices["text"][0]["content"]
            response_content.append(content)

            if status == 2:
                ws.close()

        def on_error(ws, error):
            """处理WebSocket错误"""
            raise ValueError(f"WebSocket错误: {error}")

        def on_close(ws, close_status_code, close_msg):
            """处理WebSocket关闭"""
            logger.debug("WebSocket连接关闭")

        def on_open(ws):
            """处理WebSocket打开"""
            data = json.dumps(self.gen_params(
                appid=self.config["app_id"],
                query=self.prompt,
                domain="lite"
            ))
            ws.send(data)

        websocket.enableTrace(False)
        wsUrl = wsParam.create_url()
        ws = websocket.WebSocketApp(
            wsUrl,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )
        ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

        return "".join(response_content)

    def gen_params(self, appid, query, domain):
        """生成请求参数"""
        return {
            "header": {
                "app_id": appid,
                "uid": "1234",
            },
            "parameter": {
                "chat": {
                    "domain": domain,
                    "temperature": 0.5,
                    "max_tokens": 4096,
                    "auditing": "default",
                }
            },
            "payload": {
                "message": {
                    "text": [{"role": "user", "content": query}]
                }
            }
        }


class AIWidget(QWidget):
    """AI功能部件"""

    def __init__(self, parent=None):
        """初始化AI部件"""
        super().__init__(parent)
        self.parent = parent
        logger.debug("初始化AIWidget")

        # 主布局
        main_layout = QGridLayout()
        self.setLayout(main_layout)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(10)

        # 模型选择区
        model_layout = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.addItems([model.value for model in AIModelType])
        model_layout.addWidget(QLabel("模型:"))
        model_layout.addWidget(self.model_combo)
        model_layout.addStretch()
        main_layout.addLayout(model_layout, 0, 0, 1, 2)

        # 功能区
        function_group = QGroupBox("快捷功能")
        function_layout = QGridLayout()
        function_group.setLayout(function_layout)

        self.summary_btn = QPushButton("总结")
        self.summary_btn.setToolTip("总结当前内容")

        self.translate_btn = QPushButton("翻译")
        self.translate_btn.setToolTip("翻译当前内容")

        self.explain_btn = QPushButton("解释")
        self.explain_btn.setToolTip("解释当前内容")

        self.ask_btn = QPushButton("提问")
        self.ask_btn.setToolTip("提问当前内容")

        function_layout.addWidget(self.summary_btn, 0, 0)
        function_layout.addWidget(self.translate_btn, 0, 1)
        function_layout.addWidget(self.explain_btn, 0, 2)
        function_layout.addWidget(self.ask_btn, 0, 3)

        function_layout.setHorizontalSpacing(10)
        function_layout.setVerticalSpacing(10)

        main_layout.addWidget(function_group, 1, 0, 1, 2)

        # 输出区
        output_group = QGroupBox("AI响应")
        output_layout = QVBoxLayout()
        output_group.setLayout(output_layout)

        self.output_edit = QTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setMinimumHeight(250)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.output_edit)
        output_layout.addWidget(scroll_area)

        button_layout = QHBoxLayout()
        self.send_btn = QPushButton("发送")
        self.copy_btn = QPushButton("复制")
        self.clear_btn = QPushButton("清空")

        button_layout.addWidget(self.send_btn)
        button_layout.addWidget(self.copy_btn)
        button_layout.addWidget(self.clear_btn)
        output_layout.addLayout(button_layout)

        main_layout.addWidget(output_group, 2, 0, 1, 2)

        # 输入区
        input_group = QGroupBox("输入")
        input_layout = QVBoxLayout()
        input_group.setLayout(input_layout)

        self.input_edit = QTextEdit()
        self.input_edit.setPlaceholderText("输入问题或指令...")
        self.input_edit.setMaximumHeight(100)

        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("预设提示:"))
        self.presets_combo = QComboBox()
        self.presets_combo.addItems([
            "请总结这段内容",
            "请翻译成英文",
            "请解释这段内容",
            "请用简单的语言解释",
            "这段内容的主要观点是什么"
        ])
        self.presets_combo.currentTextChanged.connect(self.apply_preset)
        preset_layout.addWidget(self.presets_combo)
        input_layout.addWidget(self.input_edit)
        input_layout.addLayout(preset_layout)

        main_layout.addWidget(input_group, 3, 0, 1, 2)

        main_layout.setRowStretch(2, 7)
        main_layout.setRowStretch(3, 3)

        # 连接信号
        self.summary_btn.clicked.connect(self.summarize_current_content)
        self.translate_btn.clicked.connect(self.translate_current_content)
        self.explain_btn.clicked.connect(self.explain_current_content)
        self.ask_btn.clicked.connect(self.ask_about_content)
        self.send_btn.clicked.connect(self.send_request)
        self.copy_btn.clicked.connect(self.copy_result)
        self.clear_btn.clicked.connect(self.clear_output)

        # 加载模型配置
        self.model_configs = self.load_model_configs()
        logger.debug(f"加载的模型配置: {self.model_configs}")

        # 当前选择的模型
        self.current_model = AIModelType.XUNFEI

    def apply_preset(self, text):
        """应用预设提示词"""
        logger.debug(f"应用预设提示词: {text}")
        self.input_edit.setPlainText(text)

    def get_current_content(self):
        """获取当前阅读的内容"""
        if self.parent and hasattr(self.parent, 'text_browser'):
            html_content = self.parent.text_browser.toHtml()
            soup = BeautifulSoup(html_content, 'html.parser')
            content = soup.get_text().strip()
            logger.debug(f"获取当前内容: {content[:100]}...")
            return content
        logger.warning("无法获取当前内容，parent或text_browser不存在")
        return ""

    def summarize_current_content(self):
        """总结当前内容"""
        logger.debug("执行总结当前内容")
        content = self.get_current_content()
        if not content:
            self.output_edit.setPlainText("错误：没有可总结的内容")
            return

        self.input_edit.setPlainText(f"请用简洁的语言总结以下内容，提取关键点:\n\n{content}")
        self.send_request()

    def translate_current_content(self):
        """翻译当前内容"""
        logger.debug("执行翻译当前内容")
        content = self.get_current_content()
        if not content:
            self.output_edit.setPlainText("错误：没有可翻译的内容")
            return

        self.input_edit.setPlainText(f"请将以下内容翻译成英文:\n\n{content}")
        self.send_request()

    def explain_current_content(self):
        """解释当前内容"""
        logger.debug("执行解释当前内容")
        content = self.get_current_content()
        if not content:
            self.output_edit.setPlainText("错误：没有可解释的内容")
            return

        self.input_edit.setPlainText(f"请用简单的语言解释以下内容:\n\n{content}")
        self.send_request()

    def ask_about_content(self):
        """提问当前内容"""
        logger.debug("执行提问当前内容")
        content = self.get_current_content()
        if not content:
            self.output_edit.setPlainText("错误：没有可提问的内容")
            return

        question, ok = QInputDialog.getText(self, "提问", "请输入关于当前内容的问题:")
        if ok and question:
            self.input_edit.setPlainText(f"关于以下内容:\n\n{content}\n\n问题:{question}")
            self.send_request()

    def send_request(self):
        """发送请求到AI模型"""
        prompt = self.input_edit.toPlainText().strip()
        logger.debug(f"准备发送请求，提示词: {prompt}")

        if not prompt:
            self.output_edit.setPlainText("错误：请输入问题或指令")
            return

        try:
            model_type = AIModelType(self.model_combo.currentText())
            logger.debug(f"选择的模型类型: {model_type}")
        except ValueError as e:
            error_msg = f"无效的模型类型: {e}"
            logger.error(error_msg)
            self.output_edit.setPlainText(error_msg)
            return

        self.output_edit.setPlainText("正在思考...")
        QApplication.processEvents()

        config = self.model_configs.get(model_type.value, {})
        if not config:
            error_msg = f"找不到模型配置: {model_type.value}"
            logger.error(error_msg)
            self.output_edit.setPlainText(error_msg)
            return

        logger.debug(f"使用的配置: {config}")

        self.worker = AIWorker(model_type, prompt, config)
        self.worker.response_signal.connect(self.handle_response)
        self.worker.error_signal.connect(self.handle_error)
        logger.debug("启动AI工作线程...")
        self.worker.start()

    def handle_response(self, response):
        """处理AI响应"""
        logger.debug(f"处理AI响应，长度: {len(response)}")
        self.output_edit.setPlainText(response)

    def handle_error(self, error):
        """处理错误"""
        logger.error(f"处理错误: {error}")
        self.output_edit.setPlainText(f"错误: {error}")

    def copy_result(self):
        """复制结果到剪贴板"""
        logger.debug("复制结果到剪贴板")
        clipboard = QApplication.clipboard()
        clipboard.setText(self.output_edit.toPlainText())

    def clear_output(self):
        """清空输出"""
        logger.debug("清空输出")
        self.output_edit.clear()

    def load_model_configs(self) -> Dict[str, Dict[str, Any]]:
        """加载模型配置"""
        config_path = os.path.join(os.path.dirname(__file__), "ai_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载配置文件出错: {e}")
###————————————————————————————————————————填入API接口————————————————————————————————————————————————————————————————————————————
        return {
            "讯飞星火": {
                "app_id": "",
                "api_secret": "",
                "api_key": "",
                "api_url": ""
            }
        }

if __name__ == "__main__":
    app = QApplication([])
    dialog = AIWidget()
    dialog.show()
    app.exec()