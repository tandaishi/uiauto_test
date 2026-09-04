"""Appium Android 驱动封装。

负责按设备地址 + Appium server 建立 uiautomator2 会话，
并提供设备级操作（停 app、清数据、退出会话）。
"""

import shlex
import subprocess

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.webdriver import WebDriver


class Android:
    """一台安卓设备上的 Appium 会话（uiautomator2）。

    用法：
        device = Android('192.168.137.219:45067', 'http://localhost:4723')
        device.stop_app('com.demo.app')   # adb am force-stop
        device.clear('com.demo.app')      # adb pm clear（清数据 = 全新状态）
        device.driver.find_element(...)
        device.quit()
    """

    def __init__(self, device_name: str, appium_server: str):
        capabilities = dict(
            platformName='Android',
            automationName='uiautomator2',
            deviceName=device_name,
            language='zh',
            locale='CN',
            noReset=True,
        )
        self.device_name = device_name
        self.appium_server = appium_server
        self.driver: WebDriver = webdriver.Remote(
            appium_server,
            options=UiAutomator2Options().load_capabilities(capabilities),
        )

    def stop_app(self, package_name: str):
        """强制停掉 app（走宿主机 adb：am force-stop）"""
        subprocess.run(
            shlex.split(f'adb -s {self.device_name} shell am force-stop {package_name}'),
            check=True,
        )

    def clear(self, package_name: str):
        """清空 app 数据，下次启动是全新状态（走宿主机 adb：pm clear，也会停掉 app 进程）"""
        subprocess.run(
            shlex.split(f'adb -s {self.device_name} shell pm clear {package_name}'),
            check=True,
        )

    def quit(self):
        """结束 Appium 会话，断开与设备的 driver 连接"""
        self.driver.quit()
