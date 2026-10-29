"use strict";

async function openTools(ui) {
  const menu = ui.locator(".more-tools");
  if (!(await menu.getAttribute("open"))) {
    if (!(await menu.evaluate(node => node.open))) await menu.locator("summary").click();
  }
}
async function enterBrowse(ui) {
  const cancel = ui.locator('[data-action="browse"]');
  if (await cancel.isVisible()) await cancel.click();
}
async function openAdjust(ui) {
  const adjust = ui.getByRole("button", { name: "Juster visning", exact: true });
  if (!(await adjust.isVisible())) await openTools(ui);
  await adjust.click();
}
async function startComparison(ui) {
  await enterBrowse(ui);
  const variants = ui.locator("xpath=..").locator(".vc-variant-nav");
  const namedCompare = variants.getByRole("button", { name: "Sammenlign", exact: true });
  if (await namedCompare.isVisible()) { await namedCompare.click(); return; }
  const compare = ui.getByRole("button", { name: "Sammenlign varianter", exact: true });
  if (!(await compare.isVisible())) await openTools(ui);
  await compare.click();
}
// Older round scenarios deliberately stage notes before opening their basket.
// Keep that intent explicit now that a single note can be sent directly.
async function collectFeedback(ui) {
  const collect = ui.locator('[data-action="collect"]');
  const retry = ui.getByRole("button", { name: "Prøv samme lagring igjen", exact: true });
  if (await retry.isVisible()) await retry.click();
  else await collect.click();
  const end = Date.now() + 15000;
  while (await collect.isVisible()) {
    if (await ui.locator(".compose-error").isVisible()) return;
    if (Date.now() >= end) throw new Error("Staging feedback did not settle.");
    await new Promise(resolve => setTimeout(resolve, 25));
  }
  const panel = ui.getByRole("region", { name: "Innspill til prototypen", exact: true });
  if (!(await panel.isVisible())) await ui.locator('[data-action="panel"]').click();
}

module.exports = { openTools, enterBrowse, openAdjust, startComparison, collectFeedback };
