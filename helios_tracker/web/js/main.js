// The page's entry point (index.html calls start()). Modules only define things at import time -
// every DOM hookup happens here, in order - so any of them can be imported under Node (the
// offline check imports them all).
import { connect } from "./data.js";
import { applyI18n } from "./i18n.js";
import { initInput } from "./input.js";
import { invalidate } from "./scheduler.js";
import { initColors } from "./shapes.js";
import { initInspector } from "./ui/inspector.js";
import { initPanel, renderTargets } from "./ui/panel.js";
import { refreshStatus } from "./ui/status.js";
import { initView } from "./view.js";

export function start() {
  initColors();
  initView();
  initPanel();
  initInspector();
  initInput();
  applyI18n();
  renderTargets();
  refreshStatus();
  connect();
  invalidate();
}
