/**
 * Responsible for:
 *    high level application layout
 *    rendering top level pages and features
 *    composing other components together
 */

// import DriversPage
import DriversPage from '../features/drivers/pages/DriversPage.jsx'

// import CSS associated with this component
import './App.css'

// returns UI description
function App() {
  return (
    <main>
      <DriversPage/>
    </main>
  )
}

// make app available for another module to import as this file's default export
export default App


