import { ScrollText } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { LogLine } from "@/lib/api"
import { cn } from "@/lib/utils"

export function LogPanel({ logs }: { logs: LogLine[] }) {
  if (!logs.length) {
    return (
      <div className="panel-surface-soft flex h-full flex-col items-center justify-center gap-2 rounded-lg border text-center text-xs text-muted-foreground">
        <ScrollText className="h-8 w-8 opacity-35" />
        <div className="font-medium text-foreground">暂无日志</div>
        <div>预览、替换过程中的每一步都会记录在这里</div>
      </div>
    )
  }
  return (
    <ScrollArea className="panel-surface-soft h-full rounded-lg border">
      <div className="space-y-0.5 p-3 font-mono text-[11px] leading-5">
        {logs.map((line, index) => (
          <div key={`${line.ts}-${index}`} className="flex gap-2.5">
            <span className="shrink-0 tabular-nums text-muted-foreground/70">
              {new Date(line.ts).toLocaleTimeString("zh-CN", { hour12: false })}
            </span>
            <span
              className={cn(
                "w-12 shrink-0 uppercase",
                line.level === "error" && "text-destructive",
                line.level === "warn" && "text-[hsl(var(--warning))]",
                line.level === "info" && "text-[hsl(var(--brand))]",
              )}
            >
              {line.level}
            </span>
            <span className="break-all text-foreground/85">{line.text}</span>
          </div>
        ))}
      </div>
    </ScrollArea>
  )
}
