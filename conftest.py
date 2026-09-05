import glob
import os
import re
import shutil
import subprocess
import tempfile
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
LOCAL_DEVICE_NAME = '127.0.0.1:1040'
LOCAL_APPIUM_SERVER = 'http://localhost:1030'

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
REC_TAIL_SECONDS = 3   # 用例结束后多录的秒数：末尾画面（最后一步操作的结果/动画收尾）完整入镜

# ---- 录屏：android（guest 自带 screenrecord，conftest 经 adb 直连驱动）----
# 模拟器 headless 运行、镜像无 ffmpeg，录制由 guest 内 MediaCodec 完成；
# adb 是安卓用例本来就依赖的前提（Android.stop_app/clear 也走它），录屏不新增依赖。
ANDROID_REC_BIT_RATE = '4M'
ANDROID_REC_GUEST_DIR = '/data/local/tmp'

_current_chrome_host = None  # browser fixture 申请到哪个 chrome，录屏就录哪个


def _adb_run(serial: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(['adb', '-s', serial, *args], capture_output=True, text=True, timeout=60)


def _adb_connect_wait(serial: str, timeout: float = 90.0) -> None:
    """adb connect 并等设备状态为 device（首次调用会自动拉起 adb server）"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        subprocess.run(['adb', 'connect', serial], capture_output=True, text=True, timeout=15)
        r = _adb_run(serial, 'get-state')
        if r.returncode == 0 and r.stdout.strip() == 'device':
            return
        time.sleep(2)
    raise RuntimeError(f'adb 设备 {serial} 未就绪（get-state 非 device），请检查容器与网络')


def _android_rec_start(serial: str, name: str) -> subprocess.Popen:
    """用例开始：收掉残留 screenrecord → 清旧文件 → 后台启动 guest 录屏。"""
    _adb_run(serial, 'shell', 'pkill', '-INT', '-x', 'screenrecord')
    _adb_run(serial, 'shell', 'rm', '-f', f'{ANDROID_REC_GUEST_DIR}/{name}.mp4')
    return subprocess.Popen(
        ['adb', '-s', serial, 'shell', 'screenrecord', '--time-limit', '0',
         '--bit-rate', ANDROID_REC_BIT_RATE, f'{ANDROID_REC_GUEST_DIR}/{name}.mp4'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _android_rec_stop(serial: str, name: str, proc: subprocess.Popen | None = None) -> str | None:
    """用例结束：SIGINT 让 guest 收尾（写 moov）→ 等进程退出 → pull 回本地临时文件。

    返回本地 mp4 路径；失败返回 None（不留半截文件）。
    """
    guest = f'{ANDROID_REC_GUEST_DIR}/{name}.mp4'
    local = os.path.join(tempfile.gettempdir(), f'{name}.mp4')
    _adb_run(serial, 'shell', 'pkill', '-INT', '-x', 'screenrecord')
    deadline = time.time() + 15
    while time.time() < deadline:
        r = _adb_run(serial, 'shell', 'pgrep', '-x', 'screenrecord')
        if r.returncode != 0:  # pgrep 无匹配 = guest 进程已退出，文件已定型
            break
        time.sleep(0.5)
    if proc is not None:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    time.sleep(1)  # 等编码器 flush + moov 落盘
    r = _adb_run(serial, 'pull', guest, local)
    _adb_run(serial, 'shell', 'rm', '-f', guest)
    if r.returncode != 0:
        if os.path.exists(local):
            os.remove(local)
        return None
    return local if os.path.exists(local) else None


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

    非 --local（默认，jenkins agent）：从资源池申请远程安卓设备，
    先 adb connect 确保连通（stop_app/clear 与录屏都走 adb），
    会话结束后 quit driver 并释放回池；
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
    serial = res['devicename']
    try:
        if shutil.which('adb') is None:
            raise RuntimeError(
                '远程模式需要 adb（Android.stop_app/clear 与录屏都走宿主 adb）。'
                'jenkins-node 镜像需安装 platform-tools 并重建。'
            )
        _adb_connect_wait(serial)  # adb connect + 等 device 状态
        device = Android(serial, res['appiumserver'])
    except Exception:
        pool.release_android(serial)  # 锁到了设备但连接失败也要归还，避免设备被锁死
        raise
    try:
        yield device
    finally:
        try:
            device.quit()  # 结束 Appium 会话，归还前不留孤儿 session
        finally:
            pool.release_android(serial)


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
    """每个用例录屏，结束后把 mp4 作为 allure 附件挂到该用例。

    - browser/chrome：控制文件经共享卷驱动容器内 ffmpeg（x11grab）
    - android：adb 直连 guest 自带 screenrecord（模拟器 headless，镜像无 ffmpeg）

    仅远程模式录屏（--local 不录，与浏览器一致）。以下情况自动跳过：
    - 当前用例没声明 browser/android
    - 共享卷没挂到 jenkins-node / adb 不可用（录不了但不影响测试）
    """
    if request.config.getoption('--local'):
        yield
        return

    name = f"{_sanitize_name(request.node.name)}-{uuid4().hex[:6]}"

    # chrome：ffmpeg（容器内 x11grab），控制文件经共享卷
    chrome_dir = None
    if 'browser' in request.fixturenames and _current_chrome_host:
        d = CHROME_REC_DIRS.get(_current_chrome_host)
        if d and os.path.isdir(d):
            chrome_dir = d

    # android：guest screenrecord，adb 直连；getfixturevalue 保证在录屏前拿到设备
    android_serial = None
    if 'android' in request.fixturenames and shutil.which('adb') is not None:
        device = request.getfixturevalue('android')
        android_serial = device.device_name

    if not chrome_dir and not android_serial:
        yield
        return

    rec_proc = None
    if chrome_dir:
        _rec_start(chrome_dir, name)
        # 等 ffmpeg 真正开始写文件（最多 5s），避免漏掉用例开头
        mp4 = os.path.join(chrome_dir, f'{name}.mp4')
        deadline = time.time() + 5
        while not os.path.exists(mp4) and time.time() < deadline:
            time.sleep(0.3)
    if android_serial:
        rec_proc = _android_rec_start(android_serial, name)

    try:
        yield
    finally:
        # 用例已跑完但先别停：多录 REC_TAIL_SECONDS 秒再收尾，
        # 否则最后一步操作引起的页面切换/动画可能还没播完就被掐断，末尾画面一闪而过。
        time.sleep(REC_TAIL_SECONDS)
        if chrome_dir:
            mp4 = _rec_stop(chrome_dir, name)
            if mp4 and os.path.getsize(mp4) > 0:
                allure.attach.file(
                    mp4,
                    name=f'录屏-{request.node.name}',
                    attachment_type=allure.attachment_type.MP4,
                )
        if android_serial:
            local = _android_rec_stop(android_serial, name, rec_proc)
            if local and os.path.getsize(local) > 0:
                allure.attach.file(
                    local,
                    name=f'录屏-{request.node.name}',
                    attachment_type=allure.attachment_type.MP4,
                )
            if local:
                try:
                    os.remove(local)  # attach 已读完，清理临时文件
                except OSError:
                    pass
