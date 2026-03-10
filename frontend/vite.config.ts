import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig } from "vite"

// https://vitejs.dev/config/
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
    // Prevent duplicate instances from nested node_modules (radix-ui ships nested deps)
    dedupe: [
      "react",
      "react-dom",
      "@radix-ui/react-compose-refs",
      "@radix-ui/react-slot",
      "@radix-ui/react-use-layout-effect",
    ],
  },
  plugins: [
    tanstackRouter({
      target: "react",
      autoCodeSplitting: true,
    }),
    react(),
    tailwindcss(),
  ],
  define: {
    "import.meta.env.VITE_BUILD_ID": JSON.stringify(Date.now().toString()),
  },
})
