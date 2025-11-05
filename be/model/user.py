import jwt
import time
import logging
import pymongo
from be.model import error
from be.model import db_conn


def jwt_encode(user_id: str, terminal: str) -> str:
    """
    生成 JWT 字符串。
    负载包含：user_id、terminal、timestamp。
    注意：这里使用 user_id 作为对称密钥，仅供示例；生产环境应使用独立的服务端密钥。
    """
    encoded = jwt.encode(
        {"user_id": user_id, "terminal": terminal, "timestamp": time.time()},
        key=user_id,
        algorithm="HS256",
    )
    # 统一返回 str（pyjwt 在不同版本可能返回 bytes/str）
    return encoded.encode("utf-8").decode("utf-8")


def jwt_decode(encoded_token, user_id: str):
    """
    解码并验证 JWT。
    使用 user_id 作为密钥进行 HS256 验签。
    返回解码后的 payload（dict）。
    """
    decoded = jwt.decode(encoded_token, key=user_id, algorithms="HS256")
    return decoded


class User(db_conn.DBConn):
    # 令牌有效期（秒）
    token_lifetime: int = 3600

    def __init__(self):
        # 初始化数据库连接
        db_conn.DBConn.__init__(self)

    def __check_token(self, user_id, db_token, token) -> bool:
        """
        与数据库中 token 对比并校验有效期。
        仅当：
          1) 明文相等；
          2) JWT 验签通过；
          3) 含有效 timestamp 且未过期；
        才判定为有效。
        """
        try:
            # 快速失败：明文不一致直接判无效
            if db_token != token:
                return False

            # 解析并校验签名与时间
            jwt_text = jwt_decode(encoded_token=token, user_id=user_id)
            ts = jwt_text.get("timestamp")
            if ts is None:
                return False

            now = time.time()
            if now - ts <= self.token_lifetime:
                return True
        except jwt.exceptions.InvalidSignatureError as e:
            # 验签失败
            logging.error(str(e))

        return False

    def register(self, user_id: str, password: str):
        """
        注册用户：
          - user_id 唯一；
          - 初始余额 0；
          - 生成首个 token/terminal。
        """
        try:
            # 检查是否已存在同名用户
            existing_user = self.conn['user'].find_one({"user_id": user_id})
            if existing_user:
                return error.error_exist_user_id(user_id)

            terminal = "terminal_{}".format(str(time.time()))
            token = jwt_encode(user_id, terminal)
            user_doc = {
                "user_id": user_id,
                "password": password,
                "balance": 0,
                "token": token,
                "terminal": terminal
            }
            self.conn['user'].insert_one(user_doc)
            return 200, "ok"
        except pymongo.errors.PyMongoError as e:
            return 528, str(e)

    def check_token(self, user_id: str, token: str) -> (int, str):
        """
        校验用户 token。
        成功返回 200；失败返回鉴权错误。
        """
        user = self.conn['user'].find_one({'user_id': user_id})
        if user is None:
            return error.error_authorization_fail()

        db_token = user.get('token', '')
        is_token_valid = self.__check_token(user_id, db_token, token)
        if not is_token_valid:
            return error.error_authorization_fail()

        return 200, "ok"

    def check_password(self, user_id: str, password: str) -> (int, str):
        """
        校验用户密码（仅取 password 字段，避免多余字段传输）。
        """
        try:
            user = self.conn['user'].find_one({'user_id': user_id}, {'_id': 0, 'password': 1})
            if user is None:
                return error.error_authorization_fail()

            if user.get('password') != password:
                return error.error_authorization_fail()

        except pymongo.errors.PyMongoError as e:
            return 528, str(e)

        return 200, "ok"

    def login(self, user_id: str, password: str, terminal: str) -> (int, str, str):
        """
        登录并刷新 token/terminal。
        成功：返回 (200, "ok", token)
        """
        try:
            code, message = self.check_password(user_id, password)
            if code != 200:
                return code, message, ""

            # 使用登录时提供的 terminal 生成新 token
            token = jwt_encode(user_id, terminal)
            result = self.conn['user'].update_one(
                {'user_id': user_id},
                {'$set': {'token': token, 'terminal': terminal}}
            )
            if not result.matched_count:
                return error.error_authorization_fail()
        except pymongo.errors.PyMongoError as e:
            return 528, str(e), ""
        except Exception as e:
            return 530, str(e), ""
        return 200, "ok", token

    def logout(self, user_id: str, token: str):
        """
        登出：
          - 校验现有 token；
          - 颁发并写入一个新的“无意义”token，使旧 token 失效。
        """
        try:
            code, message = self.check_token(user_id, token)
            if code != 200:
                return code, message

            # 通过更换 terminal + token 的方式使旧 token 失效
            terminal = "terminal_{}".format(str(time.time()))
            dummy_token = jwt_encode(user_id, terminal)

            result = self.conn['user'].update_one(
                {'user_id': user_id},
                {'$set': {'token': dummy_token, 'terminal': terminal}}
            )
            if not result.matched_count:
                return error.error_authorization_fail()
        except pymongo.errors.PyMongoError as e:
            return 528, str(e)
        except Exception as e:
            return 530, str(e)
        return 200, "ok"

    def unregister(self, user_id: str, password: str) -> (int, str):
        """
        注销账号：
          - 需校验密码；
          - 成功后删除 user 文档。
        """
        try:
            code, message = self.check_password(user_id, password)
            if code != 200:
                return code, message

            result = self.conn['user'].delete_one({'user_id': user_id})
            # 期望只删除一条
            if result.deleted_count != 1:
                return error.error_authorization_fail()
        except pymongo.errors.PyMongoError as e:
            return 528, str(e)
        except Exception as e:
            return 530, str(e)
        return 200, "ok"

    def change_password(self, user_id: str, old_password: str, new_password: str) -> (int, str):
        """
        修改密码：
          - 校验旧密码；
          - 更新密码并同时刷新 token/terminal（旧 token 失效）。
        """
        try:
            code, message = self.check_password(user_id, old_password)
            if code != 200:
                return code, message

            terminal = "terminal_{}".format(str(time.time()))
            token = jwt_encode(user_id, terminal)
            self.conn['user'].update_one(
                {'user_id': user_id},
                {'$set': {
                    'password': new_password,
                    'token': token,
                    'terminal': terminal,
                }},
            )
        except pymongo.errors.PyMongoError as e:
            return 528, str(e)
        except Exception as e:
            return 530, str(e)
        return 200, "ok"

    ### 新功能：图书搜索 ###
    def search_book(self, title: str = '', content: str = '', tag: str = '', store_id: str = ''):
        """
        图书搜索（模糊匹配）。
        查询规则：
          - title -> books.title  使用 $regex
          - content -> books.content 使用 $regex
          - tag -> books.tags 使用 $regex
          - 可选：限定在某个 store_id 的在售图书范围内
            · 先从 store 集合查出该店铺所有 book_id
            · 用 $in 约束 books 集合的 id 字段
        返回：
          - 成功：200, "ok"
          - 未命中：529, "No matching books found."
          - 异常：528/530
        说明：
          - 此处使用的字段名 'id' 与常见 'book_id' 命名可能不一致，保持与现有集合结构一致。
          - 可根据实际数据模型做统一（TODO）。
        """
        try:
            query = {}

            if title:
                query['title'] = {"$regex": title}
            if content:
                query['content'] = {"$regex": content}
            if tag:
                query['tags'] = {"$regex": tag}

            # 限定店铺范围（可选）
            if store_id:
                # 从 store 集合中取出该店铺所有 book_id
                store_query = {"store_id": store_id}
                store_result = list(self.conn["store"].find(store_query))
                if len(store_result) == 0:
                    return error.error_non_exist_store_id(store_id)

                book_ids = [item["book_id"] for item in store_result]
                # 注意：此处使用 'id' 字段进行过滤，需与 books 集合字段保持一致
                query['id'] = {"$in": book_ids}

            # 执行查询
            results = list(self.conn["books"].find(query))

        except pymongo.errors.PyMongoError as e:
            return 528, str(e)
        except BaseException as e:
            return 530, "{}".format(str(e))

        if not results:
            return 529, "No matching books found."
        else:
            return 200, "ok"
