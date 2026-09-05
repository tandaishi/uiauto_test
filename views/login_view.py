"""Android 登录页 Page Object：com.demo.app 的登录 / 欢迎页。"""

from appium.webdriver.common.appiumby import AppiumBy
from appium.webdriver.webdriver import WebDriver

from core.logger import logger

_APP_PACKAGE = 'com.demo.app'


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
        

    def _by_resource_id(self, widget: str, res_id: str):
        """按 resource-id 定位元素（widget: EditText / Button / TextView）"""
        return self.driver.find_element(
            by=AppiumBy.XPATH,
            value=f'//android.widget.{widget}[@resource-id="{_APP_PACKAGE}:id/{res_id}"]',
        )

    def login(self, username: str, password: str):
        """把 app 切到前台、输入账号密码并提交登录"""
        logger.info(f'{username} 登录')
        self.driver.activate_app(_APP_PACKAGE)

        username_box = self._by_resource_id('EditText', 'et_username')
        username_box.clear()
        username_box.send_keys(username)

        password_box = self._by_resource_id('EditText', 'et_password')
        password_box.clear()
        password_box.send_keys(password)

        self._by_resource_id('Button', 'btn_login').click()

    def get_greet_content(self):
        """点开欢迎语并返回 tv_welcome 元素（调用方取 .text）"""
        logger.info('获取欢迎语')
        
        self._by_resource_id('Button', 'btn_show_welcome').click()
        return self._by_resource_id('TextView', 'tv_welcome')
        
