import json
import os
import sys
from datetime import datetime

# 禁用 Chromium GPU 合成器以节省显存（把 4060 Ti 显存留给《暗黑2：重制版》）
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu-compositing"

from PySide6.QtCore import QUrl, Signal, QObject, Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLabel, QSplitter, QMessageBox
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage, QWebEngineUrlRequestInterceptor
)


class AuthSignalBridge(QObject):
    """用于在底层网络拦截线程与主界面 UI 线程之间安全传递捕获到的凭证"""
    log_signal = Signal(str)
    token_captured_signal = Signal(dict)


class DD373RequestInterceptor(QWebEngineUrlRequestInterceptor):
    """底层网络请求拦截器：无感捕获 DD373 接口请求中的 Token 和关键 Header"""
    def __init__(self, bridge: AuthSignalBridge):
        super().__init__()
        self.bridge = bridge
        self.captured_headers = {}

    def interceptRequest(self, info):
        url = info.requestUrl().toString()
        # 仅监听 DD373 主域名及 API 域名的请求
        if "dd373.com" not in url:
            return

        # 过滤掉图片、CSS、JS 等静态资源，聚焦业务数据接口
        lower_url = url.lower()
        if any(lower_url.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".css", ".js", ".woff2", ".ico"]):
            return

        # 提取请求头（在 Qt6 中需通过 info.httpHeaders() 获取）
        headers_dict = {}
        try:
            raw_headers = info.httpHeaders()
            for k, v in raw_headers.items():
                key_str = bytes(k).decode("utf-8", errors="ignore")
                val_str = bytes(v).decode("utf-8", errors="ignore")
                headers_dict[key_str] = val_str
        except Exception:
            pass

        # 检查是否包含常见的鉴权 Header 字段
        auth_keys = [k for k in headers_dict.keys() if any(
            word in k.lower() for word in ["token", "auth", "sign", "session", "uid", "userid"]
        )]

        if auth_keys:
            extracted = {k: headers_dict[k] for k in auth_keys}
            # 如果捕获到了新的 Token 或凭证发生变化，通知界面更新并保存
            if extracted != self.captured_headers:
                self.captured_headers = extracted
                self.bridge.log_signal.emit(f"🎯 [捕获到关键鉴权 Header] 来源接口: {url[:75]}...")
                self.bridge.token_captured_signal.emit({
                    "headers": extracted,
                    "user_agent": headers_dict.get("User-Agent", ""),
                    "sample_api_url": url
                })


