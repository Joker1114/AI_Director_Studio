export interface SharedProps {
  projectId: string
  scriptId: string
  execute: <T>(action: () => Promise<T>) => Promise<T | undefined>
  report: (error: unknown) => void
  busy: boolean
}
