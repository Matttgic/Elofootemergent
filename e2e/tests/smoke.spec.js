// Parcours principaux du site sur l'API simulée (données de test déterministes).
const { test, expect } = require("@playwright/test");

// Erreurs JavaScript et erreurs console (hors ressources non chargées) : aucune tolérée.
function watchErrors(page) {
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(m.text());
  });
  return errors;
}

// Accueil, puis journée suivante si aujourd'hui est sans match ; renvoie la grille.
async function openMatchday(page) {
  await page.goto("/");
  await expect(page.locator('[data-testid="no-matches"], [data-testid="matches-grid"]').first()).toBeVisible();
  if (await page.getByTestId("no-matches").isVisible()) {
    await page.getByTestId("goto-next-matchday").click();
  }
  const grid = page.getByTestId("matches-grid");
  await expect(grid).toBeVisible();
  return grid;
}

test("accueil : journée suivante, probabilités Elo et cotes sur les cartes", async ({ page }) => {
  const errors = watchErrors(page);
  const grid = await openMatchday(page);
  await expect(grid.locator('[data-testid$="-prediction"]').first()).toBeVisible();
  await expect(grid.locator('[data-testid$="-odds"]').first()).toContainText("Cotes");
  // la barre 1N2 affiche trois pourcentages cohérents
  const text = await grid.locator('[data-testid$="-probas"]').first().innerText();
  const pcts = [...text.matchAll(/(\d+)%/g)].map((m) => Number(m[1]));
  expect(pcts).toHaveLength(3);
  expect(Math.abs(pcts.reduce((a, b) => a + b, 0) - 100)).toBeLessThanOrEqual(2);
  expect(errors).toEqual([]);
});

test("fiche match puis fiche équipe : Elo, cotes et courbe d'évolution", async ({ page }) => {
  const errors = watchErrors(page);
  const grid = await openMatchday(page);
  await grid.locator("a").first().click();
  await expect(page.getByTestId("prediction-panel")).toBeVisible();
  await expect(page.getByTestId("elo-note")).toContainText("Elo");
  await expect(page.getByTestId("xg-note")).toContainText("Forme xG");   // modèle Elo + xG
  await expect(page.getByTestId("prediction-panel")).toContainText("Modèle Elo + xG");
  await expect(page.getByTestId("detail-odds")).toBeVisible();
  await page.getByTestId("team-link-home").click();
  await expect(page.getByTestId("team-elo")).toContainText("Elo");
  await expect(page.getByTestId("team-xg")).toContainText("forme xG");
  await expect(page.getByTestId("team-elo-chart").locator(".recharts-line path").first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("classements : équipes triées par Elo puis par note, buteurs avec logos", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/classements");
  const rows = page.getByTestId("teams-leaderboard").locator("a");
  await expect(rows).toHaveCount(20);
  const elos = await page.locator('[data-testid^="lb-team-elo-"] .font-stat').allInnerTexts();
  const values = elos.map(Number);
  expect(values).toEqual([...values].sort((a, b) => b - a));
  await page.getByTestId("team-sort-note").click();
  await expect(page.getByTestId("team-sort-note")).toHaveClass(/bg-cyan-500/);
  await page.getByTestId("tab-buteurs").click();
  const scorers = page.getByTestId("players-leaderboard-buteurs");
  await expect(scorers.locator("a").first()).toBeVisible();
  await expect(scorers.locator("img").first()).toHaveAttribute("src", /favicon\.svg/);
  expect(errors).toEqual([]);
});

test("stats : qualité du modèle, avertissement et paris suivis", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/stats");
  await expect(page.getByTestId("stat-model-quality")).toBeVisible();
  await expect(page.getByTestId("quality-calibration").locator("tbody tr").first()).toBeVisible();
  await expect(page.getByTestId("sim-backtest-warning")).toContainText("13 273");
  await expect(page.getByTestId("bets-rows-en_attente").locator("a")).toHaveCount(10);
  await page.getByTestId("bets-tab-regles").click();
  await expect(page.getByTestId("bets-rows-regles").locator("a")).toHaveCount(10);
  expect(errors).toEqual([]);
});

test("méthodologie et recherche", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/methodologie");
  await expect(page.getByTestId("methodo-backtest").locator("table").first().locator("tbody tr")).toHaveCount(5);
  await expect(page.getByTestId("methodo-backtest-xg").locator("tbody tr")).toHaveCount(4);
  await expect(page.getByTestId("methodo-xg")).toContainText("xG");
  await page.goto("/recherche?q=man");
  await expect(page.getByTestId("search-teams")).toContainText("Manchester City");
  // un joueur trouvé mène à sa fiche
  await page.goto("/recherche?q=Joueur 1");
  await page.getByTestId("search-players").locator("a").first().click();
  await expect(page).toHaveURL(/\/joueur\/\d+/);
  await expect(page.getByTestId("player-header")).toBeVisible();
  expect(errors).toEqual([]);
});

test("bandeau « Réveil du serveur » quand l'API tarde à répondre", async ({ page }) => {
  await page.route("**/api/status", async (route) => {
    await new Promise((r) => setTimeout(r, 6000));
    await route.continue();
  });
  await page.goto("/");
  await expect(page.getByTestId("server-wake-banner")).toBeVisible({ timeout: 8000 });
  await expect(page.getByTestId("server-wake-banner")).toBeHidden({ timeout: 15000 });
});

test("comparateur : depuis une fiche équipe, probabilités selon le terrain", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/equipe/PL/1");
  await page.getByTestId("team-compare-link").click();
  await expect(page).toHaveURL(/\/comparer\?a=PL-1&b=PL-\d+/);
  await expect(page.getByTestId("compare-result")).toBeVisible();
  await expect(page.getByTestId("compare-a_recoit")).toBeVisible();
  await expect(page.getByTestId("compare-b_recoit")).toBeVisible();
  await expect(page.getByTestId("compare-elo-chart").locator(".recharts-line").first()).toBeVisible();
  // changer d'adversaire met à jour l'adresse et le résultat
  await page.getByTestId("compare-select-b").selectOption("PL-4");
  await expect(page).toHaveURL(/b=PL-4/);
  await expect(page.getByTestId("compare-stats")).toContainText("Manchester City");
  expect(errors).toEqual([]);
});
