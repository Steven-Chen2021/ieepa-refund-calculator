import { useCallback, useEffect, useRef, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { v4 as uuidv4 } from 'uuid'
import uploadCloudIcon from '../../icon/uploadCloud.png'
import { calculate, getJobStatus, uploadDocument } from '../api/documents'
import StepIndicator from '../components/ui/StepIndicator'
import type { UploadStatus } from '../store/uploadStore'
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
  INVALID_7501_FORMAT: 'calculate.err_invalid_7501',
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

  // Reset stale state when the user navigates back to this page
  useEffect(() => {
    const terminalStates: UploadStatus[] = ['completed', 'review_required', 'calculating']
    if (terminalStates.includes(status)) {
      reset()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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
    <div className="min-h-screen bg-white font-body">

      {/* Page title with separator */}
      <div className="border-b border-gray-200 py-8 text-center bg-white">
        <h1 className="text-3xl font-heading font-bold text-gray-900">
          {t('home.hero_title')}
        </h1>
      </div>

      <div className="max-w-3xl mx-auto px-4 py-8 text-navy-blue">
        <StepIndicator current={1} />

        {/* Description */}
        <p className="text-dark-gray mb-3 text-base">
          {t('calculate.page_subtitle')}
        </p>

        {/* Orange notice */}
        <p className="text-logo-orange text-sm mb-8">
          {t('calculate.page_notice')}
        </p>

        {/* Section heading */}
        <h2 className="text-2xl font-heading font-bold text-gray-900 mb-6">
          {t('calculate.section_heading')}
        </h2>

        {/* Main card */}
        <div className="border border-gray-200 rounded-lg bg-white overflow-hidden">

          {/* Privacy section */}
          <div className="p-6">
            <h3 className="font-heading font-semibold text-navy-blue mb-2">
              {t('calculate.privacy_title')}
            </h3>
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

          {/* Upload section */}
          <div className="border-t border-gray-200">
            <div className="px-6 pt-5 pb-3">
              <p className="font-heading font-semibold text-navy-blue mb-0.5">
                {t('calculate.upload_section_title')}{' '}
                <span className="text-logo-orange">*</span>
              </p>
              <p className="text-sm text-gray-500">
                {t('calculate.upload_section_desc')}
              </p>
            </div>

            {/* Drop zone inside gray area */}
            <div className="bg-gray-50 mx-6 mb-6 border border-gray-200 rounded-lg overflow-hidden">
              <div
                {...getRootProps()}
                className={`relative p-8 text-center transition-colors
                  ${!privacyAccepted ? 'opacity-50 cursor-not-allowed' : ''}
                  ${privacyAccepted && !isProcessing && status !== 'ready' ? 'hover:bg-gray-100 cursor-pointer' : ''}
                  ${isDragActive ? 'bg-blue-50' : ''}
                  ${status === 'ready' ? 'bg-green-50 cursor-pointer' : ''}
                  ${isProcessing ? 'cursor-default' : ''}
                `}
                title={!privacyAccepted ? t('calculate.dropzone_disabled_tip') : undefined}
              >
                <input {...getInputProps()} />

                {!isProcessing && status !== 'ready' && (
                  <div className="pointer-events-none">
                    <div className="flex justify-center mb-3">
                      <img
                        src={uploadCloudIcon}
                        alt=""
                        className={`w-16 h-16 object-contain transition-opacity ${isDragActive ? 'opacity-70' : 'opacity-100'}`}
                      />
                    </div>
                    <p className="text-navy-blue font-heading font-semibold mb-1">
                      {isDragActive ? t('calculate.dropzone_active') : t('calculate.dropzone_title')}
                    </p>
                    <p className="text-brand-gray text-sm mb-3">
                      {t('calculate.dropzone_or')}{' '}
                      <span className="text-logo-blue underline">{t('calculate.dropzone_browse')}</span>
                    </p>
                    <p className="text-xs text-brand-gray">{t('calculate.dropzone_hint')}</p>
                  </div>
                )}

                {/* File selected preview */}
                {status === 'ready' && file && (
                  <div className="pointer-events-none flex items-center gap-4 text-left">
                    <div className="text-3xl shrink-0">
                      {file.type === 'application/pdf' ? '📄' : '🖼️'}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-navy-blue text-sm mb-1">{t('calculate.file_selected')}</p>
                      <div className="grid grid-cols-3 gap-x-4 text-xs text-dark-gray">
                        <div>
                          <span className="text-brand-gray block">{t('calculate.file_name')}</span>
                          <span className="font-medium truncate block">{file.name}</span>
                        </div>
                        <div>
                          <span className="text-brand-gray block">{t('calculate.file_size')}</span>
                          <span className="font-medium">{formatBytes(file.size)}</span>
                        </div>
                        <div>
                          <span className="text-brand-gray block">{t('calculate.file_type')}</span>
                          <span className="font-medium">{file.type || '—'}</span>
                        </div>
                      </div>
                    </div>
                    <div className="shrink-0 w-5 h-5 rounded-full bg-success flex items-center justify-center">
                      <span className="text-white text-xs font-bold">✓</span>
                    </div>
                  </div>
                )}

                {/* Processing state */}
                {isProcessing && (
                  <div className="pointer-events-none flex flex-col items-center gap-4">
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
                    <div className="w-9 h-9 border-4 border-gray-200 border-t-logo-orange rounded-full animate-spin" />
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
            </div>
          </div>

          {/* Error banner */}
          {status === 'failed' && errorText && (
            <div className="mx-6 mb-6 flex items-start gap-3 bg-red-50 border border-error text-error rounded-lg p-4 text-sm">
              <span className="text-lg">⚠️</span>
              <div className="flex-1">
                <p className="font-medium">{errorText}</p>
              </div>
              <button
                onClick={() => reset()}
                className="ml-auto px-3 py-1.5 bg-error text-white rounded text-xs font-heading font-semibold hover:opacity-90"
              >
                {t('calculate.btn_retry')}
              </button>
            </div>
          )}

          {/* Action buttons */}
          {!isProcessing && (
            <div className="border-t border-gray-200 px-6 py-4 flex gap-3 justify-end bg-white">
              {status === 'ready' && (
                <button
                  onClick={() => setFile(null)}
                  className="px-4 py-2 text-sm text-navy-blue border border-gray-300 bg-white font-heading font-semibold rounded hover:border-navy-blue transition-colors"
                >
                  {t('calculate.btn_change')}
                </button>
              )}
              <button
                disabled={status !== 'ready'}
                onClick={handleUpload}
                className={`px-6 py-2.5 font-heading font-semibold rounded text-sm text-white transition-opacity shadow-sm
                  ${status === 'ready'
                    ? 'bg-logo-orange hover:bg-logo-orange-dark active:opacity-100'
                    : 'bg-gray-300 cursor-not-allowed'
                  }`}
              >
                {t('calculate.btn_start')}
              </button>
            </div>
          )}

        </div>

        {/* File type reminder when no file and not visible above */}
        {!ALLOWED_MIME.includes(file?.type ?? '') && !file && !isProcessing && (
          <p className="mt-3 text-center text-xs text-brand-gray">{t('calculate.dropzone_hint')}</p>
        )}
      </div>
    </div>
  )
}
