import { create } from 'zustand'

export type UploadStatus =
  | 'idle'
  | 'ready'           // file selected, not yet uploaded
  | 'uploading'
  | 'queued'
  | 'processing'
  | 'review_required'
  | 'completed'
  | 'calculating'
  | 'failed'

interface UploadState {
  file: File | null
  jobId: string | null
  calculationId: string | null
  status: UploadStatus
  errorCode: string | null

  setFile: (file: File | null) => void
  setJobId: (id: string) => void
  setCalculationId: (id: string) => void
  setStatus: (status: UploadStatus) => void
  setError: (code: string) => void
  reset: () => void
}

export const useUploadStore = create<UploadState>((set) => ({
  file: null,
  jobId: null,
  calculationId: null,
  status: 'idle',
  errorCode: null,

  setFile: (file) => set({ file, status: file ? 'ready' : 'idle', errorCode: null }),
  setJobId: (jobId) => set({ jobId }),
  setCalculationId: (calculationId) => set({ calculationId }),
  setStatus: (status) => set({ status }),
  setError: (errorCode) => set({ status: 'failed', errorCode }),
  reset: () =>
    set({ file: null, jobId: null, calculationId: null, status: 'idle', errorCode: null }),
}))
