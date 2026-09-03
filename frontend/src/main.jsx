/**
 * Responsibility: entry point of app, used to start react app, connect to HTML page,
 *    and tell react which component should become the root of the app
 */
// points out problems in code
import { StrictMode } from 'react'
// connect react to the browser
import { createRoot } from 'react-dom/client'
// import styling
import './index.css'
// import the actual application
import App from './app/App.jsx'

/** 
 * createRoot: create a react app and attach it
 * document: the web page
 * getElementByld: finds the HTML element then gives ownership of root to react
 * render(): create this UI
 * <App />: JSX for render the app component
 * <StrictMode> </StrictMode>: wrap contents and watch for mistakes while developing
*/ 
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
