"""Aether design tokens and shared component classes (no external assets)."""

CSS = """
:root {
  --aether-bg: #000000;
  --aether-sidebar: #030a05;
  --aether-tool: #04120a;
  --aether-accent: #00ff41;
  --aether-text: #b6ffc8;
  --aether-muted: #4fae6a;
  --aether-border: #0b3d1a;
  --aether-radius: 10px;
  --aether-font: 'JetBrains Mono', 'DejaVu Sans Mono', Consolas, monospace;
  --aether-code-font: 'JetBrains Mono', Consolas, monospace;
}
body, .q-page, .q-layout { background: var(--aether-bg); color: var(--aether-text); }
body, .q-field, .q-btn { font-family: var(--aether-font); }
.nicegui-content { padding: 0; gap: 0; }
.aether-shell { width: 100%; height: 100dvh; flex-wrap: nowrap; gap: 0; }
.aether-sidebar { width: 260px; flex-shrink: 0; height: 100%; padding: 28px 20px;
  background: var(--aether-sidebar); border-right: 1px solid var(--aether-border); }
.aether-main { flex: 1; min-width: 0; height: 100%; flex-wrap: nowrap; gap: 0; }
.aether-header { width: 100%; padding: 22px 32px; align-items: center;
  border-bottom: 1px solid var(--aether-border); }
.aether-title { font-size: 24px; font-weight: 650; letter-spacing: -.6px; }
.aether-muted { color: var(--aether-muted); font-size: 13px; }
.aether-section { font-size: 11px; color: var(--aether-muted);
  letter-spacing: 1.5px; text-transform: uppercase; margin-top: 24px; }
.aether-chat { flex: 1; width: 100%; min-height: 0; }
.aether-messages { width: 100%; max-width: 960px; margin: 0 auto; padding: 32px;
  gap: 20px; }
.message-user, .message-agent { max-width: 88%; padding: 16px 20px;
  border-radius: var(--aether-radius); overflow-wrap: anywhere; }
.message-user { align-self: flex-end; background: #062a12;
  border: 1px solid var(--aether-accent); color: var(--aether-text); }
.message-agent { align-self: flex-start; background: var(--aether-sidebar);
  border: 1px solid var(--aether-border); color: var(--aether-text); }
.message-user .message-body, .message-agent .message-body { white-space: pre-wrap; }
.message-author { color: var(--aether-muted); font-size: 11px; font-weight: 600;
  letter-spacing: .8px; text-transform: uppercase; margin-bottom: 8px; }
.tool-card { width: 100%; background: var(--aether-tool);
  border: 1px solid var(--aether-border); border-radius: var(--aether-radius);
  box-shadow: none; padding: 14px 18px; }
.tool-card .tool-name, .tool-card .tool-output, code, pre {
  font-family: var(--aether-code-font); }
.tool-card .tool-name { font-size: 13px; }
.tool-card .tool-output { white-space: pre-wrap; overflow-wrap: anywhere;
  font-size: 12px; line-height: 1.65; max-height: 320px; overflow-y: auto; }
.status-badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 9px;
  border: 1px solid var(--aether-border); border-radius: var(--aether-radius);
  background: var(--aether-tool); color: var(--aether-muted); font-size: 11px; }
.status-badge[data-state="busy"] { color: #00ff41; border-color: var(--aether-accent); }
.status-badge[data-state="success"] { color: #00ff41; }
.status-badge[data-state="error"] { color: #fda4af; }
.aether-composer { width: 100%; padding: 20px 32px 24px;
  border-top: 1px solid var(--aether-border); background: var(--aether-bg); }
.aether-composer .q-field__control { background: var(--aether-sidebar);
  border-radius: var(--aether-radius); }
.aether-send { background: var(--aether-accent) !important; color: #000000 !important;
  border-radius: var(--aether-radius); padding: 9px 18px; }
.aether-question { width: 100%; padding: 16px; background: var(--aether-sidebar);
  border: 1px solid var(--aether-accent); border-radius: var(--aether-radius); }
.aether-welcome { padding: 28px 0; max-width: 620px; }
.aether-icon { color: #00ff41; }
.q-field__native { color: var(--aether-text) !important; }
.q-btn:focus-visible, textarea:focus-visible { outline: 2px solid var(--aether-accent);
  outline-offset: 3px; }
@media (max-width: 760px) {
  .aether-sidebar { width: 190px; padding: 20px 12px; }
  .aether-header, .aether-messages, .aether-composer { padding: 16px; }
  .message-user, .message-agent { max-width: 100%; }
}
"""


def apply_theme() -> None:
    from nicegui import ui

    ui.dark_mode().enable()
    ui.colors(primary="#00ff41", secondary="#4fae6a", dark="#000000")
    ui.add_css(CSS)
