import React from "react"
import ReactDOM from "react-dom/client"
import App from "./App"
import "./index.css"

// 在 React 挂载前先应用主题，避免启动时闪一下白屏。
const theme = (localStorage.getItem("otr-theme") as "light" | "dark") || "dark"
const accent = localStorage.getItem("otr-accent") || "blue"
document.documentElement.classList.toggle("dark", theme === "dark")
document.documentElement.dataset.accent = accent
document.documentElement.style.colorScheme = theme

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
