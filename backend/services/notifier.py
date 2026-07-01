"""Email notification service using SendGrid."""

from __future__ import annotations

import logging
import os
from typing import Any

_logger = logging.getLogger("experimentiq.notifier")

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
FROM_EMAIL = os.getenv("NOTIFY_FROM_EMAIL", "reports@experimentiq.ai")
FROM_NAME = os.getenv("NOTIFY_FROM_NAME", "ExperimentIQ")


def _build_html(report_date: str, sections: list[dict[str, Any]]) -> str:
    """Build the daily report HTML email body."""
    section_html = ""
    for section in sections:
        platform_color = {
            "growthbook": "#34d399",
            "launchdarkly": "#405BFF",
            "statsig": "#EF6E23",
        }.get(section.get("platform", ""), "#6366f1")

        experiments_html = ""
        for exp in section.get("experiments", []):
            health = exp.get("health_status", "unknown")
            health_color = {"healthy": "#34d399", "warning": "#fbbf24", "critical": "#ef4444"}.get(health, "#9ca3af")
            actions = "".join(f"<li>{a}</li>" for a in exp.get("suggested_actions", []))
            experiments_html += f"""
            <div style="margin:12px 0;padding:16px;background:#1a1a2e;border-radius:12px;border-left:3px solid {health_color}">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <strong style="color:#e2e8f0">{exp.get('name','Untitled')}</strong>
                <span style="font-size:12px;color:{health_color};font-weight:600;text-transform:uppercase">{health}</span>
              </div>
              <p style="margin:8px 0 4px;color:#94a3b8;font-size:13px">{exp.get('summary','')}</p>
              {"<ul style='margin:8px 0;padding-left:18px;color:#94a3b8;font-size:12px'>" + actions + "</ul>" if actions else ""}
              {"<div style='margin-top:8px;font-size:12px;color:#fbbf24;font-weight:600'>⚠ SRM Detected</div>" if exp.get('has_srm') else ""}
              {"<div style='margin-top:4px;font-size:12px;color:#34d399'>✓ Can stop early: " + exp.get('stop_recommendation','') + "</div>" if exp.get('can_stop') else ""}
            </div>"""

        if not experiments_html:
            experiments_html = "<p style='color:#64748b;font-size:13px;font-style:italic'>No active experiments found.</p>"

        section_html += f"""
        <div style="margin-bottom:32px">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
            <span style="width:10px;height:10px;border-radius:50%;background:{platform_color};display:inline-block"></span>
            <h3 style="margin:0;color:#e2e8f0;font-size:15px;text-transform:capitalize">{section.get('platform','').replace('growthbook','GrowthBook').replace('launchdarkly','LaunchDarkly').replace('statsig','Statsig')}</h3>
            <span style="font-size:12px;color:#64748b">({len(section.get('experiments',[]))} experiments)</span>
          </div>
          {experiments_html}
        </div>"""

    return f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0f0f1a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
  <div style="max-width:640px;margin:0 auto;padding:32px 16px">
    <div style="margin-bottom:24px">
      <span style="color:#6366f1;font-size:12px;font-weight:700;letter-spacing:0.15em;text-transform:uppercase">ExperimentIQ</span>
      <h1 style="margin:8px 0 4px;color:#f1f5f9;font-size:24px;font-weight:700">Daily Experiment Report</h1>
      <p style="margin:0;color:#64748b;font-size:14px">{report_date}</p>
    </div>
    <div style="height:1px;background:#1e293b;margin-bottom:24px"></div>
    {section_html}
    <div style="height:1px;background:#1e293b;margin:24px 0"></div>
    <p style="color:#334155;font-size:12px;text-align:center">
      Sent by ExperimentIQ · <a href="#" style="color:#6366f1">View in app</a>
    </p>
  </div>
</body>
</html>"""


async def send_daily_report(
    to_email: str,
    report_date: str,
    sections: list[dict[str, Any]],
) -> bool:
    """Send the daily report email via SendGrid. Returns True on success."""
    if not SENDGRID_API_KEY:
        _logger.warning("SENDGRID_API_KEY not set — skipping email notification")
        return False

    try:
        import sendgrid as sg_module
        from sendgrid.helpers.mail import Mail, To, From, HtmlContent, Subject

        total = sum(len(s.get("experiments", [])) for s in sections)
        subject = f"ExperimentIQ Daily Report — {total} experiment{'s' if total != 1 else ''} tracked · {report_date}"

        message = Mail(
            from_email=(FROM_EMAIL, FROM_NAME),
            to_emails=to_email,
            subject=subject,
            html_content=_build_html(report_date, sections),
        )

        client = sg_module.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        response = client.send(message)
        _logger.info("Daily report sent to %s — status %s", to_email, response.status_code)
        return response.status_code in (200, 201, 202)
    except Exception as exc:
        _logger.error("Failed to send daily report to %s: %s", to_email, exc)
        return False
