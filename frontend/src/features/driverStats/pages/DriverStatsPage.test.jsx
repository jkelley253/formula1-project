// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import App from '../../../app/App.jsx'
import getDrivers from '../../drivers/api/driversApi.js'
import getDriverStats from '../api/driverStatsApi.js'

vi.mock('../../drivers/api/driversApi.js')
vi.mock('../api/driverStatsApi.js')

const driver = {
    drivers_id: 'hamilton', drivers_first_name: 'Lewis', drivers_last_name: 'Hamilton',
    drivers_number: 44, drivers_driver_code: 'HAM', drivers_nationality: 'British',
    drivers_current_team_names: ['Ferrari'], drivers_current_position: 3,
    drivers_current_total_points: 120, drivers_current_total_wins: 2,
}
const metrics = {
    entries: 12, finishes: 10, points: 120.5, wins: 2, podiums: 5, pole_starts: 1,
    top_10_finishes: 9, dnfs: 2, best_finish: { position: 1, count: 2 }, best_grid: { position: 1, count: 1 },
}
const profile = {
    driver_id: 'hamilton', season: 2026, updated_at: '2026-01-01T00:00:00Z',
    completeness: { season: { unavailable_metrics: [] }, career: { unavailable_metrics: [] } },
    season_stats: { overall: { championship_position: 3, total_points: 120.5, total_wins: 2, total_dnfs: 2 }, grand_prix: metrics, sprint: { ...metrics, wins: 0 } },
    career_stats: { overall: { world_championships: 7, total_points: 5000.5, total_wins: 105, total_dnfs: 34 }, grand_prix: metrics, sprint: { ...metrics, wins: 0 } },
}

beforeEach(() => {
    vi.resetAllMocks()
    window.location.hash = '#/drivers/hamilton'
    window.scrollTo = vi.fn()
    getDrivers.mockResolvedValue([driver])
    getDriverStats.mockResolvedValue(profile)
})
afterEach(cleanup)

describe('driver profiles', () => {
    it('loads a direct link and keeps Grand Prix and sprint stats distinct', async () => {
        render(<App />)
        expect(await screen.findByRole('heading', { name: 'Lewis Hamilton' })).toBeInTheDocument()
        const season = await screen.findByRole('region', { name: 'Current season · 2026' })
        const gp = within(season).getByRole('region', { name: 'Grand Prix' })
        const sprint = within(season).getByRole('region', { name: 'Sprint' })
        expect(within(gp).getByText('Wins').nextSibling).toHaveTextContent('2')
        expect(within(sprint).getByText('Wins').nextSibling).toHaveTextContent('0')
        expect(screen.getAllByText('1 (2)')).toHaveLength(2)
        expect(getDriverStats).toHaveBeenCalledWith('hamilton', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    })

    it('renders stats when identity lookup fails and supports retry', async () => {
        getDrivers.mockRejectedValueOnce(new Error('network'))
        render(<App />)
        expect(await screen.findByText('Could not load driver identity information.')).toBeInTheDocument()
        expect(screen.getByRole('heading', { name: 'Career' })).toBeInTheDocument()
        fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
        expect(await screen.findByRole('heading', { name: 'Lewis Hamilton' })).toBeInTheDocument()
    })

    it('preserves identity when stats fail and recovers on retry', async () => {
        getDriverStats.mockRejectedValueOnce(new Error('Driver statistics are awaiting their first update.'))
        render(<App />)
        expect(await screen.findByRole('alert')).toHaveTextContent('awaiting their first update')
        expect(screen.getByRole('heading', { name: 'Lewis Hamilton' })).toBeInTheDocument()
        fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
        expect(await screen.findByRole('heading', { name: 'Career' })).toBeInTheDocument()
    })

    it('distinguishes unavailable values from zero and no best result', async () => {
        const data = structuredClone(profile)
        data.season_stats.sprint.dnfs = null
        data.career_stats.sprint.best_finish = { position: null, count: 0 }
        data.completeness.season.unavailable_metrics = ['sprint_dnfs']
        getDriverStats.mockResolvedValue(data)
        render(<App />)
        expect(await screen.findByText('Unavailable')).toBeInTheDocument()
        expect(screen.getByText('None yet')).toBeInTheDocument()
        expect(screen.getByText(/Some source data is incomplete/)).toBeInTheDocument()
    })

    it('follows hash navigation back to standings and into another profile', async () => {
        render(<App />)
        await screen.findByRole('heading', { name: 'Career' })
        await act(async () => {
            window.location.hash = '#/'
            window.dispatchEvent(new HashChangeEvent('hashchange'))
        })
        expect(await screen.findByRole('heading', { name: 'Driver standings' })).toBeInTheDocument()
        expect(screen.getByRole('link', { name: 'Lewis Hamilton' })).toHaveAttribute('href', '#/drivers/hamilton')
        await act(async () => {
            window.location.hash = '#/drivers/hamilton'
            window.dispatchEvent(new HashChangeEvent('hashchange'))
        })
        expect(await screen.findByRole('heading', { name: 'Career' })).toBeInTheDocument()
    })

    it('handles malformed routes without making stats requests', () => {
        window.location.hash = '#/drivers/invalid/id'
        render(<App />)
        expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
        expect(getDriverStats).not.toHaveBeenCalled()
    })
})
