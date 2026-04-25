import { Link, Outlet } from "react-router-dom";
import { useEffect, useState } from "react";
import { AnalystBar } from "@/components/AnalystBar";
import { Button } from "@/components/ui/button";
import { metaApi } from "@/lib/api";
import { ShieldCheck, Sun, Moon } from "lucide-react";

export function RootLayout() {
  const [dark, setDark] = useState(true);
  const [health, setHealth] = useState<{ status: string; db: string } | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  useEffect(() => {
    let alive = true;
    metaApi
      .health()
      .then((h) => alive && setHealth(h))
      .catch(() => alive && setHealth({ status: "down", db: "unreachable" }));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur">
        <div className="container flex h-14 items-center justify-between gap-4">
          <Link to="/" className="flex items-center gap-2 font-semibold">
            <ShieldCheck className="h-5 w-5 text-primary" />
            AML Investigation Console
          </Link>
          <div className="flex items-center gap-3">
            <span
              className={
                "text-xs " +
                (health?.status === "ok"
                  ? "text-success"
                  : health?.status === "degraded"
                    ? "text-warning"
                    : "text-destructive")
              }
            >
              {health ? `api: ${health.status} · db: ${health.db}` : "api: …"}
            </span>
            <AnalystBar />
            <Button
              variant="ghost"
              size="icon"
              aria-label="Toggle theme"
              onClick={() => setDark((d) => !d)}
            >
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </header>
      <main className="container py-6">
        <Outlet />
      </main>
    </div>
  );
}
