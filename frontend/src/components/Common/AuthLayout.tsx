import { Appearance } from "@/components/Common/Appearance"
import { Footer } from "./Footer"

interface AuthLayoutProps {
  children: React.ReactNode
}

export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="grid min-h-svh lg:grid-cols-2">
      {/* ── Left branding panel ─────────────────────────────────────────── */}
      <div className="relative hidden lg:flex lg:flex-col lg:items-center lg:justify-center bg-zinc-950 overflow-hidden">
        {/* Background glow */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-80 h-80 rounded-full bg-blue-600/15 blur-[80px]" />
        </div>

        {/* Content */}
        <div className="relative z-10 flex flex-col items-center gap-6 px-14 text-center">
          {/* SparkPitLabs eyebrow */}
          <p className="text-xs font-semibold tracking-[0.2em] uppercase text-blue-400/80">
            SparkPitLabs
          </p>

          {/* SparkBot heading */}
          <h1 className="text-5xl font-bold text-white tracking-tight leading-none">
            SparkBot
          </h1>

          {/* Sparkbot lightning bolt icon */}
          <img
            src="/assets/images/sparkbot-icon.svg"
            alt="SparkBot"
            className="w-24 h-24 drop-shadow-lg"
          />

          {/* Tagline */}
          <p className="text-zinc-400 text-sm max-w-[220px] leading-relaxed">
            Your self-hosted AI workspace
          </p>
        </div>
      </div>

      {/* ── Right login form panel ───────────────────────────────────────── */}
      <div className="flex flex-col gap-4 p-6 md:p-10">
        <div className="flex justify-end">
          <Appearance />
        </div>
        <div className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-xs">{children}</div>
        </div>
        <Footer />
      </div>
    </div>
  )
}