class DD373AuthTestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DD373 内嵌浏览器无感鉴权测试工具 (Win10)")
        self.resize(1380, 820)

        # 确保存储目录存在
        self.profile_dir = os.path.abspath("./storage/browser_profile")
        self.auth_save_path = os.path.abspath("./storage/dd373_auth_test.json")
        os.makedirs(self.profile_dir, exist_ok=True)

        # 存储实时捕获的凭证状态
        self.auth_state = {
            "updated_at": "",
            "user_agent": "",
            "auth_headers": {},
            "cookies": {},
            "cookie_string": ""
        }

        self.bridge = AuthSignalBridge()
        self.bridge.log_signal.connect(self.append_log)
        self.bridge.token_captured_signal.connect(self.on_headers_captured)

        self._init_ui()
        self._init_browser()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 顶部控制栏
        top_bar = QHBoxLayout()
        self.status_label = QLabel("🟡 状态：等待登录 DD373（请在左侧网页登录您的卖家账号）")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #d97706;")
        top_bar.addWidget(self.status_label)
        top_bar.addStretch()

        btn_reload = QPushButton("🔄 刷新网页 (触发续期)")
        btn_reload.clicked.connect(lambda: self.web_view.reload())
        top_bar.addWidget(btn_reload)

        btn_center = QPushButton("👤 跳转个人/卖家中心")
        btn_center.clicked.connect(lambda: self.web_view.setUrl(QUrl("https://dd373.com")))
        top_bar.addWidget(btn_center)

        btn_save = QPushButton("💾 手动导出凭证 JSON")
        btn_save.clicked.connect(self.save_auth_to_disk)
        top_bar.addWidget(btn_save)

        main_layout.addLayout(top_bar)

        # 左右分栏：左侧内嵌浏览器，右侧实时鉴权监控日志
        splitter = QSplitter(Qt.Horizontal)

        self.web_view = QWebEngineView()
        splitter.addWidget(self.web_view)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(QLabel("📡 实时捕获的鉴权凭证与监控日志："))
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet("font-family: Consolas, 'Microsoft YaHei'; font-size: 12px; background-color: #1e1e1e; color: #d4d4d4;")
        right_layout.addWidget(self.log_box)

        splitter.addWidget(right_panel)
        splitter.setSizes([900, 480])
        main_layout.addWidget(splitter)

    def _init_browser(self):
        # 1. 创建独立持久化 Profile（自动记住登录态，重启软件免重复扫码）
        self.profile = QWebEngineProfile("DD373_Merchant_Profile", self.web_view)
        self.profile.setPersistentStoragePath(self.profile_dir)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)

        # 记录当前浏览器的真实 User-Agent（后续 API 请求必须保持一致）
        self.auth_state["user_agent"] = self.profile.httpUserAgent()

        # 2. 挂载底层网络请求拦截器（捕获 Header Token）
        self.interceptor = DD373RequestInterceptor(self.bridge)
        self.profile.setUrlRequestInterceptor(self.interceptor)

        # 3. 挂载底层 Cookie 监听器（实时捕获所有 dd373.com 的 Cookie）
        self.cookie_store = self.profile.cookieStore()
        self.cookie_store.cookieAdded.connect(self.on_cookie_added)
        self.cookie_store.loadAllCookies()

        # 4. 绑定页面并加载 DD373 登录页
        web_page = QWebEnginePage(self.profile, self.web_view)
        self.web_view.setPage(web_page)
        self.append_log("🚀 内嵌 Chromium 引擎已启动，正在加载 DD373 登录页面...")
        self.web_view.setUrl(QUrl("https://dd373.com"))

    def on_cookie_added(self, cookie):
        domain = cookie.domain()
        if "dd373.com" in domain:
            name = bytes(cookie.name()).decode("utf-8", errors="ignore")
            value = bytes(cookie.value()).decode("utf-8", errors="ignore")
            self.auth_state["cookies"][name] = value
            # 拼接标准 Cookie 字符串
            self.auth_state["cookie_string"] = "; ".join(
                [f"{k}={v}" for k, v in self.auth_state["cookies"].items()]
            )

    def on_headers_captured(self, data: dict):
        self.auth_state["auth_headers"].update(data["headers"])
        if data.get("user_agent"):
            self.auth_state["user_agent"] = data["user_agent"]

        self.status_label.setText("🟢 状态：已成功捕获 DD373 登录凭证！(已自动保存至本地)")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #16a34a;")

        self.append_log(f"✅ 当前累计捕获关键 Header: {json.dumps(self.auth_state['auth_headers'], ensure_ascii=False)}")
        self.save_auth_to_disk(silent=True)

    def save_auth_to_disk(self, silent=False):
        self.auth_state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.auth_save_path, "w", encoding="utf-8") as f:
            json.dump(self.auth_state, f, ensure_ascii=False, indent=2)

        msg = f"💾 凭证已保存至: {self.auth_save_path} (包含 {len(self.auth_state['cookies'])} 个 Cookie, {len(self.auth_state['auth_headers'])} 个鉴权 Header)"
        self.append_log(msg)
        if not silent:
            QMessageBox.information(self, "导出成功", msg)

    def append_log(self, text: str):
        now = datetime.now().strftime("%H:%M:%S")
        self.log_box.append(f"[{now}] {text}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DD373AuthTestWindow()
    window.show()
    sys.exit(app.exec())
