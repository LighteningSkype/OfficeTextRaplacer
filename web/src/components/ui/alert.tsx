import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const alertVariants = cva(
  "relative flex w-full gap-2.5 rounded-lg border px-3.5 py-2.5 text-xs [&>svg]:mt-0.5 [&>svg]:size-4 [&>svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "panel-surface text-card-foreground",
        info: "border-[hsl(var(--brand)/0.28)] bg-[hsl(var(--brand)/0.07)] text-foreground",
        destructive: "border-destructive/30 bg-destructive/8 text-destructive",
        warning: "border-[hsl(var(--warning)/0.3)] bg-[hsl(var(--warning)/0.08)] text-foreground",
        success: "border-[hsl(var(--success)/0.3)] bg-[hsl(var(--success)/0.08)] text-foreground",
      },
    },
    defaultVariants: { variant: "default" },
  },
)

const Alert = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>
>(({ className, variant, ...props }, ref) => (
  <div ref={ref} role="alert" className={cn(alertVariants({ variant }), className)} {...props} />
))
Alert.displayName = "Alert"

const AlertTitle = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h5 ref={ref} className={cn("font-semibold leading-none tracking-tight", className)} {...props} />
  ),
)
AlertTitle.displayName = "AlertTitle"

const AlertDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("leading-relaxed text-muted-foreground", className)} {...props} />
  ),
)
AlertDescription.displayName = "AlertDescription"

export { Alert, AlertTitle, AlertDescription }
