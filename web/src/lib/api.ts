export type Kind = "word" | "excel" | "powerpoint" | ""

export interface Rule {
  find: string
  replace: string
  regex: boolean
  case_sensitive: boolean
  whole_word: boolean
}

export interface Scope {
  body: boolean
  table: boolean
  header_footer: boolean
  notes: boolean
  sheets: string[]
}

export interface FileEntry {
  path: string
  name: string
  folder: string
  kind: Kind
  kind_label: string
  exists: boolean
}

export interface Hit {
  location: string
  region: string
  before: string
  matched: string
  after: string
  replacement: string
}

export interface Scan {
  path: string
  name: string
  folder: string
  kind: Kind
  kind_label: string
  ok: boolean
  error: string
  error_code: string
  hit_count: number
  element_count: number
  excluded_hits: number
  truncated: boolean
  duration: number
  hits: Hit[]
  hits_shown: number
  excluded: { location: string; reason: string; count: number }[]
}

export interface FileResultRow {
  path: string
  name: string
  folder: string
  kind: Kind
  kind_label: string
  status: "success" | "no_match" | "skipped" | "error" | "cancelled"
  status_label: string
  hits: number
  elements: number
  skipped: number
  message: string
  notes: string[]
  backup: string
  duration: number
}

export interface LogLine {
  level: string
  text: string
  ts: number
}

export interface Summary {
  files?: number
  hits?: number
  matched_files?: number
  errors?: number
  skipped?: number
  success?: number
  no_match?: number
  error?: number
  cancelled?: number
  seconds?: number
  run_dir?: string
}

export interface JobSnapshot {
  id: string
  mode: "preview" | "apply"
  status: "running" | "done" | "cancelled" | "error"
  total: number
  done: number
  current: string
  error: string
  summary: Summary
  scans: Scan[]
  results: FileResultRow[]
  logs: LogLine[]
  counts: { scans: number; results: number; logs: number }
}

export interface Settings {
  cli_path: string
  keep_backup: boolean
  verify_after: boolean
  backup_root: string
  last_dir: string
  recursive_scan: boolean
  max_files: number
  theme: string
  accent: string
  wallpaper_source: WallpaperSource
  wallpaper_id: string
  wallpaper_path: string
  wallpaper_blur: number
  /** 功能面板（卡片）不透明度 30-100 */
  wallpaper_panel_opacity: number
  /** 仅保存/引导接口返回：当前自定义图片是否仍可读 */
  wallpaper_exists?: boolean
}

export interface Bootstrap {
  ok: boolean
  app: { title: string; subtitle: string; version: string }
  cli: { found: boolean; version: string; origin: string; path: string }
  settings: Settings
  platform: string
  wallpaper_exists?: boolean
}

declare global {
  interface Window {
    __OFFICE_REPLACER_API__?: string
    __OFFICE_REPLACER_NATIVE__?: boolean
  }
}

const BASE = (window.__OFFICE_REPLACER_API__ || "").replace(/\/$/, "")

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  })
  const data = (await res.json()) as T & { message?: string }
  if (!res.ok) {
    throw new Error((data as { message?: string }).message || `请求失败 (${res.status})`)
  }
  return data
}

export const api = {
  bootstrap: () => request<Bootstrap>("/api/bootstrap"),
  post: <T>(path: string, body: unknown = {}) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  job: (id: string, since: { scans: number; results: number; logs: number }) =>
    request<{ ok: boolean } & JobSnapshot>(
      `/api/job?id=${encodeURIComponent(id)}&since_scan=${since.scans}&since_result=${since.results}&since_log=${since.logs}`,
    ),
}

export const THEMES = [
  { mode: "light", label: "浅色" },
  { mode: "dark", label: "深色" },
] as const

export const ACCENTS = [
  { id: "zinc", label: "石墨", hex: "#27272a", dark: "#fafafa" },
  { id: "blue", label: "湛蓝", hex: "#2563eb", dark: "#60a5fa" },
  { id: "violet", label: "紫罗兰", hex: "#7c3aed", dark: "#a78bfa" },
  { id: "emerald", label: "翡翠", hex: "#059669", dark: "#34d399" },
  { id: "rose", label: "玫瑰", hex: "#e11d48", dark: "#fb7185" },
  { id: "amber", label: "琥珀", hex: "#d97706", dark: "#fbbf24" },
] as const

export type AccentId = (typeof ACCENTS)[number]["id"]

/* ------------------------------------------------------------------ 背景壁纸 */

export type WallpaperSource = "none" | "preset" | "custom"

export interface WallpaperPreset {
  id: string
  label: string
  /** 风格分类，用于缩略图下方的标签 */
  style: string
  /** 必应壁纸的原始标题，作为 title 提示与无障碍描述 */
  credit: string
  /** 缩略预览（480×270） */
  thumb: string
  /** 应用为背景的完整图（1920×1080） */
  full: string
}

const WALLPAPER_BASE = "wallpapers"

export const WALLPAPERS: WallpaperPreset[] = [
  {
    id: "nature",
    label: "北窗拱门",
    style: "自然",
    credit: "北窗，拱门国家公园，犹他州（必应壁纸）",
    thumb: `${WALLPAPER_BASE}/thumbs/nature.jpg`,
    full: `${WALLPAPER_BASE}/nature.jpg`,
  },
  {
    id: "city",
    label: "河畔老城",
    style: "城市",
    credit: "特里亚纳历史街区，塞维利亚（必应壁纸）",
    thumb: `${WALLPAPER_BASE}/thumbs/city.jpg`,
    full: `${WALLPAPER_BASE}/city.jpg`,
  },
  {
    id: "minimal",
    label: "石墙晚霞",
    style: "极简",
    credit: "湖区石墙与晚霞，英格兰（必应壁纸）",
    thumb: `${WALLPAPER_BASE}/thumbs/minimal.jpg`,
    full: `${WALLPAPER_BASE}/minimal.jpg`,
  },
  {
    id: "anime",
    label: "云海黄昏",
    style: "动漫",
    credit: "动画电影质感的云海晚霞插画（公开壁纸）",
    thumb: `${WALLPAPER_BASE}/thumbs/anime.jpg`,
    full: `${WALLPAPER_BASE}/anime.jpg`,
  },
  {
    id: "starry",
    label: "林间星空",
    style: "夜景",
    credit: "松林仰望银河夜空（公开壁纸）",
    thumb: `${WALLPAPER_BASE}/thumbs/starry.jpg`,
    full: `${WALLPAPER_BASE}/starry.jpg`,
  },
]

export const WALLPAPER_BLUR_MAX = 40
export const PANEL_OPACITY_MIN = 45
export const PANEL_OPACITY_MAX = 100

export function findWallpaper(id: string): WallpaperPreset | undefined {
  return WALLPAPERS.find((item) => item.id === id)
}

/** 前端解析相对资源时要带上 <base>，打包后 base 是 ./ */
export function assetUrl(path: string): string {
  if (!path) return ""
  if (/^(https?:|data:|blob:|file:)/i.test(path)) return path
  return new URL(path, document.baseURI).toString()
}

/** 自定义壁纸经由本地服务读取，避免 Chromium 直接访问 file:// */
export function customWallpaperUrl(version = 0): string {
  return `${BASE || ""}/api/wallpaper?v=${version}`
}
