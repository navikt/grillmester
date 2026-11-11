# Figma to Aksel code

The Figma design is the source and Aksel is the building material. The result is
Aksel components, primitives and tokens, never the HTML that Figma generates.

## 1. Get the design

This needs the Figma MCP tools and a link of the form
`https://figma.com/design/<fileKey>/<name>?node-id=1-2`.

- **No Figma tools in the session:** say so, and ask the user to connect Figma or
  attach a screenshot or an export of the frame. Build nothing from the link
  alone.
- Call `get_design_context` for the node with the arguments its schema lists.
  Keep the screenshot it returns, or call `get_screenshot` for the same node. It
  is the reference in step 3.
- **Truncated output:** call `get_metadata` to list the child nodes, fetch the
  frame you need, and tell the user you narrowed the scope.
- If Figma offers to create Code Connect mappings, continue without them. Create
  or publish a mapping only when the user asks for it.

## 2. Translate

Weigh each part of the design context:

| Part | Trust | Use it for |
|---|---|---|
| Code Connect snippet | Highest | Which component to use. Keep its composition, and check its props against the installed types, because a snippet can be older than the package. |
| Screenshot | High | Hierarchy, spacing rhythm and intent |
| Generated HTML and Tailwind | Low | Structural hints only |

- A row is `HStack`, a column is `VStack`, a grid is `HGrid`, and a frame with
  padding, background or border is `Box`.
- A gap or padding becomes the nearest `space-*` token. A colour or size becomes
  the Aksel token with the same role; Figma's variables carry the token names.
  Copy no hex value and no pixel value.
- A layer named after a component, such as Button or Card, is a hint: look the
  real component up before you write markup.
- A font, colour or padding that Figma emits as CSS becomes the component's prop
  or a token, not a `style` attribute.
- Find icons in Aksel. Save other assets through the project's own asset
  handling; the URLs Figma returns expire.
- Figma often shows one width. Look for a mobile and a desktop frame; without
  them, use responsive props and say what you assumed.

## 3. Check

1. Run the type check and lint on the changed files. A type error usually
   renders a blank page, which makes a visual check worthless.
2. Compare the rendered result with the screenshot when the project already has
   a way to render it. Ask before you start a dev server or install a tool.
   Without a rendering, ask the user for a screenshot, and say the fidelity is
   unverified.

Report which parts came from Code Connect and which you inferred.
