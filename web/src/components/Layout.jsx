import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import AlertBanner from './AlertBanner'
import { useState, useEffect } from 'react'
import { getStatus } from '../api'

export default function Layout() {
  const [status, setStatus] = useState(null)
  const [alert, setAlert] = useState(null)

  useEffect(() => {
    const poll = setInterval(async () => {
      try {
        const { data } = await getStatus()
        setStatus(data)
        // Check all cameras for fire/smoke alerts
        const cameras = data.cameras || {}
        let foundAlert = null
        for (const camId of Object.keys(cameras)) {
          const det = cameras[camId] || {}
          if (det.fire) { foundAlert = { type: 'fire', message: `PHAT HIEN LUA! (${camId})` }; break }
          if (det.smoke && !foundAlert) { foundAlert = { type: 'smoke', message: `PHAT HIEN KHOI! (${camId})` } }
        }
        setAlert(foundAlert)
      } catch (e) {
        setStatus(null)
      }
    }, 800)
    return () => clearInterval(poll)
  }, [])

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar status={status} />
      <div className="flex-1 flex flex-col overflow-hidden">
        {alert && <AlertBanner type={alert.type} message={alert.message} />}
        <main className="flex-1 overflow-y-auto p-4 md:p-6">
          <Outlet context={{ status }} />
        </main>
      </div>
    </div>
  )
}
