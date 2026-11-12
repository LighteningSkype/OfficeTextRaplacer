import { useEffect, useState } from "react"
import { FolderOpen, RefreshCw } from "lucide-react"
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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { api, type Settings } from "@/lib/api"
import { toast } from "sonner"

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  settings: Settings
  onSave: (next: Settings) => void
  cliFound: boolean
  cliVersion: string
  onProbe: () => void
}

export function SettingsDialog({
  open,
  onOpenChange,
  settings,
  onSave,
  cliFound,
  cliVersion,
  onProbe,
}: Props) {
  const [draft, setDraft] = useState<Settings>(settings)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (open) setDraft(settings)
  }, [open, settings])

  const pick = async () => {
    try {
      const res = await api.post<{ ok: boolean; path: string }>("/api/dialog/cli", {
        start_dir: draft.cli_path,
      })
      if (res.path) setDraft((d) => ({ ...d, cli_path: res.path }))
    } catch (error) {
      toast.error(String(error))
    }
  }

  const save = async () => {
    setBusy(true)
    try {
      const res = await api.post<{ ok: boolean; settings: Settings }>("/api/settings", draft)
      onSave(res.settings)
      onProbe()
      toast.success("设置已保存")
      onOpenChange(false)
    } catch (error) {
      toast.error(String(error))
    } finally {
      setBusy(false)
    }
  }

  const field = (key: keyof Settings, value: unknown) =>
    setDraft((d) => ({ ...d, [key]: value }) as Settings)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>设置</DialogTitle>
          <DialogDescription>
            office-cli 是替换引擎，本工具通过它读写 Word / Excel / PowerPoint。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <Alert variant={cliFound ? "success" : "destructive"}>
            <AlertDescription>
              {cliFound
                ? `已检测到 office-cli ${cliVersion}，可正常使用。`
                : "未检测到 office-cli，预览与替换不可用。可留空自动搜索，或手动指定可执行文件。"}
            </AlertDescription>
          </Alert>

          <div className="space-y-1.5">
            <Label>office-cli 可执行文件</Label>
            <div className="flex gap-2">
              <Input
                value={draft.cli_path}
                placeholder="留空则自动搜索 PATH / npm 全局目录"
                onChange={(e) => field("cli_path", e.target.value)}
              />
              <Button variant="outline" size="icon" onClick={pick} title="浏览">
                <FolderOpen />
              </Button>
              <Button variant="outline" size="icon" onClick={onProbe} title="重新检测">
                <RefreshCw />
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>备份目录</Label>
              <Input
                value={draft.backup_root}
                onChange={(e) => field("backup_root", e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label>单次最多处理文件数</Label>
              <Input
                type="number"
                min={1}
                max={2000}
                value={draft.max_files}
                onChange={(e) => field("max_files", Number(e.target.value) || 500)}
              />
            </div>
          </div>

          <div className="space-y-3 rounded-lg border p-3.5">
            <Row
              id="keep-backup"
              title="替换前自动备份"
              desc="每次运行生成独立备份目录，可一键撤销"
              checked={draft.keep_backup}
              onChange={(v) => field("keep_backup", v)}
            />
            <Row
              id="verify"
              title="写回前校验文档结构"
              desc="用 OpenXML 校验器确认副本合法后才覆盖原文件"
              checked={draft.verify_after}
              onChange={(v) => field("verify_after", v)}
            />
            <Row
              id="recursive"
              title="递归扫描子文件夹"
              desc="添加文件夹时包含所有下级目录"
              checked={draft.recursive_scan}
              onChange={(v) => field("recursive_scan", v)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={save} disabled={busy}>
            保存设置
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Row({
  id,
  title,
  desc,
  checked,
  onChange,
}: {
  id: string
  title: string
  desc: string
  checked: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <div className="flex items-start gap-3">
      <Checkbox id={id} checked={checked} onCheckedChange={(v) => onChange(Boolean(v))} className="mt-0.5" />
      <label htmlFor={id} className="flex-1 cursor-pointer leading-tight">
        <div className="text-xs font-medium">{title}</div>
        <div className="mt-0.5 text-[11px] text-muted-foreground">{desc}</div>
      </label>
    </div>
  )
}
