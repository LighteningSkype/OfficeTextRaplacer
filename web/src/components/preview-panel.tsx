import { useState } from "react"
import { ChevronDown, ChevronRight, FileSearch, Info, TriangleAlert } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { Scan, Summary } from "@/lib/api"
import { cn } from "@/lib/utils"

interface Props {
  scans: Scan[]
  summary: Summary
}

export function StatCards({
  items,
}: {
  items: { label: string; value: number | string; tone?: "brand" | "success" | "warning" | "danger" }[]
}) {
  const toneClass: Record<string, string> = {
    brand: "text-[hsl(var(--brand))]",
    success: "text-[hsl(var(--success))]",
    warning: "text-[hsl(var(--warning))]",
    danger: "text-destructive",
  }
  return (
    <div className="grid grid-cols-4 gap-2.5">
      {items.map((item) => (
        <Card key={item.label} className="px-3.5 py-2.5">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
            {item.label}
          </div>
          <div
            className={cn(
              "mt-1 text-xl font-semibold tabular-nums",
              item.value === 0 || item.value === "0"
                ? "text-muted-foreground"
                : toneClass[item.tone || "brand"],
            )}
          >
            {item.value}
          </div>
        </Card>
      ))}
    </div>
  )
}

export function PreviewPanel({ scans, summary }: Props) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})

  if (!scans.length) {
    return (
      <div className="panel-surface-soft flex h-full flex-col items-center justify-center gap-2 rounded-lg border text-center text-xs text-muted-foreground">
        <FileSearch className="h-8 w-8 opacity-35" />
        <div className="font-medium text-foreground">还没有预览结果</div>
        <div>配置规则后点击「预览匹配」，这里会逐条显示命中位置与替换效果</div>
      </div>
    )
  }

  const toggle = (path: string) =>
    setCollapsed((prev) => ({ ...prev, [path]: !prev[path] }))

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <StatCards
        items={[
          { label: "已扫描文件", value: summary.files ?? scans.length },
          { label: "命中处数", value: summary.hits ?? 0, tone: "brand" },
          { label: "命中文件", value: summary.matched_files ?? 0, tone: "success" },
          { label: "读取失败", value: summary.errors ?? 0, tone: "danger" },
        ]}
      />

      <ScrollArea className="min-h-0 flex-1 rounded-lg border">
        <div className="divide-y divide-[hsl(var(--grid-line))]">
          {scans.map((scan) => {
            const isCollapsed = collapsed[scan.path]
            return (
              <div key={scan.path}>
                <button
                  type="button"
                  onClick={() => toggle(scan.path)}
                  className="panel-surface flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-accent/60"
                >
                  {isCollapsed ? (
                    <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  )}
                  <span className="truncate text-xs font-medium">{scan.name}</span>
                  <Badge variant="muted">{scan.kind_label}</Badge>
                  {scan.error ? (
                    <Badge variant="destructive">读取失败</Badge>
                  ) : scan.hit_count ? (
                    <Badge variant="brand">{scan.hit_count} 处</Badge>
                  ) : (
                    <Badge variant="muted">无匹配</Badge>
                  )}
                  {scan.excluded_hits > 0 && (
                    <Badge variant="warning">{scan.excluded_hits} 处跳过</Badge>
                  )}
                  <span className="mono-path ml-auto hidden truncate text-right text-muted-foreground xl:block">
                    {scan.folder}
                  </span>
                </button>

                {!isCollapsed && (
                  <div className="bg-background/25 px-3 pb-3 pl-8 pt-1">
                    {scan.error && (
                      <Alert variant="destructive" className="my-2">
                        <TriangleAlert />
                        <AlertDescription>{scan.error}</AlertDescription>
                      </Alert>
                    )}
                    {scan.truncated && (
                      <Alert variant="warning" className="my-2">
                        <Info />
                        <AlertDescription>
                          命中较多，仅展示前 {scan.hits_shown} 条；实际替换数量以统计为准。
                        </AlertDescription>
                      </Alert>
                    )}
                    {scan.hits.length > 0 && (
                      <div className="overflow-hidden rounded-md border">
                        <table className="w-full text-[11px]">
                          <thead className="bg-muted/60 text-muted-foreground">
                            <tr>
                              <th className="w-40 px-2.5 py-1.5 text-left font-medium">位置</th>
                              <th className="px-2.5 py-1.5 text-left font-medium">上下文与命中</th>
                              <th className="w-44 px-2.5 py-1.5 text-left font-medium">替换为</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-[hsl(var(--grid-line))]">
                            {scan.hits.map((hit, index) => (
                              <tr key={`${scan.path}-${index}`} className="hover:bg-accent/40">
                                <td className="px-2.5 py-1.5 align-top text-muted-foreground">
                                  <span className="font-mono">{hit.location}</span>
                                  <div className="mt-0.5 text-[10px] opacity-70">{hit.region}</div>
                                </td>
                                <td className="px-2.5 py-1.5 align-top leading-5">
                                  <span className="text-muted-foreground">{hit.before}</span>
                                  <span className="brand-chip mx-0.5 line-through decoration-1">
                                    {hit.matched}
                                  </span>
                                  <span className="text-muted-foreground">{hit.after}</span>
                                </td>
                                <td className="px-2.5 py-1.5 align-top">
                                  <span className="rounded bg-[hsl(var(--success)/0.14)] px-1.5 py-0.5 font-medium text-[hsl(var(--success))]">
                                    {hit.replacement || "（删除）"}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                    {scan.excluded.length > 0 && (
                      <div className="mt-2 rounded-md border border-[hsl(var(--warning)/0.25)] bg-[hsl(var(--warning)/0.06)] px-2.5 py-2 text-[11px]">
                        <span className="font-medium">自动跳过（避免破坏公式或日期）：</span>
                        <span className="ml-1 text-muted-foreground">
                          {scan.excluded
                            .slice(0, 6)
                            .map((item) => `${item.location} ${item.reason}`)
                            .join("；")}
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </ScrollArea>
    </div>
  )
}
