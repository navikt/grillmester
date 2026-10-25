"use strict";

const crypto = require("node:crypto");
const { validDesign, validEditableText } = require("./design-contract.js");
const FIELD_ID = /^(?:text:[a-z][a-z0-9-]{0,47}|control:(?:[a-z][a-z0-9-]{0,47})?\/[a-z][a-z0-9-]{0,47}\/[a-z][a-z0-9-]{0,47})$/;
const signature = value => crypto.createHash("sha256").update(JSON.stringify(value)).digest("hex");

// The paired descriptor is editable source. HTML remains an immutable fragment;
// the trusted renderer applies only named text and explicitly editable choices.
function editorFields(design) {
  if (!validDesign(design) || design.version !== 2) return [];
  const fields = design.texts.map(({ id, label, value }) => ({ id: `text:${id}`, kind: "text", label, value,
    signature: signature(["text", id, label]) }));
  for (const target of design.targets) {
    const variant = design.variants.find(item => item.key === target.variant);
    for (const control of target.controls.filter(item => item.editable === true)) {
      fields.push({ id: `control:${target.variant}/${target.key}/${control.id}`, kind: "control",
        label: `${control.label} · ${target.label}${variant ? ` · ${variant.label}` : ""}`, value: control.initial, options: control.options,
        signature: signature(["control", target.variant, variant?.label ?? "", target.key, target.label, control.id, control.label, control.type, control.options]) });
    }
  }
  return fields;
}
function validHolds(holds, design) {
  if (!Array.isArray(holds) || holds.length > 32 || new Set(holds.map(item => item?.id)).size !== holds.length) return false;
  const fields = editorFields(design);
  return holds.every(item => item && typeof item === "object" && Object.keys(item).length === 4 &&
    ["id", "label", "value", "signature"].every(key => Object.hasOwn(item, key)) && typeof item.id === "string" && FIELD_ID.test(item.id) &&
    typeof item.label === "string" && validEditableText(item.value) && /^[a-f0-9]{64}$/.test(item.signature) &&
    fields.some(field => field.id === item.id && field.label === item.label && field.value === item.value && field.signature === item.signature));
}
function conflictingHolds(holds, design) {
  const fields = editorFields(design);
  return holds.filter(hold => !fields.some(field => field.id === hold.id && field.signature === hold.signature && field.value === hold.value));
}
function holdFor({ id, label, value, signature }) { return { id, label, value, signature }; }
function setField(design, id, value) {
  if (id.startsWith("text:")) design.texts.find(item => `text:${item.id}` === id).value = value;
  else {
    for (const target of design.targets) for (const control of target.controls) {
      if (`control:${target.variant}/${target.key}/${control.id}` === id) control.initial = value;
    }
  }
}
module.exports = { FIELD_ID, editorFields, validHolds, conflictingHolds, holdFor, setField };
