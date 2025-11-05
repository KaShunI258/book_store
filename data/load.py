import os
import sqlite3
import pymongo


def load_books(Use_Large_DB: bool):
    """
    从本地 SQLite 文件加载图书数据并写入 MongoDB。
    """

    # 确定数据库路径
    db_file = './book_lx.db' if Use_Large_DB else './book.db'
    sqlite_path = os.path.join(os.path.dirname(__file__), db_file)

    # 建立 SQLite 连接
    with sqlite3.connect(sqlite_path) as sqlite_conn:
        cursor = sqlite_conn.cursor()

        # 连接 MongoDB
        mongo_uri = os.getenv('MONGODB_API')
        mongo_client = pymongo.MongoClient(
            mongo_uri, server_api=pymongo.server_api.ServerApi('1')
        )
        # mongo_client = pymongo.MongoClient('mongodb://localhost:27017')

        db = mongo_client['bookstore']

        # 如果集合已存在则清空，避免重复导入
        if 'books' in db.list_collection_names():
            db.drop_collection('books')
            print("Succeed to init collection 'books'.")

        # 从 SQLite 读取所有书籍信息
        cursor.execute("SELECT * FROM book")
        books_data = cursor.fetchall()

        # 写入 MongoDB
        for item in books_data:
            doc = {
                'id': item[0],
                'title': item[1],
                'author': item[2],
                'publisher': item[3],
                'original_title': item[4],
                'translator': item[5],
                'pub_year': item[6],
                'pages': item[7],
                'price': item[8],
                'currency_unit': item[9],
                'binding': item[10],
                'isbn': item[11],
                'author_intro': item[12],
                'book_intro': item[13],
                'content': item[14],
                'tags': item[15],
                'picture': item[16],
            }
            db['books'].insert_one(doc)

        # 关闭连接
        mongo_client.close()
