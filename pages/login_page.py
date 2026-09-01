import os

from DrissionPage.errors import WaitTimeoutError
from DrissionPage import Chromium
from core.logger import logger

class LoginPage:
    """登录页 Page Object，封装登录和欢迎页操作。

    用法：
        page = LoginPage(browser)
        page.login('tan', 'tan123')
        text = page.get_welcome_text()
    """

    def __init__(self, browser: Chromium):
        self.browser = browser
        self.tab = browser.latest_tab
        self.domin_url = os.environ['DOMIN_URL']

    def login(self, username, password):
        """打开登录页并提交登录"""
        logger.info(f'{username}登录')
        self.tab.get(self.domin_url)
        self.tab.wait(5) # 故意等待以演示效果
        self.tab.ele('#username').clear()
        self.tab.ele('#username').input(username)
        self.tab.ele('#password').clear()
        self.tab.ele('#password').input(password)
        self.tab.ele('@type=submit').click()
        self.tab.wait.ele_displayed('#welcome-btn')
        return self.tab.ele('#welcome-btn').text


    def get_welcome_text(self):
        """进入欢迎页并返回欢迎语文本"""
        logger.info('获取欢迎语文本')
        self.tab.ele('#welcome-btn').click()
        self.tab.wait(5) # 故意等待以演示效果
        self.tab.wait.ele_displayed('#welcome-msg')
        return self.tab.ele('#welcome-msg').text
