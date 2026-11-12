import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react"
import { Check, ImageIcon, ImageOff, Layers, Loader2, RotateCcw, Upload, Waves, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  api,
  assetUrl,
  customWallpaperUrl,
  PANEL_OPACITY_MAX,
  PANEL_OPACITY_MIN,
  WALLPAPER_BLUR_MAX,
  WALLPAPERS,
} from "@/lib/api"
import { cn } from "@/lib/utils"
import { toast } from "sonner"
import { NO_WALLPAPER, type WallpaperState } from "./wallpaper-layer"
interface Props {
  open: boolean
  onClose: () => void
  wallpaper: WallpaperState
  /** 选择预设 / 自定义图片时回调（App 负责落盘后再渲染，避免预览 404） */
  onSelect: (next: WallpaperState) => void
  /** 虚化落定后回调，交给 App 保存 */
  onBlurCommit: (blur: number) => void
  /** 面板不透明度落定后回调，交给 App 保存 */
  onPanelOpacityCommit: (value: number) => void
  revision: number
  /** 自定义图片是否可读；false 时展示回退提示 */
  customAvailable: boolean
  native: boolean
}

export function WallpaperPanel({
  open,
  onClose,
  wallpaper,
  onSelect,
  onBlurCommit,
  onPanelOpacityCommit,
  revision,
  customAvailable,
  native,
}: Props) {
  const [busy, setBusy] = useState(false)
  const [broken, setBroken] = useState(false)
  const fileRef = useRef<HTMLInputElement | null>(null)

  // 拖动中的草稿值：只在本组件内更新，绝不触发 App 重渲染（那会重排整页导致频闪）
  const [draftBlur, setDraftBlur] = useState(wallpaper.blur)
  const [draftOpacity, setDraftOpacity] = useState(wallpaper.panelOpacity)
  const draftRef = useRef({ blur: wallpaper.blur, opacity: wallpaper.panelOpacity })

  useEffect(() => {
    setDraftBlur(wallpaper.blur)
    setDraftOpacity(wallpaper.panelOpacity)
    draftRef.current = { blur: wallpaper.blur, opacity: wallpaper.panelOpacity }
  }, [wallpaper.blur, wallpaper.panelOpacity])

  useEffect(() => {
    setBroken(false)
  }, [wallpaper.path, revision])

  const flush = useCallback(() => {
    const { blur, opacity } = draftRef.current
    if (blur !== wallpaper.blur) onBlurCommit(blur)
    if (opacity !== wallpaper.panelOpacity) onPanelOpacityCommit(opacity)
  }, [wallpaper.blur, wallpaper.panelOpacity, onBlurCommit, onPanelOpacityCommit])

  const close = useCallback(() => {
    flush()
    onClose()
  }, [flush, onClose])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, close])

  // 拖动时直接改样式，不触发 React 重渲染；松手才提交到 store。
  // 这样滑杆高频回调不会反复重建整棵组件树，消除频闪。
  const paintBlur = useCallback((value: number) => {
    const img = document.querySelector<HTMLImageElement>("[data-wallpaper-img]")
    if (!img) return
    const scale = value > 0 ? 1 + Math.min(value, 40) / 110 : 1
    img.style.filter = value > 0 ? `blur(${value}px)` : "none"
    img.style.transform = scale > 1 ? `scale(${scale})` : "none"
  }, [])

  const paintPanelOpacity = useCallback((value: number) => {
    document.documentElement.style.setProperty("--panel-opacity", String(value / 100))
  }, [])


  if (!open) return null

  const preset = wallpaper.source === "preset" ? WALLPAPERS.find((w) => w.id === wallpaper.id) : undefined
  const isCustom = wallpaper.source === "custom"
  const previewUrl = preset
    ? assetUrl(preset.full)
    : isCustom && wallpaper.path
      ? customWallpaperUrl(revision)
      : ""

  const pickLocal = async () => {
    if (!native) {
      fileRef.current?.click()
      return
    }
    setBusy(true)
    try {
      const res = await api.post<{ ok: boolean; path: string; message?: string }>(
        "/api/dialog/wallpaper",
        {},
      )
      if (!res.ok) throw new Error(res.message || "无法打开文件选择框")
      const path = (res.path || "").trim()
      if (!path) return
      onSelect({ ...wallpaper, source: "custom", path })
    } catch (error) {
      toast.error(String(error))
    } finally {
      setBusy(false)
    }
  }

  const uploadFromBrowser = async (file: File | null | undefined) => {
    if (!file) return
    if (!file.type.startsWith("image/")) {
      toast.error("请选择图片文件")
      return
    }
    setBusy(true)
    try {
      const data = await fileToBase64(file)
      const res = await api.post<{ ok: boolean; path: string; message?: string }>(
        "/api/wallpaper/upload",
        { name: file.name, data },
      )
      if (!res.ok || !res.path) throw new Error(res.message || "图片保存失败")
      onSelect({ ...wallpaper, source: "custom", path: res.path })
      toast.success("已载入自定义壁纸")
    } catch (error) {
      toast.error(String(error))
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  return (
    <>
      {/* 点击面板外关闭；透明遮罩不妨碍观察背景效果 */}
      <div className="fixed inset-0 z-40" onClick={close} aria-hidden="true" />
      <aside
        role="dialog"
        aria-label="背景壁纸"
        className="fixed right-4 top-[60px] z-50 flex max-h-[calc(100vh-76px)] w-[384px] flex-col overflow-hidden rounded-lg border bg-popover text-popover-foreground shadow-xl"
      >
        <header className="flex shrink-0 items-start justify-between gap-3 border-b px-4 py-3">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-sm font-semibold">
              <ImageIcon className="h-4 w-4 text-[hsl(var(--brand))]" />
              背景壁纸
            </div>
            <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
              独立的壁纸层，不改变明暗与强调色，可随时关闭。
            </p>
          </div>
          <Button variant="ghost" size="icon-sm" className="-mr-1 -mt-1" onClick={close} title="关闭">
            <X />
          </Button>
        </header>

        <div className="min-h-0 flex-1 space-y-3.5 overflow-y-auto px-4 py-3.5">
          {/* 当前壁纸 */}
          <div className="overflow-hidden rounded-lg border">
            <div className="relative h-[132px] bg-muted/40">
              {previewUrl ? (
                <img
                  key={`${previewUrl}-${revision}`}
                  src={previewUrl}
                  alt="当前壁纸预览"
                  draggable={false}
                  onError={() => setBroken(true)}
                  className="h-full w-full object-cover"
                  style={{ filter: draftBlur ? `blur(${draftBlur}px)` : undefined }}
                />
              ) : (
                <div className="flex h-full flex-col items-center justify-center gap-1.5 text-[11px] text-muted-foreground">
                  <ImageOff className="h-5 w-5 opacity-50" />
                  当前使用纯色背景
                </div>
              )}
              <span className="absolute left-2 top-2 rounded bg-black/55 px-1.5 py-0.5 text-[10px] font-medium text-white">
                {preset ? `预设 · ${preset.style}` : isCustom ? "自定义图片" : "未启用"}
              </span>
              {previewUrl && draftBlur > 0 && (
                <span className="absolute bottom-2 right-2 rounded bg-black/55 px-1.5 py-0.5 text-[10px] font-medium text-white">
                  虚化 {draftBlur}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 border-t px-2.5 py-2">
              <div className="min-w-0 flex-1">
                <div className="truncate text-[11px] font-medium">
                  {preset
                    ? preset.label
                    : isCustom
                      ? wallpaper.path.split(/[\\/]/).pop() || "自定义图片"
                      : "无壁纸"}
                </div>
                <div className="truncate text-[10px] text-muted-foreground">
                  {preset
                    ? preset.credit
                    : isCustom
                      ? customAvailable
                        ? "本地文件 · 随主题配置保存"
                        : "图片已失效，已回退到预设壁纸"
                      : "选择下方任意壁纸即可生效"}
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="h-7 shrink-0 gap-1 px-2 text-[11px]"
                onClick={() => void pickLocal()}
                disabled={busy}
              >
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
                本地图片
              </Button>
            </div>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(event) => void uploadFromBrowser(event.target.files?.[0])}
          />

          {/* 内置预设 */}
          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <Label>内置预设</Label>
              <span className="text-[10px] text-muted-foreground">5 种风格 · 点击立即生效</span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {WALLPAPERS.map((item) => {
                const active = wallpaper.source === "preset" && wallpaper.id === item.id
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => onSelect({ ...wallpaper, source: "preset", id: item.id })}
                    title={item.credit}
                    className={cn(
                      "group relative overflow-hidden rounded-md border text-left transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      active
                        ? "border-primary ring-2 ring-primary/35"
                        : "border-border/70 hover:border-primary/60",
                    )}
                  >
                    <img
                      src={assetUrl(item.thumb)}
                      alt={`${item.label} · ${item.style}`}
                      loading="lazy"
                      draggable={false}
                      className="h-[58px] w-full object-cover transition-transform duration-200 group-hover:scale-[1.05]"
                    />
                    <span className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between gap-1 bg-gradient-to-t from-black/80 via-black/45 to-transparent px-1.5 pb-0.5 pt-2.5">
                      <span className="truncate text-[10px] font-medium text-white">{item.style}</span>
                      <span className="truncate text-[9px] text-white/70">{item.label}</span>
                    </span>
                    {active && (
                      <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-primary-foreground shadow">
                        <Check className="h-2.5 w-2.5" strokeWidth={3} />
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>

          {/* 虚化强度 */}
          <div className="space-y-2 rounded-lg border bg-muted/25 px-3 py-2.5">
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-1.5">
                <Waves className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <Label htmlFor="wallpaper-blur">背景虚化</Label>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-10 text-right text-[11px] tabular-nums text-muted-foreground">
                  {draftBlur === 0 ? "无" : draftBlur}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-1.5 text-[10px]"
                  onClick={() => {
                    draftRef.current.blur = 0
                    setDraftBlur(0)
                    paintBlur(0)
                    onBlurCommit(0)
                  }}
                  disabled={draftBlur === 0}
                  title="恢复为无虚化"
                >
                  <RotateCcw className="h-3 w-3" />
                  复位
                </Button>
              </div>
            </div>
            <input
              id="wallpaper-blur"
              type="range"
              min={0}
              max={WALLPAPER_BLUR_MAX}
              step={1}
              value={draftBlur}
              disabled={!previewUrl}
              style={{ "--range-fill": `${(draftBlur / WALLPAPER_BLUR_MAX) * 100}%` } as CSSProperties}
              onChange={(event) => {
                const value = Number(event.target.value)
                draftRef.current.blur = value
                setDraftBlur(value)
                paintBlur(value)
              }}
              onPointerUp={() => onBlurCommit(draftRef.current.blur)}
              onKeyUp={() => onBlurCommit(draftRef.current.blur)}
              onBlur={() => onBlurCommit(draftRef.current.blur)}
              className="range-accent h-1.5 w-full cursor-pointer appearance-none rounded-full disabled:cursor-not-allowed disabled:opacity-40"
            />
            <div className="flex justify-between text-[9px] text-muted-foreground/85">
              <span>清晰</span>
              <span>柔化</span>
              <span>强虚化</span>
            </div>
          </div>

          {/* 功能面板不透明度 */}
          <div className="space-y-2 rounded-lg border bg-muted/25 px-3 py-2.5">
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-1.5">
                <Layers className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <Label htmlFor="panel-opacity">面板不透明度</Label>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-10 text-right text-[11px] tabular-nums text-muted-foreground">
                  {draftOpacity}%
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-1.5 text-[10px]"
                  onClick={() => {
                    draftRef.current.opacity = PANEL_OPACITY_MAX
                    setDraftOpacity(PANEL_OPACITY_MAX)
                    paintPanelOpacity(PANEL_OPACITY_MAX)
                    onPanelOpacityCommit(PANEL_OPACITY_MAX)
                  }}
                  disabled={draftOpacity === PANEL_OPACITY_MAX}
                  title="恢复为完全不透明"
                >
                  <RotateCcw className="h-3 w-3" />
                  复位
                </Button>
              </div>
            </div>
            <input
              id="panel-opacity"
              type="range"
              min={PANEL_OPACITY_MIN}
              max={PANEL_OPACITY_MAX}
              step={1}
              value={draftOpacity}
              style={
                {
                  "--range-fill": `${((draftOpacity - PANEL_OPACITY_MIN) / (PANEL_OPACITY_MAX - PANEL_OPACITY_MIN)) * 100}%`,
                } as CSSProperties
              }
              onChange={(event) => {
                const value = Number(event.target.value)
                draftRef.current.opacity = value
                setDraftOpacity(value)
                paintPanelOpacity(value)
              }}
              onPointerUp={() => onPanelOpacityCommit(draftRef.current.opacity)}
              onKeyUp={() => onPanelOpacityCommit(draftRef.current.opacity)}
              onBlur={() => onPanelOpacityCommit(draftRef.current.opacity)}
              className="range-accent h-1.5 w-full cursor-pointer appearance-none rounded-full disabled:cursor-not-allowed disabled:opacity-40"
            />
            <div className="flex justify-between text-[9px] text-muted-foreground/85">
              <span>通透 {PANEL_OPACITY_MIN}%</span>
              <span>半透</span>
              <span>实底 {PANEL_OPACITY_MAX}%</span>
            </div>
            <p className="text-[10px] leading-4 text-muted-foreground/85">
              控制卡片、结果区等白色功能框的底色透明度；文字始终不透明，调低后能透出壁纸。
            </p>
          </div>

          {broken && isCustom && (
            <p className="rounded-md border border-[hsl(var(--warning)/0.35)] bg-[hsl(var(--warning)/0.08)] px-2.5 py-1.5 text-[10px] leading-4 text-[hsl(var(--warning))]">
              本地图片读取失败，已回退到预设壁纸；重新选择一张图片即可恢复。
            </p>
          )}
        </div>

        <footer className="flex shrink-0 items-center justify-between gap-2 border-t px-4 py-2.5">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1 px-2 text-[11px]"
            onClick={() => onSelect({ ...NO_WALLPAPER, blur: 0 })}
            disabled={wallpaper.source === "none"}
          >
            <ImageOff className="h-3.5 w-3.5" />
            不使用壁纸
          </Button>
          <span className="text-[10px] text-muted-foreground">改动随主题自动保存</span>
        </footer>
      </aside>
    </>
  )
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result || "")
      resolve(result.includes(",") ? result.split(",")[1] : result)
    }
    reader.onerror = () => reject(new Error("读取图片失败"))
    reader.readAsDataURL(file)
  })
}
