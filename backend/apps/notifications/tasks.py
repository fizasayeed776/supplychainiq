from celery import shared_task


@shared_task
def send_teams_alert(workspace_id, title, text, facts=None):
    from apps.core.models import Workspace
    from apps.workflow.outbound import post_signed_webhook
    from .teams import build_teams_card

    workspace = Workspace.objects.get(id=workspace_id)
    urls = [u for u in (workspace.settings_json or {}).get("outbound_webhook_urls", []) if "office.com" in u or "teams" in u.lower()]
    card = build_teams_card(title, text, facts)
    for url in urls:
        post_signed_webhook(workspace, url, card)
