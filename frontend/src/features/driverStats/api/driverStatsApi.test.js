import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import getDriverStats from './driverStatsApi.js'

beforeEach(() => {
    vi.stubEnv('VITE_DRIVER_STATS_API_BASE_URL', 'https://stats.example/')
    vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
})

it('uses the separate stats endpoint and forwards cancellation', async () => {
    const controller = new AbortController()
    fetch.mockResolvedValue({ ok: true, json: async () => ({ driver_id: 'hamilton' }) })
    expect(await getDriverStats('hamilton', { signal: controller.signal })).toEqual({ driver_id: 'hamilton' })
    expect(fetch).toHaveBeenCalledWith('https://stats.example/api/driver-stats/hamilton', { signal: controller.signal })
})

it.each([
    [400, 'This driver link is invalid.'],
    [404, 'This driver is not in the current season roster.'],
    [503, 'Driver statistics are awaiting their first update.'],
    [502, 'Driver statistics are temporarily unavailable.'],
])('explains HTTP %s without exposing upstream errors', async (status, message) => {
    fetch.mockResolvedValue({ ok: false, status })
    await expect(getDriverStats('hamilton')).rejects.toThrow(message)
})
