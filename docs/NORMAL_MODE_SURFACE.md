# Normal Mode Surface Decision

VOCR uses a local Tkinter GUI as the default surface for `vocr start`.

## Decision

Selected for the MVP:

- stdlib Tkinter GUI
- central conversation area
- multiline text input
- compact status panel
- no process button collection
- terminal fallback with `vocr start --console`
- alias with `vocr gui`

This keeps VOCR Python-first, local-first and testable without adding a web
server, frontend buildchain or new runtime dependency.

## Why Not Textual First

Textual is a good future option for a polished terminal UI. It is not selected
as the MVP default because it adds a dependency while the current need is simply
a quiet dialogue room with a textbox and status panel.

## Why Not Local Web GUI First

A local web GUI can become the best normal user experience later. It is not
selected for the MVP because even a small FastAPI/HTMX surface introduces a
server lifecycle, routing, browser state and more testing surface. VOCR does not
need that complexity to validate the Visionary-led intake flow.

## Acceptance

- `vocr start` opens the selected local GUI when a window system is available.
- `vocr gui` is an alias for the same local GUI.
- `vocr start --console` keeps a no-window fallback.
- No cloud dependency is required.
- No frontend buildchain is required.
- The UI stays a conversation room: the Visionary leads, the user writes natural
  language, and the status panel summarizes the intake.

## Later Upgrade Path

If the normal mode needs richer layout in the terminal, add Textual behind the
same `NormalModeController`.

If the normal mode needs browser delivery, add a local web GUI behind the same
controller and keep `vocr start` pointed at the most user-friendly stable
surface.
