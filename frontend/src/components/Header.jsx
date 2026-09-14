import { Link, useLocation, useNavigate } from "react-router-dom";
import { useState } from "react";
import { Activity, Search, Trophy, BarChart3, BookOpen, PieChart } from "lucide-react";
import { Input } from "../components/ui/input";

export function Header() {
  const [q, setQ] = useState("");
  const nav = useNavigate();
  const loc = useLocation();

  const submit = (e) => {
    e.preventDefault();
    if (q.trim().length >= 2) nav(`/recherche?q=${encodeURIComponent(q.trim())}`);
  };

  const links = [
    { to: "/", label: "Matchs", icon: Activity },
    { to: "/classements", label: "Classements", icon: Trophy },
    { to: "/stats", label: "Stats", icon: PieChart },
    { to: "/methodologie", label: "Méthode", icon: BookOpen },
  ];

  return (
    <header className="sticky top-0 z-50 glass border-b border-slate-800">
      <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 h-16 sm:h-20 flex items-center gap-3 sm:gap-6">
        <Link to="/" className="flex items-center gap-2 shrink-0" data-testid="logo-home-link">
          <div className="w-9 h-9 rounded-lg bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center">
            <BarChart3 className="w-5 h-5 text-emerald-400" />
          </div>
          <div className="leading-none">
            <div className="font-head font-extrabold text-lg text-slate-50 tracking-tight">FootPulse</div>
            <div className="text-[9px] uppercase tracking-[0.2em] text-emerald-400 font-semibold">Analytics Pro</div>
          </div>
        </Link>

        <nav className="hidden md:flex items-center gap-1">
          {links.map((l) => {
            const active = loc.pathname === l.to;
            return (
              <Link key={l.to} to={l.to} data-testid={`nav-${l.label.toLowerCase()}`}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  active ? "text-emerald-400 bg-emerald-500/10" : "text-slate-400 hover:text-slate-100 hover:bg-slate-800/60"}`}>
                <l.icon className="w-4 h-4" />{l.label}
              </Link>
            );
          })}
        </nav>

        <form onSubmit={submit} className="ml-auto relative w-full max-w-xs">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <Input
            data-testid="search-input-team-player"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Rechercher une équipe…"
            className="pl-9 bg-slate-900/60 border-slate-700 text-slate-100 placeholder:text-slate-500 h-10"
          />
        </form>
      </div>

      <nav className="md:hidden flex items-center gap-1 px-3 pb-2 -mt-1">
        {links.map((l) => {
          const active = loc.pathname === l.to;
          return (
            <Link key={l.to} to={l.to} data-testid={`nav-mobile-${l.label.toLowerCase()}`}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                active ? "text-emerald-400 bg-emerald-500/10" : "text-slate-400 hover:text-slate-100"}`}>
              <l.icon className="w-3.5 h-3.5" />{l.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
