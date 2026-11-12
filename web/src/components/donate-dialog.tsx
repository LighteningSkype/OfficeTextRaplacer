import { Coffee, Heart } from "lucide-react"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import { assetUrl } from "@/lib/api"

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function DonateDialog({ open, onOpenChange }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[380px] gap-3.5 p-5">
        <div className="flex flex-col items-center gap-1 text-center">
          <div className="mb-1 flex h-10 w-10 items-center justify-center rounded-full bg-[hsl(var(--brand)/0.14)] text-[hsl(var(--brand-ink))]">
            <Coffee className="h-5 w-5" />
          </div>
          <DialogTitle className="text-base">请开发者喝个咖啡！</DialogTitle>
          <DialogDescription>
            这个小工具如果帮你省下了时间，欢迎扫码支持后续维护。
          </DialogDescription>
        </div>

        <div className="mx-auto w-full max-w-[252px]">
          <div className="rounded-xl border bg-white p-2.5 shadow-sm">
            <img
              src={assetUrl("donate-qr.png")}
              alt="微信收款码"
              width={252}
              height={252}
              draggable={false}
              className="block h-auto w-full select-none rounded-md [image-rendering:-webkit-optimize-contrast]"
            />
          </div>
          <p className="mt-2 text-center text-[11px] text-muted-foreground">
            微信扫码 · 金额随意，心意就好
          </p>
        </div>

        <div className="flex items-center justify-center gap-1.5 text-[11px] text-muted-foreground">
          <Heart className="h-3.5 w-3.5 text-[hsl(var(--brand))]" />
          感谢每一位使用者，也感谢每一杯咖啡
        </div>
      </DialogContent>
    </Dialog>
  )
}
