"""查找/替换规则的编译层。

同一份用户规则需要同时供两处使用：

* 本地预览引擎（Python ``re``）—— 负责统计命中、生成上下文片段与替换预览；
* office-cli（.NET Regex）—— 真正落盘执行替换。

因此这里把规则归一化成一条"双方都认"的正则表达式：普通文本模式先做字面转义，
全词匹配用 ASCII 词边界断言包裹，忽略大小写用 ``(?i)`` 内联标志。
替换串则区分两种方言：.NET 用 ``$1`` / ``$$``，Python 用 ``\\g<1>``。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

# 只转义真正的正则元字符。不能直接用 re.escape：它会把空格写成 "\ "，
# .NET 会把这种未知转义当作语法错误。
_META = set("\\^$.|?*+()[]{}")

# 全词匹配的边界：只把 ASCII 字母/数字/下划线视作"词字符"。
# 中文没有空格分词，若按 Unicode 词字符处理，"华为"这类词在中文句子里将永远匹配不到。
_WORD_LEFT = r"(?<![A-Za-z0-9_])"
_WORD_RIGHT = r"(?![A-Za-z0-9_])"

CONTEXT_CHARS = 26


class RuleError(ValueError):
    """规则无法编译（正则语法错误、查找内容为空等）。"""


def escape_literal(text: str) -> str:
    return "".join("\\" + ch if ch in _META else ch for ch in text)


def _build_source(rule: "ReplaceRule") -> str:
    body = rule.find if rule.regex else escape_literal(rule.find)
    if rule.whole_word:
        body = f"{_WORD_LEFT}(?:{body}){_WORD_RIGHT}"
    if not rule.case_sensitive:
        body = "(?i)" + body
    return body


@dataclass(frozen=True)
class ReplaceRule:
    """用户可见的规则配置。"""

    find: str = ""
    replace: str = ""
    regex: bool = False
    case_sensitive: bool = True
    whole_word: bool = False

    def compile(self) -> "CompiledRule":
        return CompiledRule(self)


class CompiledRule:
    """编译后的规则：对外暴露预览与执行所需的两种表达。"""

    def __init__(self, rule: ReplaceRule) -> None:
        if not rule.find:
            raise RuleError("查找内容不能为空")
        self.rule = rule
        self.source = _build_source(rule)
        try:
            self.regex: re.Pattern[str] = re.compile(self.source)
        except re.error as exc:
            pos = exc.pos if exc.pos is not None else 0
            raise RuleError(
                f"正则表达式无效（第 {pos + 1} 个字符附近）：{_translate_regex_error(exc)}"
            ) from exc

    # ------------------------------------------------------------------ 匹配

    def iter_matches(self, text: str) -> Iterator[re.Match[str]]:
        if not text:
            return iter(())
        return self.regex.finditer(text)

    def count(self, text: str) -> int:
        if not text:
            return 0
        return sum(1 for _ in self.regex.finditer(text))

    def replace(self, text: str) -> str:
        if not text:
            return text
        if self.rule.regex:
            try:
                return self.regex.sub(self._python_template(), text)
            except re.error:
                # 用户写了一个不存在的分组引用：退化为整体字面替换，绝不抛给界面。
                return self.regex.sub(lambda _m: self.rule.replace, text)
        return self.regex.sub(lambda _m: self.rule.replace, text)

    def replacement_for(self, match: re.Match[str]) -> str:
        """按单个匹配生成替换文本。

        不能拿命中片段再跑一次正则：像 ``Hello(?=\\s)`` 这种依赖上下文的模式，
        单独对 "Hello" 匹配会失败，预览就会显示成"没有变化"。
        """
        if not self.rule.regex:
            return self.rule.replace
        try:
            return match.expand(self._python_template())
        except (re.error, IndexError):
            return self.rule.replace

    def replaced_text(self, value: str) -> str:
        """替换单个匹配片段（用于预览列）。"""
        return self.replace(value)

    # ------------------------------------------------------- 与 CLI 的对接

    def cli_find(self) -> str:
        return self.source

    def cli_replace(self) -> str:
        if self.rule.regex:
            return self.rule.replace
        # .NET 的替换串里 $ 是特殊字符（$1、$$、$&），普通文本必须转义。
        return self.rule.replace.replace("$", "$$")

    def cli_props(self) -> dict[str, str]:
        return {"find": self.cli_find(), "replace": self.cli_replace(), "regex": "true"}

    # ------------------------------------------------------------ 内部实现

    def _python_template(self) -> str:
        """把 .NET 风格的替换串翻译成 Python ``re.sub`` 模板。"""
        rep = self.rule.replace
        groups = self.regex.groups
        named = set(self.regex.groupindex)
        out: list[str] = []
        i = 0
        while i < len(rep):
            ch = rep[i]
            if ch == "$":
                nxt = rep[i + 1 : i + 2]
                if nxt == "$":
                    out.append("$")
                    i += 2
                    continue
                if nxt == "&":
                    out.append(r"\g<0>")
                    i += 2
                    continue
                if nxt == "{":
                    end = rep.find("}", i + 2)
                    if end > 0:
                        name = rep[i + 2 : end]
                        if _valid_group(name, groups, named):
                            out.append(f"\\g<{name}>")
                        else:
                            out.append(re.escape("${" + name + "}"))
                        i = end + 1
                        continue
                if nxt.isdigit():
                    j = i + 1
                    while j < len(rep) and rep[j].isdigit():
                        j += 1
                    num = int(rep[i + 1 : j])
                    if 1 <= num <= groups:
                        out.append(f"\\g<{num}>")
                    else:
                        out.append(re.escape("$" + str(num)))
                    i = j
                    continue
                out.append("$")
                i += 1
                continue
            if ch == "\\":
                out.append("\\\\")
                i += 1
                continue
            out.append(ch)
            i += 1
        return "".join(out)


def _valid_group(name: str, groups: int, named: set[str]) -> bool:
    if name.isdigit():
        return 1 <= int(name) <= groups
    return name in named


def _translate_regex_error(exc: re.error) -> str:
    msg = exc.msg or str(exc)
    table = {
        "unterminated character set": "字符集合缺少右方括号 ]",
        "missing ), unterminated subpattern": "括号未闭合",
        "nothing to repeat": "量词前面没有可重复的内容",
        "bad character range": "字符范围写法有误",
        "invalid group name": "分组名称无效",
        "unbalanced parenthesis": "括号不配对",
        "bad escape": "无效的转义字符",
    }
    for key, zh in table.items():
        if key in msg:
            return zh
    return msg


def snippet(text: str, start: int, end: int, context: int = CONTEXT_CHARS) -> tuple[str, str, str]:
    """返回 (前文, 命中, 后文)，换行与连续空白折叠为单个空格。"""
    raw_before = text[max(0, start - context) : start]
    raw_after = text[end : end + context]
    before = _squash(raw_before)
    after = _squash(raw_after)
    if start - context > 0:
        before = "…" + before
    if end + context < len(text):
        after = after + "…"
    return before, text[start:end], after


def _squash(value: str) -> str:
    return re.sub(r"[\r\n\t\u000b]+", " ", value).replace("  ", " ")
