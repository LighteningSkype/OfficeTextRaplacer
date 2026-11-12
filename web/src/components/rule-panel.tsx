import { useEffect, useState } from "react"
import { AlertCircle, Braces, CaseSensitive, Check, ChevronDown } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { api, type FileEntry, type Rule, type Scope } from "@/lib/api"
import { toast } from "sonner"

interface Props {
  rule: Rule
  onRule: (rule: Rule) => void
  scope: Scope
  onScope: (scope: Scope) => void
  files: FileEntry[]
  ruleError: string
  onRuleError: (error: string) => void
  busy: boolean
}

const SCOPE_ITEMS: { key: keyof Scope; label: string; hint: string }[] = [
  { key: "body", label: "正文 / 文本框 / 形状", hint: "Word 段落、PPT 文本框与形状" },
  { key: "table", label: "表格单元格", hint: "Word / PPT 表格、Excel 单元格" },
  { key: "header_footer", label: "页眉与页脚", hint: "Word 页眉页脚" },
  { key: "notes", label: "PPT 备注", hint: "默认关闭，按需开启" },
]

export function RulePanel({
  rule,
  onRule,
  scope,
  onScope,
  files,
  ruleError,
  onRuleError,
  busy,
}: Props) {
  const [sheets, setSheets] = useState<string[]>([])
  const [sheetsOpen, setSheetsOpen] = useState(false)
  const [loadingSheets, setLoadingSheets] = useState(false)

  // 规则变化后向后端校验正则（后端与执行用的是同一套编译逻辑）。
  useEffect(() => {
    if (!rule.regex || !rule.find) {
      onRuleError(rule.find ? "" : "查找内容不能为空")
      return
    }
    let alive = true
    const timer = window.setTimeout(async () => {
      try {
        const res = await api.post<{ ok: boolean; error: string }>("/api/validate-rule", rule)
        if (alive) onRuleError(res.ok ? "" : res.error)
      } catch {
        if (alive) onRuleError("无法校验规则")
      }
    }, 220)
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rule.find, rule.replace, rule.regex, rule.case_sensitive, rule.whole_word])

  const loadSheets = async () => {
    const target = files.find((f) => f.kind === "excel")
    if (!target) {
      toast.info("列表中没有 Excel 文件")
      return
    }
    setLoadingSheets(true)
    try {
      const res = await api.post<{ ok: boolean; sheets: string[] }>("/api/sheets", {
        path: target.path,
      })
      setSheets(res.sheets || [])
      setSheetsOpen(true)
      if (!res.sheets?.length) toast.info("未读取到工作表")
    } catch (error) {
      toast.error(String(error))
    } finally {
      setLoadingSheets(false)
    }
  }

  const toggleSheet = (name: string) => {
    const next = scope.sheets.includes(name)
      ? scope.sheets.filter((s) => s !== name)
      : [...scope.sheets, name]
    onScope({ ...scope, sheets: next })
  }

  const set = (key: keyof Rule, value: unknown) =>
    onRule({ ...rule, [key]: value } as Rule)

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <CardTitle>替换规则</CardTitle>
        <Tabs value={rule.regex ? "regex" : "text"} onValueChange={(v) => set("regex", v === "regex")}>
          <TabsList className="h-8">
            <TabsTrigger value="text" disabled={busy}>普通文本</TabsTrigger>
            <TabsTrigger value="regex" disabled={busy}>
              <Braces className="h-3 w-3" /> 正则
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="find">查找内容</Label>
            <Input
              id="find"
              value={rule.find}
              disabled={busy}
              placeholder={rule.regex ? "例如 (草稿|初稿)-(\\d+)" : "例如 初稿"}
              className={ruleError && ruleError !== "查找内容不能为空" ? "border-destructive" : ""}
              onChange={(e) => set("find", e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="replace">替换为</Label>
            <Input
              id="replace"
              value={rule.replace}
              disabled={busy}
              placeholder={rule.regex ? "例如 $1-终稿（支持 $1 / ${name}）" : "例如 终稿（$ 会按字面处理）"}
              onChange={(e) => set("replace", e.target.value)}
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={rule.case_sensitive ? "soft" : "outline"}
                size="sm"
                disabled={busy}
                onClick={() => set("case_sensitive", !rule.case_sensitive)}
              >
                <CaseSensitive /> 区分大小写 {rule.case_sensitive ? "开" : "关"}
              </Button>
            </TooltipTrigger>
            <TooltipContent>关闭后 Draft / draft / DRAFT 都会命中</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={rule.whole_word ? "soft" : "outline"}
                size="sm"
                disabled={busy}
                onClick={() => set("whole_word", !rule.whole_word)}
              >
                全词匹配 {rule.whole_word ? "开" : "关"}
              </Button>
            </TooltipTrigger>
            <TooltipContent>按 ASCII 词边界匹配，中文词组同样可用</TooltipContent>
          </Tooltip>
          {rule.regex && (
            <Badge variant="brand">.NET 正则 · 替换串用 $1</Badge>
          )}
        </div>

        {ruleError === "查找内容不能为空" ? (
          <p className="text-[11px] text-muted-foreground">填写查找内容后即可预览匹配结果</p>
        ) : ruleError ? (
          <Alert variant="destructive">
            <AlertCircle />
            <AlertDescription>{ruleError}</AlertDescription>
          </Alert>
        ) : null}

        <Separator />

        <div className="flex items-center justify-between">
          <div className="text-xs font-medium">替换范围</div>
          <Button
            variant="ghost"
            size="sm"
            disabled={busy || loadingSheets}
            onClick={loadSheets}
            className="h-7 text-[11px]"
          >
            <ChevronDown className="h-3 w-3" /> Excel 工作表限定
          </Button>
        </div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          {SCOPE_ITEMS.map((item) => (
            <label key={item.key} className="flex cursor-pointer items-start gap-2">
              <Checkbox
                className="mt-0.5"
                checked={Boolean(scope[item.key])}
                disabled={busy}
                onCheckedChange={(v) =>
                  onScope({ ...scope, [item.key]: Boolean(v) } as Scope)
                }
              />
              <span className="leading-tight">
                <span className="block text-[11px] font-medium">{item.label}</span>
                <span className="block text-[10px] leading-4 text-muted-foreground/90">
                  {item.hint}
                </span>
              </span>
            </label>
          ))}
        </div>

        {sheetsOpen && sheets.length > 0 && (
          <div className="panel-surface-soft rounded-lg border p-2.5">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[11px] font-medium">
                仅处理选中的工作表（不选 = 全部）
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 text-[10px]"
                onClick={() => onScope({ ...scope, sheets: [] })}
              >
                清除限定
              </Button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {sheets.map((name) => {
                const active = scope.sheets.includes(name)
                return (
                  <button
                    key={name}
                    type="button"
                    onClick={() => toggleSheet(name)}
                    className={
                      "flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] transition-colors " +
                      (active
                        ? "border-primary bg-[hsl(var(--brand)/0.12)] text-foreground"
                        : "hover:bg-accent")
                    }
                  >
                    {active && <Check className="h-3 w-3" />}
                    {name}
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
