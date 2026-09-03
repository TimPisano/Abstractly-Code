# Self-hosted fonts

`inter-latin-var.woff2` — Inter, variable weight axis (100–900), Latin
subset only. 48 KB. Pulled from the Google Fonts CDN
(`fonts.gstatic.com/s/inter/v20/…`, the `U+0000-00FF` subset file, which
is the same variable file every weight 400–900 resolves to).

Self-hosted instead of linked from `fonts.googleapis.com` to remove two
render-blocking cross-origin round trips (the CSS request, then the
font request on a second domain) from every page load. Declared once in
`../design-system.css` via `@font-face`.

Licensed under the SIL Open Font License 1.1 — see `OFL.txt`. Free to
bundle and redistribute; the license file must ship alongside the font.

To update: re-fetch the subset file from the current Google Fonts css2
response for `Inter:wght@100..900` and replace `inter-latin-var.woff2`.
