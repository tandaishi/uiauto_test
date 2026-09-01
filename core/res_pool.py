import couchdb3
from couchdb3.exceptions import ConflictError
from uuid import uuid4
import time
from core.logger import logger

class AccountPool:
    """CouchDB 账号池：insert / acquire / release"""

    def __init__(self, url="http://admin:waf914@127.0.0.1:1005", dbname="accounts"):
        self.client = couchdb3.Server(url)
        self.db = (
            self.client.get(dbname)
            if dbname in self.client.all_dbs()
            else self.client.create(dbname)
        )

    def insert(self, username, password, role):
        """插入账号，username 已存在则跳过"""
        exists = self.db.find(selector={"username": username})
        if exists["docs"]:
            return
        doc = {
            '_id': str(uuid4()),
            'username': username,
            'password': password,
            'role': role,
            'is_locked': 'N',
        }
        self.db.save(doc)

    def acquire_account_by_role(self, role, wait=10):
        """申请一个指定角色且未锁定的账号并锁定。

        全部被占用时每 wait 秒重试（默认 10s），直到有账号释放才返回。
        并发申请时靠 _rev 冲突（ConflictError）兜底，不会重复拿同一个账号。
        """
        while True:
            docs = self.db.find(
                selector={"role": role, "is_locked": "N"},
                limit=1,
            )
            if not docs["docs"]:
                logger.info('no available account')
                time.sleep(wait)
                continue
            doc = docs["docs"][0]
            doc["is_locked"] = 'Y'
            try:
                self.db.save(doc)
            except ConflictError:
                # 并发申请时被别的进程抢先锁定，重新找一个
                continue
            return {"username": doc["username"], "password": doc["password"]}

    def release_account_by_username(self, username):
        """释放账号（解锁）"""
        docs = self.db.find(selector={"username": username})
        for doc in docs["docs"]:
            doc["is_locked"] = 'N'
            self.db.save(doc)

    def seed(self, accounts):
        """批量初始化账号"""
        for account in accounts:
            self.insert(account['username'], account['password'], account['role'])


class BrowserPool:
    """CouchDB 浏览器池：host+port 唯一，insert / acquire / release"""

    def __init__(self, url="http://admin:waf914@127.0.0.1:1005", dbname="browsers"):
        self.client = couchdb3.Server(url)
        self.db = (
            self.client.get(dbname)
            if dbname in self.client.all_dbs()
            else self.client.create(dbname)
        )

    def insert(self, host, port):
        """插入浏览器记录，host+port 已存在则跳过"""
        exists = self.db.find(selector={"host": host, "port": port})
        if exists["docs"]:
            return
        doc = {
            '_id': str(uuid4()),
            'host': host,
            'port': port,
            'is_locked': 'N',
        }
        self.db.save(doc)

    def acquire_browser(self, wait=10):
        """申请一个空闲浏览器并锁定。

        全部被占用时每 wait 秒重试（默认 10s），直到有浏览器释放才返回。
        """
        while True:
            docs = self.db.find(
                selector={"is_locked": "N"},
                limit=1,
            )
            if not docs["docs"]:
                logger.info('no available browser')
                time.sleep(wait)
                continue
            doc = docs["docs"][0]
            doc["is_locked"] = 'Y'
            try:
                self.db.save(doc)
            except ConflictError:
                # 并发申请时被别的进程抢先锁定，重新找一个
                continue
            return {"host": doc["host"], "port": doc["port"]}

    def release_browser(self, host, port):
        """释放浏览器（解锁）"""
        docs = self.db.find(selector={"host": host, "port": port})
        for doc in docs["docs"]:
            doc["is_locked"] = 'N'
            self.db.save(doc)

    def seed(self, browsers):
        """批量初始化浏览器"""
        for browser in browsers:
            self.insert(browser['host'], browser['port'])


if __name__ == '__main__':
    # account_pool = AccountPool()
    # init_accounts = [
    #     {'username': 'tan', 'password': 'tan123', 'role': 'teacher'},
    #     {'username': 'zhang', 'password': 'zhang123', 'role': 'teacher'},
    #     {'username': 'wang', 'password': 'wang123', 'role': 'teacher'},
    #     {'username': 'xiaohong', 'password': 'xiaohong123', 'role': 'student'},
    #     {'username': 'xiaoming', 'password': 'xiaoming123', 'role': 'student'},
    #     {'username': 'xiaoqiang', 'password': 'xiaoqiang123', 'role': 'student'},
    # ]
    # account_pool.seed(init_accounts)

    browser_pool = BrowserPool()
    init_browsers = [
        {'host':'localhost','port':'1010'},
        {'host':'localhost','port':'1011'}
    ]
    browser_pool.seed(init_browsers)