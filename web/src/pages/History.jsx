import { useState, useEffect } from 'react'
import { getHistory } from '../api'

export default function History() {
  const [history, setHistory] = useState([])
  const [filter, setFilter] = useState('all')
  const [total, setTotal] = useState(0)

  const fetchHistory = async () => {
    try {
      const { data } = await getHistory(100, filter)
      setHistory(data.history || [])
      setTotal(data.total || 0)
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => { fetchHistory() }, [filter])
  useEffect(() => {
    const interval = setInterval(fetchHistory, 5000)
    return () => clearInterval(interval)
  }, [filter])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Lich su phat hien</h2>
        <span className="text-sm text-slate-400">Tong: {total} su kien</span>
      </div>

      {/* Filter */}
      <div className="flex gap-2">
        {[
          { value: 'all', label: 'Tat ca' },
          { value: 'fire', label: '🔥 Lua' },
          { value: 'smoke', label: '💨 Khoi' },
        ].map(f => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
              filter === f.value ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            {f.label}
          </button>
        ))}
        <button
          onClick={fetchHistory}
          className="ml-auto px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm"
        >
          🔄 Lam moi
        </button>
      </div>

      {/* List */}
      {history.length === 0 ? (
        <div className="text-center py-12 text-slate-500">
          <p className="text-3xl mb-2">📋</p>
          <p>Chua co su kien nao</p>
        </div>
      ) : (
        <div className="space-y-2">
          {history.map((item, i) => (
            <div key={i} className="bg-[#1e293b] rounded-xl p-4 flex gap-4 items-start slide-in">
              {/* Thumbnail */}
              {item.thumbnail ? (
                <img
                  src={`data:image/jpeg;base64,${item.thumbnail}`}
                  alt="Detection"
                  className="w-24 h-18 rounded-lg object-cover shrink-0"
                />
              ) : (
                <div className="w-24 h-18 rounded-lg bg-slate-700 flex items-center justify-center text-2xl shrink-0">
                  {item.fire ? '🔥' : '💨'}
                </div>
              )}

              {/* Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                    item.fire ? 'bg-red-600/20 text-red-400' : 'bg-orange-500/20 text-orange-400'
                  }`}>
                    {item.fire ? 'LUA' : 'KHOI'}
                  </span>
                  <span className="text-sm text-slate-400">{item.timestamp}</span>
                </div>
                <div className="text-sm text-slate-300">
                  {item.fire && `${item.fire_count} vung lua`}
                  {item.fire && item.smoke && ' | '}
                  {item.smoke && `${item.smoke_count} vung khoi`}
                </div>
                {item.fire_bboxes?.length > 0 && (
                  <div className="text-xs text-slate-500 mt-1">
                    Conf: {item.fire_bboxes.map(b => `${(b.conf * 100).toFixed(0)}%`).join(', ')}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
