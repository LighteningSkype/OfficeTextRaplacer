"""端到端自测：真实调用 office-cli 构建文档并验证替换行为。

运行： ``python tests/selftest.py``  （约 40 秒，需要已安装 office-cli）

覆盖：
* 三种格式的文本抽取（正文 / 表格 / 页眉页脚 / 文本框 / 备注）
* 普通文本、正则、大小写、全词、$ 字面量、中文
* Excel 公式单元格跳过
* 无匹配不改文件、损坏文件报错、被占用文件跳过
* 备份与撤销（还原后字节一致）
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import engine  # noqa: E402
from app.core.cli import OfficeCli, discover  # noqa: E402
from app.core.rules import ReplaceRule, RuleError  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def build_fixtures(cli: OfficeCli, work: Path) -> dict[str, Path]:
    docx = work / "demo.docx"
    xlsx = work / "demo.xlsx"
    pptx = work / "demo.pptx"
    for path in (docx, xlsx, pptx):
        cli.run(["create", str(path), "--json"])

    cli.batch(
        str(docx),
        [
            {"command": "add", "parent": "/body", "type": "paragraph", "props": {"text": "年度报告 Draft 第一段"}},
            {"command": "add", "parent": "/body", "type": "table", "props": {"rows": 1, "cols": 1}},
            {"command": "set", "path": "/body/tbl[1]/tr[1]/tc[1]", "props": {"text": "表格内容 Draft"}},
            {"command": "add", "parent": "/", "type": "header", "props": {"text": "页眉 Draft 标题"}},
            {"command": "add", "parent": "/", "type": "footer", "props": {"text": "页脚 Draft 注"}},
            {"command": "add", "parent": "/body", "type": "textbox", "props": {"text": "文本框 Draft", "x": "2cm", "y": "2cm", "w": "6cm", "h": "2cm"}},
            {"command": "add", "parent": "/body", "type": "paragraph", "props": {"text": "混合 hello Hello HELLO helloworld"}},
        ],
    )
    cli.batch(
        str(xlsx),
        [
            {"command": "add", "parent": "/", "type": "sheet", "props": {"name": "第二表"}},
            {"command": "set", "path": "/Sheet1/A1", "props": {"text": "Draft 主表"}},
            {"command": "set", "path": "/第二表/A1", "props": {"text": "Draft 副表"}},
            {"command": "set", "path": "/Sheet1/C1", "props": {"formula": 'CONCATENATE("Draft","x")'}},
            {"command": "set", "path": "/Sheet1/A4", "props": {"text": "100"}},
        ],
    )
    cli.batch(
        str(pptx),
        [
            {"command": "add", "parent": "/", "type": "slide", "props": {"title": "Draft 标题页"}},
            {"command": "add", "parent": "/slide[1]", "type": "textbox", "props": {"text": "文本框 Draft", "x": "2cm", "y": "6cm", "w": "8cm", "h": "2cm"}},
            {"command": "add", "parent": "/", "type": "slide"},
            {"command": "add", "parent": "/slide[2]", "type": "textbox", "props": {"text": "第二页 Draft", "x": "2cm", "y": "2cm", "w": "8cm", "h": "2cm"}},
            {"command": "set", "path": "/slide[1]/notes", "props": {"text": "备注 Draft"}},
        ],
    )
    return {"docx": docx, "xlsx": xlsx, "pptx": pptx}


def texts(cli: OfficeCli, path: Path, selector: str) -> list[str]:
    return [str(row.get("text") or "") for row in cli.query(str(path), selector)]


def main() -> int:
    info = discover(None)
    if not info:
        print("未找到 office-cli，请先执行：npm install -g @officecli/officecli")
        return 2
    print(f"office-cli {info.version} · {info.path}")
    cli = OfficeCli(info)

    work = Path(tempfile.mkdtemp(prefix="otr-selftest-"))
    print(f"临时目录 {work}")
    try:
        files = build_fixtures(cli, work)
        scope_all = engine.Scope(notes=False)
        rule = ReplaceRule(find="Draft", replace="最终").compile()

        print("\n[1] 抽取与预览")
        scan_docx = engine.scan_file(cli, str(files["docx"]), rule, scope_all)
        check("docx 命中 5 处（正文/表格/页眉/页脚/文本框）", scan_docx.hit_count == 5, str(scan_docx.hit_count))
        check("docx 命中位置 5 个", len(scan_docx.elements) == 5, str(len(scan_docx.elements)))

        scan_xlsx = engine.scan_file(cli, str(files["xlsx"]), rule, scope_all)
        check("xlsx 命中 2 处文本单元格", scan_xlsx.hit_count == 2, str(scan_xlsx.hit_count))
        check("xlsx 公式单元格被跳过", scan_xlsx.excluded_hits == 1, str(scan_xlsx.excluded_hits))
        check("xlsx 工作表被识别", len(scan_xlsx.elements) == 2, str(len(scan_xlsx.elements)))

        scan_pptx = engine.scan_file(cli, str(files["pptx"]), rule, scope_all)
        check("pptx 默认不含备注 → 3 处", scan_pptx.hit_count == 3, str(scan_pptx.hit_count))
        scan_pptx_notes = engine.scan_file(
            cli, str(files["pptx"]), rule, engine.Scope(notes=True)
        )
        check("pptx 含备注 → 4 处", scan_pptx_notes.hit_count == 4, str(scan_pptx_notes.hit_count))

        print("\n[2] 执行替换与写回")
        run_dir = engine.make_run_dir(str(work / "backups"))
        result = engine.apply_file(
            cli, scan_docx, rule, scope_all, run_dir=run_dir, keep_backup=True, verify_after=True
        )
        check("docx 替换成功", result.status == "success", result.message)
        check("docx 命中数一致", result.hits == 5, str(result.hits))
        check("docx 备份已生成", Path(result.backup).is_file())
        after = cli.query(str(files["docx"]), "p")
        joined = " | ".join(str(row.get("text")) for row in after)
        check("docx 正文已替换", "最终" in joined and "Draft" not in joined, joined[:120])

        result = engine.apply_file(
            cli, scan_xlsx, rule, scope_all, run_dir=run_dir, keep_backup=True, verify_after=True
        )
        check("xlsx 替换成功", result.status == "success", result.message)
        rows = cli.query(str(files["xlsx"]), "cell")
        cells = {str(r.get("path")): str(r.get("text")) for r in rows}
        formulas = {
            str(r.get("path")): str((r.get("format") or {}).get("formula") or "") for r in rows
        }
        check("xlsx 文本单元格已替换", cells.get("/Sheet1/A1") == "最终 主表", str(cells.get("/Sheet1/A1")))
        check("xlsx 公式未被破坏", "CONCATENATE" in formulas.get("/Sheet1/C1", ""), str(formulas))

        result = engine.apply_file(
            cli, scan_pptx_notes, rule, engine.Scope(notes=True), run_dir=run_dir, keep_backup=True
        )
        check("pptx 替换成功", result.status == "success", result.message)
        slide_text = " ".join(texts(cli, files["pptx"], "paragraph"))
        check("pptx 文本已替换", "最终" in slide_text and "Draft" not in slide_text, slide_text[:120])
        notes = " ".join(texts(cli, files["pptx"], "notes"))
        check("pptx 备注已替换", "最终" in notes, notes)

        print("\n[3] 规则语义")
        sample = work / "rules.docx"
        cli.run(["create", str(sample), "--json"])
        cli.batch(
            str(sample),
            [
                {"command": "add", "parent": "/body", "type": "paragraph", "props": {"text": "hello Hello HELLO helloworld 订单号 A-1"}},
            ],
        )

        def apply_rule(path: Path, compiled, scope=None) -> engine.FileResult:
            scope = scope or engine.Scope()
            scan = engine.scan_file(cli, str(path), compiled, scope)
            return engine.apply_file(cli, scan, compiled, scope, run_dir=None, keep_backup=False)

        ci = ReplaceRule(find="hello", replace="X", case_sensitive=False).compile()
        check("忽略大小写（含子串）命中 4 处", ci.count("hello Hello HELLO helloworld") == 4, str(ci.count("hello Hello HELLO helloworld")))

        ww = ReplaceRule(find="hello", replace="X", whole_word=True, case_sensitive=False).compile()
        check("全词匹配排除 helloworld", ww.count("hello Hello HELLO helloworld") == 3, str(ww.count("hello Hello HELLO helloworld")))

        grp = ReplaceRule(find=r"(订单号)\s*(A-1)", replace=r"[$1:$2]", regex=True).compile()
        shutil.copy(sample, work / "grp.docx")
        res = apply_rule(work / "grp.docx", grp)
        text = " ".join(texts(cli, work / "grp.docx", "p"))
        check("正则分组 $1/$2 生效", res.status == "success" and "[订单号:A-1]" in text, text)

        dollar = ReplaceRule(find="订单号", replace="$100").compile()
        shutil.copy(sample, work / "dollar.docx")
        apply_rule(work / "dollar.docx", dollar)
        text = " ".join(texts(cli, work / "dollar.docx", "p"))
        check("普通文本中的 $ 不被当作分组", "$100" in text, text)

        print("\n[4] 异常与安全")
        try:
            ReplaceRule(find="([a-z", regex=True).compile()
            check("无效正则应报错", False)
        except RuleError as exc:
            check("无效正则应报错", "正则" in str(exc), str(exc))

        no_match = work / "no_match.docx"
        shutil.copy(sample, no_match)
        before = md5(no_match)
        res = apply_rule(no_match, ReplaceRule(find="不存在的词", replace="X").compile())
        check("无匹配时状态正确", res.status == "no_match", res.status)
        check("无匹配时文件未被改动", md5(no_match) == before)

        broken = work / "broken.docx"
        broken.write_bytes(b"not a zip")
        scan = engine.scan_file(cli, str(broken), rule, scope_all)
        check("损坏文件给出明确错误", scan.error_code == "corrupt_file", scan.error)

        locked = work / "locked.docx"
        shutil.copy(sample, locked)
        (locked.with_name("~$" + locked.name)).write_bytes(b"lock")
        scan = engine.scan_file(cli, str(locked), ReplaceRule(find="hello", replace="X", case_sensitive=False).compile(), scope_all)
        res = engine.apply_file(cli, scan, ReplaceRule(find="hello", replace="X", case_sensitive=False).compile(), scope_all, run_dir=None, keep_backup=False)
        check("被占用文件被跳过", res.status == "skipped", res.message)

        print("\n[5] 撤销")
        restored = engine.restore_run(str(run_dir))
        check("撤销覆盖全部文件", len(restored) == 3, str(len(restored)))
        check("撤销后文件可读", engine.scan_file(cli, str(files["docx"]), rule, scope_all).hit_count == 5)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print(f"\n结果：{PASS} 项通过，{FAIL} 项失败")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
