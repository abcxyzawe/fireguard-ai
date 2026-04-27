import { useState, useEffect, useRef } from 'react'
import { useOutletContext } from 'react-router-dom'
import { saveCapture, getStreamUrl } from '../api'

const CAM_IDS = ['cam1', 'cam2']
const CAM_LABELS = { cam1: 'Camera 1', cam2: 'Camera 2' }

export default function Dashboard() {
  const { status } = useOutletContext()
  const cameras = status?.cameras || {}
  const [activeCam, setActiveCam] = useState('cam1')
  const [logs, setLogs] = useState([])
  const [crosshairs, setCrosshairs] = useState({
    cam1: { x: 50, y: 50 },
    cam2: { x: 50, y: 50 },
  })
  const [dragging, setDragging] = useState(false)
  const [hits, setHits] = useState({ cam1: false, cam2: false })
  const streamRefs = useRef({ cam1: null, cam2: null })

  const det = cameras[activeCam] || {}
  const crosshair = crosshairs[activeCam] || { x: 50, y: 50 }
  const hit = hits[activeCam] || false

  // Add log entry on detection for all cameras
  useEffect(() => {
    CAM_IDS.forEach(camId => {
      const camDet = cameras[camId] || {}
      if (!camDet.fire && !camDet.smoke) return
      const entry = {
        time: new Date().toLocaleTimeString(),
        cam: camId,
        type: camDet.fire ? 'LUA' : 'KHOI',
        count: camDet.fire ? (camDet.fire_bboxes?.length || 0) : (camDet.smoke_bboxes?.length || 0),
      }
      setLogs(prev => {
        // Avoid duplicate entries for the same timestamp+cam
        if (prev.length > 0 && prev[0].cam === camId && prev[0].type === entry.type &&
            prev[0].time === entry.time) return prev
        return [entry, ...prev].slice(0, 50)
      })
    })
  }, [cameras?.cam1?.timestamp, cameras?.cam2?.timestamp,
      cameras?.cam1?.fire, cameras?.cam1?.smoke,
      cameras?.cam2?.fire, cameras?.cam2?.smoke])

  // Check crosshair hit for active camera
  useEffect(() => {
    const newHits = { ...hits }
    CAM_IDS.forEach(camId => {
      const camDet = cameras[camId] || {}
      const ch = crosshairs[camId] || { x: 50, y: 50 }
      if (!camDet.fire_bboxes?.length) { newHits[camId] = false; return }
      const imgW = 800, imgH = 600
      const cx = (ch.x / 100) * imgW
      const cy = (ch.y / 100) * imgH
      const isHit = camDet.fire_bboxes.some(fb => {
        const [x1, y1, x2, y2] = fb.bbox
        return cx >= x1 && cx <= x2 && cy >= y1 && cy <= y2
      })
      newHits[camId] = isHit
    })
    setHits(newHits)
  }, [crosshairs, cameras?.cam1?.fire_bboxes, cameras?.cam2?.fire_bboxes])

  const handleMouseMove = (e) => {
    if (!dragging) return
    const rect = e.currentTarget.getBoundingClientRect()
    setCrosshairs(prev => ({
      ...prev,
      [activeCam]: {
        x: Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100)),
        y: Math.max(0, Math.min(100, ((e.clientY - rect.top) / rect.height) * 100)),
      }
    }))
  }

  const handleCapture = async (camId) => {
    const img = streamRefs.current[camId]
    if (!img) return
    const canvas = document.createElement('canvas')
    canvas.width = img.naturalWidth || img.width
    canvas.height = img.naturalHeight || img.height
    const ctx = canvas.getContext('2d')
    ctx.drawImage(img, 0, 0)
    const dataUrl = canvas.toDataURL('image/jpeg', 0.9)
    try {
      await saveCapture(dataUrl)
      setLogs(prev => [{ time: new Date().toLocaleTimeString(), cam: camId, type: 'CAPTURE', count: 0 }, ...prev])
    } catch (e) {
      console.error('Capture failed', e)
    }
  }

  const fireBoxes = det.fire_bboxes || []
  const smokeBoxes = det.smoke_bboxes || []

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">Dashboard - Multi Camera Realtime</h2>

      {/* Camera selector tabs */}
      <div className="flex gap-2">
        {CAM_IDS.map(camId => {
          const camDet = cameras[camId] || {}
          const isActive = activeCam === camId
          const hasFire = camDet.fire
          const hasSmoke = camDet.smoke
          return (
            <button
              key={camId}
              onClick={() => setActiveCam(camId)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2
                ${isActive
                  ? 'bg-blue-600 text-white'
                  : 'bg-[#1e293b] text-slate-300 hover:bg-slate-700'
                }`}
            >
              {CAM_LABELS[camId]}
              {hasFire && <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />}
              {!hasFire && hasSmoke && <span className="w-2 h-2 rounded-full bg-orange-500 animate-pulse" />}
              {!hasFire && !hasSmoke && <span className="w-2 h-2 rounded-full bg-green-500" />}
            </button>
          )
        })}
      </div>

      {/* Dual camera preview strip */}
      <div className="grid grid-cols-2 gap-2">
        {CAM_IDS.map(camId => {
          const camDet = cameras[camId] || {}
          const isSelected = activeCam === camId
          return (
            <div
              key={camId}
              onClick={() => setActiveCam(camId)}
              className={`relative bg-black rounded-lg overflow-hidden aspect-video cursor-pointer border-2 transition-colors
                ${isSelected ? 'border-blue-500' : 'border-transparent hover:border-slate-600'}`}
            >
              <img
                ref={el => { streamRefs.current[camId] = el }}
                src={getStreamUrl(camId)}
                alt={CAM_LABELS[camId]}
                className="w-full h-full object-contain"
                crossOrigin="anonymous"
              />
              <div className="absolute top-2 left-2 flex gap-1">
                <span className="text-xs bg-black/70 text-white px-2 py-0.5 rounded">
                  {CAM_LABELS[camId]}
                </span>
                <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                  camDet.fire ? 'bg-red-600 text-white' :
                  camDet.smoke ? 'bg-orange-500 text-white' :
                  'bg-green-600/80 text-white'
                }`}>
                  {camDet.fire ? 'LUA' : camDet.smoke ? 'KHOI' : 'OK'}
                </span>
              </div>
            </div>
          )
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Active camera stream with crosshair */}
        <div className="lg:col-span-2">
          <div
            className="relative bg-black rounded-xl overflow-hidden aspect-video cursor-crosshair"
            onMouseMove={handleMouseMove}
            onMouseDown={() => setDragging(true)}
            onMouseUp={() => setDragging(false)}
            onMouseLeave={() => setDragging(false)}
          >
            <img
              src={getStreamUrl(activeCam)}
              alt={`${CAM_LABELS[activeCam]} Stream`}
              className="w-full h-full object-contain"
              crossOrigin="anonymous"
            />

            {/* Crosshair overlay */}
            <div
              className="absolute pointer-events-none"
              style={{
                left: `${crosshair.x}%`,
                top: `${crosshair.y}%`,
                transform: 'translate(-50%, -50%)',
              }}
            >
              <div className={`w-10 h-10 rounded-full border-2 ${hit ? 'border-red-500' : 'border-green-400'}`}>
                <div className={`absolute top-1/2 left-0 w-full h-0.5 ${hit ? 'bg-red-500' : 'bg-green-400'}`} />
                <div className={`absolute left-1/2 top-0 h-full w-0.5 ${hit ? 'bg-red-500' : 'bg-green-400'}`} />
              </div>
              {hit && (
                <span className="absolute -top-6 left-1/2 -translate-x-1/2 text-xs bg-red-600 text-white px-2 py-0.5 rounded whitespace-nowrap">
                  TARGET LOCKED
                </span>
              )}
            </div>

            {/* Status overlay */}
            <div className="absolute top-3 left-3 flex gap-2">
              <span className="px-2 py-1 rounded text-xs font-bold bg-black/60 text-white">
                {CAM_LABELS[activeCam]}
              </span>
              <span className={`px-2 py-1 rounded text-xs font-bold ${
                det.fire ? 'bg-red-600 text-white fire-pulse' :
                det.smoke ? 'bg-orange-500 text-white' :
                'bg-green-600/80 text-white'
              }`}>
                {det.fire ? 'LUA' : det.smoke ? 'KHOI' : 'AN TOAN'}
              </span>
            </div>

            <div className="absolute bottom-3 right-3 text-xs text-white/70 bg-black/50 px-2 py-1 rounded">
              {status?.mode?.toUpperCase() || '---'} | Brightness: {det.brightness?.toFixed(0) || '--'}
            </div>
          </div>

          {/* Buttons */}
          <div className="flex gap-3 mt-3">
            <button
              onClick={() => handleCapture(activeCam)}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Chup anh ({CAM_LABELS[activeCam]})
            </button>
            <button
              onClick={() => setCrosshairs(prev => ({ ...prev, [activeCam]: { x: 50, y: 50 } }))}
              className="px-4 py-2 bg-slate-600 hover:bg-slate-700 text-white rounded-lg text-sm transition-colors"
            >
              Reset tam
            </button>
          </div>
        </div>

        {/* Right panel */}
        <div className="space-y-4">
          {/* Per-camera detection info */}
          <div className="bg-[#1e293b] rounded-xl p-4">
            <h3 className="text-sm font-semibold text-slate-400 mb-3">
              PHAT HIEN - {CAM_LABELS[activeCam]}
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <InfoCard label="Lua" value={fireBoxes.length} color="text-red-400" />
              <InfoCard label="Khoi" value={smokeBoxes.length} color="text-orange-400" />
            </div>

            {fireBoxes.length > 0 && (
              <div className="mt-3 space-y-2">
                {fireBoxes.map((fb, i) => (
                  <div key={i} className="bg-slate-800 rounded-lg p-2 text-xs">
                    <div className="flex justify-between">
                      <span className="text-red-400 font-bold">LUA #{i + 1}</span>
                      <span className="text-white">{(fb.conf * 100).toFixed(1)}%</span>
                    </div>
                    <div className="text-slate-400 mt-1">
                      Verify: {((fb.verify_score || 0) * 100).toFixed(1)}%
                    </div>
                    <div className="text-slate-500">
                      Tam: ({Math.round((fb.bbox[0] + fb.bbox[2]) / 2)}, {Math.round((fb.bbox[1] + fb.bbox[3]) / 2)})
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* All cameras summary */}
          <div className="bg-[#1e293b] rounded-xl p-4">
            <h3 className="text-sm font-semibold text-slate-400 mb-3">TONG QUAN CAMERA</h3>
            <div className="space-y-2">
              {CAM_IDS.map(camId => {
                const camDet = cameras[camId] || {}
                const camFire = camDet.fire_bboxes?.length || 0
                const camSmoke = camDet.smoke_bboxes?.length || 0
                return (
                  <div
                    key={camId}
                    onClick={() => setActiveCam(camId)}
                    className={`flex justify-between items-center p-2 rounded-lg cursor-pointer transition-colors
                      ${activeCam === camId ? 'bg-slate-700' : 'bg-slate-800 hover:bg-slate-700/50'}`}
                  >
                    <span className="text-sm text-slate-300">{CAM_LABELS[camId]}</span>
                    <div className="flex items-center gap-2">
                      {camFire > 0 && <span className="text-xs text-red-400 font-bold">Lua: {camFire}</span>}
                      {camSmoke > 0 && <span className="text-xs text-orange-400 font-bold">Khoi: {camSmoke}</span>}
                      <span className={`w-2 h-2 rounded-full ${
                        camDet.fire ? 'bg-red-500 animate-pulse' :
                        camDet.smoke ? 'bg-orange-500 animate-pulse' :
                        'bg-green-500'
                      }`} />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Server Status */}
          <div className="bg-[#1e293b] rounded-xl p-4">
            <h3 className="text-sm font-semibold text-slate-400 mb-3">TRANG THAI</h3>
            <div className="space-y-2 text-sm">
              <StatusRow label="Server" value={status?.server || 'offline'} ok={status?.server === 'running'} />
              <StatusRow label="Model" value={status?.model_loaded ? 'Loaded' : 'N/A'} ok={status?.model_loaded} />
              <StatusRow label="Serial" value={status?.serial_connected ? 'Connected' : 'N/A'} ok={status?.serial_connected} />
              <StatusRow label="Mode" value={status?.mode || '---'} ok={true} />
            </div>
          </div>

          {/* Log */}
          <div className="bg-[#1e293b] rounded-xl p-4 max-h-60 overflow-y-auto">
            <h3 className="text-sm font-semibold text-slate-400 mb-3">LOG</h3>
            {logs.length === 0 ? (
              <p className="text-xs text-slate-500">Chua co su kien</p>
            ) : (
              <div className="space-y-1">
                {logs.map((log, i) => (
                  <div key={i} className="text-xs flex gap-2">
                    <span className="text-slate-500">{log.time}</span>
                    <span className="text-slate-600">[{log.cam}]</span>
                    <span className={
                      log.type === 'LUA' ? 'text-red-400' :
                      log.type === 'KHOI' ? 'text-orange-400' :
                      'text-blue-400'
                    }>
                      [{log.type}]
                    </span>
                    {log.count > 0 && <span className="text-slate-300">x{log.count}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function InfoCard({ label, value, color }) {
  return (
    <div className="bg-slate-800 rounded-lg p-3 text-center">
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="text-xs text-slate-400 mt-1">{label}</div>
    </div>
  )
}

function StatusRow({ label, value, ok }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-slate-400">{label}</span>
      <span className={`flex items-center gap-1.5 ${ok ? 'text-green-400' : 'text-red-400'}`}>
        <span className={`w-1.5 h-1.5 rounded-full ${ok ? 'bg-green-400' : 'bg-red-400'}`} />
        {value}
      </span>
    </div>
  )
}
