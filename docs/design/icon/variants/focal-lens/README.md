# Teamplay Talk Icon Variant: Focal Lens

Concept: **Signals Through a Lens**

This variant uses a lens cross-section and focal length metaphor. Separate team signals enter from the left, pass through one liquid lens, and converge into a single focal decision.

## Why This Works

The product promise is coordination:

- Separate inputs remain visible.
- The lens represents the AI PM layer.
- The focal point represents a shared decision, plan, or next action.

This avoids literal chat bubbles, checkmarks, network lines, and calendar symbols.

## Icon Composer Layers

Import these layers in order:

1. `layers/01_ray_upper.svg`
2. `layers/02_ray_middle_upper.svg`
3. `layers/03_ray_middle_lower.svg`
4. `layers/04_ray_lower.svg`
5. `layers/05_lens_body.svg`
6. `layers/06_focal_point.svg`

## Generator

`generate_focal_lens.py` controls the geometry:

- `INPUT_X`: where independent signals begin
- `LENS_X`: where the liquid lens sits
- `FOCAL_X`: focal length / decision point
- `input_offset`: how separated each signal is before the lens
- `lens_offset`: how compressed each signal becomes inside the lens

Adjust the constants instead of hand-editing SVG paths.

## Preview

`teamplay-icon-preview.svg` includes baked gradients and bloom only for discussion. The import layers stay flat so Icon Composer can apply Liquid Glass material, depth, highlights, and shadows.
