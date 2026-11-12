import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  Coffee,
  Cpu,
  Eye,
  Image as ImageIcon,
  Loader2,
  Play,
  RotateCcw,
  Settings2,
  ShieldCheck,
  Square,
  WandSparkles,
} from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Progress } from "@/components/ui/progress"
import { Separator } from "@/components/ui/separator"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { TooltipProvider } from "@/components/ui/tooltip"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Toaster } from "@/components/ui/sonner"
import { FilePanel } from "@/components/file-panel"
import { DonateDialog } from "@/components/donate-dialog"
import { LogPanel } from "@/components/log-panel"
import { PreviewPanel } from "@/components/preview-panel"
import { ResultsPanel } from "@/components/results-panel"
import { RulePanel } from "@/components/rule-panel"
import { SettingsDialog } from "@/components/settings-dialog"
import { ThemePicker } from "@/components/theme-picker"
import { WallpaperLayer, NO_WALLPAPER, type WallpaperState } from "@/components/wallpaper-layer"
import { WallpaperPanel } from "@/components/wallpaper-panel"
import {
  api,
  ACCENTS,
  type AccentId,
  type Bootstrap,
  type FileEntry,
  type FileResultRow,
  type JobSnapshot,
  type LogLine,
  type Rule,
  type Scan,
  type Scope,
  type Settings,
  type Summary,
  PANEL_OPACITY_MAX,
  PANEL_OPACITY_MIN,
  WALLPAPER_BLUR_MAX,
  WALLPAPERS,
  type WallpaperSource,
} from "@/lib/api"
import { toast } from "sonner"

const DEFAULT_RULE: Rule = {
  find: "",
  replace: "",
  regex: false,
  case_sensitive: true,
  whole_word: false,
}

const DEFAULT_SCOPE: Scope = {
  body: true,
  table: true,
  header_footer: true,
  notes: false,
  sheets: [],
}

type TabKey = "preview" | "results" | "log"

interface JobView {
  id: string
  mode: "preview" | "apply"
  status: JobSnapshot["status"]
  total: number
  done: number
  current: string
  error: string
}

