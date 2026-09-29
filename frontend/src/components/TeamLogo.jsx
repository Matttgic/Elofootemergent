// Logo d'équipe (URL football-data) ; rien n'est affiché si le logo est inconnu.
export function TeamLogo({ src, className = "w-4 h-4" }) {
  if (!src) return null;
  return <img src={src} alt="" loading="lazy" className={`${className} object-contain shrink-0`} />;
}
