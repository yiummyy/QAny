import asyncio

from app.knowledge.parsers.base import BaseParser


class TxtParser(BaseParser):
    async def parse(self, file_path: str) -> list[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: str) -> list[dict]:
        text = ""
        # 尝试多种常见编码格式读取文件
        for enc in ["utf-8", "gbk", "gb2312", "latin-1"]:
            try:
                with open(file_path, encoding=enc) as f:
                    text = f.read()
                break  # 成功读取则跳出循环
            except UnicodeDecodeError:
                continue

        if not text.strip():
            return []
        return [{"text": text.strip(), "section": ""}]
