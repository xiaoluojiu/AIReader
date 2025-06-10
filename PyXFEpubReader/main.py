import os
import sys
import re
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, \
    QWidget, QSplitter, QTableWidget, QTableWidgetItem, QTextBrowser, QFileDialog, QProgressBar, QComboBox, \
    QFontDialog, QSlider, QDialog, QListWidget, QStatusBar
from PyQt6.QtCore import Qt, QThread
from PyQt6.QtGui import QIcon, QFont
import zipfile
import pyaudio
import threading
from xfyun_tts import XFYunTTS
from PyQt6.QtCore import QObject, pyqtSignal
import shutil
import json
import time
from ai_features import AIWidget
from search_feature import SearchDialog

script_path = os.path.abspath(__file__)
script_dir = os.path.dirname(script_path)
os.chdir(script_dir)


class EpubReader(QMainWindow):
    def __init__(self, *args, **kwargs):
        """初始化EPUB阅读器主窗口"""
        super().__init__(*args, **kwargs)
        self.max_retries = 3
        self.setWindowTitle("EPUB 阅读器")
        self.setWindowIcon(QIcon("./icon/icons8-book-96.png"))
        self.resize(1600, 1000)

        # 语音相关初始化
        self.xfyun_tts = None
        self.is_playing = False

        # 初始化行间距和段间距
        self.line_spacing = 20
        self.paragraph_spacing = 10

        # 创建主部件和布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 创建顶部控制栏
        self.create_top_control_bar(main_layout)

        # 创建主内容分割器
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧章节表格
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(1)
        self.table_widget.setHorizontalHeaderLabels(["章节"])
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.itemDoubleClicked.connect(self.render_selected_file)

        # 中部主文本框
        self.text_browser = QTextBrowser()

        # 创建右侧AI区域
        self.ai_widget = AIWidget(self)

        # 添加到主分割器
        self.main_splitter.addWidget(self.table_widget)
        self.main_splitter.addWidget(self.text_browser)
        self.main_splitter.addWidget(self.ai_widget)

        # 设置初始比例 (1:3:1)
        total_width = self.width()
        self.main_splitter.setSizes([
            int(total_width * 0.2),  # 左侧章节表格
            int(total_width * 0.6),  # 中部主文本框
            int(total_width * 0.2)  # 右侧AI区域
        ])
        main_layout.addWidget(self.main_splitter)

        # 创建底部状态栏
        self.status_bar = QStatusBar()
        self.status_bar.setMaximumHeight(20)
        self.status_bar.setStyleSheet("QStatusBar { font-size: 10pt; }")
        main_layout.addWidget(self.status_bar)

        # 初始化其他属性
        self.epub_file_path = None
        self.font_size = 14
        self.sentences = []
        self.current_sentence_index = -1
        self.html_path_name = []
        self.is_eye_protection_mode_active = False

        # 初始化字体
        self.font = QFont("Microsoft YaHei", 14)
        self.text_browser.setFont(self.font)

        # 自动加载书籍
        self.populate_books_combo()

    def create_top_control_bar(self, main_layout):
        """创建顶部控制栏"""
        # 第一行按钮
        hbox1 = QHBoxLayout()

        # 文件选择
        hbox1.addWidget(QLabel("选择文件:"))
        self.file_combo = QComboBox()
        self.file_combo.setMinimumWidth(50)
        self.file_combo.currentIndexChanged.connect(self.on_combo_changed)
        hbox1.addWidget(self.file_combo)

        # 操作按钮
        buttons = [
            ("打开文件", "icons8-打开文件夹-240.png", self.open_file, "open_button"),
            ("选择字体", "icons8-font-96.png", self.select_and_apply_font, "font_button"),
            ("护眼模式", "icons8-眼睛-96.png", self.set_eye_protection_mode, "eye_protection_button"),
            ("隐藏边栏", "icons8-add-bookmark-240.png", self.toggle_sidebar, "toggle_sidebar_button"),
            ("AI功能", "icons8-ai-96.png", lambda: None, "ai_button"),
            ("全文搜索", "icons8-search-96.png", self.show_search_dialog, "search_button"),
            ("增大字号", "icons8-加大字体-96.png", self.increase_font_size, "increase_font_button"),
            ("减小字号", "icons8-减小字体-96.png", self.decrease_font_size, "decrease_font_button"),
            ("播放当前页", "icons8-connect-240.png", self.play_current_text, "play_button"),
            ("停止播放", "icons8-stop-64.png", self.stop_playback, "stop_button"),
            ("全屏模式", "icons8-checkmark-240.png", self.toggle_fullscreen, "fullscreen_button")
        ]

        for text, icon, callback, button_name in buttons:
            btn = QPushButton(text)
            btn.setIcon(QIcon(f"./icon/{icon}"))
            btn.clicked.connect(callback)
            setattr(self, button_name, btn)
            hbox1.addWidget(btn)
        main_layout.addLayout(hbox1)

        # 第二行进度条
        hbox2 = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hbox2.addWidget(self.progress_bar)
        main_layout.addLayout(hbox2)

        # 第三行滑块控制
        hbox3 = QHBoxLayout()

        # 页边距
        self.margin_label = QLabel("页边距: 10")
        hbox3.addWidget(self.margin_label)
        self.margin_slider = QSlider(Qt.Orientation.Horizontal)
        self.margin_slider.setRange(0, 50)
        self.margin_slider.setValue(10)
        self.margin_slider.valueChanged.connect(self.update_margin)
        hbox3.addWidget(self.margin_slider)

        # 行间距
        self.line_spacing_label = QLabel("行间距: 20")
        hbox3.addWidget(self.line_spacing_label)
        self.line_spacing_slider = QSlider(Qt.Orientation.Horizontal)
        self.line_spacing_slider.setRange(0, 50)
        self.line_spacing_slider.setValue(20)
        self.line_spacing_slider.valueChanged.connect(self.update_line_spacing)
        hbox3.addWidget(self.line_spacing_slider)

        # 段间距
        self.paragraph_spacing_label = QLabel("段间距: 10")
        hbox3.addWidget(self.paragraph_spacing_label)
        self.paragraph_spacing_slider = QSlider(Qt.Orientation.Horizontal)
        self.paragraph_spacing_slider.setRange(0, 50)
        self.paragraph_spacing_slider.setValue(10)
        self.paragraph_spacing_slider.valueChanged.connect(self.update_paragraph_spacing)
        hbox3.addWidget(self.paragraph_spacing_slider)

        # 收藏按钮
        self.favorites_file = os.path.join(os.path.dirname(__file__), "book", "favorites.txt")
        hbox3.addWidget(QPushButton("收藏", clicked=self.add_to_favorites))
        hbox3.addWidget(QPushButton("查看收藏", clicked=self.show_favorites))
        main_layout.addLayout(hbox3)

    def play_current_text(self):
        """播放当前页面的文本"""
        if self.is_playing:
            return

        current_text = self.text_browser.toPlainText()
        if not current_text:
            self.status_bar.showMessage("没有可播放的文本内容", 3000)
            return

        # 限制文本长度
        if len(current_text) > 500:
            current_text = current_text[:500] + "..."
