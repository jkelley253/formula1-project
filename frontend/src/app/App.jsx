import { useEffect, useState } from 'react'
import DriversPage from '../features/drivers/pages/DriversPage.jsx'
import DriverStatsPage from '../features/driverStats/pages/DriverStatsPage.jsx'
import './App.css'

function App() {
    const [hash, setHash] = useState(window.location.hash)
    useEffect(() => {
        function navigate() {
            setHash(window.location.hash)
            window.scrollTo(0, 0)
        }
        window.addEventListener('hashchange', navigate)
        return () => window.removeEventListener('hashchange', navigate)
    }, [])
    const profile = /^#\/drivers\/([a-z0-9_]{1,80})$/.exec(hash)
    if (profile) return <main><DriverStatsPage key={profile[1]} driverId={profile[1]} /></main>
    if (hash && hash !== '#' && hash !== '#/') {
        return <main className="driver-profile"><h1>Page not found</h1><p><a href="#/">Return to driver standings</a></p></main>
    }
    return <main><DriversPage /></main>
}

export default App
