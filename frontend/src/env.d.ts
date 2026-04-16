/// <reference types="vite/client" />

declare interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly [key: string]: string | undefined;
}

declare interface ImportMeta {
  readonly env: ImportMetaEnv;
}
