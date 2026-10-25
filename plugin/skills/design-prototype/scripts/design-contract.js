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
function validEditableText(value) {
  return typeof value === "string" && Buffer.byteLength(value, "utf8") <= 2000 &&
    !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value);
}
function validDesign(value) {
  const editable = value?.version === 2;
  if (!exact(value, editable ? ["version", "variants", "targets", "texts"] : ["version", "variants", "targets"]) ||
      ![1, 2].includes(value.version) || !Array.isArray(value.variants) ||
      ![0, 2, 3, 4].includes(value.variants.length) || !Array.isArray(value.targets) || value.targets.length > 24) return false;
  if (editable && (!Array.isArray(value.texts) || value.texts.length > 16 || !unique(value.texts, item => item?.id) ||
      !value.texts.every(item => exact(item, ["id", "label", "value"]) && validKey(item.id) && label(item.label) && validEditableText(item.value)))) return false;
  if (!value.variants.every((variant) => exact(variant, ["key", "label"]) && validKey(variant.key) && label(variant.label)) || !unique(value.variants, (variant) => variant.key)) return false;
  const variants = new Set(value.variants.map((variant) => variant.key));
  if (!value.targets.every((target) => {
    if (!exact(target, ["key", "variant", "label", "controls"]) || !validKey(target.key) ||
        !(target.variant === "" || variants.has(target.variant)) || !label(target.label) || !Array.isArray(target.controls) || target.controls.length > 8) return false;
    return unique(target.controls, (control) => control?.id) && target.controls.every((control) => {
      const fields = ["id", "label", "type", "initial", "options"];
      if (editable && Object.hasOwn(control || {}, "editable")) fields.push("editable");
      if (!exact(control, fields) || (fields.includes("editable") && typeof control.editable !== "boolean") || !validKey(control.id) || !label(control.label) ||
          !["select", "range", "toggle"].includes(control.type) || !validKey(control.initial) || !Array.isArray(control.options) ||
          control.options.length < 2 || control.options.length > 8 || (control.type === "toggle" && control.options.length !== 2)) return false;
      return control.options.every((option) => exact(option, ["value", "label"]) && validKey(option.value) && label(option.label)) &&
        unique(control.options, (option) => option.value) && control.options.some((option) => option.value === control.initial);
    });
  }) || !unique(value.targets, (target) => `${target.variant}\0${target.key}`)) return false;
  if (editable && value.texts.length + value.targets.reduce((count, target) => count + target.controls.filter(control => control.editable === true).length, 0) > 32) return false;
  // Editor reads include both current fields and their preserved values. Keep
  // the complete response within the canvas transport's 64 KiB envelope.
  try { return Buffer.byteLength(JSON.stringify(value), "utf8") <= (editable ? 24 * 1024 : MAX_DESIGN_BYTES); }
  catch { return false; }
}
module.exports = { validDesign, MAX_DESIGN_BYTES, validKey, validEditableText };
