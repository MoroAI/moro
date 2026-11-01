# Bundled dashboard dependencies

Runtime assets are served locally; no CDN is required. `packages.json` records exact versions and upstream license identifiers. Upstream license files and the npm provisioning lock are included. These dependencies were provisioned with npm scripts disabled. Tailwind 3.4.17 generated `tailwind.css` from the dashboard template with the original Moro color palette. Regenerate CSS when introducing new utility classes.

Bundling removes runtime CDN trust and availability requirements; it does not certify that upstream code is vulnerability-free. Alpine's current template expressions require the documented CSP compatibility allowances for inline code/evaluation. Moving to its CSP build and external event handlers remains separate work.
