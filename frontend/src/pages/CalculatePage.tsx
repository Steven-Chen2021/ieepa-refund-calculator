import { useCallback, useEffect, useRef, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { v4 as uuidv4 } from 'uuid'
import { calculate, getJobStatus, uploadDocument } from '../api/documents'
import StepIndicator from '../components/ui/StepIndicator'
import { useUploadStore } from '../store/uploadStore'

const ALLOWED_MIME = ['application/pdf', 'image/jpeg', 'image/png']
const MAX_BYTES = 20 * 1024 * 1024

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 ** 2).toFixed(2)} MB`
}

const ERROR_MAP: Record<string, string> = {
  UNSUPPORTED_FILE_TYPE: 'calculate.err_unsupported',
  FILE_TOO_LARGE: 'calculate.err_too_large',
  UNRECOGNISED_DOCUMENT: 'calculate.err_unrecognised',
  OCR_TIMEOUT: 'calculate.err_timeout',
  RATE_LIMIT_EXCEEDED: 'calculate.err_rate_limit',
}

export default function CalculatePage(): JSX.Element {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { file, status, errorCode, setFile, setJobId, setCalculationId, setStatus, setError, reset } =
    useUploadStore()

  const [privacyAccepted, setPrivacyAccepted] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Clean up polling on unmount
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  const stopPoll = (): void => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }

  const startPolling = (jobId: string): void => {
    pollRef.current = setInterval(async () => {
      try {
        const res = await getJobStatus(jobId)
        setStatus(res.status as never)
        if (res.status === 'review_required') {
          stopPoll()
          navigate(`/review?job_id=${jobId}`)
        } else if (res.status === 'completed') {
          stopPoll()
          setStatus('calculating')
          const { calculation_id } = await calculate(jobId)
          setCalculationId(calculation_id)
          navigate(`/results/${calculation_id}`)
        } else if (res.status === 'failed') {
          stopPoll()
          setError(res.error ?? 'GENERIC')
        }
      } catch {
        stopPoll()
        setError('GENERIC')
      }
    }, 2000)
  }

  const handleUpload = async (): Promise<void> => {
    if (!file) return
    const idempotencyKey = uuidv4()
    setStatus('uploading')
    try {
      const { job_id } = await uploadDocument(file, idempotencyKey)
      setJobId(job_id)
      setStatus('queued')
      startPolling(job_id)
    } catch (err: unknown) {
      const code =
        (err as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'GENERIC'
      setError(code)
    }
  }

  const onDrop = useCallback(
    (accepted: File[], rejected: readonly { errors: readonly { code: string }[] }[]): void => {
      if (rejected.length > 0) {
        const code = rejected[0].errors[0].code
        if (code === 'file-too-large') setError('FILE_TOO_LARGE')
        else setError('UNSUPPORTED_FILE_TYPE')
        return
      }
      if (accepted[0]) setFile(accepted[0])
    },
    [setFile, setError],
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'], 'image/jpeg': ['.jpg', '.jpeg'], 'image/png': ['.png'] },
    maxSize: MAX_BYTES,
    maxFiles: 1,
    disabled: !privacyAccepted || (status !== 'idle' && status !== 'ready' && status !== 'failed'),
  })

  const isProcessing = ['uploading', 'queued', 'processing', 'calculating'].includes(status)

  const errorText = errorCode
    ? t(ERROR_MAP[errorCode] ?? 'calculate.err_generic')
    : null

  const progressStep =
    status === 'uploading' ? 0 : status === 'queued' || status === 'processing' ? 1 : 2

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 font-body text-navy-blue">
      <StepIndicator current={1} />

      {/* Privacy notice */}
      <div className="mb-6 bg-gray-white border border-gray-200 rounded-none rounded-br-lg p-5">
        <h2 className="font-heading font-semibold text-navy-blue mb-2 flex items-center gap-2">
          <span>📋</span> {t('calculate.privacy_title')}
        </h2>
        <p className="text-sm text-dark-gray mb-4">{t('calculate.privacy_text')}</p>
        <label className="flex items-start gap-2 cursor-pointer select-none text-sm text-navy-blue font-medium">
          <input
            type="checkbox"
            className="mt-0.5 accent-navy-blue w-4 h-4"
            checked={privacyAccepted}
            onChange={(e) => setPrivacyAccepted(e.target.checked)}
          />
          {t('calculate.privacy_accept')}
        </label>
      </div>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={`relative border-2 border-dashed rounded-none rounded-br-lg p-10 text-center transition-colors
          ${!privacyAccepted ? 'opacity-50 cursor-not-allowed border-gray-200 bg-gray-white' : ''}
          ${privacyAccepted && !isProcessing && status !== 'ready' ? 'border-logo-blue bg-gray-white hover:border-navy-blue cursor-pointer' : ''}
          ${isDragActive ? 'border-navy-blue bg-gray-100' : ''}
          ${status === 'ready' ? 'border-success bg-green-50 cursor-pointer' : ''}
          ${isProcessing ? 'border-gray-200 bg-gray-white cursor-default' : ''}
        `}
        title={!privacyAccepted ? t('calculate.dropzone_disabled_tip') : undefined}
      >
        <input {...getInputProps()} />

        {!isProcessing && status !== 'ready' && (
          <>
            <div className="text-5xl mb-4">{isDragActive ? '📂' : '⬆️'}</div>
            <p className="text-navy-blue font-heading font-semibold mb-1">
              {isDragActive ? t('calculate.dropzone_active') : t('calculate.dropzone_title')}
            </p>
            <p className="text-brand-gray text-sm mb-4">
              {t('calculate.dropzone_or')}{' '}
              <span className="text-logo-blue underline">{t('calculate.dropzone_browse')}</span>
            </p>
            <p className="text-xs text-brand-gray">{t('calculate.dropzone_hint')}</p>
          </>
        )}

        {/* File selected preview */}
        {status === 'ready' && file && (
          <div className="flex flex-col items-center gap-3">
            <div className="text-5xl">
              {file.type === 'application/pdf' ? '📄' : '🖼️'}
            </div>
            <div className="w-full max-w-xs bg-white border border-success rounded-none rounded-br-lg p-4 text-left text-sm shadow-sm">
              <p className="font-semibold text-navy-blue mb-2">{t('calculate.file_selected')}</p>
              <div className="space-y-1 text-dark-gray">
                <div className="flex justify-between">
                  <span className="text-brand-gray">{t('calculate.file_name')}</span>
                  <span className="font-medium truncate max-w-[160px]">{file.name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-brand-gray">{t('calculate.file_size')}</span>
                  <span className="font-medium">{formatBytes(file.size)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-brand-gray">{t('calculate.file_type')}</span>
                  <span className="font-medium">{file.type || '—'}</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Processing state */}
        {isProcessing && (
          <div className="flex flex-col items-center gap-4">
            {/* Progress steps */}
            <div className="flex items-center gap-2 text-xs font-medium">
              {[t('calculate.uploading'), t('calculate.queued'), t('calculate.processing')].map(
                (label, i) => (
                  <div key={label} className="flex items-center gap-1">
                    <span
                      className={`w-2 h-2 rounded-full ${i <= progressStep ? 'bg-logo-orange' : 'bg-brand-gray'}`}
                    />
                    <span className={i <= progressStep ? 'text-logo-orange' : 'text-brand-gray'}>
                      {label}
                    </span>
                    {i < 2 && <span className="text-brand-gray mx-1">──</span>}
                  </div>
                ),
              )}
            </div>
            {/* Spinner */}
            <div className="w-10 h-10 border-4 border-gray-200 border-t-logo-orange rounded-full animate-spin" />
            <p className="text-dark-gray text-sm">
              {status === 'uploading'
                ? t('calculate.uploading')
                : status === 'queued'
                  ? t('calculate.queued')
                  : status === 'calculating'
                    ? `${t('calculate.processing')} (${t('common.loading')})`
                    : t('calculate.processing')}
            </p>
            {file && (
              <p className="text-xs text-brand-gray truncate max-w-xs">{file.name}</p>
            )}
          </div>
        )}
      </div>

      {/* Error banner */}
      {status === 'failed' && errorText && (
        <div className="mt-4 flex items-start gap-3 bg-red-50 border border-error text-error rounded-none rounded-br-lg p-4 text-sm">
          <span className="text-lg">⚠️</span>
          <div className="flex-1">
            <p className="font-medium">{errorText}</p>
          </div>
          <button
            onClick={() => reset()}
            className="ml-auto px-3 py-1.5 bg-error text-white rounded-none rounded-br-lg text-xs font-heading font-semibold hover:opacity-90"
          >
            {t('calculate.btn_retry')}
          </button>
        </div>
      )}

      {/* CTA buttons */}
      {!isProcessing && (
        <div className="mt-6 flex gap-3 justify-end">
          {status === 'ready' && (
            <button
              onClick={() => setFile(null)}
              className="px-4 py-2 text-sm text-logo-orange border border-logo-orange bg-transparent font-heading font-semibold rounded-none hover:bg-orange-50"
            >
              {t('calculate.btn_change')}
            </button>
          )}
          <button
            disabled={status !== 'ready'}
            onClick={handleUpload}
            className={`px-6 py-3 font-heading font-semibold rounded-none rounded-br-lg text-white transition-opacity shadow-sm
              ${status === 'ready'
                ? 'bg-gradient-to-b from-logo-orange to-logo-orange-dark hover:opacity-90 active:opacity-100'
                : 'bg-brand-gray cursor-not-allowed'
              }`}
          >
            {t('calculate.btn_start')}
          </button>
        </div>
      )}

      {/* Allowed types reminder */}
      {!ALLOWED_MIME.includes(file?.type ?? '') && !file && (
        <p className="mt-4 text-center text-xs text-brand-gray">{t('calculate.dropzone_hint')}</p>
      )}
    </div>
  )
}
