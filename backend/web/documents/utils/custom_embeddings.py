import os

from langchain_core.embeddings import Embeddings
from openai import OpenAI


class CustomEmbeddings(Embeddings):
    """
    自定义向量化类，对接 OpenAI 兼容的 Embedding API。
    用于将文档或查询语句转换为向量。
    """
    def __init__(self):
        self.client = OpenAI(
            api_key=os.getenv("API_KEY"),
            base_url=os.getenv("API_BASE")
        )

    def embed_documents(self, texts):
        """
        批量将文档列表转换为向量。
        :param texts: 待向量化的文本列表
        :return: 向量列表
        """
        batch_size = 10  # 每次请求处理 10 条数据
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i: i + batch_size]
            # 过滤掉空字符串或仅含空格的文本
            batch = [t for t in batch if t.strip()]
            if not batch:
                continue
            
            # 调用 Embedding 接口
            response = self.client.embeddings.create(
                model="text-embedding-v4",
                input=batch,
                dimensions=1024  # 指定向量维度为 1024
            )
            all_embeddings.extend([data.embedding for data in response.data])
        return all_embeddings

    def embed_query(self, text):
        """
        将单条查询语句转换为向量。
        :param text: 查询文本
        :return: 对应的向量
        """
        return self.embed_documents([text])[0]
