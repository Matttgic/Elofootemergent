import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const api = axios.create({ baseURL: `${BACKEND_URL}/api` });

// Hébergement gratuit : l'API se met en veille après 15 min sans visite et met
// jusqu'à ~1 min à se réveiller. On signale les requêtes qui traînent (> 4 s)
// pour afficher un bandeau d'attente au lieu d'une page qui semble figée.
const SLOW_MS = 4000;
let pending = 0;
let timer = null;
let slow = false;
const listeners = new Set();

function setSlow(value) {
  if (slow === value) return;
  slow = value;
  listeners.forEach((l) => l(value));
}

export function onSlowChange(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function done() {
  pending = Math.max(0, pending - 1);
  if (pending === 0) {
    clearTimeout(timer);
    timer = null;
    setSlow(false);
  }
}

api.interceptors.request.use((config) => {
  pending += 1;
  if (!timer) timer = setTimeout(() => setSlow(true), SLOW_MS);
  return config;
});
api.interceptors.response.use(
  (response) => { done(); return response; },
  (error) => { done(); return Promise.reject(error); },
);
