import glob
import os
import re
import time
from uuid import uuid4

import allure
import pytest
from dotenv import load_dotenv

from DrissionPage import Chromium, ChromiumOptions
from DrissionPage.common import Settings

from core.android_driver import Android
from core.res_pool import AndroidPool, BrowserPool

LOCAL_BROWSER_PATH = r'C:\papp\uc\chrome.exe'
LOCAL_DEVICE_NAME = '192.168.137.219:46643'
LOCAL_APPIUM_SERVER = 'http://localhost:4723'

# ---- 录屏：remote-chrome 容器内 ffmpeg 抓取 :99，mp4 经共享卷回到 agent ----
# key: 浏览器池里的 host；value: 该容器在 jenkins-node 上的共享卷路径
CHROME_REC_DIRS = {
    'remote-chrome-1': '/shared/chrome1/rec',
    'remote-chrome-2': '/shared/chrome2/rec',
}
# CDP 的 Host 检查只认 IP/localhost（反 DNS-rebinding），hostname 直连会被 500 拒绝。
# jenkins-node 镜像用 socat 把 remote-chrome 的 CDP 转发到本机固定端口：
# remote-chrome-1 -> 127.0.0.1:9223，remote-chrome-2 -> 127.0.0.1:9224
CHROME_LOCAL_PORTS = {
    'remote-chrome-1': 9223,
    'remote-chrome-2': 9224,
}
REC_CLEANUP_DAYS = 7   # 共享卷里 mp4 保留天数
REC_STOP_TIMEOUT = 60  # 等 ffmpeg 收尾的最长秒数

_current_chrome_host = None  # browser fixture 申请到哪个 chrome，录屏就录哪个


def _sanitize_name(text: str) -> str:
    return re.sub(r'[^A-Za-z0-9_.-]', '_', text)[:80]


def _rec_cleanup_old(rec_dir: str):
    """清理过期的 mp4/done 文件，防止共享卷被录屏撑爆"""
    cutoff = time.time() - REC_CLEANUP_DAYS * 86400
    for p in glob.glob(os.path.join(rec_dir, '*.mp4')) + glob.glob(os.path.join(rec_dir, '*.done')):
        try:
            if os.path.getmtime(p) < cutoff:
                os.remove(p)
        except OSError:
            pass


def _rec_start(rec_dir: str, name: str):
    os.makedirs(rec_dir, exist_ok=True)
    _rec_cleanup_old(rec_dir)
    with open(os.path.join(rec_dir, 'start'), 'w', encoding='utf-8') as f:
        f.write(name)


def _rec_stop(rec_dir: str, name: str) -> str | None:
    """写 stop 标记并等 ffmpeg 收尾（容器侧会写 <name>.done）。返回 mp4 路径或 None。"""
    with open(os.path.join(rec_dir, 'stop'), 'w', encoding='utf-8') as f:
        f.write(name)
    mp4 = os.path.join(rec_dir, f'{name}.mp4')
    done = f'{mp4}.done'
    deadline = time.time() + REC_STOP_TIMEOUT
    while time.time() < deadline:
        if os.path.exists(done):
            break
        time.sleep(0.5)
    return mp4 if os.path.exists(mp4) else None


def pytest_addoption(parser):
    parser.addoption(
        '--local',
        action='store_true',
        default=False,
        help='本地调试模式：使用本地浏览器，跳过资源池申请',
    )


def pytest_configure(config):
    """按 --local 加载对应的 env 文件（此时参数已解析）"""
    env_file = '.local_env' if config.getoption('--local') else '.remote_env'
    if not load_dotenv(env_file):
        raise SystemExit(f'缺少环境配置文件: {env_file}')



@pytest.fixture(scope='session')
def android(request):
    """全局单例 Android（Appium driver）。

    非 --local（默认）：从资源池申请远程安卓设备，会话结束后 quit driver 并释放回池；
    --local：直接用本地 LOCAL_DEVICE_NAME + LOCAL_APPIUM_SERVER，不碰资源池。
    只有测试用例声明了 android 参数才会创建，不需要的用例不受影响。
    """
    local = request.config.getoption('--local')

    if local:
        device = Android(LOCAL_DEVICE_NAME, LOCAL_APPIUM_SERVER)
        try:
            yield device
        finally:
            device.quit()
        return

    pool = AndroidPool()
    res = pool.acquire_android()  # 没有空闲设备时每 10s 重试直到有
    try:
        device = Android(res['devicename'], res['appiumserver'])
    except Exception:
        pool.release_android(res['devicename'])  # 锁到了设备但连接失败也要归还，避免设备被锁死
        raise
    try:
        yield device
    finally:
        try:
            device.quit()  # 结束 Appium 会话，归还前不留孤儿 session
        finally:
            pool.release_android(res['devicename'])


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

    global _current_chrome_host

    local = request.config.getoption('--local')

    if local:
        _current_chrome_host = None
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
        _current_chrome_host = res['host']
        local_port = CHROME_LOCAL_PORTS.get(res['host'], res['port'])
        co = (
            ChromiumOptions()
            .set_address(f'127.0.0.1:{local_port}')
            .headless(False)
            .set_argument('--window-size', '1920,1080')
        )
        browser = Chromium(co)
        try:
            yield browser
        finally:
            pool.release_browser(res['host'], res['port'])


@pytest.fixture(autouse=True)
def screen_record(request):
    """每个用例录屏：用例开始前通过控制文件启动 remote-chrome 里的 ffmpeg，
    结束后停录并把 mp4 作为 allure 附件挂到该用例。

    以下情况自动跳过：
    - 本地调试（--local）
    - 当前用例没声明 browser（不用浏览器就不录）
    - 共享卷没挂到 jenkins-node（比如本机直连远程池调试）
    """
    if request.config.getoption('--local'):
        yield
        return
    if 'browser' not in request.fixturenames or _current_chrome_host is None:
        yield
        return

    rec_dir = CHROME_REC_DIRS.get(_current_chrome_host)
    if not rec_dir or not os.path.isdir(rec_dir):
        yield  # 共享卷不可用，跳过录屏，不影响测试
        return

    name = f"{_sanitize_name(request.node.name)}-{uuid4().hex[:6]}"
    _rec_start(rec_dir, name)

    # 等 ffmpeg 真正开始写文件（最多 5s），避免漏掉用例开头
    mp4 = os.path.join(rec_dir, f'{name}.mp4')
    deadline = time.time() + 5
    while not os.path.exists(mp4) and time.time() < deadline:
        time.sleep(0.3)

    try:
        yield
    finally:
        mp4 = _rec_stop(rec_dir, name)
        if mp4 and os.path.getsize(mp4) > 0:
            allure.attach.file(
                mp4,
                name=f'录屏-{request.node.name}',
                attachment_type=allure.attachment_type.MP4,
            )