export default function App() {
  const [boot, setBoot] = useState<Bootstrap | null>(null)
  const [bootError, setBootError] = useState("")
  const [settings, setSettings] = useState<Settings | null>(null)
  const [mode, setMode] = useState<"light" | "dark">(
    () => (localStorage.getItem("otr-theme") as "light" | "dark") || "dark",
  )
  const [accent, setAccent] = useState<AccentId>(
    () => (localStorage.getItem("otr-accent") as AccentId) || "blue",
  )

  const [files, setFiles] = useState<FileEntry[]>([])
  const [rule, setRule] = useState<Rule>(DEFAULT_RULE)
  const [scope, setScope] = useState<Scope>(DEFAULT_SCOPE)
  const [ruleError, setRuleError] = useState("查找内容不能为空")
  const [tab, setTab] = useState<TabKey>("preview")

  const [scans, setScans] = useState<Scan[]>([])
  const [results, setResults] = useState<FileResultRow[]>([])
  const [logs, setLogs] = useState<LogLine[]>([])
  const [summary, setSummary] = useState<Summary>({})
  const [job, setJob] = useState<JobView | null>(null)
  const cursors = useRef({ scans: 0, results: 0, logs: 0 })
  const pollRef = useRef<number | null>(null)

  const [settingsOpen, setSettingsOpen] = useState(false)
  const [donateOpen, setDonateOpen] = useState(false)
  const [wallpaperOpen, setWallpaperOpen] = useState(false)
  const [wallpaper, setWallpaper] = useState<WallpaperState>(NO_WALLPAPER)
  const [wallpaperRevision, setWallpaperRevision] = useState(0)
  const [customAvailable, setCustomAvailable] = useState(true)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmChecked, setConfirmChecked] = useState(false)
  const [cli, setCli] = useState({ found: false, version: "", origin: "", path: "" })

  const native = Boolean(window.__OFFICE_REPLACER_NATIVE__)
  const busy = job?.status === "running"
  // 连续调节虚化时避免旧请求覆盖新状态
  const wallpaperToken = useRef(0)
  // 已落盘的壁纸状态：拖动预览会先改 state，提交时必须和它比较才知道要不要写
  const savedWallpaper = useRef<WallpaperState>(NO_WALLPAPER)

  // ---- 初始化 ------------------------------------------------------------

  useEffect(() => {
    api
      .bootstrap()
      .then((data) => {
        setBoot(data)
        setSettings(data.settings)
        setCli(data.cli)
        setMode(data.settings.theme === "light" ? "light" : "dark")
        if (ACCENTS.some((a) => a.id === data.settings.accent)) {
          setAccent(data.settings.accent as AccentId)
        }
        const restored = resolveWallpaper(data.settings, data.wallpaper_exists !== false)
        savedWallpaper.current = restored.state
        setWallpaper(restored.state)
        setCustomAvailable(restored.customAvailable)
        if (restored.fellBack) {
          // 本地图片不可用：立刻把回退结果写回配置，下次启动不必再判断
          void api
            .post<{ ok: boolean; settings: Settings }>("/api/settings", wallpaperPayload(restored.state))
            .then((res) => setSettings(res.settings))
            .catch(() => {})
        }
      })
      .catch((error) => setBootError(String(error)))
  }, [])

  // ---- 主题 --------------------------------------------------------------

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle("dark", mode === "dark")
    root.dataset.accent = accent
    root.style.colorScheme = mode
    localStorage.setItem("otr-theme", mode)
    localStorage.setItem("otr-accent", accent)
  }, [mode, accent])

  // 功能面板不透明度：只写一个 CSS 变量，避免重渲染整棵组件树。
  // 注意：这里不再联动 backdrop-filter，实时模糊在 QtWebEngine 的软件合成下会持续重绘导致频闪。
  useEffect(() => {
    document.documentElement.style.setProperty(
      "--panel-opacity",
      String(wallpaper.panelOpacity / 100),
    )
  }, [wallpaper.panelOpacity])

  const persistTheme = useCallback(
    (nextMode: "light" | "dark", nextAccent: AccentId) => {
      if (!settings) return
      const next = { ...settings, theme: nextMode, accent: nextAccent }
      setSettings(next)
      api.post("/api/settings", { theme: nextMode, accent: nextAccent }).catch(() => {})
    },
    [settings],
  )

  const changeMode = (next: "light" | "dark") => {
    setMode(next)
    persistTheme(next, accent)
  }
  const changeAccent = (next: AccentId) => {
    setAccent(next)
    persistTheme(mode, next)
  }

  // ---- 背景壁纸 ----------------------------------------------------------
  // 壁纸独立于 theme / accent，但走同一个 /api/settings 落盘，随主题配置保存。

  const persistWallpaper = useCallback(
    (state: WallpaperState, options: { silent?: boolean } = {}) => {
      const token = ++wallpaperToken.current
      savedWallpaper.current = state
      setWallpaper(state)
      setSettings((prev) => (prev ? { ...prev, ...wallpaperPayload(state) } : prev))
      api
        .post<{ ok: boolean; settings: Settings; wallpaper_exists?: boolean }>(
          "/api/settings",
          wallpaperPayload(state),
        )
        .then((res) => {
          if (token !== wallpaperToken.current) return
          if (res.settings) setSettings(res.settings)
          setCustomAvailable(res.wallpaper_exists !== false)
          if (state.source === "custom" && res.wallpaper_exists === false) {
            const next = fallbackWallpaper(state)
            savedWallpaper.current = next
            setWallpaper(next)
            toast.warning("本地图片已不可用，已回退到预设壁纸")
          }
        })
        .catch((error) => {
          if (!options.silent) toast.error(`壁纸保存失败：${error}`)
        })
    },
    [],
  )

  const selectWallpaper = useCallback(
    (next: WallpaperState) => {
      // 换图时若还没设虚化，保持现状；换来源都重新校验可用性
      setCustomAvailable(next.source === "custom")
      setWallpaperRevision((v) => v + 1)
      persistWallpaper(next)
    },
    [persistWallpaper],
  )

  const commitBlur = useCallback(
    (blur: number) => {
      if (savedWallpaper.current.blur === blur) return
      const next = { ...savedWallpaper.current, blur }
      persistWallpaper(next, { silent: true })
    },
    [persistWallpaper],
  )

  const commitPanelOpacity = useCallback(
    (panelOpacity: number) => {
      const current = savedWallpaper.current
      if (current.panelOpacity === panelOpacity) return
      persistWallpaper({ ...current, panelOpacity }, { silent: true })
    },
    [persistWallpaper],
  )

  const handleWallpaperError = useCallback(() => {
    setWallpaper((prev) => {
      if (prev.source !== "custom") return prev
      const next = fallbackWallpaper(prev)
      savedWallpaper.current = next
      void api.post("/api/settings", wallpaperPayload(next)).catch(() => {})
      toast.warning("自定义壁纸读取失败，已回退到预设壁纸")
      return next
    })
  }, [])

  const openWallpaperPanel = () => {
    setWallpaperOpen((open) => {
      if (!open) setCustomAvailable((v) => v)
      return !open
    })
  }

  // ---- 系统拖放路径（由 Qt 宿主窗口注入） --------------------------------

  useEffect(() => {
    const handler = async (event: Event) => {
      const paths = (event as CustomEvent<{ paths: string[] }>).detail?.paths || []
      if (!paths.length) return
      try {
        const res = await api.post<{ ok: boolean; files: FileEntry[]; notes: string[] }>(
          "/api/add-paths",
          { paths },
        )
        setFiles((prev) => {
          const known = new Set(prev.map((f) => f.path.toLowerCase()))
          return [...prev, ...res.files.filter((f) => !known.has(f.path.toLowerCase()))]
        })
        res.notes.forEach((note) => toast.warning(note))
        if (res.files.length) toast.success(`已从拖放添加 ${res.files.length} 个文件`)
      } catch (error) {
        toast.error(String(error))
      }
    }
    window.addEventListener("native-paths", handler)
    return () => window.removeEventListener("native-paths", handler)
  }, [])

  // ---- 任务轮询 ----------------------------------------------------------

  const stopPolling = () => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  useEffect(() => {
    if (!job || job.status !== "running") return
    stopPolling()
    const tick = async () => {
      try {
        const snap = await api.job(job.id, cursors.current)
        cursors.current = snap.counts
        if (snap.scans.length) setScans((prev) => [...prev, ...snap.scans])
        if (snap.results.length) setResults((prev) => [...prev, ...snap.results])
        if (snap.logs.length) setLogs((prev) => [...prev, ...snap.logs])
        if (Object.keys(snap.summary || {}).length) setSummary(snap.summary)
        const finished = snap.status !== "running"
        setJob((prev) =>
          prev
            ? {
                ...prev,
                status: snap.status,
                done: snap.done,
                total: snap.total,
                current: snap.current,
                error: snap.error,
              }
            : prev,
        )
        if (finished) {
          stopPolling()
          toast[snap.status === "error" ? "error" : snap.status === "cancelled" ? "warning" : "success"](
            snap.status === "error"
              ? snap.error || "任务失败"
              : `${job.mode === "preview" ? "预览" : "替换"}${snap.status === "cancelled" ? "已取消" : "完成"} · ${snap.done}/${snap.total} 个文件`,
          )
        }
      } catch (error) {
        stopPolling()
        setJob((prev) => (prev ? { ...prev, status: "error", error: String(error) } : prev))
        toast.error(String(error))
      }
    }
    void tick()
    pollRef.current = window.setInterval(tick, 240)
    return stopPolling
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.id])

  // ---- 动作 --------------------------------------------------------------

  const startJob = async (kind: "preview" | "apply") => {
    if (!files.length) return toast.warning("请先添加文件")
    if (!rule.find) return toast.warning("请填写查找内容")
    if (ruleError) return toast.error(ruleError)
    if (!cli.found) return toast.error("未找到 office-cli，请先在设置中配置")
    if (busy) return

    if (kind === "preview") {
      setScans([])
      setSummary({})
      setTab("preview")
    } else {
      setResults([])
      setSummary({})
      setTab("results")
    }
    setLogs([])
    cursors.current = { scans: 0, results: 0, logs: 0 }
    try {
      const res = await api.post<{ ok: boolean; job_id: string; message?: string }>(
        `/api/${kind === "preview" ? "preview" : "apply"}`,
        {
          paths: files.map((f) => f.path),
          rule,
          scope,
        },
      )
      if (!res.ok) return toast.error(res.message || "任务启动失败")
      setJob({
        id: res.job_id,
        mode: kind,
        status: "running",
        total: files.length,
        done: 0,
        current: "",
        error: "",
      })
    } catch (error) {
      toast.error(String(error))
    }
  }

  const cancel = async () => {
    if (!job) return
    try {
      await api.post("/api/cancel", { id: job.id })
      toast.info("正在停止…")
    } catch (error) {
      toast.error(String(error))
    }
  }

  const undo = async () => {
    try {
      const res = await api.post<{ ok: boolean; message: string; failed: string[] }>(
        "/api/undo",
        {},
      )
      if (res.ok) {
        toast.success(res.message)
        res.failed.forEach((item) => toast.error(item))
      } else {
        toast.error(res.message)
      }
    } catch (error) {
      toast.error(String(error))
    }
  }

  const probe = async () => {
    try {
      const res = await api.post<{ ok: boolean; cli: typeof cli }>("/api/probe", {})
      setCli(res.cli)
      if (res.cli.found) toast.success(`已连接 office-cli ${res.cli.version}`)
      else toast.error("仍未检测到 office-cli")
    } catch (error) {
      toast.error(String(error))
    }
  }

  const canRun = useMemo(
    () => Boolean(files.length && rule.find && !ruleError && cli.found && !busy),
    [files.length, rule.find, ruleError, cli.found, busy],
  )

  // ---- 渲染 --------------------------------------------------------------

  if (bootError) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <Alert variant="destructive" className="max-w-lg">
          <CircleAlert />
          <AlertDescription>
            无法连接本地服务：{bootError}
            <div className="mt-2 font-mono text-[11px]">python main.py</div>
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <TooltipProvider delayDuration={300}>
      <WallpaperLayer
        wallpaper={wallpaper}
        revision={wallpaperRevision}
        onError={handleWallpaperError}
      />
      <div className="relative z-10 flex h-full flex-col">
        {/* 顶栏 */}
        <header className="flex h-14 shrink-0 items-center gap-3 border-b bg-background/95 px-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <WandSparkles className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="truncate text-sm font-semibold">
                {boot?.app.title || "Office 文字替换器"}
              </h1>
              <Badge variant="muted">v{boot?.app.version || "2.0"}</Badge>
            </div>
            <p className="truncate text-[10px] text-muted-foreground">
              {boot?.app.subtitle || "基于 office-cli · 支持 Word / Excel / PowerPoint"}
            </p>
          </div>

          <div className="ml-auto flex items-center gap-2">
            <div className="flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px]">
              <Cpu className="h-3.5 w-3.5 text-muted-foreground" />
              {cli.found ? (
                <>
                  <span className="h-1.5 w-1.5 rounded-full bg-[hsl(var(--success))]" />
                  <span className="font-medium">office-cli</span>
                  <span className="text-muted-foreground">{cli.version}</span>
                </>
              ) : (
                <>
                  <span className="h-1.5 w-1.5 rounded-full bg-destructive" />
                  <span className="text-destructive">未找到 office-cli</span>
                </>
              )}
            </div>
            <Separator orientation="vertical" className="h-6" />
            <Button variant="outline" size="sm" onClick={undo} title="撤销上一次替换">
              <RotateCcw /> 撤销
            </Button>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant={wallpaper.source === "none" ? "ghost" : "soft"}
                  size="icon-sm"
                  onClick={openWallpaperPanel}
                  aria-label="背景壁纸"
                  aria-pressed={wallpaperOpen}
                  className={wallpaper.source === "none" ? undefined : "shadow-sm"}
                >
                  <ImageIcon />
                </Button>
              </TooltipTrigger>
              <TooltipContent>背景壁纸</TooltipContent>
            </Tooltip>
            <ThemePicker
              mode={mode}
              accent={accent}
              onMode={changeMode}
              onAccent={changeAccent}
            />
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => setDonateOpen(true)}
                  aria-label="请开发者喝个咖啡"
                  className="text-[hsl(var(--brand))] hover:text-[hsl(var(--brand-ink))]"
                >
                  <Coffee />
                </Button>
              </TooltipTrigger>
              <TooltipContent>请开发者喝个咖啡</TooltipContent>
            </Tooltip>
            <Button variant="ghost" size="icon-sm" onClick={() => setSettingsOpen(true)} title="设置">
              <Settings2 />
            </Button>
          </div>
        </header>

        {/* 主体 */}
        <div className="flex min-h-0 flex-1 gap-4 p-4">
          <div className="flex w-[360px] shrink-0 flex-col gap-3">
            <FilePanel files={files} onFiles={setFiles} busy={Boolean(busy)} native={native} />
            <div className="panel-surface-soft flex items-start gap-2 rounded-lg border px-3 py-2 text-pretty text-[11px] leading-4 text-muted-foreground">
              <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[hsl(var(--success))]" />
              替换只在副本上进行：校验通过并备份原文件后才原子写回，任一步失败都不改动原文件。
            </div>
          </div>

          <div className="flex min-w-0 flex-1 flex-col gap-3">
            <RulePanel
              rule={rule}
              onRule={setRule}
              scope={scope}
              onScope={setScope}
              files={files}
              ruleError={ruleError}
              onRuleError={setRuleError}
              busy={Boolean(busy)}
            />

            {/* 操作栏 */}
            <div className="panel-surface flex shrink-0 flex-wrap items-center gap-2 rounded-lg border px-3.5 py-2.5">
              <Button variant="outline" onClick={() => startJob("preview")} disabled={!canRun}>
                {busy && job?.mode === "preview" ? <Loader2 className="animate-spin" /> : <Eye />}
                预览匹配
              </Button>
              <Button
                onClick={() => {
                  setConfirmChecked(false)
                  setConfirmOpen(true)
                }}
                disabled={!canRun}
              >
                <Play /> 执行替换 <ArrowRight />
              </Button>
              {busy && (
                <>
                  <Button variant="ghost" size="sm" onClick={cancel}>
                    <Square /> 取消
                  </Button>
                  <div className="ml-2 flex min-w-0 flex-1 items-center gap-2">
                    <Progress value={job.total ? (job.done / job.total) * 100 : 0} className="max-w-[220px]" />
                    <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
                      {job.done}/{job.total}
                    </span>
                    <span className="mono-path truncate text-muted-foreground">{job.current}</span>
                  </div>
                </>
              )}
              {!busy && (
                <span className="ml-auto text-[11px] text-muted-foreground">
                  {files.length
                    ? `${files.length} 个文件待处理 · 建议先预览再替换`
                    : "先添加文件，再配置规则"}
                </span>
              )}
            </div>

            {/* 结果区 */}
            <Tabs
              value={tab}
              onValueChange={(v) => setTab(v as TabKey)}
              className="flex min-h-0 flex-1 flex-col"
            >
              <div className="flex shrink-0 items-center justify-between gap-2">
                <TabsList>
                  <TabsTrigger value="preview">
                    预览 <Badge variant="muted" className="ml-1">{scans.length}</Badge>
                  </TabsTrigger>
                  <TabsTrigger value="results">
                    结果 <Badge variant="muted" className="ml-1">{results.length}</Badge>
                  </TabsTrigger>
                  <TabsTrigger value="log">
                    日志 <Badge variant="muted" className="ml-1">{logs.length}</Badge>
                  </TabsTrigger>
                </TabsList>
                {job && job.status !== "running" && (
                  <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    {job.status === "done" ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-[hsl(var(--success))]" />
                    ) : (
                      <CircleAlert className="h-3.5 w-3.5 text-[hsl(var(--warning))]" />
                    )}
                    {job.status === "done" ? "已完成" : job.status === "cancelled" ? "已取消" : "失败"}
                    {job.error ? ` · ${job.error}` : ""}
                  </span>
                )}
              </div>
              <TabsContent value="preview" className="mt-3 min-h-0 flex-1 data-[state=inactive]:hidden">
                <PreviewPanel scans={scans} summary={summary} />
              </TabsContent>
              <TabsContent value="results" className="mt-3 min-h-0 flex-1 data-[state=inactive]:hidden">
                <ResultsPanel results={results} summary={summary} />
              </TabsContent>
              <TabsContent value="log" className="mt-3 min-h-0 flex-1 data-[state=inactive]:hidden">
                <LogPanel logs={logs} />
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </div>

      {/* 执行确认 */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>确认执行替换</DialogTitle>
            <DialogDescription>
              替换会写回原文件。程序会先复制副本、校验结构、自动备份，任何一步失败都会保留原文件。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 rounded-lg border bg-muted/30 p-3 text-xs">
            <Line label="文件数量" value={`${files.length} 个`} />
            <Line label="查找" value={rule.find} mono />
            <Line label="替换为" value={rule.replace || "（删除）"} mono />
            <Line
              label="匹配模式"
              value={`${rule.regex ? "正则表达式" : "普通文本"} · ${rule.case_sensitive ? "区分大小写" : "忽略大小写"}${rule.whole_word ? " · 全词匹配" : ""}`}
            />
            {settings?.keep_backup && <Line label="自动备份" value="已开启，可在顶栏一键撤销" />}
          </div>
          {files.length > 0 && (
            <div className="max-h-28 overflow-auto rounded-md border p-2 font-mono text-[10px] text-muted-foreground">
              {files.slice(0, 20).map((f) => (
                <div key={f.path} className="truncate">
                  {f.path}
                </div>
              ))}
              {files.length > 20 && <div>… 另有 {files.length - 20} 个文件</div>}
            </div>
          )}
          <label className="flex cursor-pointer items-center gap-2 text-xs">
            <Checkbox
              checked={confirmChecked}
              onCheckedChange={(v) => setConfirmChecked(Boolean(v))}
            />
            我已确认以上规则与文件列表
          </label>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
              取消
            </Button>
            <Button
              disabled={!confirmChecked}
              onClick={() => {
                setConfirmOpen(false)
                void startJob("apply")
              }}
            >
              <Play /> 开始替换
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {settings && (
        <SettingsDialog
          open={settingsOpen}
          onOpenChange={setSettingsOpen}
          settings={settings}
          onSave={setSettings}
          cliFound={cli.found}
          cliVersion={cli.version}
          onProbe={probe}
        />
      )}

      <WallpaperPanel
        open={wallpaperOpen}
        onClose={() => setWallpaperOpen(false)}
        wallpaper={wallpaper}
        onSelect={selectWallpaper}
        onBlurCommit={commitBlur}
        onPanelOpacityCommit={commitPanelOpacity}
        revision={wallpaperRevision}
        customAvailable={customAvailable}
        native={native}
      />

      <DonateDialog open={donateOpen} onOpenChange={setDonateOpen} />

      <Toaster />
    </TooltipProvider>
  )
}

