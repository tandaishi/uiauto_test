"""Android 登录页 Page Object：com.demo.app 的登录 / 欢迎页。"""

from appium.webdriver.common.appiumby import AppiumBy
from appium.webdriver.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from core.logger import logger

_APP_PACKAGE = 'com.demo.app'
_ELEMENT_TIMEOUT = 30  # 模拟器运行慢时，单次找元素/等元素可点的超时上限（秒）


class LoginView:
    """封装 com.demo.app 的登录与欢迎页操作。

    用法：
        view = LoginView(android.driver)
        view.login('tan', 'tan123')
        greet = view.get_greet_content()
        assert 'tan' in greet.text
    """

    def __init__(self, driver: WebDriver):
        self.driver = driver

    def login(self, username: str, password: str):
        """把 app 切到前台、输入账号密码并提交登录"""
        logger.info(f'{username} 登录')
        self.driver.activate_app(_APP_PACKAGE)

        username_box = WebDriverWait(self.driver, _ELEMENT_TIMEOUT).until(EC.presence_of_element_located((AppiumBy.XPATH, '//android.widget.EditText[@resource-id="com.demo.app:id/et_username"]')))
        username_box.clear()
        username_box.send_keys(username)

        password_box = WebDriverWait(self.driver, _ELEMENT_TIMEOUT).until(EC.presence_of_element_located((AppiumBy.XPATH, '//android.widget.EditText[@resource-id="com.demo.app:id/et_password"]')))
        password_box.clear()
        password_box.send_keys(password)

        WebDriverWait(self.driver, _ELEMENT_TIMEOUT).until(EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.Button[@resource-id="com.demo.app:id/btn_login"]'))).click()

    def get_greet_content(self):
        """点开欢迎语并返回 tv_welcome 元素（调用方取 .text）"""
        logger.info('获取欢迎语')

        WebDriverWait(self.driver, _ELEMENT_TIMEOUT).until(EC.element_to_be_clickable((AppiumBy.XPATH, '//android.widget.Button[@resource-id="com.demo.app:id/btn_show_welcome"]'))).click()
        return WebDriverWait(self.driver, _ELEMENT_TIMEOUT).until(EC.presence_of_element_located((AppiumBy.XPATH, '//android.widget.TextView[@resource-id="com.demo.app:id/tv_welcome"]')))
