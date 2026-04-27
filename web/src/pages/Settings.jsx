import { useState, useEffect } from 'react'
import { useOutletContext } from 'react-router-dom'
import { getConfig, updateConfig } from '../api'

export default function Settings() {
  const { status } = useOutletContext()
  const [config, setConfig] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [activeMode, setActiveMode] = useState('')

  useEffect(() => {
    getConfig().then(({ data }) => {
      setConfig(data)
      setActiveMode(data.active_mode || 'sensitive')
    }).catch(() => {})
  }, [])

  const handleModeChange = async (mode) => {
    setActiveMode(mode)
    setSaving(true)
    try {
      await updateConfig({ active_mode: mode })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      alert('Loi cap nhat: ' + e.message)
    }
    setSaving(false)
  }

  const modes = [
    {
      id: 'safe',
      name: 'An toan',
      icon: '🛡',
      desc: 'Nguong cao, it canh bao nham. Phu hop moi truong nhieu nhieu.',
      color: 'border-green-500',
    },
    {
      id: 'sensitive',
      name: 'Nhay',
      icon: '👁',
      desc: 'Can bang giua do nhay va do chinh xac. Phu hop phong kin.',
      color: 'border-blue-500',
    },
    {
      id: 'ultra_sensitive',
      name: 'Cuc nhay',
      icon: '⚡',
      desc: 'Nguong thap, phat hien moi dau hieu nho. Co the nhieu canh bao.',
      color: 'border-red-500',
    },
  ]

  const modeConfig = config?.fire_modes?.[activeMode] || {}

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold">Cai dat he thong</h2>

      {/* Mode Selection */}
      <div>
        <h3 className="text-sm font-semibold text-slate-400 mb-3">CHE DO HOAT DONG</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {modes.map(mode => (
            <button
              key={mode.id}
              onClick={() => handleModeChange(mode.id)}
              className={`p-4 rounded-xl border-2 text-left transition-all ${
                activeMode === mode.id
                  ? `${mode.color} bg-slate-800`
                  : 'border-slate-700 bg-[#1e293b] hover:border-slate-500'
              }`}
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="text-2xl">{mode.icon}</span>
                <span className="font-semibold">{mode.name}</span>
                {activeMode === mode.id && (
                  <span className="ml-auto text-xs bg-blue-600 text-white px-2 py-0.5 rounded">ACTIVE</span>
                )}
              </div>
              <p className="text-xs text-slate-400">{mode.desc}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Current Config */}
      <div className="bg-[#1e293b] rounded-xl p-4">
        <h3 className="text-sm font-semibold text-slate-400 mb-3">THONG SO HIEN TAI ({activeMode.toUpperCase()})</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <ConfigItem label="YOLO Conf" value={modeConfig.yolo_conf} />
          <ConfigItem label="Verify Threshold" value={modeConfig.verify_threshold} />
          <ConfigItem label="Confirm Frames" value={modeConfig.confirm_frames} />
          <ConfigItem label="Image Size" value={config?.model?.imgsz} />
        </div>
      </div>

      {/* System Info */}
      <div className="bg-[#1e293b] rounded-xl p-4">
        <h3 className="text-sm font-semibold text-slate-400 mb-3">THONG TIN HE THONG</h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-slate-400">Model: </span>
            <span className="text-white">{config?.model?.weights || '---'}</span>
          </div>
          <div>
            <span className="text-slate-400">Device: </span>
            <span className="text-white">{config?.model?.device ?? '---'}</span>
          </div>
          <div>
            <span className="text-slate-400">Server: </span>
            <span className={status?.server === 'running' ? 'text-green-400' : 'text-red-400'}>
              {status?.server || 'offline'}
            </span>
          </div>
          <div>
            <span className="text-slate-400">Serial: </span>
            <span className={status?.serial_connected ? 'text-green-400' : 'text-red-400'}>
              {status?.serial_connected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        </div>
      </div>

      {/* Save indicator */}
      {saved && (
        <div className="slide-in bg-green-600/20 text-green-400 px-4 py-2 rounded-lg text-sm">
          ✅ Da luu cau hinh thanh cong!
        </div>
      )}
    </div>
  )
}

function ConfigItem({ label, value }) {
  return (
    <div className="bg-slate-800 rounded-lg p-3">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="text-lg font-bold text-white mt-1">{value ?? '---'}</div>
    </div>
  )
}
