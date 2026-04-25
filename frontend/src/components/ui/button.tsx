import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Variant = "default" | "secondary" | "outline" | "ghost" | "destructive" | "success";
type Size = "sm" | "md" | "lg" | "icon";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const VARIANTS: Record<Variant, string> = {
  default:
    "bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50",
  secondary:
    "bg-secondary text-secondary-foreground hover:bg-secondary/80 disabled:opacity-50",
  outline:
    "border border-border bg-transparent hover:bg-accent hover:text-accent-foreground disabled:opacity-50",
  ghost: "hover:bg-accent hover:text-accent-foreground disabled:opacity-50",
  destructive:
    "bg-destructive text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50",
  success:
    "bg-success text-success-foreground hover:bg-success/90 disabled:opacity-50",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-9 px-4 text-sm",
  lg: "h-10 px-6 text-sm",
  icon: "h-9 w-9",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "md", ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = "Button";
