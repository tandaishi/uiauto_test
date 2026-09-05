import pytest
from views.login_view import LoginView

from core.res_pool import AccountPool
from core.logger import logger


@pytest.fixture
def account():
    """setup：申请账号；teardown：无论测试成功失败都释放"""
    pool = AccountPool()
    acc = pool.acquire_account_by_role('teacher')
    yield acc
    pool.release_account_by_username(acc['username'])


def test_app_teacher_login(android, account):
    """从干净状态登录：先停掉 app、清掉数据，再走正常登录流程"""
    android.stop_app('com.demo.app')
    android.clear('com.demo.app')

    view = LoginView(android.driver)
    view.login(account['username'], account['password'])

    greet = view.get_greet_content().text
    logger.info(f'欢迎语：{greet}')
    assert account['username'] in greet
    assert 'teacher' in greet
