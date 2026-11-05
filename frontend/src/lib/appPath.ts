/** Prefix full-page navigation with the build's mount path; API URLs stay separate. */
export function appPath(path: string, base = import.meta.env.BASE_URL): string {
  return `${base.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`
}
