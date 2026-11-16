import React, { useEffect, useState } from 'react'
import { motion, AnimatePresence, MotionConfig } from 'motion/react'
import { api, STATIC, DEFAULT_SETTINGS } from './api'
import { Loading, setPalette } from './ui'
import Overview from './Overview'
import Optimizer from './Optimizer'
import Forecasts from './Forecasts'
import Risk from './Risk'
import Home from './Home'
import WhatIf from './WhatIf'
import Suppliers from './Suppliers'
import Evaluation from './Evaluation'
import DataIntegration from './DataIntegration'

const TABS = [
  ['home', 'How it works'],
  ['optimizer', 'Budget Optimizer'],
  ['simulation', 'What-If Simulation'],
  ['suppliers', 'Supplier Intelligence'],
  ['overview', 'Opportunities'],
  ['forecasts', 'Forecast Explorer'],
  ['evaluation', 'Accuracy & Backtest'],
  ['integration', 'Data & Replanning'],
  ['risk', 'Risk Strategy'],
]
const TAB_KEYS = TABS.map(([k]) => k)

const tabFromHash = () => {
  const h = (window.location.hash || '').replace('#', '')
  return TAB_KEYS.includes(h) ? h : 'home'
}
const systemTheme = () => (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
const savedTheme = () => {
  try {
    return localStorage.getItem('tbo-theme-mono')
  } catch {
    return null
  }
}
const storedTheme = () => savedTheme() || systemTheme()

export default function App() {
  const [tab, setTab] = useState(tabFromHash)
  const [theme, setTheme] = useState(storedTheme)
  const [summary, setSummary] = useState(null)
  const [err, setErr] = useState(null)
  const [settings, setSettings] = useState(DEFAULT_SETTINGS)
  const [forecastItem, setForecastItem] = useState('H-GOA-M')

  setPalette(theme)

  const go = (t) => {
    setTab(t)
    try {
      if (window.location.hash !== `#${t}`) window.history.replaceState(null, '', `#${t}`)
    } catch {
      window.location.hash = t
    }
    window.scrollTo(0, 0)
  }

  useEffect(() => {
    api.summary()
      .then(setSummary)
      .catch((e) => setErr(e.message))
  }, [])

  useEffect(() => {
    const onHash = () => setTab(tabFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!mq) return
    const onChange = () => {
      if (!savedTheme()) setTheme(mq.matches ? 'dark' : 'light')
    }
    mq.addEventListener?.('change', onChange)
    return () => mq.removeEventListener?.('change', onChange)
  }, [])

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    try {
      localStorage.setItem('tbo-theme-mono', next)
    } catch {
      /* storage unavailable */
    }
  }

  useEffect(() => {
    const label = TABS.find(([k]) => k === tab)?.[1]
    document.title = `${label} · TBO Inventory Intelligence`
  }, [tab])

  if (err)
    return (
      <div className="fatal">
        Could not load data ({err}).{' '}
        {STATIC ? (
          'Please refresh the page.'
        ) : (
          <>
            Start the API with <code>uvicorn app:app --port 8000</code> in <code>backend/</code>.
          </>
        )}
      </div>
    )

  if (!summary) return <Loading text="Loading platform models & intelligence engines…" />

  const openForecast = (id) => {
    setForecastItem(id)
    go('forecasts')
  }

  return (
    <MotionConfig reducedMotion="user">
      <div className="app">
        <a
          className="skip"
          href="#main-content"
          onClick={(e) => {
            e.preventDefault()
            document.getElementById('main-content')?.focus()
          }}
        >
          Skip to content
        </a>
        <header className="top">
          <div className="brand">
            <button className="logo" onClick={() => go('home')} aria-label="Go to home">
              TBO
            </button>
            <div>
              <div className="brand-t">Inventory Intelligence</div>
              <div className="brand-s">
                Pre-buy planning · travel weeks {summary.horizon.start} → {summary.horizon.end}
              </div>
            </div>
          </div>
          <nav aria-label="Main sections" style={{ overflowX: 'auto', maxWidth: '1000px' }}>
            {TABS.map(([k, l]) => (
              <button
                key={k}
                className={tab === k ? 'on' : ''}
                onClick={() => go(k)}
                aria-current={tab === k ? 'page' : undefined}
                style={{ whiteSpace: 'nowrap' }}
              >
                {tab === k && (
                  <motion.span
                    layoutId="navpill"
                    className="navpill"
                    transition={{ type: 'spring', stiffness: 420, damping: 34 }}
                  />
                )}
                <span className="navtxt">{l}</span>
              </button>
            ))}
          </nav>
          <div className="top-right">
            <div className="asof">
              Planning date<b>{summary.today}</b>
            </div>
            <motion.button
              className="theme-btn"
              onClick={toggleTheme}
              whileTap={{ rotate: 25, scale: 0.9 }}
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
              title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            >
              {theme === 'dark' ? '☀' : '☾'}
            </motion.button>
          </div>
        </header>

        <main id="main-content" tabIndex={-1}>
          <AnimatePresence mode="wait">
            <motion.div
              key={tab}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            >
              {tab === 'home' && <Home summary={summary} go={go} />}
              {tab === 'optimizer' && (
                <Optimizer
                  summary={summary}
                  settings={settings}
                  setSettings={setSettings}
                  openForecast={openForecast}
                />
              )}
              {tab === 'simulation' && <WhatIf summary={summary} />}
              {tab === 'suppliers' && <Suppliers />}
              {tab === 'overview' && <Overview summary={summary} openForecast={openForecast} />}
              {tab === 'forecasts' && <Forecasts itemId={forecastItem} setItemId={setForecastItem} />}
              {tab === 'evaluation' && <Evaluation summary={summary} />}
              {tab === 'integration' && <DataIntegration />}
              {tab === 'risk' && <Risk settings={settings} />}
            </motion.div>
          </AnimatePresence>
        </main>

        <footer>
          Built by Team Void · TBO Inventory Intelligence 2.0 · Data Provenance: {summary.provenance?.dataset_name || 'Benchmark Dataset'} · LightGBM Quantile Ensemble · Monte Carlo Risk · HiGHS MILP Allocation
        </footer>
      </div>
    </MotionConfig>
  )
}
