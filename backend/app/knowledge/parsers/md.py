import asyncio

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

from app.knowledge.parsers.base import BaseParser


class MarkdownParser(BaseParser):
    def __init__(self):
        self._md = MarkdownIt("commonmark")
        self._section_stack: list[str] = []

    async def parse(self, file_path: str) -> list[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: str) -> list[dict]:
        with open(file_path, encoding="utf-8") as f:
            text = f.read()
        tokens = self._md.parse(text)
        node = SyntaxTreeNode(tokens)

        results: list[dict] = []
        self._section_stack = []
        self._walk(node, results)
        return results

    def _walk(self, node: SyntaxTreeNode, results: list[dict]) -> None:
        for child in node.children:
            if child.type == "heading":
                level = child.meta.get("level", 1) if child.meta else 1
                heading_text = self._collect_text(child)
                while len(self._section_stack) >= level:
                    self._section_stack.pop()
                self._section_stack.append(heading_text)
            elif child.type == "paragraph":
                para_text = self._collect_text(child)
                if para_text and para_text.strip():
                    section = " > ".join(self._section_stack) if self._section_stack else ""
                    results.append({"text": para_text.strip(), "section": section})
            else:
                self._walk(child, results)

    @staticmethod
    def _collect_text(node: SyntaxTreeNode) -> str:
        parts: list[str] = []

        def _recurse(n: SyntaxTreeNode) -> None:
            if n.type == "text" and n.content:
                parts.append(n.content)
            elif n.type == "code_inline" and n.content:
                parts.append(n.content)
            elif n.type == "softbreak":
                parts.append(" ")
            for c in n.children:
                _recurse(c)

        _recurse(node)
        return "".join(parts)
