import "./App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Header } from "./components/Header";
import Home from "./pages/Home";
import MatchDetail from "./pages/MatchDetail";
import TeamPage from "./pages/TeamPage";
import Leaderboards from "./pages/Leaderboards";
import Stats from "./pages/Stats";
import Search from "./pages/Search";
import Methodologie from "./pages/Methodologie";
import { Toaster } from "./components/ui/sonner";

function App() {
  return (
    <div className="App min-h-screen">
      <BrowserRouter>
        <Header />
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/match/:id" element={<MatchDetail />} />
          <Route path="/equipe/:code/:id" element={<TeamPage />} />
          <Route path="/classements" element={<Leaderboards />} />
          <Route path="/stats" element={<Stats />} />
          <Route path="/recherche" element={<Search />} />
          <Route path="/methodologie" element={<Methodologie />} />
        </Routes>
        <footer className="max-w-7xl mx-auto px-4 py-8 mt-8 text-center text-xs text-slate-600 border-t border-slate-800">
          FootPulse Analytics Pro — Système de notation statistique. Données football-data.org.
          Les signaux sont indicatifs et ne constituent en aucun cas des prédictions certaines.
        </footer>
      </BrowserRouter>
      <Toaster />
    </div>
  );
}

export default App;
