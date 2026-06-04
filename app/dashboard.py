from __future__ import annotations


def render_dashboard(default_store_id: str) -> str:
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Store Intelligence Dashboard</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Inter, ui-sans-serif, "Segoe UI", Arial, sans-serif;
      --page: #f7fafc;
      --panel: rgba(255, 255, 255, 0.92);
      --panel-solid: #ffffff;
      --ink: #0b1b34;
      --muted: #6d7890;
      --soft: #eef6f4;
      --line: #e4ebf2;
      --teal: #079680;
      --teal-dark: #057367;
      --green: #21c998;
      --blue: #2f8df2;
      --purple: #9b6bff;
      --orange: #f4a236;
      --red: #d94d48;
      --shadow: 0 18px 40px rgba(38, 56, 83, 0.08);
      --shadow-soft: 0 12px 26px rgba(38, 56, 83, 0.06);
    }

    * { box-sizing: border-box; }
    html { min-height: 100%; background: var(--page); }
    body {
      min-height: 100vh;
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at 88% 2%, rgba(173, 203, 255, 0.28), transparent 30%),
        linear-gradient(115deg, #ffffff 0%, #f9fbff 42%, #f4fbf8 100%);
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image:
        linear-gradient(rgba(216, 226, 239, 0.22) 1px, transparent 1px),
        linear-gradient(90deg, rgba(216, 226, 239, 0.22) 1px, transparent 1px);
      background-size: 42px 42px;
      mask-image: linear-gradient(to bottom, rgba(0,0,0,0.42), transparent 62%);
    }
    button, select, input, a { font: inherit; }
    button { border: 0; cursor: pointer; }
    a { color: inherit; }
    h1, h2, h3, p { margin: 0; }
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    .icon { width: 22px; height: 22px; stroke: currentColor; stroke-width: 2; fill: none; stroke-linecap: round; stroke-linejoin: round; flex: 0 0 auto; }

    .app-shell {
      position: relative;
      display: grid;
      grid-template-columns: 222px minmax(0, 1fr);
      min-height: 100vh;
      padding: 24px 28px 28px 24px;
      gap: 26px;
    }
    .sidebar {
      position: sticky;
      top: 24px;
      height: calc(100vh - 52px);
      display: grid;
      grid-template-rows: auto auto 1fr auto;
      gap: 24px;
      z-index: 1;
    }
    .rail-top { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .logo-tile, .top-icon, .metric-icon, .system-check {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 20px;
      background: rgba(255, 255, 255, 0.78);
      box-shadow: var(--shadow-soft);
      color: var(--teal);
    }
    .logo-tile { width: 58px; height: 58px; }
    .menu-button { width: 46px; height: 46px; border-radius: 16px; background: rgba(243, 247, 252, 0.92); color: #0e2943; display: inline-flex; align-items: center; justify-content: center; }
    .store-card {
      min-height: 102px;
      border-radius: 14px;
      padding: 20px;
      color: #ffffff;
      background:
        linear-gradient(135deg, rgba(152, 113, 255, 0.95), rgba(82, 206, 230, 0.95)),
        linear-gradient(135deg, #8c6bff, #57d4df);
      box-shadow: 0 20px 36px rgba(99, 132, 220, 0.23);
      display: grid;
      grid-template-columns: 48px minmax(0, 1fr);
      gap: 14px;
      align-items: center;
    }
    .store-card .store-avatar {
      width: 44px;
      height: 44px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.9);
      color: var(--teal);
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }
    .store-eyebrow { color: rgba(255, 255, 255, 0.78); font-size: 12px; font-weight: 700; }
    .store-name { margin-top: 7px; font-size: 15px; font-weight: 800; overflow-wrap: anywhere; }
    .store-city { margin-top: 10px; display: inline-flex; align-items: center; gap: 8px; color: rgba(255, 255, 255, 0.74); font-size: 12px; }
    .live-dot { width: 7px; height: 7px; border-radius: 50%; background: #21f2b6; box-shadow: 0 0 0 5px rgba(33, 242, 182, 0.12); }

    .nav-list { display: grid; gap: 10px; align-content: start; }
    .nav-button {
      width: 100%;
      height: 52px;
      display: flex;
      align-items: center;
      gap: 14px;
      padding: 0 20px;
      border-radius: 11px;
      color: #627089;
      background: transparent;
      font-size: 14px;
      font-weight: 800;
      text-align: left;
      transition: background 140ms ease, color 140ms ease, transform 140ms ease;
    }
    .nav-button.active {
      color: var(--teal);
      background: linear-gradient(90deg, rgba(225, 248, 242, 0.98), rgba(238, 250, 248, 0.74));
      box-shadow: inset 0 0 0 1px rgba(202, 239, 231, 0.78);
    }
    .nav-button:hover { transform: translateX(2px); color: var(--teal-dark); }
    .insight-card {
      min-height: 248px;
      border-radius: 13px;
      padding: 22px;
      overflow: hidden;
      color: #ffffff;
      background:
        linear-gradient(155deg, rgba(177, 111, 255, 0.9), rgba(67, 156, 244, 0.96)),
        #5f8eff;
      box-shadow: 0 20px 34px rgba(73, 118, 239, 0.22);
      display: grid;
      align-content: space-between;
    }
    .insight-card strong { display: block; font-size: 18px; line-height: 1.35; }
    .insight-card span { display: block; margin-top: 12px; max-width: 135px; color: rgba(255,255,255,0.72); font-size: 13px; line-height: 1.6; }
    .growth-art { width: 158px; height: 112px; align-self: end; justify-self: center; opacity: 0.9; }

    .workspace { min-width: 0; z-index: 1; }
    .topbar {
      min-height: 94px;
      display: grid;
      grid-template-columns: minmax(360px, 1fr) auto;
      gap: 24px;
      align-items: start;
      margin-bottom: 16px;
    }
    .title-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
    h1 { font-size: 28px; line-height: 1.1; letter-spacing: 0; font-weight: 900; }
    .live-pill {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 7px 12px;
      border-radius: 999px;
      color: #0f9f79;
      background: #e9fbf3;
      font-size: 12px;
      font-weight: 900;
      box-shadow: inset 0 0 0 1px rgba(23, 202, 151, 0.16);
    }
    .subtitle { margin-top: 20px; max-width: 620px; color: #30415e; font-size: 14px; line-height: 1.8; font-weight: 650; }
    .utility-icons { display: flex; align-items: center; justify-content: flex-end; gap: 12px; }
    .top-icon { width: 46px; height: 46px; border-radius: 16px; color: #102a43; background: rgba(242, 246, 255, 0.92); position: relative; }
    .top-icon.alert::after, .avatar::after {
      content: "";
      position: absolute;
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: #f34747;
      border: 2px solid #ffffff;
      right: 10px;
      top: 9px;
    }
    .notification-wrap { position: relative; }
    .notification-count {
      position: absolute;
      right: -4px;
      top: -5px;
      min-width: 19px;
      height: 19px;
      padding: 0 5px;
      border-radius: 999px;
      background: #f34747;
      color: #ffffff;
      border: 2px solid #ffffff;
      display: none;
      align-items: center;
      justify-content: center;
      font-size: 10px;
      font-weight: 950;
    }
    .notification-panel {
      position: absolute;
      right: 0;
      top: 58px;
      width: min(360px, calc(100vw - 32px));
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.98);
      border: 1px solid rgba(226, 232, 241, 0.96);
      box-shadow: 0 24px 48px rgba(33, 54, 81, 0.14);
      padding: 16px;
      display: none;
      z-index: 20;
    }
    .notification-panel.open { display: block; }
    .notification-panel h3 { font-size: 15px; font-weight: 950; margin: 0 0 12px; }
    .notification-list { display: grid; gap: 10px; }
    .notification-item {
      display: grid;
      gap: 5px;
      padding: 11px 12px;
      border-radius: 10px;
      background: #f7fbfa;
      border: 1px solid #e7f1ef;
    }
    .notification-item strong { color: #172943; font-size: 13px; }
    .notification-item span { color: #64748b; font-size: 12px; line-height: 1.45; font-weight: 700; }
    .notification-item.warn { background: #fff8e8; border-color: #fde7b6; }
    .notification-item.critical { background: #fff0ef; border-color: #f8c7c4; }
    .avatar {
      width: 48px;
      height: 48px;
      border-radius: 18px;
      position: relative;
      overflow: hidden;
      background:
        linear-gradient(135deg, rgba(13, 155, 136, 0.18), rgba(153, 107, 255, 0.16)),
        #ffffff;
      display: grid;
      place-items: center;
      box-shadow: var(--shadow-soft);
      color: var(--teal);
      font-weight: 900;
    }
    .avatar::after { background: #18c786; right: 2px; top: auto; bottom: 3px; }

    .control-row {
      display: grid;
      grid-template-columns: minmax(250px, 1fr) minmax(180px, 200px) auto auto auto auto;
      align-items: end;
      gap: 12px;
      padding: 4px 0 22px;
    }
    label { display: grid; gap: 8px; color: #748198; font-size: 12px; font-weight: 850; }
    .input-shell {
      min-height: 48px;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 0 14px;
      border: 1px solid var(--line);
      border-radius: 11px;
      background: rgba(255, 255, 255, 0.9);
      box-shadow: 0 12px 24px rgba(33, 54, 81, 0.045);
    }
    select, input {
      width: 100%;
      min-width: 0;
      border: 0;
      outline: 0;
      background: transparent;
      color: #30415e;
      font-size: 13px;
      font-weight: 800;
    }
    .action-button, .link-button {
      min-height: 48px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      border-radius: 11px;
      padding: 0 18px;
      text-decoration: none;
      white-space: nowrap;
      font-size: 13px;
      font-weight: 900;
      box-shadow: 0 12px 22px rgba(16, 125, 116, 0.11);
    }
    .action-button.primary, .link-button.primary { background: linear-gradient(180deg, #078b80, #05736f); color: #ffffff; }
    .action-button.ghost, .link-button.ghost { background: rgba(255, 255, 255, 0.85); color: #20324f; border: 1px solid #a9e0d9; box-shadow: none; }

    .section { display: none; }
    .section.active { display: block; }
    .section-card {
      position: relative;
      min-height: 136px;
      border-radius: 13px;
      background: var(--panel);
      border: 1px solid rgba(226, 232, 241, 0.92);
      box-shadow: var(--shadow);
      padding: 34px 34px;
      margin-bottom: 22px;
      overflow: hidden;
    }
    .section-card h2 { font-size: 25px; letter-spacing: 0; line-height: 1.2; font-weight: 900; }
    .section-card p { margin-top: 18px; color: #4b5870; font-size: 14px; line-height: 1.75; font-weight: 650; max-width: 780px; }
    .hero-art {
      position: absolute;
      right: 24px;
      top: 18px;
      width: min(330px, 28vw);
      height: 96px;
      display: grid;
      grid-template-columns: 1.2fr 0.9fr;
      gap: 14px;
      opacity: 0.95;
    }
    .mini-analytics {
      border-radius: 12px;
      background: rgba(255,255,255,0.76);
      box-shadow: 0 16px 28px rgba(105, 103, 220, 0.14);
      transform: rotate(-4deg);
      padding: 12px;
    }
    .mini-analytics:nth-child(2) { transform: rotate(3deg); }
    .mini-bars { display: grid; grid-template-columns: repeat(7, 1fr); gap: 7px; align-items: end; height: 54px; }
    .mini-bars span { border-radius: 6px 6px 3px 3px; background: linear-gradient(180deg, #8b6cff, #4fd9bd); }
    .mini-ring {
      width: 58px;
      height: 58px;
      margin: 3px auto 0;
      border-radius: 50%;
      background: conic-gradient(var(--teal) 0 58%, var(--purple) 58% 76%, #f4eafd 76% 100%);
      box-shadow: inset 0 0 0 13px #ffffff;
    }

    .metric-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 20px;
      margin-bottom: 22px;
    }
    .metric-card {
      min-height: 238px;
      border-radius: 12px;
      background: var(--panel);
      border: 1px solid rgba(226, 232, 241, 0.92);
      box-shadow: var(--shadow-soft);
      padding: 24px;
      display: grid;
      grid-template-rows: auto auto 1fr auto;
      gap: 10px;
    }
    .metric-head { display: flex; align-items: center; gap: 16px; }
    .metric-icon { width: 58px; height: 58px; border-radius: 17px; box-shadow: none; }
    .metric-icon.teal { color: var(--teal); background: #dff8ef; }
    .metric-icon.purple { color: var(--purple); background: #efe7ff; }
    .metric-icon.blue { color: var(--blue); background: #e4f1ff; }
    .metric-icon.orange { color: var(--orange); background: #fff0dc; }
    .metric-label { color: #748198; font-size: 13px; font-weight: 950; text-transform: uppercase; }
    .metric-value { font-size: 33px; line-height: 1.05; font-weight: 950; letter-spacing: 0; overflow-wrap: anywhere; }
    .metric-value.date { font-size: 18px; line-height: 1.35; }
    .metric-copy { color: #526078; font-size: 14px; line-height: 1.55; font-weight: 650; }
    .sparkline { width: 100%; height: 42px; align-self: end; overflow: visible; }
    .sparkline polyline { fill: none; stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; }
    .sparkline path { opacity: 0.14; }

    .wide-panel {
      min-height: 136px;
      border-radius: 13px;
      background: var(--panel);
      border: 1px solid rgba(226, 232, 241, 0.92);
      box-shadow: var(--shadow-soft);
      padding: 28px 34px;
      margin-bottom: 22px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 24px;
      align-items: center;
      overflow: hidden;
    }
    .confidence-row { display: flex; align-items: center; gap: 18px; }
    .confidence-copy h3 { font-size: 17px; font-weight: 950; margin-bottom: 12px; }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      min-height: 30px;
      padding: 6px 11px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 850;
      color: var(--teal-dark);
      background: #e6fbf3;
    }
    .status-pill.warn { color: #a26900; background: #fff3d5; }
    .status-pill.critical { color: #b3312d; background: #fde6e4; }
    .shield-art { width: 180px; height: 96px; color: #58ceb0; opacity: 0.95; }
    .system-band {
      min-height: 72px;
      border-radius: 12px;
      padding: 18px 24px;
      background:
        linear-gradient(115deg, rgba(219, 250, 242, 0.95), rgba(238, 252, 249, 0.78)),
        #e7fbf4;
      display: flex;
      gap: 18px;
      align-items: center;
      color: #23645e;
      overflow: hidden;
    }
    .system-check { width: 46px; height: 46px; border-radius: 15px; color: var(--teal); background: #cffff0; box-shadow: none; }
    .system-band strong { display: block; margin-bottom: 6px; color: #146c61; font-size: 14px; }
    .system-band span { color: #697894; font-size: 13px; font-weight: 650; }

    .data-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 18px; }
    .table-card, .info-card {
      border-radius: 13px;
      background: var(--panel);
      border: 1px solid rgba(226, 232, 241, 0.92);
      box-shadow: var(--shadow-soft);
      padding: 24px;
    }
    .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 15px 10px; text-align: left; border-bottom: 1px solid #edf2f6; vertical-align: top; }
    th { color: #7c889d; font-size: 12px; text-transform: uppercase; letter-spacing: 0; font-weight: 950; }
    td { color: #273a56; font-size: 14px; font-weight: 700; }
    .bar { width: 100%; height: 10px; border-radius: 999px; background: #edf4f6; overflow: hidden; }
    .bar span { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--teal), var(--purple)); }
    .empty { color: #7a879a; padding: 18px 0; font-weight: 700; }
    code { background: #edf8f5; color: #106f65; padding: 4px 7px; border-radius: 7px; font-size: 13px; }

    @media (max-width: 1180px) {
      .app-shell { grid-template-columns: 1fr; padding: 18px; }
      .sidebar { position: static; height: auto; grid-template-columns: auto minmax(180px, 260px) 1fr; grid-template-rows: auto auto; align-items: start; }
      .insight-card { display: none; }
      .nav-list { grid-column: 1 / -1; grid-template-columns: repeat(6, minmax(0, 1fr)); }
      .nav-button { justify-content: center; padding: 0 10px; }
      .control-row { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 820px) {
      .topbar, .wide-panel, .two-col { grid-template-columns: 1fr; }
      .utility-icons { justify-content: flex-start; }
      .control-row { grid-template-columns: 1fr; }
      .sidebar { grid-template-columns: 1fr; }
      .nav-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .hero-art { display: none; }
      .section-card, .wide-panel { padding: 24px; }
    }
    @media (max-width: 560px) {
      .app-shell { padding: 12px; }
      .metric-grid, .nav-list { grid-template-columns: 1fr; }
      h1 { font-size: 24px; }
      .metric-card { min-height: 210px; }
    }
  </style>
</head>
<body>
  <svg aria-hidden="true" style="position:absolute;width:0;height:0;overflow:hidden">
    <symbol id="i-bag" viewBox="0 0 24 24"><path d="M6 8h12l-1 12H7L6 8Z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/><path d="M10 13l2 2 4-5"/></symbol>
    <symbol id="i-menu" viewBox="0 0 24 24"><path d="M4 7h16"/><path d="M4 12h10"/><path d="M4 17h16"/></symbol>
    <symbol id="i-home" viewBox="0 0 24 24"><path d="m4 11 8-7 8 7"/><path d="M6 10v10h12V10"/><path d="M10 20v-6h4v6"/></symbol>
    <symbol id="i-filter" viewBox="0 0 24 24"><path d="M4 5h16l-6 7v6l-4 2v-8L4 5Z"/></symbol>
    <symbol id="i-grid" viewBox="0 0 24 24"><path d="M4 4h6v6H4z"/><path d="M14 4h6v6h-6z"/><path d="M4 14h6v6H4z"/><path d="M14 14h6v6h-6z"/></symbol>
    <symbol id="i-alert" viewBox="0 0 24 24"><path d="M12 4 3 20h18L12 4Z"/><path d="M12 9v5"/><path d="M12 17h.01"/></symbol>
    <symbol id="i-heart" viewBox="0 0 24 24"><path d="M20.8 5.6a5.4 5.4 0 0 0-7.7 0L12 6.7l-1.1-1.1a5.4 5.4 0 0 0-7.7 7.7L12 22l8.8-8.7a5.4 5.4 0 0 0 0-7.7Z"/><path d="M3.5 12h4l1.5-3 3 7 1.5-4h3"/></symbol>
    <symbol id="i-help" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.8 2.8 0 0 1 5.3 1.3c0 1.8-1.7 2.4-2.4 3.3-.3.4-.4.7-.4 1.4"/><path d="M12 18h.01"/></symbol>
    <symbol id="i-store" viewBox="0 0 24 24"><path d="M4 10h16l-1-5H5l-1 5Z"/><path d="M6 10v10h12V10"/><path d="M9 20v-5h6v5"/></symbol>
    <symbol id="i-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></symbol>
    <symbol id="i-bell" viewBox="0 0 24 24"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/></symbol>
    <symbol id="i-sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.9 4.9 1.4 1.4"/><path d="m17.7 17.7 1.4 1.4"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m4.9 19.1 1.4-1.4"/><path d="m17.7 6.3 1.4-1.4"/></symbol>
    <symbol id="i-users" viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2"/><circle cx="9.5" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9"/><path d="M16 3.1a4 4 0 0 1 0 7.8"/></symbol>
    <symbol id="i-tag" viewBox="0 0 24 24"><path d="M20 13 13 20 4 11V4h7l9 9Z"/><circle cx="8.5" cy="8.5" r="1.5"/></symbol>
    <symbol id="i-calendar" viewBox="0 0 24 24"><path d="M8 2v4"/><path d="M16 2v4"/><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18"/></symbol>
    <symbol id="i-code" viewBox="0 0 24 24"><path d="m8 9-4 3 4 3"/><path d="m16 9 4 3-4 3"/><path d="m14 5-4 14"/></symbol>
    <symbol id="i-shield" viewBox="0 0 24 24"><path d="M12 3 20 6v6c0 5-3.4 8.3-8 9-4.6-.7-8-4-8-9V6l8-3Z"/><path d="m8.5 12 2.2 2.2 4.8-5.2"/></symbol>
    <symbol id="i-check" viewBox="0 0 24 24"><path d="m5 12 4 4L19 6"/></symbol>
  </svg>
  <div class="app-shell">
    <aside class="sidebar" aria-label="Store Intelligence navigation">
      <div class="rail-top">
        <div class="logo-tile" aria-label="Store Intelligence"><svg class="icon"><use href="#i-bag"></use></svg></div>
        <button class="menu-button" type="button" aria-label="Menu"><svg class="icon"><use href="#i-menu"></use></svg></button>
      </div>
      <div class="store-card">
        <div class="store-avatar"><svg class="icon"><use href="#i-store"></use></svg></div>
        <div>
          <div class="store-eyebrow">Connected Store</div>
          <div id="connectedStoreName" class="store-name">Loading store</div>
          <div class="store-city"><span class="live-dot"></span><span id="connectedStoreCity">Live feed</span></div>
        </div>
      </div>
      <nav class="nav-list" aria-label="Dashboard sections">
        <button class="nav-button active" data-tab="overview" onclick="showTab('overview')" type="button"><svg class="icon"><use href="#i-home"></use></svg><span>Overview</span></button>
        <button class="nav-button" data-tab="funnel" onclick="showTab('funnel')" type="button"><svg class="icon"><use href="#i-filter"></use></svg><span>Funnel</span></button>
        <button class="nav-button" data-tab="heatmap" onclick="showTab('heatmap')" type="button"><svg class="icon"><use href="#i-grid"></use></svg><span>Heatmap</span></button>
        <button class="nav-button" data-tab="anomalies" onclick="showTab('anomalies')" type="button"><svg class="icon"><use href="#i-alert"></use></svg><span>Anomalies</span></button>
        <button class="nav-button" data-tab="health" onclick="showTab('health')" type="button"><svg class="icon"><use href="#i-heart"></use></svg><span>Health</span></button>
        <button class="nav-button" data-tab="guide" onclick="showTab('guide')" type="button"><svg class="icon"><use href="#i-help"></use></svg><span>How it works</span></button>
      </nav>
      <div class="insight-card">
        <div><strong>Smart insights.<br />Better decisions.</strong><span>Real-time analytics for your store.</span></div>
        <svg class="growth-art" viewBox="0 0 180 120" aria-hidden="true">
          <defs><linearGradient id="g-growth" x1="0" x2="1"><stop stop-color="#e9f7ff"/><stop offset="1" stop-color="#ffffff"/></linearGradient></defs>
          <path d="M18 94 48 69l28 18 33-38 45 21" fill="none" stroke="rgba(255,255,255,.82)" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M18 94 48 69l28 18 33-38 45 21" fill="none" stroke="#78ffd9" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M28 97V75h22v22M70 97V65h22v32M112 97V42h22v55M150 97V20h22v77" fill="url(#g-growth)" opacity=".75"/>
          <path d="m146 26 16-16 16 16" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M162 12v91" stroke="#fff" stroke-width="7" stroke-linecap="round"/>
        </svg>
      </div>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <div class="title-row">
            <h1>Store Intelligence</h1>
            <span class="live-pill"><span class="live-dot"></span>Live Overview</span>
          </div>
          <p class="subtitle">Turns CCTV-derived events and POS transactions into visitor counts, conversion funnel, zone heatmap, queue alerts, and feed health.</p>
        </div>
        <div class="utility-icons" aria-label="Utility actions">
          <button class="top-icon" type="button" aria-label="Search"><svg class="icon"><use href="#i-search"></use></svg></button>
          <div class="notification-wrap">
            <button id="notificationButton" class="top-icon" type="button" aria-label="Notifications" onclick="toggleNotifications()">
              <svg class="icon"><use href="#i-bell"></use></svg>
              <span id="notificationCount" class="notification-count">0</span>
            </button>
            <div id="notificationPanel" class="notification-panel" role="status" aria-live="polite">
              <h3>Notifications</h3>
              <div id="notificationList" class="notification-list"><div class="empty">No important notifications.</div></div>
            </div>
          </div>
          <button class="top-icon" type="button" aria-label="Theme"><svg class="icon"><use href="#i-sun"></use></svg></button>
          <div class="avatar" aria-label="Signed in user">SI</div>
        </div>
      </header>

      <section class="control-row" aria-label="Dashboard filters">
        <label>Store
          <span class="input-shell"><svg class="icon"><use href="#i-store"></use></svg><select id="storeSelect"></select></span>
        </label>
        <label>Date
          <span class="input-shell"><input id="dateInput" type="date" /></span>
        </label>
        <button class="action-button ghost" onclick="clearDate()" type="button">Latest day</button>
        <button class="action-button primary" onclick="refreshAll()" type="button">Refresh</button>
        <a class="link-button primary" href="/video-demo"><svg class="icon"><use href="#i-code"></use></svg>Live detection</a>
        <a class="link-button ghost" href="/docs" target="_blank" rel="noreferrer"><svg class="icon"><use href="#i-code"></use></svg>API docs</a>
      </section>

      <section id="overview" class="section active">
        <div class="section-card">
          <h2>Overview</h2>
          <p>Use this page for the live store snapshot: traffic, purchase conversion, queue pressure, and whether the data is trustworthy.</p>
          <div class="hero-art" aria-hidden="true">
            <div class="mini-analytics"><div class="mini-bars"><span style="height:22%"></span><span style="height:42%"></span><span style="height:34%"></span><span style="height:68%"></span><span style="height:58%"></span><span style="height:82%"></span><span style="height:92%"></span></div></div>
            <div class="mini-analytics"><div class="mini-ring"></div></div>
          </div>
        </div>
        <div class="metric-grid">
          <article class="metric-card">
            <div class="metric-head"><div class="metric-icon teal"><svg class="icon"><use href="#i-users"></use></svg></div><div class="metric-label">Unique visitors</div></div>
            <div class="metric-value" id="visitors">0</div>
            <p class="metric-copy">Non-staff visitor sessions in the selected window.</p>
            <svg class="sparkline" viewBox="0 0 220 44" aria-hidden="true"><path d="M0 43 0 24 C42 42 50 4 79 24 C101 39 125 31 147 31 C172 31 178 12 198 18 C208 21 214 18 220 20 L220 44 L0 44Z" fill="#1fc9a8"/><polyline points="0,32 18,32 32,22 48,30 62,38 80,38 92,31 110,38 130,38 148,38 160,23 178,23 194,22 208,17 220,21" stroke="#2bbda6"/></svg>
          </article>
          <article class="metric-card">
            <div class="metric-head"><div class="metric-icon purple"><svg class="icon"><use href="#i-tag"></use></svg></div><div class="metric-label">Conversion rate</div></div>
            <div class="metric-value" id="conversion">0%</div>
            <p class="metric-copy">Billing/POS matches divided by unique visitors.</p>
            <svg class="sparkline" viewBox="0 0 220 44" aria-hidden="true"><path d="M0 44 0 34 C17 25 31 40 45 31 C57 22 69 31 83 29 C102 26 99 9 121 20 C136 29 142 39 158 23 C178 7 194 17 220 4 L220 44Z" fill="#a66dff"/><polyline points="0,34 14,29 28,36 42,31 56,29 70,34 84,27 98,21 112,32 126,24 140,19 154,24 168,14 182,12 196,18 210,10 220,5" stroke="#9b6bff"/></svg>
          </article>
          <article class="metric-card">
            <div class="metric-head"><div class="metric-icon blue"><svg class="icon"><use href="#i-users"></use></svg></div><div class="metric-label">Queue depth</div></div>
            <div class="metric-value" id="queue">0</div>
            <p class="metric-copy">Estimated active non-staff visitors in billing.</p>
            <svg class="sparkline" viewBox="0 0 220 44" aria-hidden="true"><path d="M0 44 0 32 C24 34 29 26 48 31 C68 36 75 25 92 31 C112 38 124 30 140 33 C164 38 174 29 186 20 C198 11 208 13 220 4 L220 44Z" fill="#2f8df2"/><polyline points="0,32 12,31 24,27 36,32 48,28 60,34 72,27 84,32 98,29 110,35 122,28 136,32 148,36 160,31 172,34 184,21 196,23 208,13 220,5" stroke="#2f8df2"/></svg>
          </article>
          <article class="metric-card">
            <div class="metric-head"><div class="metric-icon orange"><svg class="icon"><use href="#i-calendar"></use></svg></div><div class="metric-label">Last event</div></div>
            <div class="metric-value date" id="last">-</div>
            <p class="metric-copy">Most recent event stored for this store.</p>
            <svg class="sparkline" viewBox="0 0 220 44" aria-hidden="true"><path d="M0 44 0 34 C22 38 34 27 52 34 C68 39 79 28 93 34 C116 43 130 34 146 26 C168 14 181 31 195 24 C207 18 214 14 220 18 L220 44Z" fill="#f4a236"/><polyline points="0,34 15,32 30,28 45,35 60,34 75,26 90,34 105,34 120,35 135,27 150,35 165,29 180,16 195,22 210,16 220,19" stroke="#f4a236"/></svg>
          </article>
        </div>
        <div class="wide-panel">
          <div class="confidence-row">
            <div class="metric-icon teal"><svg class="icon"><use href="#i-shield"></use></svg></div>
            <div class="confidence-copy">
              <h3>Data confidence</h3>
              <span id="confidence" class="status-pill">Loading</span>
            </div>
          </div>
          <svg class="shield-art" viewBox="0 0 220 110" aria-hidden="true">
            <path d="M30 58c25-46 120-45 162 0" fill="none" stroke="#d5f5eb" stroke-width="3"/>
            <circle cx="36" cy="58" r="7" fill="#21c998"/><circle cx="178" cy="30" r="5" fill="#8ee7d0"/><circle cx="192" cy="78" r="5" fill="#f7c75d"/>
            <path d="M110 20 152 36v29c0 24-18 41-42 47-24-6-42-23-42-47V36l42-16Z" fill="#a9efd9" stroke="#76ddbf" stroke-width="4"/>
            <path d="m91 63 15 15 31-34" fill="none" stroke="#fff" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <div class="system-band">
          <div class="system-check"><svg class="icon"><use href="#i-check"></use></svg></div>
          <div><strong>System is active</strong><span>Live monitoring and data collection are running.</span></div>
        </div>
      </section>

      <section id="funnel" class="section">
        <div class="section-card"><h2>Funnel</h2><p>Shows where visitor sessions drop off: entry, zone visit, billing queue, and POS purchase. Reentries reuse the same visitor id.</p></div>
        <div class="table-card"><table><thead><tr><th>Stage</th><th>Sessions</th><th>Drop-off</th><th>Visual</th></tr></thead><tbody id="funnelRows"></tbody></table></div>
      </section>

      <section id="heatmap" class="section">
        <div class="section-card"><h2>Heatmap</h2><p>Ranks product zones by visits and dwell. Zero-visit zones still appear when the layout is known.</p></div>
        <div class="table-card"><table><thead><tr><th>Zone</th><th>SKU zone</th><th>Visits</th><th>Avg dwell</th><th>Score</th></tr></thead><tbody id="heatRows"></tbody></table></div>
      </section>

      <section id="anomalies" class="section">
        <div class="section-card"><h2>Anomalies</h2><p>Flags queue spikes, conversion drops, dead zones, and low-confidence operational situations that need manager attention.</p></div>
        <div class="table-card"><table><thead><tr><th>Type</th><th>Severity</th><th>Message</th><th>Suggested action</th></tr></thead><tbody id="anomalyRows"></tbody></table></div>
      </section>

      <section id="health" class="section">
        <div class="section-card"><h2>Health</h2><p>Use this first when something looks wrong. It checks database availability, feed freshness, version, and stale-feed warnings.</p></div>
        <div class="two-col">
          <div class="info-card"><h3>Service</h3><p id="healthSummary" class="metric-copy">-</p></div>
          <div class="info-card"><h3>Warnings</h3><div id="healthWarnings" class="empty">No warnings.</div></div>
        </div>
      </section>

      <section id="guide" class="section">
        <div class="section-card"><h2>How it works</h2><p>CCTV clips are processed into events such as ENTRY, ZONE_DWELL, and BILLING_QUEUE_JOIN. The API validates and stores those events, correlates billing activity with POS transactions, and calculates metrics from the stored stream.</p></div>
        <div class="two-col">
          <div class="info-card"><h3>Process clips</h3><p class="metric-copy"><code>python -m pipeline.detect --input datasets/cctv_footage --output outputs/events.jsonl</code></p></div>
          <div class="info-card"><h3>Replay live</h3><p class="metric-copy"><code>python -m pipeline.replay outputs/events.jsonl --url http://localhost:8000/events/ingest --speed 10</code></p></div>
        </div>
      </section>
    </main>
  </div>

  <script>
    const defaultStore = "__DEFAULT_STORE_ID__";
    const state = { activeTab: "overview", timer: null, stores: [] };

    function selectedStore() {
      return document.getElementById("storeSelect").value || defaultStore;
    }

    function queryString() {
      const date = document.getElementById("dateInput").value;
      return date ? `?date=${encodeURIComponent(date)}` : "";
    }

    function cityForStore(storeId, displayName) {
      const source = `${storeId || ""} ${displayName || ""}`.toLowerCase();
      if (source.includes("mum") || source.includes("mumbai")) return "Mumbai";
      if (source.includes("blr") || source.includes("bangalore") || source.includes("brigade")) return "Bangalore";
      return "Live feed";
    }

    function currentStoreMeta() {
      const storeId = selectedStore();
      return state.stores.find(store => store.store_id === storeId) || { store_id: storeId, display_name: storeId };
    }

    function updateConnectedStore() {
      const store = currentStoreMeta();
      document.getElementById("connectedStoreName").textContent = store.display_name || store.store_id || "Store";
      document.getElementById("connectedStoreCity").textContent = cityForStore(store.store_id, store.display_name);
    }

    function showTab(tab) {
      state.activeTab = tab;
      document.querySelectorAll(".section").forEach(section => section.classList.toggle("active", section.id === tab));
      document.querySelectorAll(".nav-button").forEach(button => button.classList.toggle("active", button.dataset.tab === tab));
    }

    function toggleNotifications() {
      document.getElementById("notificationPanel").classList.toggle("open");
    }

    function clearDate() {
      document.getElementById("dateInput").value = "";
      refreshAll();
    }

    function statusClass(severity) {
      const value = String(severity || "").toLowerCase();
      if (value === "critical" || value === "error") return "status-pill critical";
      if (value === "warn" || value === "warning") return "status-pill warn";
      return "status-pill";
    }

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
    }

    async function fetchJson(url) {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return response.json();
    }

    async function loadStores() {
      const payload = await fetchJson("/stores");
      const select = document.getElementById("storeSelect");
      const urlStore = new URLSearchParams(window.location.search).get("store_id");
      const stores = payload.stores && payload.stores.length ? payload.stores : [{ store_id: defaultStore, display_name: defaultStore }];
      state.stores = stores;
      select.innerHTML = stores.map(store => {
        const label = `${store.display_name || store.store_id} (${store.store_id})`;
        return `<option value="${escapeHtml(store.store_id)}">${escapeHtml(label)}</option>`;
      }).join("");
      select.value = urlStore || stores.find(store => store.is_default)?.store_id || stores[0].store_id;
      updateConnectedStore();
    }

    async function refreshOverview(store) {
      const metrics = await fetchJson(`/stores/${encodeURIComponent(store)}/metrics${queryString()}`);
      document.getElementById("visitors").textContent = metrics.unique_visitors ?? 0;
      document.getElementById("conversion").textContent = `${Math.round((metrics.conversion_rate ?? 0) * 100)}%`;
      document.getElementById("queue").textContent = metrics.current_queue_depth ?? 0;
      document.getElementById("last").textContent = metrics.last_event_timestamp || "-";
      const confidence = metrics.data_confidence || {};
      const confidenceEl = document.getElementById("confidence");
      confidenceEl.textContent = confidence.reason || (confidence.is_confident ? "Confident" : "-");
      confidenceEl.className = confidence.is_confident ? "status-pill" : "status-pill warn";
    }

    async function refreshFunnel(store) {
      const payload = await fetchJson(`/stores/${encodeURIComponent(store)}/funnel${queryString()}`);
      const max = Math.max(...(payload.stages || []).map(stage => stage.count), 1);
      document.getElementById("funnelRows").innerHTML = (payload.stages || []).map(stage => {
        const width = Math.round(stage.count / max * 100);
        return `<tr><td>${escapeHtml(stage.stage)}</td><td>${stage.count}</td><td>${stage.drop_off_pct_from_previous}%</td><td><div class="bar"><span style="width:${width}%"></span></div></td></tr>`;
      }).join("") || `<tr><td colspan="4" class="empty">No funnel events yet.</td></tr>`;
    }

    async function refreshHeatmap(store) {
      const payload = await fetchJson(`/stores/${encodeURIComponent(store)}/heatmap${queryString()}`);
      document.getElementById("heatRows").innerHTML = (payload.zones || []).map(zone =>
        `<tr><td>${escapeHtml(zone.zone_id)}</td><td>${escapeHtml(zone.sku_zone || "-")}</td><td>${zone.visits}</td><td>${zone.avg_dwell_ms}</td><td>${zone.normalized_score_0_100}</td></tr>`
      ).join("") || `<tr><td colspan="5" class="empty">No zone data yet.</td></tr>`;
    }

    async function refreshAnomalies(store) {
      const payload = await fetchJson(`/stores/${encodeURIComponent(store)}/anomalies${queryString()}`);
      document.getElementById("anomalyRows").innerHTML = (payload.anomalies || []).map(item =>
        `<tr><td>${escapeHtml(item.type)}</td><td><span class="${statusClass(item.severity)}">${escapeHtml(item.severity)}</span></td><td>${escapeHtml(item.message)}</td><td>${escapeHtml(item.suggested_action)}</td></tr>`
      ).join("") || `<tr><td colspan="4" class="empty">No active anomalies.</td></tr>`;
    }

    async function refreshHealth() {
      const payload = await fetchJson("/health");
      document.getElementById("healthSummary").innerHTML = `Status <span class="${statusClass(payload.status)}">${escapeHtml(payload.status)}</span><br>Database: ${escapeHtml(payload.database?.status || "-")}<br>Version: ${escapeHtml(payload.version)}<br>Uptime: ${escapeHtml(payload.uptime_seconds)}s`;
      document.getElementById("healthWarnings").innerHTML = (payload.warnings || []).map(warn =>
        `<p class="metric-copy"><span class="status-pill warn">${escapeHtml(warn.type)}</span> ${escapeHtml(warn.store_id)}: ${escapeHtml(warn.message)}</p>`
      ).join("") || `<div class="empty">No warnings.</div>`;
    }

    async function refreshNotifications() {
      const payload = await fetchJson("/notifications");
      const items = payload.notifications || [];
      const count = document.getElementById("notificationCount");
      count.textContent = String(items.length);
      count.style.display = items.length ? "inline-flex" : "none";
      document.getElementById("notificationButton").classList.toggle("alert", items.length > 0);
      document.getElementById("notificationList").innerHTML = items.map(item => {
        const severity = String(item.severity || "INFO").toLowerCase();
        const css = severity === "critical" ? "critical" : severity === "warn" ? "warn" : "";
        const store = item.store_id ? ` ${escapeHtml(item.store_id)}` : "";
        return `<div class="notification-item ${css}"><strong>${escapeHtml(item.title || item.code)}${store}</strong><span>${escapeHtml(item.message || "")}</span></div>`;
      }).join("") || `<div class="empty">No important notifications.</div>`;
    }

    async function refreshAll() {
      const store = selectedStore();
      updateConnectedStore();
      try {
        await Promise.all([
          refreshOverview(store),
          refreshFunnel(store),
          refreshHeatmap(store),
          refreshAnomalies(store),
          refreshHealth(),
          refreshNotifications()
        ]);
      } catch (error) {
        const confidence = document.getElementById("confidence");
        confidence.textContent = `Refresh failed: ${error.message}`;
        confidence.className = "status-pill critical";
      }
    }

    document.getElementById("storeSelect").addEventListener("change", refreshAll);
    document.getElementById("dateInput").addEventListener("change", refreshAll);
    loadStores().then(refreshAll);
    state.timer = setInterval(refreshAll, 2000);
  </script>
</body>
</html>"""
    return html.replace("__DEFAULT_STORE_ID__", default_store_id)
