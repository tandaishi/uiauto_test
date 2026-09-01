import pytest

from DrissionPage import Chromium, ChromiumOptions
from DrissionPage.common import Settings

from core.res_pool import BrowserPool

LOCAL_BROWSER_PATH = r'C:\papp\uc\chrome.exe'
LOCAL_DOMIN_URL = 'http://localhost:1000'
REMOTE_DOMIN_URL = 'http://host.docker.internal:1000'


def pytest_addoption(parser):
    parser.addoption(
        '--local',
        action='store_true',
        default=False,
        help='本地调试模式：使用本地浏览器，跳过资源池申请',
    )



@pytest.fixture(scope='session')
def browser(request):
    """全局单例 browser。

    非 --local（默认）：从资源池申请远程浏览器，会话结束后释放回池；
    --local：直接用本地浏览器，不碰资源池。
    只有测试用例声明了 browser 参数才会创建，不需要浏览器的用例不受影响。
    """
    Settings.set_language('zh_cn')
    Settings.set_raise_when_click_failed(True)
    Settings.set_raise_when_ele_not_found(True)
    Settings.set_raise_when_wait_failed(True)

    local = request.config.getoption('--local')

    if local:
        co = (
            ChromiumOptions()
            .set_browser_path(LOCAL_BROWSER_PATH)
            .headless(False)
            .set_argument('--window-size', '1920,1080')
        )
        browser = Chromium(co)
        yield browser
    else:
        pool = BrowserPool()
        res = pool.acquire_browser()  # 没有空闲浏览器时会每 10s 重试直到有
        co = (
            ChromiumOptions()
            .set_address(f"{res['host']}:{res['port']}")
            .headless(False)
            .set_argument('--window-size', '1920,1080')
        )
        browser = Chromium(co)
        try:
            yield browser
        finally:
            pool.release_browser(res['host'], res['port'])


@pytest.fixture(scope='session')
def domin_url(request):
    """被测系统地址：--local 用本地，否则用远程"""
    if request.config.getoption('--local'):
        return LOCAL_DOMIN_URL
    return REMOTE_DOMIN_URL
