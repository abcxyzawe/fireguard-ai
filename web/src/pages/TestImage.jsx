import { useState, useRef } from 'react'
import { detectImage } from '../api'

export default function TestImage() {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [showOriginal, setShowOriginal] = useState(false)
  const fileRef = useRef()

  const handleFile = async (file) => {
    if (!file) return
    setLoading(true)
    setResult(null)
    try {
      const { data } = await detectImage(file)
      setResult(data)
    } catch (e) {
      alert('Loi: ' + (e.response?.data?.error || e.message))
    }
    setLoading(false)
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    handleFile(e.dataTransfer.files[0])
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">Test Anh</h2>

      {/* Upload zone */}
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
          accept="image/*"
          className="hidden"
          onChange={(e) => handleFile(e.target.files[0])}
        />
        <p className="text-3xl mb-2">🖼</p>
        <p className="text-slate-300">Keo tha anh vao day hoac click de chon</p>
        <p className="text-xs text-slate-500 mt-1">JPG, PNG, BMP, WEBP</p>
      </div>

      {loading && (
        <div className="text-center py-8">
          <div className="inline-block w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
          <p className="text-slate-400 mt-2">Dang phan tich...</p>
        </div>
      )}

      {result && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Image */}
          <div className="bg-[#1e293b] rounded-xl p-4">
            <div className="flex gap-2 mb-3">
              <button
                onClick={() => setShowOriginal(false)}
                className={`px-3 py-1 rounded text-sm ${!showOriginal ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}
              >
                Ket qua
              </button>
              <button
                onClick={() => setShowOriginal(true)}
                className={`px-3 py-1 rounded text-sm ${showOriginal ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}
              >
                Goc
              </button>
            </div>
            <img
              src={`data:image/jpeg;base64,${showOriginal ? result.original : result.image}`}
              alt="Result"
              className="w-full rounded-lg"
            />
            <div className="flex gap-2 mt-2 text-sm">
              <span className={`px-2 py-1 rounded font-bold ${result.fire ? 'bg-red-600 text-white' : 'bg-green-600/20 text-green-400'}`}>
                {result.fire ? `🔥 LUA (${result.fire_count})` : '✅ Khong co lua'}
              </span>
              <span className={`px-2 py-1 rounded font-bold ${result.smoke ? 'bg-orange-500 text-white' : 'bg-green-600/20 text-green-400'}`}>
                {result.smoke ? `💨 KHOI (${result.smoke_count})` : '✅ Khong co khoi'}
              </span>
            </div>
          </div>

          {/* Details */}
          <div className="bg-[#1e293b] rounded-xl p-4">
            <h3 className="font-semibold mb-3">Chi tiet Detection</h3>
            <div className="text-sm text-slate-400 mb-2">
              Mode: <span className="text-white">{result.mode}</span> | Size: <span className="text-white">{result.size}</span>
            </div>

            {result.detections?.length > 0 ? (
              <div className="space-y-3">
                {result.detections.map((d, i) => (
                  <div key={i} className="bg-slate-800 rounded-lg p-3">
                    <div className="flex justify-between mb-2">
                      <span className={`font-bold ${d.type === 'fire' ? 'text-red-400' : 'text-orange-400'}`}>
                        {d.type === 'fire' ? '🔥 LUA' : '💨 KHOI'} #{i + 1}
                      </span>
                      <span className="text-white font-mono">{(d.conf * 100).toFixed(1)}%</span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <ScoreBar label="Verify" value={d.verify} />
                      <ScoreBar label="Color" value={d.color} />
                      <ScoreBar label="Texture" value={d.texture} />
                      <ScoreBar label="Edge" value={d.edge} />
                    </div>
                    <div className="text-xs text-slate-500 mt-2">
                      BBox: [{d.bbox.join(', ')}]
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-slate-500">Khong co detection</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function ScoreBar({ label, value }) {
  const pct = ((value || 0) * 100).toFixed(1)
  const color = value > 0.7 ? 'bg-green-500' : value > 0.4 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div>
      <div className="flex justify-between text-slate-400 mb-0.5">
        <span>{label}</span>
        <span className="text-white">{pct}%</span>
      </div>
      <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
