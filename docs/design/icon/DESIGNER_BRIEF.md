# Teamplay Talk App Icon Brief

## Product

Teamplay Talk is an AI PM layer for Kakao-native team projects.

The product is not a chat app, a poll app, or a calendar app. It collects messy team inputs and turns them into structured coordination: roles, roadmap, todos, meeting times, reminders, daily check-ins, and reports.

Core idea:

> Individuals stay distinct. Teamplay Talk gives them a shared coordination layer.

## Icon Concept

Working concept: **Converging Liquid Lenses**

The icon should show several large slanted lenses floating in depth. Each lens is an individual teammate/input/decision stream. The lenses converge toward a subtle center decision surface, creating connection and binding without using literal node links.

This should feel:

- Apple-native
- liquid, dimensional, and polished
- lively but not childish
- productivity-oriented, not enterprise-heavy
- Kakao-adjacent through warmth, not through Kakao logo imitation

## Apple Icon Composer Mental Model

This icon is intended for Apple Icon Composer, not as a single baked illustration.

Good source layers:

- flat ellipse vectors
- one lens per layer
- full-canvas aligned
- no hand-drawn bevels
- no baked rounded app mask

Icon Composer should supply:

- Liquid Glass material
- depth separation
- specular highlights
- soft shadows
- appearance-mode tuning

The preview SVG bakes in highlights only as a rough conversation mock. The actual import layers should stay simple.

## Visual Direction

Base composition:

- Dark deep-purple/near-black background.
- Four large tilted lens shapes generated from a shared elliptical orbit.
- Lenses should be bigger than ordinary dots and feel like discs standing at an angle.
- Use diagonal energy: upper lenses separated, lower lenses heavier and slightly overlapping.
- Add a small, translucent center decision surface so the group reads as a coordinated system.
- No literal connecting lines.
- No checkmark.
- No speech bubble.
- No AI sparkle.
- No graph/network symbol.

Metaphor:

- Lenses: distinct people, roles, todos, opinions, schedules.
- Layering/depth: AI coordination and prioritization.
- Center surface: the moment where scattered inputs become a decision.
- Overall read: "separate signals, organized into one shared flow."

## Color Notes

Palette:

- Deep background: `#0A071A`
- Purple: `#3d348b`
- Blue-violet: `#7678ed`
- Yellow: `#f7b801`
- Amber/orange: `#f18701`
- Hot orange: `#f35b04`

Avoid black as the main lens color. The palette should feel bouncy and premium, not monochrome.

## Apple Icon Composer Delivery

Layer order:

1. `01_lens_idea.svg`
2. `02_lens_coordination.svg`
3. `03_lens_decision.svg`
4. `04_lens_handoff.svg`
5. `05_decision_surface.svg`

Guidance:

- The lens positions are generated from `generate_icon_layers.py`; adjust orbit, perspective, and emphasis constants there instead of hand-moving SVG paths.
- Give the bottom-right lens the strongest front depth.
- Keep the bottom-left lens large and warm, but do not let it dominate the full icon.
- Keep the center decision surface shallow, translucent, and glow-like.
- Preview Default, Dark, Tinted, and Mono/Clear modes.

References:

- Apple Icon Composer: https://developer.apple.com/icon-composer/
- WWDC25 Create icons with Icon Composer: https://developer.apple.com/videos/play/wwdc2025/361/
- WWDC25 Say hello to the new look of app icons: https://developer.apple.com/videos/play/wwdc2025/220/
- Apple HIG App Icons: https://developer.apple.com/design/human-interface-guidelines/app-icons
