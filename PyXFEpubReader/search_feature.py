from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLineEdit, QPushButton,
                             QListWidget, QLabel, QListWidgetItem, QHBoxLayout,
                             QTextEdit, QSplitter, QApplication)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont
import os
import re
from bs4 import BeautifulSoup

class SearchDialog(QDialog):
    def __init__(self, epub_reader, parent=None):
        """初始化搜索对话框"""
        super().__init__(parent)
        self.epub_reader = epub_reader
        self.setWindowTitle("全文搜索")
        self.resize(1000, 700)

        layout = QVBoxLayout()
        self.setLayout(layout)

        # 搜索框布局
        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("输入搜索关键词...")
        self.search_edit.returnPressed.connect(self.do_search)
        search_layout.addWidget(self.search_edit)

        self.search_btn = QPushButton("搜索")
        self.search_btn.clicked.connect(self.do_search)
        search_layout.addWidget(self.search_btn)

        layout.addLayout(search_layout)

        # 使用分割器显示结果和预览
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.splitter)

        # 结果列表
        self.results_list = QListWidget()
        self.results_list.itemSelectionChanged.connect(self.show_preview)
        self.results_list.itemDoubleClicked.connect(self.go_to_result)
        self.splitter.addWidget(self.results_list)

        # 预览面板
        self.preview_pane = QTextEdit()
        self.preview_pane.setReadOnly(True)
        self.preview_pane.setFont(QFont("Microsoft YaHei", 10))
        self.splitter.addWidget(self.preview_pane)

        # 状态标签
        self.status_label = QLabel("准备搜索")
        layout.addWidget(self.status_label)

        # 存储搜索结果
        self.search_results = []
        self.current_html_content = ""

        # 设置分割器初始比例
        self.splitter.setSizes([300, 700])

    def do_search(self):
        """执行搜索操作"""
        keyword = self.search_edit.text().strip()
        if not keyword:
            self.status_label.setText("错误: 请输入搜索关键词")
            return

        self.results_list.clear()
        self.preview_pane.clear()
        self.status_label.setText(f"正在搜索: {keyword}...")
        QApplication.processEvents()

        self.search_results = []

        # 获取当前书籍的所有HTML文件
        html_files = []
        for row in range(self.epub_reader.table_widget.rowCount()):
            item = self.epub_reader.table_widget.item(row, 0)
            if item:
                html_files.append(item.text())

        # 搜索每个文件
        results = []
        for file_name in html_files:
            file_path = os.path.join(self.epub_reader.html_path_name, file_name)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    soup = BeautifulSoup(content, 'html.parser')
                    text_content = soup.get_text()

                    # 使用正则表达式查找所有匹配项
                    matches = re.finditer(re.escape(keyword), text_content, re.IGNORECASE)

                    for match in matches:
                        start_pos = match.start()
                        end_pos = match.end()

                        # 获取上下文片段
                        context_start = max(0, start_pos - 100)
                        context_end = min(len(text_content), end_pos + 100)
                        snippet = text_content[context_start:context_end]

                        # 高亮关键词
                        highlighted_snippet = (
                                snippet[:start_pos - context_start] +
                                f"<span style='background-color:yellow;font-weight:bold;'>{snippet[start_pos - context_start:end_pos - context_start]}</span>" +
                                snippet[end_pos - context_start:]
                        )

                        # 存储结果信息
                        result_info = {
                            'file_name': file_name,
                            'file_path': file_path,
                            'content': content,
                            'text_content': text_content,
                            'keyword': keyword,
                            'keyword_position': start_pos,
                            'keyword_length': len(keyword),
                            'snippet': highlighted_snippet,
                            'full_snippet': snippet
                        }
                        results.append(result_info)
                        self.search_results.append(result_info)

            except Exception as e:
                print(f"Error reading {file_path}: {e}")

        # 显示结果
        if not results:
            self.status_label.setText(f"未找到包含'{keyword}'的结果")
            return

        self.status_label.setText(f"找到{len(results)}个结果")

        for i, result in enumerate(results):
            # 显示更友好的结果条目
            short_name = os.path.splitext(result['file_name'])[0]
            item_text = f"{short_name}: {result['full_snippet'].strip()}"

            item = QListWidgetItem(item_text)
            item.setToolTip(f"在 {result['file_name']} 中找到匹配")
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.results_list.addItem(item)

    def show_preview(self):
        """显示选中结果的预览"""
        current_item = self.results_list.currentItem()
        if not current_item:
            return

        result_index = current_item.data(Qt.ItemDataRole.UserRole)
        if 0 <= result_index < len(self.search_results):
            result = self.search_results[result_index]

            # 显示带格式的预览
            preview_html = f"""
            <div style='font-family:Microsoft YaHei; font-size:12pt;'>
                <h3>{result['file_name']}</h3>
                <p>位置: 约 {result['keyword_position']} 字符处</p>
                <hr>
                <div style='margin:10px;'>{result['snippet']}</div>
            </div>
            """
            self.preview_pane.setHtml(preview_html)

    def go_to_result(self, item):
        """跳转到选中结果的位置"""
        result_index = item.data(Qt.ItemDataRole.UserRole)
        if 0 <= result_index < len(self.search_results):
            result = self.search_results[result_index]

            # 在表格中找到并选中对应的文件
            for row in range(self.epub_reader.table_widget.rowCount()):
                if self.epub_reader.table_widget.item(row, 0).text() == result['file_name']:
                    self.epub_reader.table_widget.selectRow(row)
                    self.epub_reader.render_selected_file(self.epub_reader.table_widget.item(row, 0))

                    # 等待渲染完成
                    QApplication.processEvents()

                    # 定位到关键词
                    self.scroll_to_keyword(result['text_content'],
                                           result['keyword_position'],
                                           result['keyword_length'])
                    break
        self.close()

    def scroll_to_keyword(self, text_content, keyword_pos, keyword_len):
        """滚动到关键词位置并高亮显示"""
        text_browser = self.epub_reader.text_browser

        # 清除之前的高亮
        self.clear_highlights()

        # 设置搜索光标
        cursor = text_browser.textCursor()
        cursor.setPosition(0)
        text_browser.setTextCursor(cursor)

        # 查找关键词
        keyword = text_content[keyword_pos:keyword_pos + keyword_len]
        found = text_browser.find(keyword)

        if found:
            # 高亮所有匹配项
            self.highlight_all_matches(text_browser.toPlainText(), keyword)

            # 确保当前匹配项可见
            cursor = text_browser.textCursor()
            text_browser.setTextCursor(cursor)
            text_browser.ensureCursorVisible()

            # 额外高亮当前匹配项
            self.highlight_current_match(cursor)

    def highlight_all_matches(self, content, keyword):
        """高亮文档中所有匹配的关键词"""
        format = QTextCharFormat()
        format.setBackground(QColor(255, 255, 150))  # 浅黄色背景

        cursor = self.epub_reader.text_browser.textCursor()
        cursor.setPosition(0)

        while True:
            cursor = self.epub_reader.text_browser.document().find(keyword, cursor)
            if cursor.isNull():
                break

            cursor.mergeCharFormat(format)

    def highlight_current_match(self, cursor):
        """高亮当前匹配的关键词"""
        format = QTextCharFormat()
        format.setBackground(QColor(255, 255, 0))  # 更亮的黄色
        format.setFontWeight(QFont.Weight.Bold)

        cursor.mergeCharFormat(format)

    def clear_highlights(self):
        """清除所有高亮"""
        cursor = self.epub_reader.text_browser.textCursor()
        cursor.setPosition(0)
        cursor.movePosition(QTextCursor.MoveOperation.End,
                            QTextCursor.MoveMode.KeepAnchor)

        format = QTextCharFormat()
        format.setBackground(QColor(255, 255, 255))  # 白色背景

        cursor.mergeCharFormat(format)