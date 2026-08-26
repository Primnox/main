import React from 'react'
import ReactDOM from 'react-dom/client'
import FamiliarityDesignProto from './components/proto/familiarity-design'
import './styles/fonts.css'
import './styles/tailwind.css'
import './styles/themes.css'
import './styles/progressive-disclosure.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <FamiliarityDesignProto />
  </React.StrictMode>,
)
