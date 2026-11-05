"""Harmonize categories and derive hardware tags from the extracted text.

Most bugs name no hardware. A tag therefore means "the notes mention it", never
"only this hardware is affected", and a bug without tag stays generic.
"""
import re
from typing import Iterable, List, Optional, Set, Tuple

CATEGORY_RULES = [
    (r"6000|7000|6k|7k", "FortiGate 6000/7000"),
    (r"^(fg|fgt|fortigate|fortirugged|fortiwifi)[- ]?\d", "Hardware platform"),
    (r"hyperscale", "Hyperscale"),
    (r"agentless", "Agentless VPN"),
    (r"ssl.?vpn", "SSL VPN"),
    (r"ipsec", "IPsec VPN"),
    (r"^ha\b|high availab", "HA"),
    (r"sd-?wan|virtual wan", "SD-WAN"),
    (r"ztna", "ZTNA"),
    (r"^ips.?engine", "IPS Engine"),
    (r"^av engine", "AV Engine"),
    (r"wan.?opt", "WAN Optimization"),
    (r"proxy", "Proxy"),
    (r"web.?filter", "Web Filter"),
    (r"dns", "DNS Filter"),
    (r"spam|e-?mail", "Anti Spam"),
    (r"^ips\b|intrusion", "Intrusion Prevention"),
    (r"anti.?virus|^av\b", "AntiVirus"),
    (r"dlp|data l(eak|oss)", "Data Leak Prevention"),
    (r"app(lication)?.?control", "Application Control"),
    (r"^log|report", "Log & Report"),
    (r"fortiview", "FortiView"),
    (r"gui|web-based manager|webui", "GUI"),
    (r"rest.?api", "REST API"),
    (r"rout", "Routing"),
    (r"switch|fortilink", "Switch Controller"),
    (r"wifi|wireless|fortiap", "WiFi Controller"),
    (r"user|auth", "User & Authentication"),
    (r"security fabric|\bcsf\b", "Security Fabric"),
    (r"endpoint|forticlient", "Endpoint Control"),
    (r"firewall|polic", "Firewall"),
    (r"upgrade", "Upgrade"),
    (r"^vm\b|fortigate.?vm|virtual", "VM"),
    (r"voip|\bsip\b", "VoIP"),
    (r"system|kernel", "System"),
    (r"^(new features|changes in)|table ?size", "Changes & enhancements"),
]
UNCATEGORIZED = "Uncategorized"

MODEL_NAME = re.compile(r"^(FG|FGT|FWF|FGR|FFW|FOS|FGV)-[0-9V]")
MODEL_CORE = r"\d{2,4}[A-Z][A-Za-z0-9]*"
MENTION = re.compile(
    r"\b(?:FortiGate(?:[- ]?Rugged)?|FortiRugged|FortiWiFi|FGT|FGR|FWF|FFW|FG)[\s_-]*"
    rf"({MODEL_CORE}(?:\s*(?:/|,|&|and|or)\s*(?:(?:FGT|FG|FWF|FortiGate)[\s_-]*)?{MODEL_CORE})*)"
)
CORE = re.compile(MODEL_CORE)
SERIES = re.compile(r"\b(?:FortiGate|FGT|FG)[ -]?([67])000[EF]?(?:\s*(?:/|,|and|or)\s*(?:FG-?)?([67])000[EF]?)?")
SHORT_SERIES = re.compile(r"\b([67])K[EF]?\b")
VIRTUAL = re.compile(r"\b(?:FortiGate[- ]?VM|FGT[- ]?VM|FG-?VM|FGVM|FOS-?VM)", re.I)
ASIC = re.compile(r"\b(NP[4-7](?:lite)?|SoC[2-5]|CP(?:8|9|10))\b", re.I)


def normalize_category(category: Optional[str]) -> str:
    if not category:
        return UNCATEGORIZED
    name = category.lower()
    for pattern, canonical in CATEGORY_RULES:
        if re.search(pattern, name):
            return canonical
    return category


def canonical_model(name: str) -> Optional[str]:
    """Return the FG-style name of a model, or None for what is not a FortiGate."""
    name = name.upper()
    if not MODEL_NAME.match(name) or name.count("FG") > 1:
        return None
    return re.sub(r"^FGT-", "FG-", name)


def model_core(model: str) -> str:
    """The number shared by the variants: FWF-60F and FG-60F-POE are both 60F."""
    return model.split("-")[1]


def hardware_tags(text: str, category: str, known_cores: Iterable[str]) -> Tuple[List[str], List[str], List[str]]:
    """Return the model cores, the families (6000, 7000, VM) and the ASICs mentioned."""
    known = set(known_cores)
    source = f"{category} {text}"
    cores: Set[str] = set()
    for mention in MENTION.finditer(source):
        cores.update(core for core in CORE.findall(mention.group(1)) if core in known)

    families: Set[str] = set()
    for match in SERIES.finditer(source):
        families.update(f"{digit}000" for digit in match.groups() if digit)
    families.update(f"{digit}000" for digit in SHORT_SERIES.findall(source))
    if category == "FortiGate 6000/7000":
        families.update(("6000", "7000"))
    if category == "VM" or VIRTUAL.search(text):
        families.add("VM")

    asics = {match.upper().replace("LITE", "lite").replace("SOC", "SoC") for match in ASIC.findall(text)}
    return sorted(cores), sorted(families), sorted(asics)
