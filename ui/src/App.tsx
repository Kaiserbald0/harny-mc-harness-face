import './App.css'

function App() {
  return (
    <>
      <section id="center">
        <div>
          <h1>Harny MC Harness Face</h1>
        </div>
      </section>

      <div className="ticks"></div>

      <section id="footer">
        <div id="social">
          <ul>
            <li>
              <a href="https://github.com/Kaiserbald0/harny-mc-harness-face" target="_blank">
                <svg
                  className="button-icon"
                  role="presentation"
                  aria-hidden="true"
                >
                  <use href="/icons.svg#github-icon"></use>
                </svg>
                GitHub
              </a>
            </li>
          </ul>
        </div>
      </section>

      <div className="ticks"></div>
      <section id="spacer"></section>
    </>
  )
}

export default App
