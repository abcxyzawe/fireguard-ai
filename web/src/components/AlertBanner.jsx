export default function AlertBanner({ type, message }) {
  const isFire = type === 'fire'
  return (
    <div
      className={`slide-in px-4 py-3 flex items-center gap-3 font-bold text-white ${
        isFire ? 'bg-red-600 fire-pulse' : 'bg-orange-500'
      }`}
    >
      <span className="text-2xl">{isFire ? '🔥' : '💨'}</span>
      <span className="text-lg">{message}</span>
      <span className="ml-auto text-sm font-normal opacity-80">
        {new Date().toLocaleTimeString()}
      </span>
    </div>
  )
}
