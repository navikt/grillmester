"use strict";

// A descriptor names reviewed choices. It cannot carry selectors, CSS, scripts,
// arbitrary attributes, or values outside its finite option lists.
const MAX_DESIGN_BYTES = 32 * 1024;
const DESIGN_KEY = /^[a-z][a-z0-9-]{0,47}$/;
function exact(value, names) {
  return value !== null && typeof value === "object" && !Array.isArray(value) &&
    Object.keys(value).length === names.length && names.every((name) => Object.hasOwn(value, name));
}
function validKey(value) { return typeof value === "string" && DESIGN_KEY.test(value); }
function label(value) {
  return typeof value === "string" && value.trim().length > 0 && Buffer.byteLength(value, "utf8") <= 120 &&
    !/[\u0000-\u001f\u007f]/.test(value);
}
function unique(items, identify) { return new Set(items.map(identify)).size === items.length; }
function validDesign(value) {
  if (!exact(value, ["version", "variants", "targets"]) || value.version !== 1 || !Array.isArray(value.variants) ||
      ![0, 2, 3, 4].includes(value.variants.length) || !Array.isArray(value.targets) || value.targets.length > 24) return false;
  if (!value.variants.every((variant) => exact(variant, ["key", "label"]) && validKey(variant.key) && label(variant.label)) || !unique(value.variants, (variant) => variant.key)) return false;
  const variants = new Set(value.variants.map((variant) => variant.key));
  if (!value.targets.every((target) => {
    if (!exact(target, ["key", "variant", "label", "controls"]) || !validKey(target.key) ||
        !(target.variant === "" || variants.has(target.variant)) || !label(target.label) || !Array.isArray(target.controls) || target.controls.length > 8) return false;
    return unique(target.controls, (control) => control?.id) && target.controls.every((control) => {
      if (!exact(control, ["id", "label", "type", "initial", "options"]) || !validKey(control.id) || !label(control.label) ||
          !["select", "range", "toggle"].includes(control.type) || !validKey(control.initial) || !Array.isArray(control.options) ||
          control.options.length < 2 || control.options.length > 8 || (control.type === "toggle" && control.options.length !== 2)) return false;
      return control.options.every((option) => exact(option, ["value", "label"]) && validKey(option.value) && label(option.label)) &&
        unique(control.options, (option) => option.value) && control.options.some((option) => option.value === control.initial);
    });
  }) || !unique(value.targets, (target) => `${target.variant}\0${target.key}`)) return false;
  try { return Buffer.byteLength(JSON.stringify(value), "utf8") <= MAX_DESIGN_BYTES; }
  catch { return false; }
}
module.exports = { validDesign, MAX_DESIGN_BYTES, validKey };
