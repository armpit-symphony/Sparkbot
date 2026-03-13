import { spawn } from "node:child_process"
import path from "node:path"
import { fileURLToPath } from "node:url"

const mode = process.argv[2] ?? "build"

if (!["build", "dev"].includes(mode)) {
  console.error(`Unsupported desktop frontend mode: ${mode}`)
  process.exit(1)
}

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const repoRoot = path.resolve(__dirname, "..")
const frontendDir = path.join(repoRoot, "frontend")
const bunCommand = process.env.BUN_BIN || "bun"

const args = mode === "dev"
  ? ["run", "dev", "--host", "127.0.0.1", "--port", "5173"]
  : ["run", "build"]

const child = spawn(bunCommand, args, {
  cwd: frontendDir,
  env: {
    ...process.env,
    VITE_API_URL: process.env.VITE_API_URL || "http://127.0.0.1:8000",
    VITE_V1_LOCAL_MODE: "true",
  },
  shell: process.platform === "win32",
  stdio: "inherit",
})

child.on("exit", (code) => {
  process.exit(code ?? 1)
})

