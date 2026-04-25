import { type HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Variant =
  | "default"
  | "secondary"
  | "outline"
  | "success"
  | "warning"
  | "destructive"
  | "info";

const VARIANTS: Record<Variant, string> = {
  default: "bg-primary/15 text-primary border-primary/30",
  secondary: "bg-secondary text-secondary-foreground border-border",
  outline: "border-border text-foreground",
  success: "bg-success/15 text-success border-success/30",
  warning: "bg-warning/15 text-warning border-warning/40",
  destructive: "bg-destructive/15 text-destructive border-destructive/30",
  info: "bg-blue-500/15 text-blue-400 border-blue-500/30",
};

interface Props extends HTMLAttributes<HTMLSpanElement> {
  variant?: Variant;
}

export function Badge({ className, variant = "default", ...props }: Props) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide",
        VARIANTS[variant],
        className,
      )}
      {...props}
    />
  );
}