/* ---------------------------------------------------------------- 壁纸工具 */

/** 自定义图片不可用时回退到第一个预设，保证背景不会突然变成纯色。 */
function fallbackWallpaper(prev: WallpaperState): WallpaperState {
  return {
    source: "preset",
    id: WALLPAPERS[0].id,
    path: "",
    blur: prev.blur,
    panelOpacity: prev.panelOpacity,
  }
}


function wallpaperPayload(state: WallpaperState) {
  return {
    wallpaper_source: state.source,
    wallpaper_id: state.id,
    wallpaper_path: state.path,
    wallpaper_blur: state.blur,
    wallpaper_panel_opacity: state.panelOpacity,
  } as const
}

/**
 * 从配置恢复壁纸。
 * 自定义图片缺失（文件被删/移动/改名）时自动回退到预设，并把回退结果写回配置。
 */
function resolveWallpaper(
  settings: Settings,
  exists: boolean,
): { state: WallpaperState; customAvailable: boolean; fellBack: boolean } {
  const rawSource: WallpaperSource = settings.wallpaper_source || "none"
  const blur = clampBlur(settings.wallpaper_blur ?? 0)
  const panelOpacity = clampPanelOpacity(settings.wallpaper_panel_opacity ?? 100)
  const knownPreset = WALLPAPERS.some((w) => w.id === settings.wallpaper_id)

  if (rawSource === "custom") {
    if (settings.wallpaper_path && exists !== false) {
      return {
        state: { source: "custom", id: "", path: settings.wallpaper_path, blur, panelOpacity },
        customAvailable: true,
        fellBack: false,
      }
    }
    const fallback = fallbackWallpaper({ source: "custom", id: "", path: "", blur, panelOpacity })
    return {
      state: fallback,
      customAvailable: false,
      fellBack: true,
    }
  }
  if (rawSource === "preset") {
    const id = knownPreset ? settings.wallpaper_id : WALLPAPERS[0].id
    return {
      state: { source: "preset", id, path: "", blur, panelOpacity },
      customAvailable: true,
      fellBack: false,
    }
  }
  return {
    state: { source: "none", id: "", path: "", blur: 0, panelOpacity },
    customAvailable: true,
    fellBack: false,
  }
}

function clampBlur(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(WALLPAPER_BLUR_MAX, Math.round(value)))
}

function clampPanelOpacity(value: number): number {
  if (!Number.isFinite(value)) return PANEL_OPACITY_MAX
  return Math.max(PANEL_OPACITY_MIN, Math.min(PANEL_OPACITY_MAX, Math.round(value)))
}

function Line({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex gap-3">
      <span className="w-16 shrink-0 text-muted-foreground">{label}</span>
      <span className={mono ? "min-w-0 flex-1 break-all font-mono" : "min-w-0 flex-1 break-all"}>
        {value}
      </span>
    </div>
  )
}
