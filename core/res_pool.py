import os
import time
from uuid import uuid4

import couchdb3
from couchdb3.exceptions import ConflictError
from core.logger import logger

class AccountPool:
    """CouchDB 账号池：insert / acquire / release"""

    def __init__(self, url=None, dbname="accounts"):
        url = url or os.environ.get('COUCHDB_URL', 'http://admin:waf914@127.0.0.1:1005')
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

    def __init__(self, url=None, dbname="browsers"):
        url = url or os.environ.get('COUCHDB_URL', 'http://admin:waf914@127.0.0.1:1005')
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



class AndroidPool:
    """CouchDB 安卓设备池：insert / acquire / release

    记录字段：
        devicename:   'xxx.xxx.xxx.xxx:xxxx'   设备地址，全池唯一，作为释放依据
        appiumserver: 'http://xxx.xxx.x.xx:xxxx' Appium 服务地址
        is_locked:    'N' / 'Y'                是否被占用
    释放占用（release_android）和释放设备（remove_android）都以 devicename 为准。
    """

    def __init__(self, url=None, dbname="android_devices"):
        url = url or os.environ.get('COUCHDB_URL', 'http://admin:waf914@127.0.0.1:1005')
        self.client = couchdb3.Server(url)
        self.db = (
            self.client.get(dbname)
            if dbname in self.client.all_dbs()
            else self.client.create(dbname)
        )

    def insert(self, devicename, appiumserver):
        """插入设备记录，devicename 已存在则跳过"""
        exists = self.db.find(selector={"devicename": devicename})
        if exists["docs"]:
            return
        doc = {
            '_id': str(uuid4()),
            'devicename': devicename,
            'appiumserver': appiumserver,
            'is_locked': 'N',
        }
        self.db.save(doc)

    def acquire_android(self, wait=10):
        """申请一台空闲设备并锁定，返回 {'devicename': ..., 'appiumserver': ...}。

        全部被占用时每 wait 秒重试（默认 10s），直到有设备释放才返回。
        并发申请时靠 _rev 冲突（ConflictError）兜底，不会重复拿到同一台设备。
        """
        while True:
            docs = self.db.find(
                selector={"is_locked": "N"},
                limit=1,
            )
            if not docs["docs"]:
                logger.info('no available android device')
                time.sleep(wait)
                continue
            doc = docs["docs"][0]
            doc["is_locked"] = 'Y'
            try:
                self.db.save(doc)
            except ConflictError:
                # 并发申请时被别的进程抢先锁定，重新找一台
                continue
            return {"devicename": doc["devicename"], "appiumserver": doc["appiumserver"]}

    def release_android(self, devicename):
        """释放占用：把 devicename 对应记录的 is_locked 置回 'N'，归还池中"""
        docs = self.db.find(selector={"devicename": devicename})
        for doc in docs["docs"]:
            doc["is_locked"] = 'N'
            self.db.save(doc)

    def remove_android(self, devicename):
        """释放设备：删除 devicename 对应的整条记录，设备下线不再入池"""
        docs = self.db.find(selector={"devicename": devicename})
        for doc in docs["docs"]:
            self.db.delete(doc)

    def seed(self, devices):
        """批量初始化设备，每个元素为 {'devicename': ..., 'appiumserver': ...}"""
        for device in devices:
            self.insert(device['devicename'], device['appiumserver'])
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
        {'host':'remote-chrome-1','port':'9223'},
        {'host':'remote-chrome-2','port':'9223'}
    ]
    browser_pool.seed(init_browsers)