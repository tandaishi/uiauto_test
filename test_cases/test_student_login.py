import pytest

from pages.login_page import LoginPage
from core.res_pool import AccountPool
from core.logger import logger

@pytest.fixture
def account():
    """setup：申请账号；teardown：无论测试成功失败都释放"""
    pool = AccountPool()
    acc = pool.acquire_account_by_role('student')
    yield acc
    pool.release_account_by_username(acc['username'])


def test_student_login(browser, account):
    page = LoginPage(browser)
    button_text = page.login(account['username'], account['password'])
    logger.info(button_text)
    assert '点击查看欢迎语' == button_text
    text = page.get_welcome_text()
    logger.info(f'welcome text: {text}')
    assert account['username'] in text
    assert 'student' in text



