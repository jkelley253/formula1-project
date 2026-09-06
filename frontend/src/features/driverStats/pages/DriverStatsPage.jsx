import { useEffect, useState } from 'react'
import getDrivers from '../../drivers/api/driversApi.js'
import getDriverStats from '../api/driverStatsApi.js'
import './DriverStatsPage.css'

const labels = {
    championship_position: 'Season position', total_points: 'Points earned',
    total_wins: 'Total races won', total_dnfs: 'Total DNFs', world_championships: 'World championships',
    entries: 'Races entered', finishes: 'Races completed', points: 'Points earned',
    wins: 'Wins', podiums: 'Podiums', pole_starts: 'Pole starts (grid P1)',
    top_10_finishes: 'Top-10 finishes', dnfs: 'Did not finish',
    best_finish: 'Highest race finish', best_grid: 'Highest grid position',
}
const seasonFields = ['finishes', 'points', 'wins', 'podiums', 'pole_starts', 'top_10_finishes', 'dnfs']
const careerFields = ['entries', ...seasonFields.slice(0, -1), 'best_finish', 'best_grid', 'dnfs']
const numberFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 })

function valueText(value) {
    if (value === null || value === undefined) return 'Unavailable'
    if (typeof value === 'object') {
        if (value.count === null) return 'Unavailable'
        if (value.position === null) return 'None yet'
        return `${numberFormat.format(value.position)} (${numberFormat.format(value.count)})`
    }
    return numberFormat.format(value)
}

function Metrics({ stats, fields }) {
    return <dl className="stats-metrics">{fields.map((field) => (
        <div className="stats-metric" key={field}>
            <dt>{labels[field]}</dt><dd>{valueText(stats[field])}</dd>
        </div>
    ))}</dl>
}

function StatsSection({ title, stats, career = false }) {
    const id = career ? 'career-stats' : 'season-stats'
    return <section className="stats-section" aria-labelledby={id}>
        <h2 id={id}>{title}</h2>
        <Metrics stats={stats.overall} fields={career
            ? ['total_points', 'total_wins', 'total_dnfs', 'world_championships']
            : ['championship_position', 'total_points', 'total_wins', 'total_dnfs']} />
        <div className="stats-formats">{[['grand_prix', 'Grand Prix'], ['sprint', 'Sprint']].map(([key, name]) => (
            <section key={key} aria-labelledby={`${id}-${key}`} className="stats-format">
                <h3 id={`${id}-${key}`}>{name}</h3>
                <Metrics stats={stats[key]} fields={career ? careerFields : seasonFields} />
            </section>
        ))}</div>
    </section>
}

export default function DriverStatsPage({ driverId }) {
    const [driver, setDriver] = useState(null)
    const [identityError, setIdentityError] = useState(null)
    const [stats, setStats] = useState(null)
    const [statsError, setStatsError] = useState(null)
    const [receivedAt, setReceivedAt] = useState(null)
    const [attempt, setAttempt] = useState(0)

    useEffect(() => {
        let active = true
        const controller = new AbortController()
        getDrivers().then((drivers) => {
            if (active) {
                const found = drivers.find((item) => item.drivers_id === driverId)
                if (found) setDriver(found)
                else setIdentityError('Driver identity information is unavailable.')
            }
        }).catch(() => { if (active) setIdentityError('Could not load driver identity information.') })
        getDriverStats(driverId, { signal: controller.signal })
            .then((data) => { if (active) { setStats(data); setReceivedAt(Date.now()) } })
            .catch((error) => { if (active) setStatsError(error.message) })
        return () => { active = false; controller.abort() }
    }, [driverId, attempt])

    function retry() {
        setIdentityError(null)
        setStatsError(null)
        setAttempt((value) => value + 1)
    }

    const incomplete = stats && Object.values(stats.completeness).some((coverage) => coverage.unavailable_metrics.length > 0)
    const stale = stats && receivedAt - Date.parse(stats.updated_at) > 8 * 24 * 60 * 60 * 1000
    return <article className="driver-profile">
        <a className="back-link" href="#/">← Driver standings</a>
        <header className="profile-header">
            <p className="eyebrow">Formula 1 · Driver profile</p>
            <h1>{driver ? `${driver.drivers_first_name} ${driver.drivers_last_name}` : 'Driver statistics'}</h1>
            {driver && <p className="driver-identity">#{driver.drivers_number} · {driver.drivers_driver_code} · {driver.drivers_nationality}<br />{driver.drivers_current_team_names.join(', ')}</p>}
            {!driver && !identityError && <p role="status">Loading driver information…</p>}
            {identityError && <p role="status">{identityError}</p>}
            {stats && <p className="stats-updated">{stats.season} season · Updated <time dateTime={stats.updated_at}>{new Date(stats.updated_at).toLocaleString()}</time></p>}
        </header>
        {!stats && !statsError && <p className="status" role="status">Loading driver statistics…</p>}
        {statsError && <p className="status status--error" role="alert">{statsError}</p>}
        {(identityError || statsError) && <button className="stats-retry" onClick={retry}>Try again</button>}
        {stats && <>
            {stale && <p className="stats-notice" role="status">These statistics are from the last successful update. A newer update is pending.</p>}
            {incomplete && <p className="stats-notice">Some source data is incomplete. Affected statistics are marked unavailable.</p>}
            <StatsSection title={`Current season · ${stats.season}`} stats={stats.season_stats} />
            <StatsSection title="Career" stats={stats.career_stats} career />
            <aside className="stats-definitions" aria-label="How statistics are counted">
                <h2>About these statistics</h2>
                <p>Entries count appearances in race results, including recorded non-starts. Completed races include lapped finishers. DNFs count retirements and accidents; they exclude non-starts and disqualifications.</p>
                <p>A classified retirement can count toward a finishing-position statistic and a DNF. Pole starts mean grid position 1. Numbers in parentheses show how many times a driver achieved their best position.</p>
                <p>Overall points use championship standings and can differ from Grand Prix plus sprint points after championship adjustments. Championships count completed seasons. Grand Prix and sprint wins and DNFs are combined only in the overall totals.</p>
                <p>Source: <a href="https://api.jolpi.ca/">Jolpica F1</a>. Updated weekly.</p>
            </aside>
        </>}
    </article>
}
