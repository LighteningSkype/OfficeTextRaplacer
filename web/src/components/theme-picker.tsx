import { Check, Monitor, Moon, Palette, Sun } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { ACCENTS, THEMES, type AccentId } from "@/lib/api"
import { cn } from "@/lib/utils"

interface Props {
  mode: "light" | "dark"
  accent: AccentId
  onMode: (mode: "light" | "dark") => void
  onAccent: (accent: AccentId) => void
}

export function ThemePicker({ mode, accent, onMode, onAccent }: Props) {
  return (
    <div className="flex items-center gap-1">
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="切换明暗主题"
            onClick={() => onMode(mode === "dark" ? "light" : "dark")}
          >
            {mode === "dark" ? <Sun /> : <Moon />}
          </Button>
        </TooltipTrigger>
        <TooltipContent>{mode === "dark" ? "切换到浅色" : "切换到深色"}</TooltipContent>
      </Tooltip>

      <DropdownMenu>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label="主题配色">
                <Palette />
              </Button>
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent>主题配色</TooltipContent>
        </Tooltip>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel className="flex items-center gap-1.5">
            <Monitor className="h-3 w-3" /> 外观模式
          </DropdownMenuLabel>
          {THEMES.map((item) => (
            <DropdownMenuItem key={item.mode} onSelect={() => onMode(item.mode)}>
              {item.mode === "dark" ? <Moon /> : <Sun />}
              <span className="flex-1">{item.label}</span>
              {mode === item.mode && <Check className="text-primary" />}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuLabel>强调色 · 6 套配色</DropdownMenuLabel>
          <div className="grid grid-cols-3 gap-1.5 px-2 pb-2 pt-1">
            {ACCENTS.map((item) => (
              <button
                key={item.id}
                type="button"
                title={item.label}
                onClick={() => onAccent(item.id)}
                className={cn(
                  "group flex flex-col items-center gap-1 rounded-md border px-1 py-2 text-[10px] transition-colors",
                  accent === item.id
                    ? "border-primary bg-accent text-foreground"
                    : "border-transparent hover:bg-accent",
                )}
              >
                <span
                  className="flex h-5 w-5 items-center justify-center rounded-full shadow-sm"
                  style={{ background: mode === "dark" ? item.dark : item.hex }}
                >
                  {accent === item.id && <Check className="h-3 w-3 text-white" strokeWidth={3} />}
                </span>
                {item.label}
              </button>
            ))}
          </div>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
