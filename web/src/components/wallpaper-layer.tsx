import { useEffect, useMemo, useState } from "react"
import { assetUrl, customWallpaperUrl, findWallpaper, type WallpaperSource } from "@/lib/api"

export interface WallpaperState {
  source: WallpaperSource
  id: string
  path: string
  blur: number
  /** 功能面板不透明度 30-100；100 为完全不透明（原样） */
  panelOpacity: number
}

export const NO_WALLPAPER: WallpaperState = {
  source: "none",
  id: "",
  path: "",
  blur: 0,
  panelOpacity: 100,
}

interface Props {
  wallpaper: WallpaperState
  /** 自定义图片变化时递增，用来刷新 <img> 缓存 */
  revision: number
  onError: () => void
}

/**
 * 固定在最底层的壁纸层：图片 + 主题色蒙版。
 * 蒙版保证浅色/深色主题下正文仍然可读，同时不改变任何颜色令牌。
 */
/** 只在真正换图时重渲染：虚化/不透明度由 CSS 变量直接驱动，避免整页重绘 */
const blurScale = (blur: number) => (blur > 0 ? 1 + Math.min(blur, 40) / 110 : 1)

export function WallpaperLayer({ wallpaper, revision, onError }: Props) {
  const preset = findWallpaper(wallpaper.id)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    setFailed(false)
  }, [wallpaper.source, wallpaper.id, wallpaper.path, revision])

  const url = useMemo(() => {
    if (wallpaper.source === "preset" && preset) return assetUrl(preset.full)
    if (wallpaper.source === "custom" && wallpaper.path) return customWallpaperUrl(revision)
    return ""
  }, [wallpaper.source, wallpaper.path, preset, revision])

  const show = Boolean(url) && !failed
  const blur = Math.max(0, wallpaper.blur || 0)
  const scale = blurScale(blur)

  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 overflow-hidden bg-background">
      {show && (
        <img
          key={`${url}-${revision}`}
          src={url}
          alt=""
          data-wallpaper-img=""
          draggable={false}
          onError={() => {
            setFailed(true)
            onError()
          }}
          className="h-full w-full select-none object-cover"
          style={{
            filter: blur ? `blur(${blur}px)` : "none",
            transform: scale > 1 ? `scale(${scale})` : "none",
          }}
        />
      )}
      {show && (
        <div
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(180deg, hsl(var(--background) / var(--wp-veil-1)) 0%, hsl(var(--background) / var(--wp-veil-2)) 52%, hsl(var(--background) / var(--wp-veil-3)) 100%)",
          }}
        />
      )}
    </div>
  )
}
