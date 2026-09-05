"""
Microsoft Teams outbound notifications via Incoming Webhook / Workflows
connector. Reuses the same signed-outbound-webhook infrastructure as other
alerts; Teams webhook URLs are just another entry in a workspace's
`settings_json.outbound_webhook_urls`, formatted as a Teams "MessageCard".
"""


def build_teams_card(title: str, text: str, facts: dict | None = None) -> dict:
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": title,
        "themeColor": "0076D7",
        "title": title,
        "text": text,
    }
    if facts:
        card["sections"] = [{"facts": [{"name": k, "value": str(v)} for k, v in facts.items()]}]
    return card