####———————————————————————————————————————————————————————————————填入API接口——————————————————————————————————————————————————————
        # 初始化 TTS 引擎
        if not hasattr(self, 'xfyun_tts') or self.xfyun_tts is None:
            try:
                self.xfyun_tts = XFYunTTS(
                    APPID='',
                    APIKey='',
                    APISecret=''
                )
            except Exception as e:
                self.status_bar.showMessage(f"初始化语音引擎失败: {str(e)}", 5000)
                return

        self.status_bar.showMessage("正在生成语音...", 3000)
        self.is_playing = True
        self.audio_playing = True

        # 创建线程和 worker
        self.play_thread = QThread()
        self.play_worker = self.TTSWorker(
            self.xfyun_tts,
            current_text,
            self.max_retries
        )
        self.play_worker.moveToThread(self.play_thread)

        # 连接信号
        self.play_thread.started.connect(self.play_worker.run_tts)
        self.play_worker.tts_finished.connect(self.on_tts_finished)
        self.play_worker.tts_error.connect(self.on_tts_error)
        self.play_worker.finished.connect(self.play_thread.quit)
        self.play_thread.finished.connect(self.cleanup_playback)

        # 启动线程
        self.play_thread.start()

    def stop_playback(self):
        """停止播放"""
        if not self.is_playing:
            return

        self.audio_playing = False

        # 停止TTS生成
        if hasattr(self, 'play_worker') and self.play_worker:
            self.play_worker.stop()

        # 停止音频播放
        self.cleanup_audio_resources()

        # 清理线程
        if hasattr(self, 'play_thread') and self.play_thread.isRunning():
            self.play_thread.quit()
            self.play_thread.wait()

        self.is_playing = False
        self.status_bar.showMessage("播放已停止", 3000)

    def on_tts_finished(self, audio_data):
        """TTS 完成信号处理"""
        try:
            # 保存音频到临时文件
            temp_file = "temp_playback.pcm"
            with open(temp_file, "wb") as f:
                f.write(audio_data)

            # 在单独的线程中播放音频
            self.audio_thread = threading.Thread(
                target=self.play_audio,
                args=(temp_file,),
                daemon=True
            )
            self.audio_thread.start()

        except Exception as e:
            self.status_bar.showMessage(f"播放准备失败: {str(e)}", 5000)
            self.cleanup_playback()

    def play_audio(self, file_path):
        """播放音频文件"""
        try:
            p = pyaudio.PyAudio()
            stream = None
            try:
                stream = p.open(format=pyaudio.paInt16,
                                channels=1,
                                rate=16000,
                                output=True)

                with open(file_path, 'rb') as f:
                    while self.audio_playing:
                        data = f.read(1024)
                        if not data:
                            break
                        stream.write(data)
            finally:
                if stream:
                    stream.stop_stream()
                    stream.close()
                p.terminate()
        except Exception as e:
            print(f"播放错误: {e}")
        finally:
            try:
                os.remove(file_path)
            except:
                pass

    def cleanup_audio_resources(self):
        """清理音频资源"""
        self.audio_playing = False

        if hasattr(self, 'audio_stream') and self.audio_stream:
            try:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
            except:
                pass
        if hasattr(self, 'p') and self.p:
            try:
                self.p.terminate()
            except:
                pass
        self.p = None
        self.audio_stream = None

    def cleanup_playback(self):
        """清理播放资源"""
        self.is_playing = False

    def on_tts_error(self, error_msg):
        """TTS 错误信号处理"""
        self.status_bar.showMessage(f"语音生成错误: {error_msg}", 5000)
        self.cleanup_playback()

    def toggle_fullscreen(self):
        """切换全屏模式"""
        if self.isFullScreen():
            self.showNormal()
            self.fullscreen_button.setText("全屏模式")
        else:
            self.showFullScreen()
            self.fullscreen_button.setText("退出全屏")

    def update_margin(self, value):
        """更新页边距"""
        self.margin_label.setText(f"页边距: {value}")
        style_sheet = f"""
        QTextBrowser {{
            padding: {value}px;
        }}
        """
        self.text_browser.setStyleSheet(style_sheet)
    ##注释改====2  详细注释
    def update_line_spacing(self, value):
        """更新行间距"""
        self.line_spacing = value
        self.line_spacing_label.setText(f"行间距: {value}")

        # 更新当前显示的文本样式
        if self.text_browser.toPlainText():
            # 获取当前HTML内容
            html = self.text_browser.toHtml()

            # 使用正则表达式更新或添加行间距样式
            if "line-height:" in html:
                html = re.sub(r"line-height:\s*\d+px", f"line-height: {value}px", html)
            else:
                # 在第一个<style>标签后添加行间距样式
                if "<style>" in html:
                    html = html.replace("<style>", f"<style>\np {{ line-height: {value}px; }}")
                else:
                    # 如果没有样式标签，在头部添加
                    head_end = html.find("</head>")
                    if head_end != -1:
                        html = html[:head_end] + f"<style>p {{ line-height: {value}px; }}</style>" + html[head_end:]

            # 重新设置HTML内容
            self.text_browser.setHtml(html)

    def update_paragraph_spacing(self, value):
        """更新段间距"""
        self.paragraph_spacing = value
        self.paragraph_spacing_label.setText(f"段间距: {value}")

        # 更新当前显示的文本样式
        if self.text_browser.toPlainText():
            # 获取当前HTML内容
            html = self.text_browser.toHtml()

            # 使用正则表达式更新或添加段间距样式
            if "margin-bottom:" in html:
                html = re.sub(r"margin-bottom:\s*\d+px", f"margin-bottom: {value}px", html)
            else:
                # 在第一个<style>标签后添加段间距样式
                if "<style>" in html:
                    html = html.replace("<style>", f"<style>\np {{ margin-bottom: {value}px; }}")
                else:
                    # 如果没有样式标签，在头部添加
                    head_end = html.find("</head>")
                    if head_end != -1:
                        html = html[:head_end] + f"<style>p {{ margin-bottom: {value}px; }}</style>" + html[head_end:]

            # 重新设置HTML内容
            self.text_browser.setHtml(html)
    def toggle_sidebar(self):
        """切换左侧章节表格的显示/隐藏"""
        current_sizes = self.main_splitter.sizes()

        # 获取按钮当前文本长度（用于判断是否显示文字）
        ll = len(self.toggle_sidebar_button.text())

        if current_sizes[0] > 0:  # 如果左侧区域当前可见
            # 隐藏左侧区域，将空间分配给中部和右侧（保持它们原有比例）
            mid_ratio = current_sizes[1] / (current_sizes[1] + current_sizes[2]) if (current_sizes[1] + current_sizes[
                2]) > 0 else 0.75
            right_ratio = 1 - mid_ratio

            new_mid = int(self.width() * mid_ratio)
            new_right = self.width() - new_mid

            self.main_splitter.setSizes([0, new_mid, new_right])

            # 更新按钮文本
            if ll > 1:
                self.toggle_sidebar_button.setText("显示边栏")
            elif ll == 0:
                self.toggle_sidebar_button.setText("")

        else:  # 如果左侧区域当前隐藏
            # 显示左侧区域，设置为窗口宽度的1/6，剩余空间按当前比例分配给中部和右侧
            left_size = int(self.width() * 1 / 6)
            remaining = self.width() - left_size

            # 如果没有历史比例，使用默认比例（中部3/4，右侧1/4）
            if len(current_sizes) >= 3 and (current_sizes[1] + current_sizes[2]) > 0:
                mid_ratio = current_sizes[1] / (current_sizes[1] + current_sizes[2])
                right_ratio = 1 - mid_ratio
            else:
                mid_ratio = 0.75
                right_ratio = 0.25

            new_mid = int(remaining * mid_ratio)
            new_right = remaining - new_mid

            self.main_splitter.setSizes([left_size, new_mid, new_right])

            # 更新按钮文本
            if ll > 1:
                self.toggle_sidebar_button.setText("隐藏边栏")
            elif ll == 0:
                self.toggle_sidebar_button.setText("")

    def set_eye_protection_mode(self):
        """设置护眼配色模式"""
        self.is_eye_protection_mode_active = True
        self.text_browser.setStyleSheet("color: #1A3D14; background-color: #DCEBDD;")

    def select_and_apply_font(self):
        """选择并应用字体"""
        self.font, ok = QFontDialog.getFont()
        if ok:
            self.text_browser.setFont(self.font)
            self.apply_font_size()

    def on_combo_changed(self, index):
        """书籍选择下拉框变化事件"""
        book_name = self.file_combo.currentText()
        self.auto_load_book(book_name)
        self.load_and_render_first_file()

    def open_file(self):
        """打开文件对话框"""
        file_path, _ = QFileDialog.getOpenFileName(self, "选择EPUB文件", "", "EPUB Files (*.epub)")

        if file_path:
            self.epub_file_path = file_path
            self.unzip_file()

    def unzip_file(self):
        """解压EPUB文件"""
        if not self.epub_file_path:
            return

        # 获取 EPUB 文件的基本信息
        epub_file = os.path.basename(self.epub_file_path)
        epub_folder = os.path.splitext(epub_file)[0]

        book_path = os.path.join("book", epub_folder)

        # 检查目标目录是否已存在
        if not os.path.exists(book_path):
            # 创建 book 目录
            if not os.path.exists("book"):
                os.makedirs("book")

            # 复制 EPUB 文件到 book 目录
            shutil.copy2(self.epub_file_path, os.path.join("book", epub_file))

            # 将 EPUB 文件扩展名更改为 .zip
            zip_file = os.path.splitext(epub_file)[0] + ".zip"
            zip_file_path = os.path.join("book", zip_file)
            os.rename(os.path.join("book", epub_file), zip_file_path)

            # 解压缩 EPUB 文件
            with zipfile.ZipFile(zip_file_path, 'r') as epub_zip:
                epub_zip.extractall(book_path)

        # 搜索目录并添加到QComboBox中
        folders = self.search_folders_with_html(book_path)
        for folder in folders:
            self.file_combo.addItem(folder)
        self.html_path_name = folders[0]

        self.update_file_list()
        self.render_selected_file()

    def search_folders_with_html(self, start_path):
        """搜索包含大于3个.html或.xhtml文件的目录"""
        valid_folders = []

        for root, _, files in os.walk(start_path):
            count = sum(1 for file in files if file.endswith(('.html', '.xhtml')))
            if count > 3:
                valid_folders.append(root)

        return valid_folders

    def render_selected_file(self, item=None):
        """渲染选中的文件内容"""
        if item is None:
            return

        # 获取双击或选中的文件名
        selected_file_name = item.text()

        # 构建文件的完整路径    文件明
        epub_file = os.path.basename(self.epub_file_path)
        epub_folder = os.path.splitext(epub_file)[0]

        selected_file_path0 = self.html_path_name + '/' + selected_file_name
        selected_file_path = './' + re.sub(r'\\', '/', selected_file_path0)

        # 获取样式表的完整路径
        stylesheet_path0 = "./book/" + epub_folder + "/EPUB/"
        if os.path.exists(stylesheet_path0):
            stylesheet_path = "./book/" + epub_folder + "/EPUB/stylesheet.css"
            page_styles = "./book/" + epub_folder + "/EPUB/page_styles.css"
        else:
            stylesheet_path = "./book/" + epub_folder + "/stylesheet.css"
            page_styles = "./book/" + epub_folder + "/page_styles.css"

        if os.path.exists(selected_file_path):
            # 读取选定文件的内容
            with open(selected_file_path, "r", encoding="utf-8") as file:
                file_content = file.read()

                combined_style = f"""
                        <style>
                            img {{
                                max-width: 100%;
                                height: auto;
                            }}
                            p {{
                                line-height: {self.line_spacing}px;
                                margin-bottom: {self.paragraph_spacing}px;
                            }}
                        </style>
                        """

                file_content = combined_style + file_content
                style_tag = f"<style>{stylesheet_path}</style>"
                # 将样式内容添加到HTML头部
                file_content = file_content.replace('href="../../stylesheet.css', f'href="{stylesheet_path}')
                file_content = file_content.replace('href="../../page_styles.css', f'href="{page_styles}')

                # 修复相对图片路径
                image_base_path = os.path.join("book", epub_folder, "EPUB", "images")
                file_content = file_content.replace('src="../images/', f'src="{image_base_path}/')

                # 在右侧渲染修复后的内容
                self.text_browser.setHtml(file_content)

     #注释改-----
    def update_file_list(self):
        """更新文件列表，显示当前EPUB书籍的所有HTML/XHTML章节文件"""
        if not self.epub_file_path or not os.path.exists("book"):
            return

        try:
            # 获取书籍基本信息
            epub_file = os.path.basename(self.epub_file_path)
            epub_folder = os.path.splitext(epub_file)[0]

            # 确保路径存在
            if not os.path.exists(self.html_path_name):
                return

            # 获取并过滤HTML/XHTML文件
            all_files = os.listdir(self.html_path_name)
            xhtml_files = sorted(
                [f for f in all_files if f.lower().endswith(('.html', '.xhtml'))],
                key=lambda x: [int(s) if s.isdigit() else s.lower() for s in re.split('([0-9]+)', x)]
            )

            # 更新表格控件
            self.table_widget.setRowCount(len(xhtml_files))
            for index, xhtml_file in enumerate(xhtml_files):
                self.table_widget.setItem(index, 0, QTableWidgetItem(xhtml_file))

        except Exception as e:
            print(f"更新文件列表时出错: {e}")
            self.status_bar.showMessage(f"更新文件列表失败: {str(e)}", 5000)
    def resizeEvent(self, event):
        """处理窗口大小变化事件"""
        super().resizeEvent(event)

        if hasattr(self, "main_splitter"):
            current_sizes = self.main_splitter.sizes()
            if sum(current_sizes) > 0:
                # 保持比例关系
                if current_sizes[0] > 0:  # 如果左侧区域可见
                    left_ratio = current_sizes[0] / sum(current_sizes)
                    mid_ratio = current_sizes[1] / sum(current_sizes)

                    new_left = int(self.width() * left_ratio)
                    new_mid = int(self.width() * mid_ratio)
                    new_right = self.width() - new_left - new_mid

                    self.main_splitter.setSizes([new_left, new_mid, new_right])
                else:  # 如果左侧区域隐藏
                    total_other = current_sizes[1] + current_sizes[2]
                    if total_other > 0:
                        mid_ratio = current_sizes[1] / total_other
                        right_ratio = current_sizes[2] / total_other

                        new_mid = int(self.width() * mid_ratio)
                        new_right = self.width() - new_mid

                        self.main_splitter.setSizes([0, new_mid, new_right])

        self.update_buttons_on_resize()

    def update_buttons_on_resize(self):
        """根据窗口大小更新按钮显示方式"""
        width_threshold = 1200

        current_width = self.width()
        self.status_bar.showMessage(f"当前窗口宽度：{current_width}")

        if current_width < width_threshold:
            # 窗口宽度小于阈值，只显示图标
            for btn in [self.open_button, self.eye_protection_button, self.toggle_sidebar_button,
                        self.increase_font_button, self.decrease_font_button, self.play_voice_button,
                        self.fullscreen_button, self.stop_button, self.font_button]:
                btn.setText("")
        else:
            # 窗口宽度大于或等于阈值，显示图标和文本
            self.open_button.setText("打开文件")
            self.eye_protection_button.setText("护眼模式")
            self.toggle_sidebar_button.setText("隐藏边栏")
            self.increase_font_button.setText("增大字号")
            self.decrease_font_button.setText("减小字号")
            self.play_button.setText("播放当前页")
            self.stop_button.setText("停止播放")
            self.fullscreen_button.setText("全屏模式")
            self.font_button.setText("选择字体")

    def increase_font_size(self):
        """增大字号"""
        self.font_size += 1
        self.apply_font_size()
        self.render_selected_file()

    def decrease_font_size(self):
        """减小字号"""
        self.font_size -= 1
        self.apply_font_size()
        self.render_selected_file()

    def apply_font_size(self):
        """应用字体大小到 QTextBrowser"""
        font = QFont()
        font.setPointSize(self.font_size)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.text_browser.setFont(self.font)

        self.text_browser.setFont(font)

        # 保持护眼模式的样式
        if self.is_eye_protection_mode_active:
            self.set_eye_protection_mode()
        else:
            additional_style = """
                        color: #000000;
                        text-align: justify;
                        """
            self.text_browser.setStyleSheet(additional_style)

    def update_progress(self, value):
        """更新进度条的值"""
        self.progress_bar.setValue(value)

    def populate_books_combo(self):
        """填充书籍下拉框"""
        book_dir = os.path.join(script_dir, "book")
        if os.path.exists(book_dir):
            for book_name in os.listdir(book_dir):
                book_path = os.path.join(book_dir, book_name)
                if os.path.isdir(book_path):
                    self.file_combo.addItem(book_name)

            # 如果有书籍，自动加载第一本
            if self.file_combo.count() > 0:
                self.file_combo.setCurrentIndex(0)
                self.auto_load_book(self.file_combo.currentText())
        self.load_and_render_first_file()

    def load_and_render_first_file(self):
        """加载并渲染第一个文件"""
        if self.table_widget.rowCount() > 0:
            first_item = self.table_widget.item(0, 0)
            print("渲染文件：", first_item.text())
            self.render_selected_file(first_item)

    def auto_load_book(self, book_name):
        """自动加载书籍"""
        # 设置 epub 文件路径
        self.epub_file_path = os.path.join(script_dir, "book", book_name)
        book_path = os.path.relpath(os.path.join(script_dir, "book", book_name), start=os.curdir)
        folders = self.search_folders_with_html(book_path)
        print(folders)
        if folders:
            self.html_path_name = folders[0]
            self.update_file_list()
            self.render_selected_file()

    def get_current_position(self):
        """获取当前阅读位置"""
        vertical_scrollbar = self.text_browser.verticalScrollBar()
        position = vertical_scrollbar.value()
        return position

    def go_to_position(self, position_info):
        """跳转到指定位置"""
        if "position" in position_info:
            vertical_scrollbar = self.text_browser.verticalScrollBar()
            vertical_scrollbar.setValue(position_info["position"])

    def show_favorites(self):
        """显示收藏对话框"""
        favorites = self.load_favorites()
        dialog = FavoritesDialog(favorites, self)
        dialog.open_favorite_signal.connect(self.open_favorite)
        dialog.exec()

    def open_favorite(self, favorite_info):
        """打开收藏项"""
        print(favorite_info)
        book_name = favorite_info['book']
        document_name = favorite_info['document']
        position = int(favorite_info['position'])

        # 选中书名列表中的特定书籍
        index = self.file_combo.findText(book_name)
        if index >= 0:
            self.file_combo.setCurrentIndex(index)
            self.auto_load_book(book_name)
        self.auto_load_book(book_name)

        # 找到对应的文档
        for row in range(self.table_widget.rowCount()):
            if self.table_widget.item(row, 0).text() == document_name:
                self.table_widget.selectRow(row)
                self.render_selected_file(self.table_widget.item(row, 0))
                break

        # 滚动到指定位置
        scrollbar = self.text_browser.verticalScrollBar()
        scrollbar.setValue(position)
        print(f"打开收藏项: {favorite_info}")

    def scroll_to_percentage(self, percentage):
        """滚动到指定百分比位置"""
        if 0 <= float(percentage) <= 1:
            scrollbar = self.text_browser.verticalScrollBar()
            position = scrollbar.minimum() + (scrollbar.maximum() - scrollbar.minimum()) * float(percentage)
            scrollbar.setValue(position)

    def load_favorites(self):
        """加载收藏信息"""
        favorites = []
        try:
            with open(self.favorites_file, "r") as file:
                for line in file:
                    favorites.append(json.loads(line.strip()))
        except FileNotFoundError:
            print("收藏文件未找到")
        return favorites

    def add_to_favorites(self):
        """添加到收藏"""
        current_book = self.file_combo.currentText()
        current_document = self.table_widget.currentItem().text()
        current_position = self.get_current_position()
        print(current_position)
        favorite_info = {
            "book": current_book,
            "document": current_document,
            "position": current_position
        }

        with open(self.favorites_file, "a") as file:
            json.dump(favorite_info, file)
            file.write("\n")

        print("已添加到收藏")

    def show_search_dialog(self):
        """显示搜索对话框"""
        search_dialog = SearchDialog(self)
        search_dialog.exec()

    def show_ai_dialog(self):
        """显示AI功能对话框"""
        ai_dialog = AIWidget(self)
        ai_dialog.exec()

    def closeEvent(self, event):
        """窗口关闭事件"""
        self.stop_playback()  # 确保停止所有播放

        # 清理 TTS 资源
        if hasattr(self, 'xfyun_tts') and self.xfyun_tts:
            if hasattr(self.xfyun_tts, 'ws') and self.xfyun_tts.ws:
                try:
                    self.xfyun_tts.ws.close()
                except:
                    pass

        super().closeEvent(event)

    class TTSWorker(QObject):
        """TTS 工作线程"""
        tts_finished = pyqtSignal(bytes)
        tts_error = pyqtSignal(str)
        finished = pyqtSignal()

        def __init__(self, tts_client, text, max_retries=3):
            super().__init__()
            self.tts_client = tts_client
            self.text = text
            self.max_retries = max_retries
            self._stop_requested = False
            self._lock = threading.Lock()

        def run_tts(self):
            """执行 TTS 转换"""
            retry_count = 0
            last_error = None

            while retry_count < self.max_retries and not self._stop_requested:
                try:
                    with self._lock:
                        if self._stop_requested:
                            return

                    audio_data = self.tts_client.text_to_speech(self.text)

                    with self._lock:
                        if not self._stop_requested and audio_data:
                            self.tts_finished.emit(audio_data)
                            return

                except Exception as e:
                    last_error = str(e)
                    retry_count += 1
                    time.sleep(1)

            # 所有重试都失败
            if not self._stop_requested:
                self.tts_error.emit(f"尝试 {self.max_retries} 次后失败: {last_error}")
            self.finished.emit()

        def stop(self):
            """停止 TTS 转换"""
            with self._lock:
                self._stop_requested = True
                if hasattr(self.tts_client, 'ws') and self.tts_client.ws:
                    try:
                        self.tts_client.ws.close()
                    except:
                        pass


class FavoritesDialog(QDialog):
    """收藏对话框"""
    open_favorite_signal = pyqtSignal(dict)

    def __init__(self, favorites, parent=None):
        super().__init__(parent)
        self.setWindowTitle("收藏列表")
        self.resize(400, 300)

        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        for favorite in favorites:
            self.list_widget.addItem(f"{favorite['book']} - {favorite['document']} - {favorite['position']}")

        self.open_button = QPushButton("打开选中项")
        self.open_button.clicked.connect(self.open_selected_favorite)
        layout.addWidget(self.open_button)

    def open_selected_favorite(self):
        """打开选中的收藏项"""
        selected_item = self.list_widget.currentItem()
        if selected_item:
            favorite_info = self.get_favorite_info(selected_item.text())
            self.open_favorite_signal.emit(favorite_info)
            self.hide()

    def get_favorite_info(self, item_text):
        """从文本中获取收藏信息"""
        parts = item_text.split(" - ")
        if len(parts) == 3:
            return {
                "book": parts[0],
                "document": parts[1],
                "position": parts[2]
            }
        else:
            return {}


def main():
    """主函数"""
    app = QApplication(sys.argv)
    window = EpubReader()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()