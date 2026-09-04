/**
 * Used to communicate with Django Drivers API and return the response data to the frontend layer that requested it
 * Should know:
 *      HTTP method
 *      endpoint
 *      fetch()
 *      response status
 *      JSON parsing
 * 
 * Should not know:
 *      loading ui
 *      DriverCard
 *      React state
 *      CSS
 *      FastF1
 */

/**
 * use asynchronous function since the communication with Django app will take time
 * 
 * This function cannot immediately return driver data because it has to wait for Django
 *      to send an HTTP response
 */
async function getDrivers() {
    const apiBaseUrl = import.meta.env.VITE_API_BASE_URL
        ?? 'https://8bp62sfmta.execute-api.us-west-2.amazonaws.com'
    const response = await fetch(`${apiBaseUrl}/api/drivers`)

    if (!response.ok) {
        throw new Error(`Drivers request failed with status ${response.status}`)
    }

    const data = await response.json()
    return data.drivers
}

// export getDrivers so the useDrivers hook can import and call it
export default getDrivers
