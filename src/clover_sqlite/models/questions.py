from lazy_object_proxy.utils import await_
from tortoise import fields
from src.clover_sqlite.data_init.db_connect import Model


class Question(Model):
    id = fields.IntField(primary_key=True, generated=True)
    question = fields.CharField(max_length=155, description="问题")
    answer = fields.CharField(max_length=400,description="回答")

    class Meta:
        table = "question"
        table_description = "问答表"

    @classmethod
    async def _fetch_data(cls) -> list:
        return await cls.all().order_by("id").values_list("id", "question", "answer")

    @classmethod
    async def _get_data_by_id(cls, get_id: int | None) -> list | None:
        """
        通过id获取问答内容
        """
        if not get_id:
            return None
        else:
            return await cls.filter(id=get_id).order_by("id").values_list("id", "question", "answer")

    @classmethod
    async def _get_data_by_ques_keyword_exact(cls, keyword: str | None) -> list | None:
        """
        通过关键字精确地获取问题内容
        """
        if not keyword:
            return None
        else:
            return await cls.filter(question__icontains=keyword).order_by("id").values_list("id", "question", "answer")

    @classmethod
    async def _get_data_by_ques_keyword_fuzzy(cls, keyword: str | None) -> list | None:
        """
        通过关键字模糊匹配问题内容
        """
        if not keyword:
            return None
        else:
            key_list = list(keyword)

            result = cls.filter(question__icontains=key_list[0])
            for key in key_list:
                result = result.filter(question__icontains=key)
            return await result.order_by("id").values_list("id", "question", "answer")

    @classmethod
    async def _get_data_by_ans_keyword_exact(cls, keyword: str | None) -> list | None:
        """
        通过关键字精确地获取回答内容
        """
        if not keyword:
            return None
        else:
            return await cls.filter(answer__icontains=keyword).order_by("id").values_list("id", "question", "answer")

    @classmethod
    async def _get_data_by_ans_keyword_fuzzy(cls, keyword: str | None) -> list | None:
        """
        通过关键字模糊匹配回答内容
        """
        if not keyword:
            return None
        else:
            key_list = list(keyword)

            result = cls.filter(answer__icontains=key_list[0])
            for key in key_list:
                result = result.filter(answer__icontains=key)
            return await result.order_by("id").values_list("id", "question", "answer")

    @classmethod
    async def _insert_data(cls,
                           question: str | None,
                           answer: str | None) -> bool:

        data = {
            "question": question,
            "answer": answer
        }

        if await cls.create(**data):
            return True
        else:
            return False

    @classmethod
    async def _delete_data(cls, del_id: int | None) -> bool:
        if del_id is None:
            return False

        if await cls.filter(id=del_id).delete():
            return True
        else:
            return False

    @classmethod
    async def _alter_data(cls,
                          alter_id: int | None,
                          question: str | None,
                          answer: str | None) -> bool:

        updated_count = cls.filter(id=alter_id).update(
            question=question,
            answer=answer
        )

        print(f"更新了{updated_count}条数据")
        return True

    @classmethod
    async def fetch(cls) -> list:
        """
        获取数据库中question表中所有数据内容
        """
        return await cls._fetch_data()

    @classmethod
    async def search(cls,
                     keyword,
                     via_id: bool = False,
                     via_question: bool = False,
                     via_ans: bool = False,
                     fuzzy: bool = False) -> list | None:
        """
        搜索数据库中question表的数据，可以选择不同种搜索方式

        :param keyword: [int/str]传入的搜索关键字
        :param via_id: [bool](可选) 通过id搜索，不可与fuzzy一起使用
        :param via_question: [bool](可选) 通过问题搜索
        :param via_ans: [bool](可选) 通过回答搜索
        :param fuzzy: [bool](可选) 是否启用模糊搜索，当via_id为True时此参数不可为True
        """
        if (via_id and via_ans and via_question is False) or (fuzzy and via_id is True):
            print("不合法传参")
            return None

        if via_id:
            return await cls._get_data_by_id(keyword)
        elif via_question:
            if fuzzy:
                return await cls._get_data_by_ques_keyword_fuzzy(keyword)
            else:
                return await cls._get_data_by_ques_keyword_exact(keyword)
        elif via_ans:
            if fuzzy:
                return await cls._get_data_by_ans_keyword_fuzzy(keyword)
            else:
                return await cls._get_data_by_ans_keyword_exact(keyword)
        return None

    @classmethod
    async def update(cls, update_id, question, answer) -> bool:
        """
        更新数据库中question表的某一元素

        :param update_id: [int]需要更新的元素id
        :param question: [str]该元素更新后的问题字段内容
        :param answer: [str]该元素更新后的回答字段内容
        """
        return await cls._alter_data(update_id, question, answer)

    @classmethod
    async def delete_one(cls, delete_id) -> bool:
        """
        删除数据库中question表的某一元素

        :param delete_id: [int]需要删除元素的id
        """
        return await cls._delete_data(delete_id)

    @classmethod
    async def delete_many(cls, delete_id_list: list | None) -> bool:
        """
        批量删除数据库中question表的元素

        :param delete_id_list: [list]一个包括所有需要删除的元素的id的列表
        """
        for delete_id in delete_id_list:
            await cls._delete_data(delete_id)

        return True

    @classmethod
    async def insert_one(cls,
                         question: str | None,
                         answer: str | None) -> bool:
        """
        向数据库中的question表中插入一个元素

        :param question: 该元素的问题字段内容
        :param answer: 该元素的回答字段内容
        """
        return await cls._insert_data(question, answer)

    @classmethod
    async def insert_many(cls, data_list: list | None) -> bool:
        """
        向数据库的question表中批量插入元素

        :param data_list: [list]一个包括所有要插入数据的数组，注意该数组必须为2维数组，且每一个元组必须为question, answer两个元素组成。例如：[["问题1","回答1"],["问题2", "回答2"]]
        """
        for question, answer in data_list:
            flag = await cls._insert_data(question, answer)
            if flag is False:
                return flag

        return True