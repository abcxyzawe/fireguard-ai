import { NavLink } from 'react-router-dom'

const links = [
  { to: '/', icon: '🎥', label: 'Dashboard' },
  { to: '/test-image', icon: '🖼', label: 'Test Anh' },
  { to: '/test-video', icon: '🎬', label: 'Test Video' },
  { to: '/history', icon: '📋', label: 'Lich su' },
  { to: '/settings', icon: '⚙', label: 'Cai dat' },
]

export default function Sidebar({ status }) {
  const connected = status?.server === 'running'
  const modelOk = status?.model_loaded
  const serialOk = status?.serial_connected

  return (
    <aside className="w-56 shrink-0 bg-[#1e293b] border-r border-slate-700 flex flex-col">
      {/* Logo */}
      <div className="p-4 border-b border-slate-700">
        <h1 className="text-lg font-bold text-white flex items-center gap-2">
          🔥 Kiem Soat Lua
        </h1>
        <p className="text-xs text-slate-400 mt-1">Fire Detection System</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-3 space-y-1">
        {links.map(({ to, icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-blue-600/20 text-blue-400 font-medium'
                  : 'text-slate-300 hover:bg-slate-700/50 hover:text-white'
              }`
            }
          >
            <span className="text-base">{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Status */}
      <div className="p-3 border-t border-slate-700 space-y-2">
        <StatusDot label="Server" ok={connected} />
        <StatusDot label="Model" ok={modelOk} />
        <StatusDot label="Serial" ok={serialOk} />
        {status?.mode && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400">Mode</span>
            <span className="px-2 py-0.5 rounded bg-blue-600/20 text-blue-400 font-medium uppercase">
              {status.mode}
            </span>
          </div>
        )}
      </div>
    </aside>
  )
}

function StatusDot({ label, ok }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-slate-400">{label}</span>
      <span className={`flex items-center gap-1.5 ${ok ? 'text-green-400' : 'text-red-400'}`}>
        <span className={`w-2 h-2 rounded-full ${ok ? 'bg-green-400' : 'bg-red-400'}`} />
        {ok ? 'OK' : 'OFF'}
      </span>
    </div>
  )
}
