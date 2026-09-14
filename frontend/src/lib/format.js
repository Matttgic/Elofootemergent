export function scoreColor(s) {
  if (s === null || s === undefined) return "#64748B";
  if (s >= 90) return "#10B981";
  if (s >= 75) return "#34D399";
  if (s >= 50) return "#F59E0B";
  return "#EF4444";
}

export function scoreLabel(s) {
  if (s === null || s === undefined) return "N/D";
  if (s >= 90) return "Élite";
  if (s >= 75) return "Élevé";
  if (s >= 50) return "Moyen";
  return "Faible";
}

export function statutColor(statut) {
  if (statut === "Favorable") return "#10B981";
  if (statut === "Neutre") return "#F59E0B";
  return "#EF4444";
}

export function resultColor(r) {
  if (r === "W") return "#10B981";
  if (r === "D") return "#64748B";
  return "#EF4444";
}

const DAYS = ["dim", "lun", "mar", "mer", "jeu", "ven", "sam"];
const MONTHS = ["jan", "fév", "mar", "avr", "mai", "juin", "juil", "août", "sep", "oct", "nov", "déc"];

export function kickoff(utc) {
  if (!utc) return "";
  const d = new Date(utc);
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Paris" });
}

export function frDate(utc, withYear = false) {
  if (!utc) return "";
  const d = new Date(utc);
  const s = `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;
  return withYear ? `${s} ${d.getFullYear()}` : s;
}

export function frDateShort(iso) {
  if (!iso) return "";
  const d = new Date(iso + "T00:00:00");
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

export function todayISO() {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Europe/Paris" });
}

export function timeAgo(iso) {
  if (!iso) return "jamais";
  const diff = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return "à l'instant";
  if (diff < 3600) return `il y a ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `il y a ${Math.floor(diff / 3600)} h`;
  return `il y a ${Math.floor(diff / 86400)} j`;
}
