import { useState, useRef, useEffect } from 'react'
import { detectVideo, getVideoStatus, getVideoResultUrl } from '../api'

export default function TestVideo() {
  const [jobId, setJobId] = useState(null)
  const [progress, setProgress] = useState(null)
  const [loading, setLoading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef()
  const pollRef = useRef()

  const handleFile = async (file) => {
    if (!file) return
    setLoading(true)
    setProgress(null)
    try {
      const { data } = await detectVideo(file)
      setJobId(data.job_id)
      setLoading(false)
    } catch (e) {
      alert('Loi: ' + (e.response?.data?.error || e.message))
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!jobId) return
    pollRef.current = setInterval(async () => {
      try {
        const { data } = await getVideoStatus(jobId)
        setProgress(data)
        if (data.status === 'done' || data.status === 'error') {
          clearInterval(pollRef.current)
        }
      } catch (e) {
        clearInterval(pollRef.current)
      }
    }, 1500)
    return () => clearInterval(pollRef.current)
  }, [jobId])

  const onDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    handleFile(e.dataTransfer.files[0])
  }

  const pct = progress ? ((progress.current_frame / (progress.total_frames || 1)) * 100).toFixed(0) : 0

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">Test Video</h2>

      {!jobId && (
        <div
          className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors ${
            dragOver ? 'border-blue-400 bg-blue-600/10' : 'border-slate-600 hover:border-slate-400'
          }`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => fileRef.current?.click()}
        >
          <input
            ref={fileRef}
            type="file"
            accept="video/*"
            className="hidden"
            onChange={(e) => handleFile(e.target.files[0])}
          />
          <p className="text-3xl mb-2">🎬</p>
          <p className="text-slate-300">Keo tha video vao day hoac click de chon</p>
          <p className="text-xs text-slate-500 mt-1">MP4, AVI, MOV (max 200MB)</p>
        </div>
      )}

      {loading && (
        <div className="text-center py-8">
          <div className="inline-block w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
          <p className="text-slate-400 mt-2">Dang upload...</p>
        </div>
      )}

      {progress && (
        <div className="bg-[#1e293b] rounded-xl p-6 space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="font-semibold">{progress.filename || 'Video'}</h3>
            <span className={`px-2 py-1 rounded text-xs font-bold ${
              progress.status === 'done' ? 'bg-green-600 text-white' :
              progress.status === 'error' ? 'bg-red-600 text-white' :
              'bg-blue-600 text-white'
            }`}>
              {progress.status === 'done' ? 'HOAN THANH' :
               progress.status === 'error' ? 'LOI' :
               'DANG XU LY'}
            </span>
          </div>

          {/* Progress bar */}
          <div>
            <div className="flex justify-between text-sm text-slate-400 mb-1">
              <span>Frame: {progress.current_frame} / {progress.total_frames}</span>
              <span>{pct}%</span>
            </div>
            <div className="h-3 bg-slate-700 rounded-full overflow-hidden">
              <div className="h-full bg-blue-500 rounded-full transition-all" style={{ width: `${pct}%` }} />
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-slate-800 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-red-400">{progress.fire_frames || 0}</div>
              <div className="text-xs text-slate-400">Frame co lua</div>
            </div>
            <div className="bg-slate-800 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-orange-400">{progress.smoke_frames || 0}</div>
              <div className="text-xs text-slate-400">Frame co khoi</div>
            </div>
          </div>

          {/* Preview */}
          {progress.preview && (
            <div>
              <p className="text-sm text-slate-400 mb-1">Preview:</p>
              <img src={`data:image/jpeg;base64,${progress.preview}`} alt="Preview" className="rounded-lg max-w-md" />
            </div>
          )}

          {/* Download */}
          {progress.status === 'done' && (
            <a
              href={getVideoResultUrl(jobId)}
              className="inline-block px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-medium transition-colors"
              download
            >
              📥 Tai video da xu ly
            </a>
          )}

          {(progress.status === 'done' || progress.status === 'error') && (
            <button
              onClick={() => { setJobId(null); setProgress(null) }}
              className="ml-3 px-4 py-2 bg-slate-600 hover:bg-slate-700 text-white rounded-lg text-sm transition-colors"
            >
              Upload video khac
            </button>
          )}
        </div>
      )}
    </div>
  )
}
