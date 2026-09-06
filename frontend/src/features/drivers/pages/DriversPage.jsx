import { useEffect, useState } from 'react'
import getDrivers from '../api/driversApi.js'

function DriversPage() {
    const [drivers, setDrivers] = useState([])
    const [error, setError] = useState(null)
    const [isLoading, setIsLoading] = useState(true)

    useEffect(() => {
        let isActive = true

        getDrivers()
            .then((data) => {
                if (isActive) setDrivers(data)
            })
            .catch(() => {
                if (isActive) setError('Could not load the driver standings.')
            })
            .finally(() => {
                if (isActive) setIsLoading(false)
            })

        return () => { isActive = false }
    }, [])

    return (
        <section className="standings" aria-labelledby="standings-title">
            <header className="standings__header">
                <div>
                    <p className="eyebrow">Formula 1</p>
                    <h1 id="standings-title">Driver standings</h1>
                </div>
                {!isLoading && !error && <p className="driver-count">{drivers.length} drivers</p>}
            </header>

            {isLoading && <p className="status">Loading standings…</p>}
            {error && <p className="status status--error">{error}</p>}

            {!isLoading && !error && (
                <div className="table-shell">
                    <table>
                        <thead><tr>
                            <th scope="col">Pos</th><th scope="col">Driver</th>
                            <th scope="col">Team</th><th scope="col" className="numeric">Wins</th>
                            <th scope="col" className="numeric">Points</th>
                        </tr></thead>
                        <tbody>{drivers.map((driver) => (
                            <tr key={driver.drivers_id}>
                                <td className="position">{driver.drivers_current_position}</td>
                                <td><div className="driver">
                                    <span className="driver__code">{driver.drivers_driver_code}</span>
                                    <span><a className="driver-link" href={`#/drivers/${driver.drivers_id}`}><strong>{driver.drivers_first_name} {driver.drivers_last_name}</strong></a>
                                    <small>#{driver.drivers_number} · {driver.drivers_nationality}</small></span>
                                </div></td>
                                <td>{driver.drivers_current_team_names.join(', ')}</td>
                                <td className="numeric">{driver.drivers_current_total_wins}</td>
                                <td className="numeric points">{driver.drivers_current_total_points}</td>
                            </tr>
                        ))}</tbody>
                    </table>
                </div>
            )}
        </section>
    )
}

export default DriversPage
