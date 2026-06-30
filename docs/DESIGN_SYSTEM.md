# Teamplay Talk Design System

Update: 2026-06-27

## Direction

Teamplay Talk uses **Kakao Workbench x Liquid Glass**:

- The product is an operational tool, so density, scan speed, and alignment win over decorative drama.
- Liquid Glass belongs to the functional layer: app headers, sticky summaries, filters, tabs, and primary controls.
- Content belongs to a readable layer: poll results, todo lists, daily reports, tables, and repeated cards stay flat or lightly raised.
- Slack is a structural reference only: workspace context, readable feed, and a secondary project rail. Do not copy Slack color as the product identity.
- Kakao is the local brand cue: Kakao yellow is used for action and selection, not as a page-wide wash.

## Workspace Reference Notes

- Navigation and identity live in the workspace chrome, not as floating chips inside content.
- The central surface should behave like a channel: a readable feed where each event is one message row.
- Project state can live in a right rail, similar to Slack's secondary context surfaces, but it must not steal the reading axis.
- Teamplay charcoal anchors the shell/sidebar. Kakao yellow is a small action and selection signal. The feed stays quiet so users can scan decisions, counts, and todo text.
- Liquid/glass effects are reserved for chrome and persistent context. The feed itself is mostly flat.

## Type

- Display/headline: Kakao Big Sans.
- Body/forms: Kakao Small Sans.
- Fallbacks: Apple SD Gothic Neo, Noto Sans KR, system UI.
- Letter spacing is 0 for readable Korean UI. Use weight and spacing, not tracking, for hierarchy.

## Color

- Canvas: warm neutral, slightly yellow-tinted, never pure white.
- Ink: Kakao black for primary text.
- Primary action: Kakao yellow with black text.
- Workflow accents:
  - Slack aubergine: roles, decision structure, active navigation.
  - Slack blue/cyan: location, external/contextual information.
  - Slack red: risk, anonymous/private, retro/opinion tension.
  - Warm amber: open/in-progress state.

## Layer Rules

- Top-level glass: page masthead, stats, member chips, roadmap panel, date tabs.
- Content surfaces: timeline cards, task cards, answers, table cells, SurveyJS questions.
- Avoid nested glass. If a glass panel contains many children, those children should use flat fills and thin borders.
- Avoid blur in scroll-heavy repeated content because it hurts readability and performance.
- Radius is 8px for cards and surfaces. Pills may use 999px. Larger rounded panels should not become bubbly.

## Layout

- Dashboard follows a Teamplay workbench shell: left room/member context, center MCP work feed, right project state rail.
- The center feed is not a decorative timeline. It reads like a channel message stream, so event rows share one left avatar axis and one content axis.
- Desktop can show dense three-column views. Tablet keeps the workspace rail and stacks the project rail below the feed. Mobile compresses workspace navigation and brings the feed above project detail.
- Fixed-format controls use stable dimensions: choice buttons, date tabs, stats, chips, and table cells should not resize on hover.
- Text must wrap inside surfaces. Long answers and task names should break gracefully.

## References

- Apple Human Interface Guidelines: Materials, Layout, Typography, Color
- Apple Meet with Apple transcript provided by the team: Liquid Glass adoption examples
- Kakao official font repository
