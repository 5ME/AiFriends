from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

# 1. 加载 Markdown 文件
loader = TextLoader('../Bailian_Overview.md', encoding='utf-8')
docs = loader.load()

# 2. 先按标题切分
headers_to_split_on = [
    ("#", "Header 1"),
    ("##", "Header 2"),
    ("###", "Header 3"),
]
md_splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=headers_to_split_on,
    strip_headers=False
)
# docs 是 List[Document]
md_chunks = []
for doc in docs:
    md_chunks.extend(md_splitter.split_text(doc.page_content))

# 3. 再按长度切分
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50
)
final_chunks = text_splitter.split_documents(md_chunks)

# 4. 查看结果
for i, doc in enumerate(final_chunks):
    print(f"\n--- chunk {i} ---")
    print("metadata:", doc.metadata)
    print("content:", doc.page_content[:100])
