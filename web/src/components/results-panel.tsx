import {
  ClipboardCopy,
  ExternalLink,
  FolderOpen,
  FolderSearch,
  History,
  MousePointerClick,
  ShieldAlert,
} from "lucide-react"
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuLabel,
  ContextMenuSeparator,
  ContextMenuShortcut,
  ContextMenuTrigger,
} from "@/components/ui/context-menu"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { api, type FileResultRow, type Summary } from "@/lib/api"
import { toast } from "sonner"
import { StatCards } from "./preview-panel"

interface Props {
  results: FileResultRow[]
  summary: Summary
}

const STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "muted" | "brand"> = {
  success: "success",
  no_match: "muted",
  skipped: "warning",
  error: "destructive",
  cancelled: "muted",
}

export function ResultsPanel({ results, summary }: Props) {
  const act = async (path: string, endpoint: string, successMessage: string) => {
    try {
      const res = await api.post<{ ok: boolean; message: string }>(endpoint, { path })
      if (res.ok) toast.success(successMessage)
      else toast.error(res.message || "操作失败")
    } catch (error) {
      toast.error(String(error))
    }
  }

  const copy = async (text: string, label: string) => {
    try {
      await api.post("/api/clipboard", { text })
      toast.success(`已复制${label}`)
    } catch {
      try {
        await navigator.clipboard.writeText(text)
        toast.success(`已复制${label}`)
      } catch (error) {
        toast.error(String(error))
      }
    }
  }

  if (!results.length) {
    return (
      <div className="panel-surface-soft flex h-full flex-col items-center justify-center gap-2 rounded-lg border text-center text-xs text-muted-foreground">
        <MousePointerClick className="h-8 w-8 opacity-35" />
        <div className="font-medium text-foreground">还没有替换结果</div>
        <div>执行替换后，这里会显示每个文件的状态、命中数与跳过原因</div>
        <div className="mt-1 rounded-md border px-2.5 py-1.5 text-[11px]">
          提示：在结果行上<strong className="mx-1">右键</strong>可在文件管理器中定位文件
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <StatCards
        items={[
          { label: "处理文件", value: results.length },
          { label: "成功替换", value: summary.success ?? 0, tone: "success" },
          { label: "命中处数", value: summary.hits ?? 0, tone: "brand" },
          {
            label: "失败 / 跳过",
            value: (summary.error ?? 0) + (summary.skipped ?? 0),
            tone: "danger",
          },
        ]}
      />

      <ScrollArea className="panel-surface-soft min-h-0 flex-1 rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-24">状态</TableHead>
              <TableHead className="w-[26%]">文件</TableHead>
              <TableHead className="w-16 text-right">命中</TableHead>
              <TableHead className="w-16 text-right">跳过</TableHead>
              <TableHead>说明</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {results.map((row) => (
              <ContextMenu key={row.path + row.status}>
                <ContextMenuTrigger asChild>
                  <TableRow className="cursor-default">
                    <TableCell>
                      <Badge variant={STATUS_VARIANT[row.status] || "muted"}>
                        {row.status_label}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <div className="min-w-0">
                            <div className="truncate font-medium">{row.name}</div>
                            <div className="mono-path truncate text-muted-foreground">
                              {row.folder}
                            </div>
                          </div>
                        </TooltipTrigger>
                        <TooltipContent side="bottom" className="max-w-md break-all">
                          {row.path}
                          <div className="mt-1 opacity-70">
                            {row.kind_label} · {row.duration}s
                          </div>
                        </TooltipContent>
                      </Tooltip>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{row.hits}</TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {row.skipped}
                    </TableCell>
                    <TableCell>
                      <div className="truncate text-muted-foreground" title={row.message}>
                        {row.message}
                      </div>
                      {row.notes.map((note, index) => (
                        <div key={index} className="truncate text-[10px] text-[hsl(var(--warning))]">
                          {note}
                        </div>
                      ))}
                    </TableCell>
                  </TableRow>
                </ContextMenuTrigger>

                <ContextMenuContent>
                  <ContextMenuLabel className="max-w-[16rem] truncate" title={row.path}>
                    {row.name}
                  </ContextMenuLabel>
                  <ContextMenuSeparator />
                  <ContextMenuItem onSelect={() => act(row.path, "/api/reveal", "已在文件管理器中定位")}>
                    <FolderSearch /> 在文件管理器中显示
                    <ContextMenuShortcut>选中文件</ContextMenuShortcut>
                  </ContextMenuItem>
                  <ContextMenuItem onSelect={() => act(row.path, "/api/open-folder", "已打开所在文件夹")}>
                    <FolderOpen /> 打开所在文件夹
                  </ContextMenuItem>
                  <ContextMenuItem onSelect={() => act(row.path, "/api/open-file", "已用默认程序打开")}>
                    <ExternalLink /> 用默认程序打开文件
                  </ContextMenuItem>

                  {row.backup && (
                    <>
                      <ContextMenuSeparator />
                      <ContextMenuLabel>替换前备份</ContextMenuLabel>
                      <ContextMenuItem
                        onSelect={() => act(row.backup, "/api/reveal", "已定位备份文件")}
                      >
                        <History /> 在文件管理器中显示备份
                      </ContextMenuItem>
                      <ContextMenuItem
                        onSelect={() => act(row.backup, "/api/open-folder", "已打开备份目录")}
                      >
                        <FolderOpen /> 打开备份目录
                      </ContextMenuItem>
                    </>
                  )}

                  <ContextMenuSeparator />
                  <ContextMenuItem onSelect={() => copy(row.path, "完整路径")}>
                    <ClipboardCopy /> 复制完整路径
                  </ContextMenuItem>
                  <ContextMenuItem onSelect={() => copy(row.folder, "所在文件夹")}>
                    <ClipboardCopy /> 复制所在文件夹
                  </ContextMenuItem>
                  {row.message && (
                    <ContextMenuItem onSelect={() => copy(row.message, "说明")}>
                      <ShieldAlert /> 复制状态说明
                    </ContextMenuItem>
                  )}
                </ContextMenuContent>
              </ContextMenu>
            ))}
          </TableBody>
        </Table>
      </ScrollArea>

      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <MousePointerClick className="h-3 w-3" />
        在任意结果行右键：定位文件、打开备份、复制路径
        {summary.run_dir && (
          <span className="mono-path ml-auto truncate" title={summary.run_dir}>
            备份：{summary.run_dir}
          </span>
        )}
      </div>
    </div>
  )
}
