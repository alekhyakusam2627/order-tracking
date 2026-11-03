from urllib.parse import quote


def carrier_tracking_url(carrier: str, tracking_number: str) -> str | None:
    number = quote(tracking_number.strip(), safe="")
    routes = {
        "fedex": f"https://www.fedex.com/fedextrack/?trknbr={number}",
        "ups": f"https://www.ups.com/track?tracknum={number}",
        "usps": f"https://tools.usps.com/go/TrackConfirmAction?tLabels={number}",
        "dhl": f"https://www.dhl.com/global-en/home/tracking.html?tracking-id={number}",
        "canada-post": f"https://www.canadapost-postescanada.ca/track-reperage/en/details/{number}",
        "canadapost": f"https://www.canadapost-postescanada.ca/track-reperage/en/details/{number}",
        "india-post": f"https://www.indiapost.gov.in/vas/Pages/trackconsignment.aspx",
        "indiapost": f"https://www.indiapost.gov.in/vas/Pages/trackconsignment.aspx",
        "bluedart": f"https://www.bluedart.com/tracking?trackFor=0&trackNo={number}",
    }
    return routes.get(carrier.strip().lower())
