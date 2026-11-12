import { useState } from "react"
import {
  FilePlus2,
  FileSpreadsheet,
  FileText,
  FolderPlus,
  ListX,
  Presentation,
  Trash2,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { api, type FileEntry } from "@/lib/api"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import { Textarea } from "@/components/ui/input"

interface Props {
  files: FileEntry[]
  onFiles: (files: FileEntry[]) => void
  busy: boolean
  native: boolean
}

const KIND_ICON: Record<string, typeof FileText> = {
  word: FileText,
  excel: FileSpreadsheet,
  powerpoint: Presentation,
}

const KIND_TONE: Record<string, string> = {
  word: "bg-blue-500/12 text-blue-600 dark:text-blue-400",
  excel: "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400",
  powerpoint: "bg-orange-500/12 text-orange-600 dark:text-orange-400",
}

export function FilePanel({ files, onFiles, busy, native }: Props) {
  const [pasting, setPasting] = useState(false)
  const [pasteText, setPasteText] = useState("")
  const [dragging, setDragging] = useState(false)

  const addPaths = async (paths: string[]) => {
    if (!paths.length) return
    try {
      const res = await api.post<{ ok: boolean; files: FileEntry[]; notes: string[] }>(
        "/api/add-paths",
        { paths },
      )
      const known = new Set(files.map((f) => f.path.toLowerCase()))
      const fresh = res.files.filter((f) => !known.has(f.path.toLowerCase()))
      onFiles([...files, ...fresh])
      res.notes.forEach((note) => toast.warning(note))
      if (fresh.length) toast.success(`已添加 ${fresh.length} 个文件`)
      else if (!res.notes.length) toast.info("没有新文件")
    } catch (error) {
      toast.error(String(error))
    }
  }

  const pickFiles = async () => {
    try {
      const res = await api.post<{ ok: boolean; files: string[] }>("/api/dialog/files", {})
      await addPaths(res.files)
    } catch (error) {
      toast.error(String(error))
    }
  }

  const pickFolder = async () => {
    try {
      const res = await api.post<{ ok: boolean; folder: string }>("/api/dialog/folder", {})
      if (res.folder) await addPaths([res.folder])
    } catch (error) {
      toast.error(String(error))
    }
  }

  const submitPaste = async () => {
    const paths = pasteText
      .split(/\r?\n/)
      .map((line) => line.trim().replace(/^"|"$/g, ""))
      .filter(Boolean)
    setPasting(false)
    setPasteText("")
    await addPaths(paths)
  }

  const remove = (path: string) => onFiles(files.filter((f) => f.path !== path))

  // 桌面模式下真实路径由 Qt 注入；浏览器预览时只做视觉反馈。
  const onDrop = (event: React.DragEvent) => {
    event.preventDefault()
    setDragging(false)
    if (native) return
    const paths = Array.from(event.dataTransfer.files).map((f) => f.name)
    if (paths.length) {
      toast.info("浏览器预览无法读取完整路径，请在桌面窗口里拖放，或使用「添加文件」")
    }
  }

  return (
    <Card className="flex min-h-0 flex-1 flex-col">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <div className="flex items-center gap-2">
          <CardTitle>待处理文件</CardTitle>
          <Badge variant="muted">{files.length}</Badge>
        </div>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              disabled={busy || !files.length}
              onClick={() => onFiles([])}
            >
              <ListX />
            </Button>
          </TooltipTrigger>
          <TooltipContent>清空列表</TooltipContent>
        </Tooltip>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col gap-3">
        <div className="grid grid-cols-2 gap-2">
          <Button onClick={pickFiles} disabled={busy} size="sm">
            <FilePlus2 /> 添加文件
          </Button>
          <Button variant="outline" onClick={pickFolder} disabled={busy} size="sm">
            <FolderPlus /> 添加文件夹
          </Button>
        </div>

        <div
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => !busy && setPasting((v) => !v)}
          className={cn(
            "flex h-[68px] cursor-pointer flex-col items-center justify-center gap-0.5 rounded-lg border border-dashed text-[11px] transition-colors",
            dragging
              ? "border-primary bg-[hsl(var(--brand)/0.07)] text-foreground"
              : "border-border text-muted-foreground hover:border-primary/50 hover:bg-accent/40",
          )}
        >
          <span className="font-medium">拖入文件或文件夹</span>
          <span className="opacity-70">也可点击此处批量粘贴完整路径</span>
        </div>

        {pasting && (
          <div className="space-y-2 rounded-lg border p-2">
            <Textarea
              autoFocus
              value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
              placeholder={"每行一个路径，例如：\nD:\\报告\\初稿.docx\nD:\\汇报"}
              className="min-h-[76px] font-mono text-[11px]"
            />
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setPasting(false)}>
                取消
              </Button>
              <Button size="sm" onClick={submitPaste} disabled={!pasteText.trim()}>
                添加
              </Button>
            </div>
          </div>
        )}

        <ScrollArea className="min-h-0 flex-1 rounded-lg border">
          <div className="p-1.5">
            {!files.length && (
              <div className="flex h-32 flex-col items-center justify-center gap-1 text-center text-[11px] text-muted-foreground">
                <FileText className="h-6 w-6 opacity-40" />
                还没有文件
                <span className="opacity-70">支持 .docx / .xlsx / .pptx</span>
              </div>
            )}
            {files.map((file) => {
              const Icon = KIND_ICON[file.kind] || FileText
              return (
                <div
                  key={file.path}
                  className="group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-accent"
                >
                  <span
                    className={cn(
                      "flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
                      KIND_TONE[file.kind] || "bg-muted text-muted-foreground",
                    )}
                  >
                    <Icon className="h-3.5 w-3.5" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-xs font-medium" title={file.name}>
                      {file.name}
                    </div>
                    <div className="mono-path truncate text-muted-foreground" title={file.folder}>
                      {file.folder}
                    </div>
                  </div>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        className="opacity-0 group-hover:opacity-100"
                        disabled={busy}
                        onClick={() => remove(file.path)}
                      >
                        <Trash2 className="text-destructive" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>从列表移除（不会删除文件）</TooltipContent>
                  </Tooltip>
                </div>
              )
            })}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}
