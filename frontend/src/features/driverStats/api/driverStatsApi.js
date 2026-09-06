export default async function getDriverStats(driverId, { signal } = {}) {
    const base = import.meta.env.VITE_DRIVER_STATS_API_BASE_URL
    if (!base) throw new Error('Driver statistics are not available yet.')
    const response = await fetch(`${base.replace(/\/$/, '')}/api/driver-stats/${encodeURIComponent(driverId)}`, { signal })
    if (!response.ok) {
        const messages = {
            400: 'This driver link is invalid.',
            404: 'This driver is not in the current season roster.',
            503: 'Driver statistics are awaiting their first update.',
        }
        throw new Error(messages[response.status] ?? 'Driver statistics are temporarily unavailable.')
    }
    return response.json()
}
