/// reference types="vite/client" />
/// <reference types="vite-plugin-svgr/client" />

interface ViteTypeOptions {
  strictImportMetaEnv: unknown
}

interface ImportMetaEnv {}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
