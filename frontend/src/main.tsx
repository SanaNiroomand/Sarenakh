import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "vazirmatn/misc/UI-Farsi-Digits/Vazirmatn-UI-FD-font-face.css";
import "./index.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
