import pymongo
from be.model import error
from be.model import db_conn


class Seller(db_conn.DBConn):
    """卖家相关操作：创建店铺、上架图书、补充库存、发货等。"""

    def __init__(self):
        # 初始化数据库连接
        db_conn.DBConn.__init__(self)

    def add_book(
        self,
        user_id: str,
        store_id: str,
        book_id: str,
        book_json_str: str,
        stock_level: int,
    ):
        """
        上架新图书到指定店铺。
        前置校验：
          - 用户必须存在
          - 店铺必须存在
          - 同店铺下的 book_id 不能重复
        成功：向 store 集合写入一条图书记录。
        """
        try:
            # 基本校验
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id)
            if self.book_id_exist(store_id, book_id):
                return error.error_exist_book_id(book_id)

            # 组装并写入文档
            book_doc = {
                'store_id': store_id,
                'book_id': book_id,
                'book_info': book_json_str,  # 字符串形式存储的图书信息（JSON）
                'stock_level': stock_level,  # 初始库存
            }
            self.conn['store'].insert_one(book_doc)
        except pymongo.errors.PyMongoError as e:
            return 528, "{}".format(str(e))
        except BaseException as e:
            return 530, "{}".format(str(e))
        return 200, "ok"

    def add_stock_level(
        self, user_id: str, store_id: str, book_id: str, add_stock_level: int
    ):
        """
        为已上架图书增加库存。
        前置校验：
          - 用户存在
          - 店铺存在
          - 图书存在
        成功：对目标图书的 stock_level 做 $inc 增量更新。
        """
        try:
            # 基本校验
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id)
            if not self.book_id_exist(store_id, book_id):
                return error.error_non_exist_book_id(book_id)

            # 增加库存
            self.conn['store'].update_one(
                {'store_id': store_id, 'book_id': book_id},
                {'$inc': {'stock_level': add_stock_level}},
            )
        except pymongo.errors.PyMongoError as e:
            return 528, "{}".format(str(e))
        except BaseException as e:
            return 530, "{}".format(str(e))
        return 200, "ok"

    def create_store(self, user_id: str, store_id: str) -> (int, str):
        """
        创建店铺，绑定到指定用户。
        前置校验：
          - 用户存在
          - store_id 不可重复
        成功：在 user_store 集合插入一条店铺记录。
        """
        try:
            # 基本校验
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
            if self.store_id_exist(store_id):
                return error.error_exist_store_id(store_id)

            # 写入店铺文档
            user_store_doc = {
                'store_id': store_id,
                'user_id': user_id,
            }
            self.conn['user_store'].insert_one(user_store_doc)
        except pymongo.errors.PyMongoError as e:
            return 528, "{}".format(str(e))
        except BaseException as e:
            return 530, "{}".format(str(e))
        return 200, "ok"

    ### 新功能：商家发货 ###
    def ship_order(self, user_id: str, store_id: str, order_id: str) -> (int, str):
        """
        将订单状态从 paid 更新为 shipped。
        前置校验：
          - 用户存在
          - 店铺存在
          - 订单存在且状态为 paid
        成功：order_history.status -> 'shipped'
        """
        try:
            # 基本校验
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)
            if not self.store_id_exist(store_id):
                return error.error_exist_store_id(store_id)  # 注意：此处按原逻辑返回“已存在店铺”错误码

            # 查询订单
            order = self.conn['order_history'].find_one({'order_id': order_id})
            if not order:
                return 400, "Invalid order ID"
            if order['status'] != 'paid':
                return 400, "Order is not paid"

            # 更新状态为已发货
            self.conn['order_history'].update_one(
                {'order_id': order_id},
                {'$set': {'status': 'shipped'}},
            )
        except pymongo.errors.PyMongoError as e:
            return 528, "{}".format(str(e))
        return 200, "ok"
